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
| `acceptance_criteria` | **Declared to the agent; not a gate** | Given to the department's agent. The verifier's gate is still the plan's approved criteria plus the deterministic checks; department criteria are not added to it automatically |
| `inputs` / `outputs` | **Declared (planning)** | Shown to the CEO for planning; outputs are not schema-validated per department |

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

## Not implemented (stated plainly)
- OS-level file or network isolation of agents or generated programs (open risk D-SEC-1).
- Per-department schema validation of outputs.
- Department acceptance criteria as an automatic verification gate.
