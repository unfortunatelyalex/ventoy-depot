from pathlib import Path

from ventoy_depot.iso import identify_iso
from ventoy_depot.models import DetectedIso, IsoIdentity


class MatchingProvider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id

    def detect(self, path: Path) -> DetectedIso:
        identity = IsoIdentity(
            self.provider_id,
            "product",
            None,
            None,
            "stable",
            "x86_64",
            None,
            "1",
            None,
        )
        return DetectedIso(path, identity, 1.0, "test")


def test_multiple_provider_matches_are_reported_as_ambiguous() -> None:
    detected = identify_iso(
        Path("ambiguous.iso"),
        (MatchingProvider("one"), MatchingProvider("two")),  # type: ignore[arg-type]
    )
    assert detected.identity is None
    assert detected.detection_source == "ambiguous"


def test_builtin_detection_does_not_accept_an_unrecognized_filename_prefix() -> None:
    detected = identify_iso(Path("untrusted-ubuntu-26.04-desktop-amd64.iso"))

    assert detected.identity is None
    assert detected.detection_source == "unknown"
