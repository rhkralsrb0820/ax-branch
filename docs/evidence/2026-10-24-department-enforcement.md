# What a department spec actually enforces — AX Branch 0.1.60 (dev/departments)

AX Branch has NO operating-system isolation for agents or generated programs (no sandboxed file system, no
firewall). Enforcement below is by the engine's own checks and by the provider CLI flags it launches agents with.

| Spec field | Status | How / where |
|---|---|---|
| Only attached departments receive work | **Enforced (engine)** | `departments.check_stage` at staffing and again before execution; refused stages pause with `delegation_refused`, no work runs |
| `tools` | **Enforced (engine + provider flags)** | A stage's declared capabilities must be within its department's tools (`check_stage`). The capability lease grants only registry agent capabilities, and the provider adapter grants no shell and no file writes (`providers.authority`, CLI flags). Exception: the final producing stage always gets the engine's build contract (it returns the deliverable as JSON), whatever the department's tools |
| `permissions.network` | **Enforced for agent web research** | A stage asking for web research needs `network: true` (`check_stage`); the provider CLI is started with web search on only when the stage has it. It does NOT govern the delivered program's own network use, which goes through the separate Owner approval of `network_access` |
| `permissions.shell` | **Enforced as always false** | Specs with shell other than false are refused at load. Agents never get a shell (provider flags). This is not OS isolation |
| `permissions.read` / `write` paths | **Declared only** | Agents have no file system access at all (empty temp workdir, file writes off); the engine writes the deliverable into the project folder. There is no per-path OS enforcement |
| `knowledge` | **Declared (guidance)** | Passed to the department's agent in its brief; not checked |
| `acceptance_criteria` | **Enforced as a verification gate (0.1.61)** | Sent to the verifier separately from the project's approved criteria; each must be judged `met`. Unmet, unverifiable, not judged or `conflict` blocks PASS; conflicts are recorded (`criteria_conflict`, both kept, CEO re-plans). The judgement itself is the verifier model's; deterministic parts are the contract check |
| `inputs` / `outputs` (text) | **Declared (planning)** | Shown to the CEO for planning |
| `contract` (new, optional, versioned) | **Enforced as a FORMAT check (engine)** | Notes stages of projects with departments: required inputs before the call; after it, a non-empty result, required fields, minimum evidence/length, and no other project's id. A failing result is not saved or handed on: one rework of that department with the problems, then an Owner pause (a resume never repeats it). `format_ok` means format only, never correctness. Not applied to the final build stage (its artifact goes through the existing checks and independent verification) nor to legacy projects without departments. Specs without a contract get the universal checks only |

## Temporary agents (no fitting department) — `departments.check_stage`, staffing and again before execution
- With at least one department attached, a temporary agent (`department=""`) is refused (`delegation_refused`,
  the project pauses, no work runs, no artifact) when:
  - it declares capabilities outside reasoning ∪ the attached departments' tools;
  - it needs web research and no attached department has `network: true`;
  - its agent role equals the agent role of a library department that is NOT attached (impersonation, which would
    bypass attachment). The match is on the role name, case-insensitive.
- Allowed temporary agents are recorded as a `temporary_agent` event:
  - stage, role and reason ("why": the missing function / fallback decision the CEO gave);
  - the attached departments;
  - its tools and web flag.

  The pipeline shows them as `[임시 에이전트] <role>`.
- The final producing stage may declare `code_generation` even when no attached department has it, because
  returning the deliverable is the engine's build contract (the same exception applies to department stages).
- With no department attached, none of these department rules apply. The pre-department governance and capability
  rules apply unchanged (legacy projects).
- Tests:
  - `tests.test_departments.test_temporary_agent_cannot_bypass_attachment_tools_or_network`: impersonation,
    a tool and web are each refused; the final-stage build is allowed; legacy behaviour with nothing attached;
  - `test_no_fitting_department_is_a_recorded_temporary_agent`;
  - `test_unattached_department_or_overreach_is_refused_before_any_work`.
- Limits:
  - impersonation is matched by role name only, so a renamed role doing an unattached department's job is not
    detected (its tools and network are still bounded as above);
  - a temporary agent gets no department brief (standing instructions, knowledge).

