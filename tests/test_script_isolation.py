import json
import os
import subprocess
import sys

from solar_forge_engine.runtime.scripting import worker_bootstrap


def worker_command():
    return [
        sys.executable,
        "-I",
        "-S",
        "-B",
        "-c",
        worker_bootstrap(),
        str(os.getpid()),
    ]


def request(source, request_id=1):
    return (
        json.dumps(
            {
                "id": request_id,
                "op": "start",
                "source": source,
                "state": {
                    "objects": {},
                    "player": {},
                    "input": {},
                    "collected": 0,
                    "total_coins": 0,
                    "time": 0,
                },
            }
        )
        + "\n"
    )


def test_kernel_restrictions_deny_host_access_even_through_raw_syscalls(tmp_path):
    canary = tmp_path / "private-canary"
    canary.write_text("synthetic secret")
    with canary.open("rb") as inherited:
        source = f"""
import ctypes, errno, os
libc = ctypes.CDLL(None, use_errno=True)
def denied(name, *args):
    result = getattr(libc, name)(*args)
    assert result == -1 and ctypes.get_errno() == errno.EPERM, (name, result)
def on_start(game):
    denied("open", {os.fsencode(canary)!r}, 0)
    denied("open", {os.fsencode(canary)!r}, 1)
    denied("open", b"/proc/self/environ", 0)
    denied("open", b"/proc/1/mem", 0)
    denied("open", b"/dev/null", 1)
    denied("socket", 2, 1, 0)
    denied("socket", 1, 1, 0)
    denied("fork")
    denied("syscall", 56, 0, 0, 0, 0, 0)  # raw clone, bypass libc validation
    denied("execve", b"/bin/true", 0, 0)
    denied("kill", {os.getpid()}, 0)
    denied("ptrace", 0, 0, 0, 0)
    denied("unshare", 0x10000000)
    denied("prctl", 38, 0, 0, 0, 0)
    denied("prctl", 22, 0, 0, 0, 0)
    denied("mount", 0, 0, 0, 0, 0)
    denied("ioctl", 0, 0, 0)
    denied("syscall", 435, 0, 0)  # clone3, even inside Docker
    try:
        os.read({inherited.fileno()}, 1)
    except OSError as error:
        assert error.errno == errno.EBADF
    else:
        raise AssertionError("Inherited host descriptor survived")
    assert "SCRIPT_CANARY" not in os.environ
    game.say("Kernel denials verified")
"""
        result = subprocess.run(
            worker_command(),
            input=request(source),
            capture_output=True,
            text=True,
            env={"LANG": "C.UTF-8"},
            pass_fds=(inherited.fileno(),),
            timeout=5,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    assert messages[0] == {"type": "ready"}
    assert messages[1]["commands"] == [{"op": "message", "value": "Kernel denials verified"}]
    assert canary.read_text() == "synthetic secret"


def test_worker_reports_source_lines_and_resource_failures_without_running_on_import():
    sources = [
        ("def on_start(game):\n    raise ValueError('broken')", "ValueError", 2),
        ("def on_start(game)\n    pass", "SyntaxError", 1),
        ("def on_start(game):\n    print('x' * 5000)", "4 KiB", 2),
        ("def on_start(game):\n    data = bytearray(512 * 1024 * 1024)", "MemoryError", 2),
    ]
    for source, error, line in sources:
        result = subprocess.run(
            worker_command(),
            input=request(source),
            capture_output=True,
            text=True,
            env={"LANG": "C.UTF-8"},
            timeout=5,
        )
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        assert messages[0] == {"type": "ready"}
        assert messages[1]["type"] == "error"
        assert error in messages[1]["message"] and messages[1]["line"] == line
