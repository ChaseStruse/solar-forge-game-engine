"""Probe OS restrictions with fixed trusted code; never run a game script."""

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

NAMESPACE_PROBE = """
import ctypes, json, os
libc = ctypes.CDLL(None, use_errno=True)
libc.unshare.argtypes = [ctypes.c_int]
libc.unshare.restype = ctypes.c_int
result = libc.unshare(0x10000000)
number = ctypes.get_errno()
print(json.dumps({'user_namespace': result == 0, 'errno': number,
                  'reason': os.strerror(number) if result else None}))
"""

BOUNDARY_PROBE = """
import ctypes, json, os, socket, sys
from pathlib import Path

def denied(operation):
    try:
        operation()
    except OSError:
        return True
    return False

def tcp():
    with socket.socket() as connection:
        connection.settimeout(0.25)
        connection.connect(('127.0.0.1', int(sys.argv[2])))

def unix():
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(0.25)
        connection.connect(sys.argv[3])

libc = ctypes.CDLL(None, use_errno=True)
libc.unshare.argtypes = [ctypes.c_int]
libc.unshare.restype = ctypes.c_int
report = {
    'host_file_read_denied': denied(lambda: Path(sys.argv[1]).read_bytes()),
    'host_file_write_denied': denied(lambda: Path(sys.argv[1]).write_bytes(b'changed')),
    'helper_write_denied': denied(lambda: Path(__file__).write_text('changed')),
    'host_tcp_denied': denied(tcp),
    'host_unix_socket_denied': denied(unix),
    'home_hidden': not Path('/home').exists(),
    'environment_canary_removed': 'SOLAR_SANDBOX_CANARY' not in os.environ,
    'pid_namespace_changed': os.readlink('/proc/self/ns/pid') != sys.argv[4],
    'network_namespace_changed': os.readlink('/proc/self/ns/net') != sys.argv[5],
    'nested_user_namespace_denied': libc.unshare(0x10000000) == -1,
}
scratch = Path(sys.argv[1]).with_name('private.txt')
scratch.parent.mkdir(parents=True)
scratch.write_text('temporary scratch')
report['private_scratch_works'] = scratch.read_text() == 'temporary scratch'
print(json.dumps({'python': sys.version.split()[0], 'checks': report}))
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace-only", action="store_true")
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("This spike requires Linux.")
    if args.namespace_only:
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", NAMESPACE_PROBE],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        report = json.loads(result.stdout)
        report["scope"] = "User namespace capability only; no game script executed."
        print(json.dumps(report, indent=2))
        return 0 if report["user_namespace"] else 2
    if not Path("/usr/bin/bwrap").is_file() or not Path("/usr/bin/python3").is_file():
        parser.error("The native Arch probe needs /usr/bin/bwrap and /usr/bin/python3.")
    with (
        tempfile.TemporaryDirectory(prefix="solar-sandbox-probe-") as temporary,
        socket.socket() as tcp,
        socket.socket(socket.AF_UNIX) as unix,
    ):
        root = Path(temporary)
        canary = root / "credential-canary.txt"
        canary.write_bytes(b"synthetic canary; never a real credential")
        helper = root / "probe.py"
        helper.write_text(BOUNDARY_PROBE)
        tcp.bind(("127.0.0.1", 0))
        tcp.listen(1)
        unix_path = root / "host.sock"
        unix.bind(str(unix_path))
        unix.listen(1)
        command = [
            "/usr/bin/bwrap",
            "--unshare-all",
            "--unshare-user",
            "--disable-userns",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
            "--cap-drop",
            "ALL",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib",
            "/lib64",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            str(helper),
            "/work/probe.py",
            "--remount-ro",
            "/",
            "--chdir",
            "/work",
            "/usr/bin/python3",
            "-I",
            "-S",
            "/work/probe.py",
            str(canary),
            str(tcp.getsockname()[1]),
            str(unix_path),
            os.readlink("/proc/self/ns/pid"),
            os.readlink("/proc/self/ns/net"),
        ]
        result = subprocess.run(
            command,
            env={"SOLAR_SANDBOX_CANARY": "synthetic environment canary"},
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode:
            print(json.dumps({"supported": False, "error": result.stderr[-2000:]}, indent=2))
            return 2
        report = json.loads(result.stdout)
        report["checks"]["host_canary_unchanged"] = canary.read_bytes() == (
            b"synthetic canary; never a real credential"
        )
        report["checks"]["helper_unchanged"] = helper.read_text() == BOUNDARY_PROBE
        report["checks"]["scratch_not_on_host"] = not (root / "private.txt").exists()
        version = subprocess.run(
            ["/usr/bin/bwrap", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        report["bubblewrap"] = version.stdout.strip()
        report["scope"] = (
            "Fixed trusted boundary probes on native Arch; /usr remains readable. "
            "No game scripts, runtime IPC, resource limits or adversarial escape audit."
        )
        print(json.dumps(report, indent=2))
        return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
