# Department Harness & organizational orchestration — proposal (design only, for Owner review)

Date: 2026-10-26. Base: `dev/web-ui` @ 5f70f97 plus the preserved Product Planning / experience work (see
TAKEOVER section of `docs/CODEX_CLI_HANDOFF.md`). Status: **PROPOSAL — not implemented.** Nothing below is built
until the Owner approves. Scope source: the "Department Harness & Organizational Capability Orchestration
Directive" (attachment e36b1313…, sections 0–21).

Separate from the older 20-area evolution matrix (`docs/IN_PLACE_EVOLUTION_REVIEW.md`):
- That matrix is based on the "AX BRANCH IN-PLACE EVOLUTION DIRECTIVE", available at `C:/Users/HP/.codex/attachments/358305e6-3b45-4598-a748-d8199e092b69/붙여넣은 텍스트.txt` (located by Codex,
  2026-10-26). Its §5 lists the same 20 areas the review uses.
- The earlier note that this source was missing is withdrawn.

## 1. Architecture assessment — what already exists (behaviour, not file names)
The flow the directive asks for already runs end to end for two departments:

```
Owner (Tk window / web) ──attach (drag or button)──► department_attached event (+ pinned spec snapshot & sha256)
     │ goal + files                                        │
     ▼                                                     ▼
淸月 CEO plan (engine PLAN, STAGE.department) ◄── summaries of ATTACHED departments only
     │  check_stage at staffing and before execution: attached only, tools ⊆ department, network only if
     │  granted, temporary agents bounded by attached departments, no impersonation
     ▼
temporary specialist per stage (providers: CLI flags = no shell, no file writes, web only if the stage has it)
     │  department brief (role, workflow, instructions, contract, acceptance)
     ▼
contract check (format, references, product-plan arithmetic) ─fail→ 1 bounded rework of that department → Owner pause
     ▼
final build → deterministic checks / Runtime Acceptance (Job Object, audit hook) → independent verifier (other engine)
     │  department acceptance judged separately (met / unmet / unverifiable / conflict); anything but met blocks PASS
     ▼
CEO acceptance → Owner review → feedback (works / request → same project REWORK; reuse unchanged stages, re-run dependents)
     ▼
events (audit), experience records (scoped cards with source, verification level, difference), library / develop
```

A Department Harness in the directive's sense **is** the existing department package, plus four gaps:
1. no recommendation mode;
2. no required mode;
3. no registry lifecycle (candidate / verified / quarantined / deprecated);
4. no external-source import path.

## 2. Existing-component mapping and decisions
| Directive element | Existing AX component | Decision |
|---|---|---|
| Department Harness package | `departments/<id>/department.json`, `departments.validate/catalog` | **PRESERVE / EXTEND** with `status` and `provenance` |
| Skills / workflows | `workflow` (Codex addition), `agent.instructions`, `contract.document_sections` | **EXTEND**: workflow steps become the procedure an imported skill maps to |
| Agent templates | `agent.role` + instructions; temporary stage agents | **PRESERVE**: no permanent department agents (directive §2) |
| Tools | `tools` ⊆ `capabilities.AGENT`; `check_stage` | **PRESERVE** (enforced) |
| Connectors (MCP / OAuth SaaS) | none; external connections go through `permissions` + Owner `external_connection` approval | **REJECT import as capability**: a connector is a credential plus a network grant, Owner-only |
| Knowledge / experience scope | `knowledge`, `permissions.read` ("scoped structured experience"), `knowledge.department_experience` | **PRESERVE / EXTEND** (pinned scope, cutoff, source allowlist) |
| Capability / permission requirements | `permissions` {network, shell=false, read, write}, governance, capabilities leases | **EXTEND** declarations with data class / external actions, mapped onto EXISTING gates only |
| Input / output contract | `contract` (format, required inputs, references, document sections, product plan) | **PRESERVE** (enforced as a format check) |
| Acceptance / verification rules | `acceptance_criteria` → verifier gate | **PRESERVE** (enforced as a gate) |
| Rework rules | contract rework ×1, verification rework rounds, `_carry_over` | **PRESERVE** |
| Version / provenance / validation | `version`, pinned snapshot + sha256 (Codex addition); no status or provenance | **ADD** `status`, `provenance` (source, revision, license, imported_by) |
| Autonomous / recommended mode | none (the CEO sees attached departments only) | **ADD**: the CEO recommends from the verified library; the Owner attaches |
| Required mode | none | **ADD**, enforced at four points (§5) |
| Cross-department orchestration | sequential `pipeline` chosen by the CEO, no fixed order | **PRESERVE**. Parallel stages **DEFER** (needs a dependency field and concurrency safety in the Store and leases) |
| Harness registry | the library folder (all valid specs are attachable) | **EXTEND** the same folder with status filtering; no second registry |
| Another orchestrator / department managers | — | **REJECT** (§14) |
| Installing plugins / thin plugin wrapper | — | **REJECT** (§7) |
| RL / LoRA / world models for orchestration | — | **DEFER**; no demonstrated weakness or data |

