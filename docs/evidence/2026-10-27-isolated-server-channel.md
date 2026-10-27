# Verifying generated web/server programs inside their AppContainer — per-run channel (2026-10-27)

**Problem.** A generated server runs inside its AppContainer. Windows does not let the host connect to an
AppContainer over loopback, so the verifier could not reach it. Server/web Runtime Acceptance was therefore blocked
and needed a per-project Owner exception.

**Constraint.** No persistent Windows change: no loopback exemption, firewall, ACL, account or feature change.

## Prototype findings (real backend, synthetic data)
1. Two processes in the **same** AppContainer (same package SID) can talk over 127.0.0.1. An HTTP GET returned 200
   (`scratchpad pipe_probe.py`).
2. A container process can open a **host-created named pipe** whose DACL grants its package SID.
3. Already shown in Phase A: a container cannot reach the host's loopback (a host listener was never reached).

## Design (implemented: `axbranch/isolation.py` ServerChannel, `sandbox.Contained`, `runtime`)
- In server/web mode with isolation:
  - the generated program runs in its per-run AppContainer, as before;
  - a fixed AX Branch bridge (`BRIDGE`, written into the run folder) runs in the **same** container and Job;
  - the host creates a control pipe plus one pipe pair per connection, named `\\.\pipe\axb-<run_id>-…`, with DACL
    `D:P(A;;GA;;;<package SID>)(A;;GA;;;OW)`.
- The verifier (`http.client`, or the headless browser through the click proxy) uses `proc.reach(port)`: a host
  relay on 127.0.0.1 for that container port. Readiness (`_wait_port`) is asked inside the container through the
  bridge.
- **Not a general proxy.** The bridge connects only to `127.0.0.1:<port>` inside the container. The OS blocks
  container→host loopback and the run has no network capability, so even a modified bridge cannot reach host
  services or the internet. The relay forwards only between the verifier and that run's pipes.

## Verified (real AppContainer; `tests/test_isolation.py`, synthetic canaries)
| Question | Result | Evidence |
|---|---|---|
| Generated server actually runs isolated | PASS: per-run AppContainer manifest records `backend=appcontainer`, `serve=true` | test_generated_web_server_is_verified_inside_its_container_through_the_run_channel |
| Verifier exchanges required requests/responses | PASS: HTTP page, JSON endpoint, headless-browser render, Owner's exact launch (default port), busy-port second launch | same |
| Cannot reach other local services | PASS: the server's connect to a host listener timed out; the listener saw 0 connections | same |
| No external network | PASS: connect to 1.1.1.1:443 → PermissionError | same |
| No Owner files | PASS: outside canary → PermissionError | same |
| No unauthorized child processes | PASS: `cmd /c` → OSError (child-process policy) | same |
| Processes and temporary rights cleaned at the end | PASS: no `axb_bridge.py` process left; the run's control pipe no longer exists; the run's AppContainer profile mapping is deleted; 0 `AXBranch.Run.*` profiles remained afterwards | same, plus a registry count |
| One run's access does not carry to the next | PASS: a pipe that grants another run's SID is refused to a new run (access denied) | test_a_run_channel_pipe_refuses_any_other_run |

## Defect found and fixed during this work
- The Owner-launch "after the flow" request once got `ConnectionResetError (10054)`: 1 of the first 4 runs.
- Cause (hypothesis): the host relay closed the client socket while its other thread could still be reading,
  which Windows may turn into a reset.
- Fix: half-close (`shutdown(SHUT_WR)`) after the response; release the socket when the client side ends.
- After the fix: 3/3 runs passed. Not claimed as proven beyond that.

## Limits / UNKNOWN
- Other host processes of the **same Windows user** could connect to the temporary relay port while a check runs.
  They already have the user's full rights; the run's pipes also grant the owner. Not isolation from the Owner's
  own account.
- Programs that hard-code another host name, or need external services, still fail: no network.
  `localhost`/`127.0.0.1` inside the program work.
- A default port already used on the host (e.g. 8765, used by the Owner's AX Branch server) collides: ports are
  machine-wide. Observed once with a test fixture.
- Not tested: WebSockets and long-lived streaming through the relay, large uploads, HTTPS, more than one listening
  port per program. Each is UNKNOWN until tested.
- In-app Owner **result execution** of web/server programs still stays blocked; this change covers verification.
- The Windows loopback exemption alternative is not used. It would be an OS-wide change per package name (Owner
  approval needed); not required for the verified scope above.
