# Owner result execution isolation — 2026-10-27

Baseline: d2f63e9 (AppContainer implementation 2058648). This continuation closes the in-app result-button bypass; it does not replace the Owner's serving build.

## Behavior

- Engine.launch_verified takes the existing project run lock and uses the same AppContainer/Job Object runner for bounded CLI/native result execution by default.
- Input/artifact bytes run from a fresh temporary copy. The Owner workspace itself is never granted to the container. Changed regular output files are copied back with limits (200 files / 32 MB); symlinks/reparse points are not exported.
- The web result action can show stdout/exit/timeout in its existing text viewer. It no longer opens a shell for a protected CLI result.
- Unsupported web/GUI or foreign-interpreter runs fail before execution. A deliberately recorded project isolation exception is necessary for the older external launch, whose environment is now cleaned. That path is labelled external_unisolated; it is not described as Job Object protected.
- The external manual double-click path remains outside AX Branch's control. CLI programs needing interactive stdin are not supported by the bounded in-app runner (stdin is empty).

## Evidence

- After the main correction: five focused Owner-run/copy tests passed (33.081 s).
- Isolation and Owner-run modules: 16/16 passed (28.724 s), including nine isolation tests (six real-backend tests, three adapter tests) and actual Owner-launch canary/token/output-export coverage. A later native return-path/error-record adjustment still requires the final relevant regression.
- Real canary outcomes: outside file read/write PermissionError (errno 13), profile enumeration winerror 5, Internet connection winerror 10013, child process winerror 367. Allowed local output succeeded and the synthetic inherited token was absent.
- Loopback returned TimeoutError while the same local endpoint worked without isolation and received no isolated connection. This is observed unreachability, not an explicit access-denied error. The tests now distinguish it from OS denial and reject unrelated errors.
- DNS and HKCU denial were not tested in this continuation. The previous broad report should not be read as evidence of those claims.
- No model calls, real user files, firewall changes or global account/OS configuration changes. Temporary AppContainer profiles and grants are created/cleaned by the existing backend for these tests.

## Open work

Full final regression, current package checks and a real packaged web rework flow remain outstanding. Server-mode isolation/communication is still blocked; no implicit reduced-protection exception was added.

Platform references: [AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation), [launching AppContainers](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer), [process attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute). These describe the platform; local tests establish the observed implementation coverage.