## 3. Minimum compatible department contract
Keep every current field. Add only:

```jsonc
"status": "verified",            // candidate | verified | quarantined | deprecated   (absent = verified, legacy)
"provenance": {"source": "ax-native" | "<repo url>", "revision": "<commit>", "path": "<skill path>",
               "license": "Apache-2.0", "imported_at": "...", "evaluated": ["<evidence path>"]},
"security": {"data_classes": ["public", "owner_files"],      // declared; each maps to an existing gate (§7)
             "external_actions": [],                          // e.g. "publish", "contact" → Owner approval
             "owner_approval": []}
```

- `validate` refuses unknown statuses and data classes.
- `catalog` offers only `verified` departments for new attachment. Candidates are visible in the devroom only.
- A quarantined department cannot be newly attached. A project already pinned to it keeps its snapshot, but
  new delegation pauses with "quarantined: Owner decision needed".

## 4. External source → AX candidate (knowledge-work-plugins reviewed)
**Source inspected.** `https://github.com/anthropics/knowledge-work-plugins`, revision
`33d3dea41a341b341d4f5da2e8801ae0c89be2b8` (2026-10-21).
- License: Apache-2.0 for the root and 14 packages. `partner-built/*`: apollo, brand-voice, slack and zoom are
  MIT; common-room is Apache-2.0.
- Package structure: a manifest, `.mcp.json` (HTTP MCP servers with OAuth: Slack, Linear, Asana, Box, DocuSign,
  Gmail, Snowflake, …), `commands/*.md` and `skills/*/SKILL.md` (markdown procedures).
- Inspected in depth: product-management `write-spec`, legal `legal-risk-assessment`, finance `reconciliation`,
  and the skill and connector lists of data and operations.

**Mapping rule (provider-neutral):**

| Plugin element | AX target | Rule |
|---|---|---|
| SKILL.md workflow steps | `workflow` + `agent.instructions` | Condensed, attributed (provenance plus license notice); the source text stays reference data |
| Checklists / frameworks (e.g. the legal severity × likelihood matrix, reconciliation categories) | `acceptance_criteria`, `contract.document_sections` | Only checkable rules; "consult a professional" disclaimers become explicit limits |
| Slash commands | nothing (the Owner states goals; the CEO plans) | Not copied |
| `.mcp.json` connectors | listed as `provenance.unmapped_connectors` | Never mapped to a tool. Each would need a separate Owner-approved capability with credentials and network approval |
| Sub-agent patterns | temporary stage agents | No permanent agents |

**Pipeline:**
1. External source → offline converter writes `status: candidate` (the developer runs it; the CEO never runs it
   by itself).
2. Compatibility and permission mapping report.
3. Fixed evaluation tasks (at least 2, isolated root, budget) and security tests (it cannot request tools,
   network or connectors beyond its declaration).
4. Independent verification of the evaluation results.
5. The Owner approves promotion to `verified`; a new version is written, the old one is kept.
6. Rollback = set the new version to `deprecated` and re-verify the old one. Active projects keep their pinned
   snapshot.

**First candidates proposed (each needs its own evaluation):**
- `legal-review` from legal-risk-assessment / review-contract, read-only and without the legal-advice claim;
- `data-validation` from data `validate-data` / `statistical-analysis`, offline on attached files only.

Product-management `write-spec` overlaps the existing Product Planning package. It should become an evaluated
revision of that package, not a second department.

