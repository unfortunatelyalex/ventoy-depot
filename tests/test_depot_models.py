from pathlib import Path

from ventoy_depot.models import (
    DetectedIso,
    IsoIdentity,
    PlanItem,
    ReleaseArtifact,
    UpdateAction,
    VerificationLevel,
)


def identity(**changes: object) -> IsoIdentity:
    values = {
        "provider_id": "ubuntu",
        "product_id": "ubuntu",
        "edition": "desktop",
        "flavor": None,
        "channel": "lts",
        "architecture": "amd64",
        "language": None,
        "version": "24.04",
        "build": None,
    }
    values.update(changes)
    return IsoIdentity(**values)  # type: ignore[arg-type]


def test_variant_key_excludes_only_version_and_build() -> None:
    assert identity().variant_key() == identity(version="24.04.3", build="3").variant_key()
    assert identity().variant_key() != identity(edition="live-server").variant_key()


def test_unverified_plan_item_is_not_writable_when_skipped() -> None:
    local = DetectedIso(Path("image.iso"), identity(), 1.0, "filename")
    item = PlanItem(
        local,
        None,
        UpdateAction.SKIP,
        10,
        None,
        VerificationLevel.UNVERIFIED,
    )
    assert not item.writable


def test_signed_artifact_requires_signature_and_fingerprint() -> None:
    artifact = ReleaseArtifact(
        "1",
        None,
        "image.iso",
        "https://example.org/image.iso",
        1,
        "sha256",
        "a" * 64,
        "https://example.org/image.iso.sig",
        ("A" * 40,),
        frozenset({"example.org"}),
    )
    assert artifact.verification_level == VerificationLevel.SIGNED
