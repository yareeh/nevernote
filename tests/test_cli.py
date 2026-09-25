from pathlib import Path

import pytest

from enex_viewer.cli import main
from enexgen import note, write


def test_index_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path / "enex" / "Inbox.enex", note("A"), note("B"))
    data = tmp_path / "data"
    assert (
        main(["index", "--enex-dir", str(tmp_path / "enex"), "--data-dir", str(data)])
        == 0
    )
    assert (data / "index.sqlite").exists()
    assert "1 notebooks, 2 notes, 0 attachments" in capsys.readouterr().out


def test_index_command_reads_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path / "enex" / "Inbox.enex", note("A"))
    monkeypatch.setenv("ENEX_DIR", str(tmp_path / "enex"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    assert main(["index"]) == 0
    assert "1 notebooks, 1 notes" in capsys.readouterr().out


class FakeUvicorn:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, app: object, **kwargs: object) -> None:
        self.calls.append({"app": app, **kwargs})


def test_serve_reindexes_when_stale_then_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeUvicorn()
    monkeypatch.setattr("enex_viewer.cli.uvicorn_run", fake)
    write(tmp_path / "enex" / "Inbox.enex", note("A"))
    data = tmp_path / "data"
    argv = ["serve", "--enex-dir", str(tmp_path / "enex"), "--data-dir", str(data)]
    assert main([*argv, "--port", "9999"]) == 0
    assert (data / "index.sqlite").exists()
    [call] = fake.calls
    assert (call["host"], call["port"]) == ("0.0.0.0", 9999)

    built = (data / "index.sqlite").stat().st_mtime_ns
    assert main(argv) == 0
    assert (data / "index.sqlite").stat().st_mtime_ns == built  # not stale


def test_missing_enex_dir_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["index", "--enex-dir", str(tmp_path / "nope"), "--data-dir", str(tmp_path)]
    )
    assert code == 2
    assert "not a directory" in capsys.readouterr().err


def test_serve_no_index_serves_existing_index_without_enex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeUvicorn()
    monkeypatch.setattr("enex_viewer.cli.uvicorn_run", fake)
    enex = tmp_path / "enex"
    write(enex / "Inbox.enex", note("A"))
    data = tmp_path / "data"
    assert main(["index", "--enex-dir", str(enex), "--data-dir", str(data)]) == 0
    built = (data / "index.sqlite").stat().st_mtime_ns
    write(enex / "Inbox.enex", note("A"), note("B"))  # index is now stale
    missing = tmp_path / "no-such-dir"
    assert (
        main(
            ["serve", "--no-index", "--enex-dir", str(missing), "--data-dir", str(data)]
        )
        == 0
    )
    assert (data / "index.sqlite").stat().st_mtime_ns == built
    assert len(fake.calls) == 1


def test_serve_no_index_fails_without_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeUvicorn()
    monkeypatch.setattr("enex_viewer.cli.uvicorn_run", fake)
    assert main(["serve", "--no-index", "--data-dir", str(tmp_path)]) == 2
    assert "no index" in capsys.readouterr().err
    assert fake.calls == []