## 5. Assignment semantics and enforcement
| Mode | Meaning | Where enforced (existing points) |
|---|---|---|
| **Available** (today's attach) | The CEO may delegate to it | `check_stage` (unchanged) |
| **Recommended** (Autonomous) | The CEO proposes verified library departments with reasons in the plan (`recommended_departments`) | The plan is shown. Nothing is attached until the Owner accepts (one click attaches as Available or Required). The CEO never attaches by itself |
| **Required** | Its work and acceptance must exist before the result can be accepted | Four points, below |

`department_attached` event gains `mode: available | required`. Required enforcement:
1. **Staffing:** a plan without a stage delegated to every required department is refused (`delegation_refused`
   → re-plan, bounded by the existing rounds).
2. **Execution / rework:** a required stage counts only if it ran or was validly reused in the current plan
   version (existing `stage_reused` rule). A changed upstream discards it.
3. **Acceptance:** the verifier must judge the required department's criteria `met`. Without a recorded `met`,
   the CEO acceptance transition is refused (a check before `OWNER_REVIEW`, not a prompt).
4. **Removal:** detaching a required department needs an explicit Owner action, recorded. Until then acceptance
   stays blocked, and the change applies from the next plan.

Every point is a code check with a test; none relies on a label or prompt.

## 6. 淸月 orchestration (no hard-coded order)
- The CEO context gets attached summaries plus a short list of verified library departments (id, functions,
  tools, data classes) for recommendation, and the required set.
- The CEO composes the stage sequence from dependencies (inputs/outputs), tools, permissions, cost (budget),
  risk and retrieved experience (scoped, cited with differences). No department sequence is coded.
- **Parallelism is deferred.** It needs `depends_on` in STAGE plus concurrent leases and Store writes; today's
  sequential pipeline is correct and observable.

## 7. Governance, permission and security
**Capability ≠ permission.** Attaching never grants spending, publication, contact, credentials or confidential
data. Declared security metadata maps onto existing gates only:

| Declaration | Gate |
|---|---|
| `external_actions: publish / contact / pay` | `governance` Owner-only actions (already enforced) |
| Network | `permissions` / `external_connection` approval (logical) plus provider web flags (enforced per call) |
| `data_classes` | Only `public` and `owner_files` (attached inputs) are supported now. Anything else makes `validate` refuse the spec until an enforcement exists |

Three layers, labelled honestly:
- **Logical checks:** department, tool and contract checks, governance.
- **Process containment:** provider CLI flags, Job Object, clean environment, Python audit hook (best effort).
- **OS isolation:** not implemented. It would need admin rights and Owner approval (firewall rules or a
  low-privilege account).

A denied operation must be shown to fail in a test (as in `tests/test_owner_run.py`), not only logged.

## 8. Verification model
Unchanged authority: deterministic checks plus an independent verifier. Department-specific rules arrive as
`acceptance_criteria` and contract checks:
- legal: citations or "unverifiable" marking;
- finance: arithmetic and reconciliation in code where possible (the Product Planning scenario math is the
  pattern);
- product: measurable criteria;
- engineering: runtime acceptance.

An imported or previously successful harness is never trusted without its own evaluation.

## 9. Harness lifecycle
```
trajectory → outcome → verification → Owner feedback → experience
  → repeated verified pattern (≥2 independent tasks) → candidate (new version, status candidate)
  → isolated evaluation (fixed tasks, budget, old vs candidate) → regression → independent verification
  → Owner promotion | rejection (recorded)
```
Accumulated experience alone is never improvement; one favourable comparison is exploratory.

## 10. UI and state implications
- **Library:** shows only verified departments; candidates and quarantined ones appear in the 오너 개발실 with
  status.
- **Goal composer / project row:** an attachment chip shows its mode (lock icon plus the word "필수"); a
  "淸月 추천" row offers to accept or ignore recommendations.
- **Project view:** "필수 부서 충족 여부" (required departments satisfied or not) with the blocking reason.
- **State:** attach event `mode`; plan `recommended_departments`; events `required_unmet` and
  `department_quarantined`. No new tables.

## 11. Risks and rejected approaches
- **Endangered features:** Existing tests encode "attached = available". Adding required checks to staffing and
  acceptance can block legacy projects, so `mode` absent means available.
- **Recommendation-driven scope creep:** the CEO recommending everything. Cap it at 3 recommendations, each with
  a reason; the Owner decides.
- **Rejected:**
  - permanent department agents;
  - a second orchestrator;
  - importing MCP connectors;
  - auto-promotion from a single success;
  - plugin runtime dependency;
  - parallel execution now;
  - RL, LoRA or world models.

## 12. Smallest safe implementation sequence (after Owner approval; each with tests and evidence)
1. **H1 registry fields:** `status` / `provenance` / `security` validation and library filtering; quarantine
   pauses new delegation. Legacy specs unchanged.
2. **H2 Required mode:** attach `mode`; the four enforcement points; UI lock chip; adversarial tests (a plan
   without the required department, a stale reuse, removal without the Owner).
3. **H3 Recommendation:** the CEO returns recommendations from the verified library; the UI accepts them as
   attachments; no auto-attach.
4. **H4 External candidate:** a converter for ONE skill (proposal: `legal-review`), with candidate status,
   2 fixed evaluation tasks, Owner promotion, and provenance and license notice.
5. **Deferred:** parallel stages, connectors, OS isolation (Owner approval), learned routing.
