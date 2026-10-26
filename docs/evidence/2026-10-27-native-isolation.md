# Native bootloader isolation integration — 2026-10-27

Actual generated onefile EXE testing initially failed before the application ran: the PyInstaller bootloader could not create its private temporary extraction directory. The synthetic run and bootloader-debug log were preserved outside the repository; no user project or model was used.

Bounded probes established:
- Win32 GetTempPathW redirects into a package-relative subdirectory below the run-private LOCALAPPDATA. Its parent tree must be prepared inside the granted temporary run, not the Owner profile.
- Modify alone permits ordinary output writes but rejects directory creation with an explicit security descriptor. The diagnostic compared Modify, FullControl and Modify + WDAC. Modify + WDAC was sufficient, so FullControl was not adopted.
- PyInstaller 6.22.3's source includes the current user and AppContainer SID in its extraction descriptor. The issue was not solved by weakening that upstream security descriptor.

The native-only manifest now explicitly permits custom DACL creation (WDAC) within AX Branch's temporary writable directories, and two contained processes for the bootloader/application. It grants no access outside the run. Default Python launches still prohibit children and do not get custom-ACL authority. The Job Object refuses a third process; network capability remains absent.

The previously built synthetic Totals.exe then passed both runtime probes inside AppContainer: exit 0 and `total 30`. This is a reuse of the same built bytes after a runtime fix, not another model generation. A clean full native-build regression and the final suite remain to be recorded separately.

Platform/tool sources: [PyInstaller onefile lifecycle](https://pyinstaller.org/en/stable/feature-notes.html#onefile-mode-and-temporary-directory-cleanup), [pinned bootloader implementation](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/bootloader/src/pyi_utils_win32.c). Local diagnostic records establish the observed behavior; documentation alone is not a test.

Scope limits: native code can change permissions within its temporary run. An adversarially locked output can make host export/cleanup fail; no global ACL repair, unrestricted fallback or Owner-folder access is authorized. Web/server loopback remains unsupported. The native-only DACL/process exception is not a claim of universal sandbox security.
