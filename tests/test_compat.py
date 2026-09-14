from ventoy_depot.compat import main


def test_deprecated_command_warns_and_delegates(monkeypatch, capsys) -> None:
    calls = 0

    def depot_main() -> int:
        nonlocal calls
        calls += 1
        return 7

    monkeypatch.setattr("ventoy_depot.compat.depot_main", depot_main)

    assert main() == 7
    assert calls == 1
    assert "deprecated" in capsys.readouterr().err
