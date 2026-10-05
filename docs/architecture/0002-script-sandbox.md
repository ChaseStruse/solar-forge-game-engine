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
