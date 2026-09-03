from __future__ import annotations

import hashlib
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from .assignments import AssignmentCatalog, AssignmentError
from .config import load_settings
from .iso import find_isos
from .models import (
    DetectedIso,
    Device,
    IsoIdentity,
    PlanItem,
    ReleaseArtifact,
    UpdateAction,
    UpdatePlan,
    VerificationLevel,
)
from .providers import Provider, provider_map


def build_plan(
    device: Device,
    refresh: bool = False,
    metadata_parallelism: int | None = None,
) -> UpdatePlan:
    providers = provider_map(refresh=refresh)
    assignments = AssignmentCatalog(device.mount_path)
    detected_isos = find_isos(device.mount_path, tuple(providers.values()))
    prepared: list[tuple[DetectedIso, IsoIdentity | None, list[str]]] = []
    for detected in detected_isos:
        errors: list[str] = []
        identity = detected.identity
        if identity is None:
            try:
                identity = assignments.lookup(detected.path)
            except AssignmentError as error:
                errors.append(str(error))
            if identity is not None:
                detected = replace(
                    detected,
                    identity=identity,
                    confidence=1.0,
                    detection_source="catalog-sha256",
                )
            else:
                errors.append("ISO identity is unknown; highlight it and choose Assign ISO.")
        if identity is not None and identity.provider_id not in providers:
            errors.append(f"Unknown provider in ISO assignment: {identity.provider_id}")
        prepared.append((detected, identity, errors))

    parallelism = metadata_parallelism or load_settings().metadata_parallelism
    resolved: dict[int, tuple[ReleaseArtifact | None, str | None]] = {}
    with ThreadPoolExecutor(max_workers=parallelism, thread_name_prefix="ventoy-metadata") as pool:
        futures = {
            pool.submit(_resolve_target, providers[identity.provider_id], identity): index
            for index, (_detected, identity, errors) in enumerate(prepared)
            if identity is not None and not errors
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                resolved[index] = (future.result(), None)
            except Exception as error:  # provider failures become structured plan state
                resolved[index] = (None, str(error))

    free = shutil.disk_usage(device.mount_path).free
    remaining_free = free
    planned_destinations: set[os.PathLike[str]] = set()
    items: list[PlanItem] = []
    for index, (detected, identity, prepared_errors) in enumerate(prepared):
        warnings: list[str] = []
        errors = list(prepared_errors)
        target, resolution_error = resolved.get(index, (None, None))
        if resolution_error:
            errors.append(resolution_error)
        provider = providers.get(identity.provider_id) if identity is not None else None
        if identity is not None:
            if provider is not None:
                if getattr(provider, "custom", False):
                    warnings.append("Custom local provider; updates can only add a new ISO.")
            if target and target.verification_level == VerificationLevel.UNVERIFIED:
                errors.append("Automatic updates require an official checksum.")
        action = UpdateAction.ADD if target and not errors else UpdateAction.SKIP
        if target and identity and provider is not None and not provider.is_newer(target, identity):
            warnings.append("Already current.")
            action = UpdateAction.SKIP
        destination = detected.path.parent / target.filename if target else None
        if destination and destination.exists():
            warnings.append(f"Target ISO already exists: {target.filename}")
            action = UpdateAction.SKIP
        elif destination and destination in planned_destinations:
            errors.append(f"Another selected ISO has the same target path: {target.filename}")
            action = UpdateAction.SKIP
        if not os.access(device.mount_path, os.W_OK):
            errors.append("The Ventoy drive is not writable.")
            action = UpdateAction.SKIP
        required = target.size_bytes if target else None
        if required is not None and action != UpdateAction.SKIP and required > remaining_free:
            errors.append("Insufficient free space on the Ventoy drive.")
            action = UpdateAction.SKIP
        if action != UpdateAction.SKIP:
            if destination is not None:
                planned_destinations.add(destination)
            if required is not None:
                remaining_free -= required
        level = target.verification_level if target else VerificationLevel.UNVERIFIED
        items.append(
            PlanItem(
                detected, target, action, free, required, level, tuple(warnings), tuple(errors)
            )
        )
    seed = "\n".join(
        f"{item.local.path}:{item.local.identity}:{item.target}:{item.action}" for item in items
    )
    plan_id = hashlib.sha256(seed.encode()).hexdigest()[:16]
    return UpdatePlan(device, tuple(items), plan_id)


def _resolve_target(provider: Provider, identity: IsoIdentity) -> ReleaseArtifact:
    target = provider.resolve(identity)
    if target.identity is None:
        raise ValueError("Provider did not declare the target ISO identity.")
    provider.validate_binding(identity, target.identity)
    return target
