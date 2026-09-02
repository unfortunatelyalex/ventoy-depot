from __future__ import annotations

import hashlib
import os
import shutil

from .iso import find_isos
from .models import Device, PlanItem, UpdateAction, UpdatePlan, VerificationLevel
from .providers import provider_map


def build_plan(device: Device, refresh: bool = False) -> UpdatePlan:
    del refresh  # provider caches will consume this flag once remote registry lands
    providers = provider_map()
    free = shutil.disk_usage(device.mount_path).free
    items: list[PlanItem] = []
    for detected in find_isos(device.mount_path):
        warnings: list[str] = []
        errors: list[str] = []
        target = None
        identity = detected.identity
        if identity is None:
            errors.append("ISO identity is unknown; assign it interactively first.")
        else:
            provider = providers[identity.provider_id]
            try:
                target = provider.resolve(identity)
            except Exception as error:  # provider failure becomes structured plan state
                warnings.append(str(error))
            if target and target.verification_level == VerificationLevel.UNVERIFIED:
                errors.append("Automatic updates require an official checksum.")
        action = UpdateAction.ADD if target and not errors else UpdateAction.SKIP
        if target and identity and not provider.is_newer(target, identity):
            warnings.append("Already current.")
            action = UpdateAction.SKIP
        if target and (detected.path.parent / target.filename).exists():
            warnings.append(f"Target ISO already exists: {target.filename}")
            action = UpdateAction.SKIP
        if not os.access(device.mount_path, os.W_OK):
            errors.append("The Ventoy drive is not writable.")
            action = UpdateAction.SKIP
        required = target.size_bytes if target else None
        if required is not None and required > free:
            errors.append("Insufficient free space on the Ventoy drive.")
            action = UpdateAction.SKIP
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
