"""scripts/refresh.sh: sync -> export -> index -> verified archive, with stubs."""

import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "refresh.sh"

pytestmark = pytest.mark.skipif(shutil.which("zstd") is None, reason="needs zstd")

EXPORT_TWO = (
    'mkdir -p "$WORK/Stack" && printf "<en-export>a</en-export>" > "$WORK/A.enex" '
    '&& printf "<en-export>b</en-export>" > "$WORK/Stack/B.enex"'
)


def run(
    data: Path,
    *args: str,
    sync: str = 'echo sync >> "$DATA_ROOT/log"',
    export: str = EXPORT_TWO,
    index: str = 'echo "index $WORK" >> "$DATA_ROOT/log"',
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATA_ROOT": str(data),
        "REFRESH_SYNC_CMD": sync,
        "REFRESH_EXPORT_CMD": export,
        "REFRESH_INDEX_CMD": index,
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True
    )


def archives(data: Path) -> list[str]:
    return sorted(p.name for p in (data / "archive").iterdir())


def extract(archive: Path, dest: Path) -> dict[str, str]:
    dest.mkdir()
    subprocess.run(
        ["tar", "-I", "zstd", "-xf", str(archive), "-C", str(dest)], check=True
    )
    return {p.relative_to(dest).as_posix(): p.read_text() for p in dest.rglob("*.enex")}


@pytest.fixture
def data(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    (d / "archive").mkdir(parents=True)
    (d / "archive" / "enex-2020-01-01.tar.zst").write_bytes(b"old archive")
    return d


def test_refresh_syncs_indexes_and_replaces_the_archive(
    data: Path, tmp_path: Path
) -> None:
    result = run(data)
    assert result.returncode == 0, result.stderr
    new = f"enex-{date.today().isoformat()}.tar.zst"
    assert archives(data) == [new]
    assert extract(data / "archive" / new, tmp_path / "x") == {
        "A.enex": "<en-export>a</en-export>",
        "Stack/B.enex": "<en-export>b</en-export>",
    }
    log = (data / "log").read_text().splitlines()
    assert log[0] == "sync"
    assert log[1].startswith("index ") and log[1].endswith(".enex-refresh")
    assert not (data / ".enex-refresh").exists()
    assert oct((data / "archive" / new).stat().st_mode & 0o777) == "0o600"


def test_failed_index_keeps_previous_archive_and_cleans_up(data: Path) -> None:
    result = run(data, index="false")
    assert result.returncode != 0
    assert archives(data) == ["enex-2020-01-01.tar.zst"]
    assert not (data / ".enex-refresh").exists()


def test_empty_export_is_rejected(data: Path) -> None:
    result = run(data, export='mkdir -p "$WORK"')
    assert result.returncode != 0
    assert "no .enex files" in result.stderr
    assert archives(data) == ["enex-2020-01-01.tar.zst"]


def test_from_existing_export_skips_sync_and_keeps_the_source(
    data: Path, tmp_path: Path
) -> None:
    src = tmp_path / "existing"
    src.mkdir()
    (src / "C.enex").write_text("<en-export>c</en-export>")
    result = run(data, "--from", str(src), sync="false", export="false")
    assert result.returncode == 0, result.stderr
    [new] = archives(data)
    assert extract(data / "archive" / new, tmp_path / "x") == {
        "C.enex": "<en-export>c</en-export>"
    }
    assert (src / "C.enex").exists()
    assert f"index {src}" in (data / "log").read_text()
