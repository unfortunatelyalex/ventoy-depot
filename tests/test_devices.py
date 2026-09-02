from pathlib import Path

from ventoy_iso_updater.devices import _is_ventoy_root


def test_ventoy_marker_is_detected(tmp_path: Path) -> None:
    (tmp_path / "ventoy").mkdir()
    assert _is_ventoy_root(tmp_path)


def test_ventoy_label_is_detected(tmp_path: Path) -> None:
    assert _is_ventoy_root(tmp_path, "Ventoy")


def test_generic_removable_drive_is_not_assumed_to_be_ventoy(tmp_path: Path) -> None:
    assert not _is_ventoy_root(tmp_path, "USB")
