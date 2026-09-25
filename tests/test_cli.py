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


def test_missing_enex_dir_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["index", "--enex-dir", str(tmp_path / "nope"), "--data-dir", str(tmp_path)]
    )
    assert code == 2
    assert "not a directory" in capsys.readouterr().err
