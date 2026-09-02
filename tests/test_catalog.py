from ventoy_iso_updater.catalog import _version_key


def test_version_key_orders_release_versions_numerically() -> None:
    assert _version_key("24.10") > _version_key("24.4")
