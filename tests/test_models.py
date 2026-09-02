from ventoy_iso_updater.models import is_newer_version


def test_newer_dotted_versions_are_detected() -> None:
    assert is_newer_version("24.04.2", "24.04.1")
    assert not is_newer_version("24.04", "24.04.2")


def test_unknown_installed_version_permits_a_candidate() -> None:
    assert is_newer_version("42", None)
