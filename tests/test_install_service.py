import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "deploy" / "install-service.sh"


def fake_bin(path: Path, name: str, body: str) -> None:
    exe = path / name
    exe.write_text(f"#!/usr/bin/env bash\n{body}\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)


def run_install(tmp_path: Path, env_lines: list[str], linger: str = "yes"):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "systemctl.log"
    fake_bin(bin_dir, "systemctl", f'echo "$*" >> {log}')
    fake_bin(bin_dir, "loginctl", f"echo {linger}")
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(env_lines) + "\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
        "ENV_FILE": str(env_file),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    unit = tmp_path / "cfg" / "systemd" / "user" / "nevernote.service"
    calls = log.read_text().splitlines() if log.exists() else []
    return result, unit, calls


def test_renders_unit_with_absolute_paths(tmp_path: Path) -> None:
    enex = tmp_path / "enex"
    enex.mkdir()
    data = tmp_path / "viewer-data"
    result, unit, calls = run_install(
        tmp_path, [f"ENEX_DIR={enex}", f"DATA_DIR={data}", "VIEWER_PORT=9999"]
    )
    assert result.returncode == 0, result.stderr
    text = unit.read_text()
    assert f"WorkingDirectory={ROOT}\n" in text
    assert f"Environment=ENEX_DIR={enex}\n" in text
    assert f"Environment=DATA_DIR={data}\n" in text
    assert "Environment=PORT=9999\n" in text
    assert f"ExecStart={ROOT}/.venv/bin/enex-viewer serve\n" in text
    assert "@" not in text
    assert data.is_dir()
    assert calls == ["--user daemon-reload", "--user enable nevernote.service"]


def test_missing_enex_dir_fails_without_installing(tmp_path: Path) -> None:
    result, unit, calls = run_install(tmp_path, [f"ENEX_DIR={tmp_path / 'nope'}"])
    assert result.returncode != 0
    assert "does not exist" in result.stderr
    assert not unit.exists()
    assert calls == []


def test_warns_when_lingering_is_off(tmp_path: Path) -> None:
    enex = tmp_path / "enex"
    enex.mkdir()
    result, _, _ = run_install(
        tmp_path, [f"ENEX_DIR={enex}", f"DATA_DIR={tmp_path / 'd'}"], linger="no"
    )
    assert result.returncode == 0, result.stderr
    assert "enable-linger" in result.stderr
