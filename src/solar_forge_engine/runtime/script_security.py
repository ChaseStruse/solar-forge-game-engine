"""Irreversible OS restrictions for a single-threaded Python behavior worker.

Call before compiling/executing any project source. Failure is fatal: there is no
ordinary-subprocess fallback. The editor/runtime process must never call enforce.
"""

import ctypes
import errno
import os
import platform
import resource
import sys
import sysconfig
from pathlib import Path


class Ruleset(ctypes.Structure):
    _fields_ = [
        ("filesystem", ctypes.c_uint64),
        ("network", ctypes.c_uint64),
        ("scope", ctypes.c_uint64),
    ]


class PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("access", ctypes.c_uint64), ("parent", ctypes.c_int32)]


ALLOWED_SYSCALLS = (
    "read",
    "pread64",
    "write",
    "readv",
    "writev",
    "close",
    "close_range",
    "lseek",
    "fstat",
    "newfstatat",
    "statx",
    "stat",
    "lstat",
    "openat",
    "open",
    "readlink",
    "readlinkat",
    "getdents64",
    "access",
    "faccessat",
    "faccessat2",
    "mmap",
    "mprotect",
    "munmap",
    "mremap",
    "madvise",
    "brk",
    "rt_sigaction",
    "rt_sigprocmask",
    "rt_sigreturn",
    "sigaltstack",
    "futex",
    "futex_waitv",
    "set_robust_list",
    "rseq",
    "arch_prctl",
    "clock_gettime",
    "clock_getres",
    "gettimeofday",
    "time",
    "nanosleep",
    "clock_nanosleep",
    "getrandom",
    "getpid",
    "gettid",
    "getuid",
    "geteuid",
    "getgid",
    "getegid",
    "uname",
    "sched_yield",
    "sched_getaffinity",
    "poll",
    "ppoll",
    "select",
    "pselect6",
    "exit",
    "exit_group",
    "fcntl",
)


def enforce(parent_pid: int | None = None) -> int:
    """Return the Landlock ABI after enforcing filesystem/syscall/resource limits."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Python behaviors currently require x86_64 Linux isolation.")
    for entry in os.listdir("/proc/self/fd"):
        descriptor = int(entry)
        if descriptor > 2:
            try:
                os.close(descriptor)
            except OSError as error:
                if error.errno != errno.EBADF:
                    raise
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    libc.prctl.restype = ctypes.c_int
    expected_parent = os.getppid() if parent_pid is None else parent_pid
    if libc.prctl(1, 9, 0, 0, 0):  # PR_SET_PDEATHSIG, SIGKILL; cannot be reset after seccomp.
        raise OSError(ctypes.get_errno(), "Could not enforce worker parent-death cleanup.")
    if os.getppid() != expected_parent:
        raise RuntimeError("The Python worker's runtime parent already exited.")
    seccomp = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int
    seccomp.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    seccomp.seccomp_rule_add.restype = ctypes.c_int
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_load.restype = ctypes.c_int
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.restype = None
    abi = int(libc.syscall(444, 0, 0, 1))
    if abi < 6:
        raise RuntimeError("Python behaviors require Landlock ABI 6 or newer (Linux 6.12+).")
    # Only stdlib is readable. No project, editor installation, home, /proc, device
    # or credential path is granted; native dependencies not already loaded may fail.
    standard_library = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
    rights = (1 << (17 if abi >= 9 else 16)) - 1
    attributes = Ruleset(rights, 3, 3)
    descriptor = int(libc.syscall(444, ctypes.byref(attributes), ctypes.sizeof(attributes), 0))
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), "Could not create the script filesystem policy.")
    try:
        paths = [(standard_library, 1 << 3)]
        for path in standard_library.iterdir():
            if path.is_symlink():
                continue
            if path.is_dir() and path.name in sys.stdlib_module_names | {"lib-dynload"}:
                paths.append((path, (1 << 2) | (1 << 3)))
            elif path.suffix == ".py" and path.stem in sys.stdlib_module_names:
                paths.append((path, 1 << 2))
        for path, access in paths:
            directory = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(access, directory)
                if libc.syscall(445, descriptor, 1, ctypes.byref(rule), 0):
                    raise OSError(
                        ctypes.get_errno(), "Could not allow the Python standard library."
                    )
            finally:
                os.close(directory)
        if libc.prctl(38, 1, 0, 0, 0):
            raise OSError(ctypes.get_errno(), "Could not disable privilege acquisition.")
        if libc.syscall(446, descriptor, 0):
            raise OSError(ctypes.get_errno(), "Could not enforce the script filesystem policy.")
    finally:
        os.close(descriptor)
    for limit, value in (
        (resource.RLIMIT_AS, 256 * 1024 * 1024),
        (resource.RLIMIT_CPU, 3600),
        (resource.RLIMIT_NOFILE, 16),
        (resource.RLIMIT_NPROC, 0),
        (resource.RLIMIT_FSIZE, 64 * 1024),
        (resource.RLIMIT_CORE, 0),
    ):
        resource.setrlimit(limit, (value, value))
    context = seccomp.seccomp_init(0x00050000 | errno.EPERM)
    if not context:
        raise RuntimeError("Could not create the script syscall policy.")
    try:
        for name in ALLOWED_SYSCALLS:
            number = seccomp.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number >= 0 and seccomp.seccomp_rule_add(context, 0x7FFF0000, number, 0):
                raise RuntimeError(f"Could not allow the script syscall: {name}")
        if seccomp.seccomp_load(context):
            raise RuntimeError("Could not enforce the script syscall policy.")
    finally:
        seccomp.seccomp_release(context)
    return abi
