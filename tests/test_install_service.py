import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "deploy" / "install-service.sh"
QUADLET_BIN = Path("/usr/libexec/podman/quadlet")


def fake_bin(path: Path, name: str, body: str) -> None:
    exe = path / name
    exe.write_text(f"#!/usr/bin/env bash\n{body}\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)


def run_install(
    tmp_path: Path,
    env_lines: list[str],
    linger: str = "yes",
    subuids: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "systemctl.log"
    fake_bin(bin_dir, "systemctl", f'echo "$*" >> {log}')
    fake_bin(bin_dir, "loginctl", f"echo {linger}")
    fake_bin(bin_dir, "podman", "exit 0")
    fake_bin(bin_dir, "setfacl", f'echo "$*" >> {tmp_path / "setfacl.log"}')
    subuid = tmp_path / "subuid"
    subuid.write_text(
        f"someone:200000:65536\n{os.environ['USER']}:100000:65536\n"
        if subuids is None
        else subuids
    )
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(env_lines) + "\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
        "ENV_FILE": str(env_file),
        "SUBUID_FILE": str(subuid),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    quadlet = tmp_path / "cfg" / "containers" / "systemd" / "nevernote.container"
    calls = log.read_text().splitlines() if log.exists() else []
    return result, quadlet, calls


def data_with_index(tmp_path: Path) -> Path:
    data = tmp_path / "viewer-data"
    data.mkdir()
    (data / "index.sqlite").write_bytes(b"")
    return data


def test_renders_quadlet_with_read_only_data_mount(tmp_path: Path) -> None:
    data = data_with_index(tmp_path)
    result, quadlet, calls = run_install(
        tmp_path, [f"DATA_DIR={data}", "VIEWER_PORT=9999"]
    )
    assert result.returncode == 0, result.stderr
    text = quadlet.read_text()
    assert f"Volume={data}:/data:ro\n" in text
    assert "PublishPort=9999:8765\n" in text
    assert text.count("Volume=") == 1  # nothing but the index is mounted
    for hardening in (
        "ReadOnly=true",
        "DropCapability=all",
        "NoNewPrivileges=true",
        "UserNS=nomap",
    ):
        assert hardening in text
    assert "@" not in text.replace("[Container]", "")
    assert calls == ["--user daemon-reload"]


def test_grants_the_container_uid_read_only_access(tmp_path: Path) -> None:
    # With UserNS=nomap the container's uid 10001 is host subuid start + 10001;
    # it gets read (and directory traverse) on the index only, now and for
    # files written later (default ACL).
    data = data_with_index(tmp_path)
    result, _, _ = run_install(tmp_path, [f"DATA_DIR={data}"])
    assert result.returncode == 0, result.stderr
    acl = (tmp_path / "setfacl.log").read_text().splitlines()
    assert acl == [
        f"-R -m u:110001:rX {data}",
        f"-R -d -m u:110001:rX {data}",
    ]
    assert "110001" in result.stdout


def test_missing_subuid_range_fails(tmp_path: Path) -> None:
    data = data_with_index(tmp_path)
    (tmp_path / "subuid").parent.mkdir(exist_ok=True)
    result, quadlet, _ = run_install(tmp_path, [f"DATA_DIR={data}"], subuids="")
    assert result.returncode != 0
    assert "subuid" in result.stderr
    assert not quadlet.exists()


def test_missing_index_fails_without_installing(tmp_path: Path) -> None:
    result, quadlet, calls = run_install(tmp_path, [f"DATA_DIR={tmp_path / 'nope'}"])
    assert result.returncode != 0
    assert "make refresh" in result.stderr
    assert not quadlet.exists()
    assert calls == []


def test_replaces_the_legacy_plain_unit(tmp_path: Path) -> None:
    legacy = tmp_path / "cfg" / "systemd" / "user" / "nevernote.service"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("[Service]\n")
    data = data_with_index(tmp_path)
    result, quadlet, calls = run_install(tmp_path, [f"DATA_DIR={data}"])
    assert result.returncode == 0, result.stderr
    assert not legacy.exists()
    assert quadlet.exists()
    assert calls == ["--user disable --now nevernote.service", "--user daemon-reload"]


def test_warns_when_lingering_is_off(tmp_path: Path) -> None:
    data = data_with_index(tmp_path)
    result, _, _ = run_install(tmp_path, [f"DATA_DIR={data}"], linger="no")
    assert result.returncode == 0, result.stderr
    assert "enable-linger" in result.stderr


@pytest.mark.skipif(not QUADLET_BIN.exists(), reason="podman's quadlet not installed")
def test_rendered_quadlet_is_accepted_by_podman(tmp_path: Path) -> None:
    data = data_with_index(tmp_path)
    _, quadlet, _ = run_install(tmp_path, [f"DATA_DIR={data}"])
    result = subprocess.run(
        [str(QUADLET_BIN), "-dryrun", "-user"],
        env={**os.environ, "QUADLET_UNIT_DIRS": str(quadlet.parent)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    unit = result.stdout
    assert "---nevernote.service---" in unit
    assert f"-v {data}:/data:ro" in unit
    assert "--userns nomap" in unit
    for flag in ("--read-only", "--cap-drop=all", "--security-opt=no-new-privileges"):
        assert flag in unit, flag
    assert shutil.which("podman")