## What the final-stage `code_generation` exception allows (traced in code, 0.1.60)
1. **Agent turn: writing code only.**
   - Every build turn gets `code_generation` from the engine anyway (`capabilities.agent_requests(...,
     coding=True)` for the BUILD/BUILD_EDITS schemas). The exception in `check_stage` only stops a department
     check from refusing what the engine always grants.
   - The agent returns code as JSON. Its CLI turn has no shell, no file writes, no MCP, an empty temporary
     working folder, and web only if the stage has it (`providers.authority`; Claude `--restricted`/tool flags,
     Codex `--sandbox read-only`).
   - The agent itself executes nothing.
2. **The engine writes the files.** They go into `projects/<id>/` through `artifacts.safe_relpath`, which refuses
   paths outside the project.
3. **The engine runs the generated code** for verification: the self-test and the deterministic checks
   (`sandbox.py`), then Runtime Acceptance (`runtime.py`).
   - Containment:
     - a clean environment (no API keys or CLI tokens);
     - a Windows Job Object (at most 8 processes, 1 GB, whole tree killed at the end);
     - a Python audit hook that refuses non-local connections and name lookups (PermissionError) and logs
       subprocess, startfile and browser-open events.
   - Limits (stated in `runtime.AUDIT_NOTE` and DECISIONS D12):
     - it runs under the SAME Windows account, so it can read the user's files;
     - it is not an OS firewall: child processes, native code and the asyncio Proactor connect path are not
       intercepted.
4. **Delivered-program network use.** It needs an Owner `external_connection` approval at staffing (a new or
   risky domain pauses the project).
   - The approval is a planning and review gate: agents are told the recorded decisions, and the verifier
     reviews the source.
   - It is NOT enforced while the program runs.
5. **Owner [결과 실행] (`launch_verified`).** It runs the verified version as the Owner's own action: a fresh copy
   under `projects/<id>/run/`, with the normal environment and no audit hook or network block. Reaching this
   step requires a PASS.

So the exception grants code *writing* only. Execution happens through the engine's verification and the
Owner's own launch. Neither bypasses the existing approvals (network domains are approved before staffing;
paid tools, credentials and publishing are Owner-only in governance). Both have the containment limits above;
no new isolation was added in this step.

## Generated-program permissions: declared / pre-approved / enforced at run time (0.1.61)
| Permission | Declared | Pre-approved (before it runs) | Enforced while it runs: verification | Enforced while it runs: Owner [결과 실행] |
|---|---|---|---|---|
| Network (Python result) | plan `network_access` | Owner `external_connection` approval at staffing (a new or risky domain pauses) | audit hook refuses every non-local connection or name lookup | audit hook allows loopback plus the approved domains only (`AXB_ALLOW_HOSTS`); attempts logged to `run/vN/network-audit.jsonl` |
| Network (native .exe result) | same | same | not covered by the hook | **not enforced** (recorded in the `owner_run` event) |
| Network (child processes, native code, asyncio Proactor connect) | — | — | not intercepted | not intercepted |
| Files | `permissions.read/write` (department, declared only) | — | clean environment and Job Object (processes, memory), same Windows account | **not restricted** (same Windows account) |
| Processes | — | — | Job Object: at most 8 processes, 1 GB, tree killed at the end | normal process, its own console |

**Evidence** (`tests/test_owner_run.py`, real child processes):
- verification refuses `example.com` and an unapproved domain with PermissionError, allows loopback, and logs the
  attempt;
- the Owner's run with `example.com` approved is not refused for it, still refuses the unapproved domain, and
  allows loopback;
- `launch_verified` starts the result through the launcher, passes the approved domains and records the
  enforcement in `owner_run`.

The audit hook is a Python-level, best-effort boundary, not operating-system isolation. Stronger options were
not taken, because each needs administrator rights or Owner setup, which the Owner must approve at that step:
- Windows Firewall per-program rules;
- a separate low-privilege Windows account (DECISIONS D12).

## Not implemented (stated plainly)
- OS-level file or network isolation of agents or generated programs (open risk D-SEC-1).
- Per-department schema validation of outputs.
- Department acceptance criteria as an automatic verification gate.
