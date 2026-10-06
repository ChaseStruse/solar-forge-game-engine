# Python behavior sandbox spike

Status: Landlock/libseccomp restrictions verified natively and in Docker;
behavior-worker integration remains in progress.

Do not enable imported or generated Python behaviors without the verified worker
restrictions, bounded protocol and lifecycle checks. A Python subprocess or
isolated interpreter mode alone cannot restrict OS filesystem and network access.
The [Bubblewrap project](https://github.com/containers/bubblewrap) explains that
the caller must define its own security policy; the tool is not a complete sandbox.

`scripts/probe_script_sandbox.py` runs fixed trusted code with synthetic file,
environment and socket canaries. On native Arch, Bubblewrap 0.12.0 and system
Python 3.14.7 pass fourteen checks: hidden home and host files, denied host-file and
helper writes, denied host TCP/Unix-socket connections, removed environment canary,
separate PID/network namespaces, denied nested user namespaces, isolated writable
scratch and unchanged host canaries/helper. The probe has a five-second timeout,
no inherited file descriptors, no project mount and no shell interpolation.

The native candidate uses read-only `/usr`, private `/proc`, minimal `/dev`, private
temporary storage, a read-only fixed helper, dropped capabilities, a new session
and parent-death termination. It exposes no display, audio or credential sockets.
Read-only `/usr` is deliberately broad for this capability spike, not the final
runtime dependency allowlist. No resource-limit, hostile-code escape, descendant
termination, bounded IPC or game-script lifecycle claim has been demonstrated.

The unchanged headless Docker service denies `unshare(CLONE_NEWUSER)` with EPERM.
This prevents the unprivileged Bubblewrap candidate from bootstrapping there.
Keep the existing dropped-capability/no-new-privileges policy; do not add privileged
containers or fall back to ordinary subprocess execution. Evaluate restrictions
that work under that policy, or a separately isolated worker with a narrow contract,
then prove filesystem/network denials, limits and termination before scripting.

The implementation now uses Landlock ABI 6+ with libseccomp on x86_64 Linux.
The worker grants read access only to Python standard-library modules, excluding
site packages, and denies filesystem writes and TCP connections. Its syscall
allowlist also denies sockets, process creation, execution, signalling other
processes and namespace changes. Inherited descriptors above stdin/stdout/stderr
are closed. Hard resource limits include 256 MiB address space, 16 descriptors,
no child processes/core dumps and a cumulative 3,600 CPU-second ceiling. Landlock
does not hide all filesystem metadata; no claim of a private mount namespace is made.

A real subprocess regression verifies synthetic credential read/write denials,
socket/exec/fork/signal denials, closure of an intentionally inherited descriptor,
unavailable editor imports and memory-limit enforcement. It passes natively and
under the unchanged Docker capabilities/no-new-privileges policy. No arbitrary
project source is executed by this regression. Request deadlines, output caps and
runtime lifecycle remain mandatory before the editor can enable behaviors.
See [Landlock's kernel documentation](https://docs.kernel.org/userspace-api/landlock.html)
and [libseccomp's policy API](https://man7.org/linux/man-pages/man3/seccomp_init.3.html).

The [raw results](../performance/2026-10-05-script-sandbox.json) distinguish native
boundary checks from the container capability check. Run the developer probes:

```sh
.venv/bin/python scripts/probe_script_sandbox.py
.venv/bin/python scripts/probe_script_sandbox.py --namespace-only
```

Exit 0 means the requested probe passed; 1 means a boundary check failed; 2 means
the required capability is unavailable. Namespace-only success does not prove a
sandbox. These tools are intentionally outside normal engine startup and tests.
