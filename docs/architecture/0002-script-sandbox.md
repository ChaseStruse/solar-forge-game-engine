# Python behavior sandbox spike

Status: native candidate measured; container compatibility unresolved.

Do not enable imported or generated Python behaviors yet. A Python subprocess or
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

The [raw results](../performance/2026-10-05-script-sandbox.json) distinguish native
boundary checks from the container capability check. Run the developer probes:

```sh
.venv/bin/python scripts/probe_script_sandbox.py
.venv/bin/python scripts/probe_script_sandbox.py --namespace-only
```

Exit 0 means the requested probe passed; 1 means a boundary check failed; 2 means
the required capability is unavailable. Namespace-only success does not prove a
sandbox. These tools are intentionally outside normal engine startup and tests.

## October 6 implementation: computation-only seccomp worker

A narrower candidate avoids the namespace requirement: preload the trusted Python
bootstrap, close every descriptor except private stdin/stdout/stderr pipes, clear
the inherited environment at launch, set no-new-privileges and a parent-death kill
signal, then install a default-deny libseccomp policy before receiving source.
Only memory management, pipe I/O, clock/sleep, local signal handling, randomness and
process-ID queries are permitted. File opens, sockets, process/thread creation,
execution, signalling other processes, tracing, namespaces and policy changes are
denied by the kernel, including when requested through ctypes/raw syscalls.

This is a computation worker, with no display/audio socket, project mount, writable
scratch or file API. Commands cross a bounded JSON pipe and are validated by the
trusted runtime before changing simulation state. It cannot load new packages
from disk after policy installation; math/random are preloaded. Scripts have a
256 MiB address-space limit, 60 CPU seconds per Play session, bounded output and
a planned parent-enforced per-request deadline. Missing libseccomp or a refused policy must
fail closed. No unrestricted fallback is allowed. Initial support is Linux x86_64.
The first implemented checkpoint is the worker and synthetic kernel-boundary tests;
editor attachment and runtime lifecycle integration follow after these checks.

The policy follows the kernel's [seccomp filter contract](https://kernel.org/doc/html/latest/userspace-api/seccomp_filter.html)
and [libseccomp loading contract](https://man7.org/linux/man-pages/man3/seccomp_load.3.html).
It is not a claim of protection against kernel vulnerabilities, side channels or
an independently audited hostile-code boundary. Keep the allowlist small and extend
it only for demonstrated game requirements, with boundary regression checks.

Initial boundary verification: two focused tests pass natively outside the agent
sandbox and in the unchanged Docker security policy; Ruff and strict mypy pass.
Parent lifecycle, cancellation and hostile-output tests remain for the controller.
