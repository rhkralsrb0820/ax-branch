# Capability lifecycle, 0.1.37

AX Branch remains the owner-governed orchestration layer: the CEO selects a pipeline, temporary specialists
produce artifacts, deterministic checks and a separate verifier judge them, and the CEO can change the
pipeline after failure. Claude Code and Codex are interchangeable execution providers for these roles.

The CEO now receives the actual capability inventory and harness time limits on every audited decision,
including planning, diagnosis, probe review, strategy and executive acceptance. Each production stage declares
`capabilities`; old plans infer their existing reasoning, code-generation and web flags. Unsupported names are
retained and refused before production; they are never silently converted into a promise to execute a tool.
Public web research selects the existing restricted adapter. Delivered-program network access still goes
through the separate Owner approval gate. The fixed governance module is unchanged.

The registry in `capabilities.py` is intentionally small. ML/LLM analysis can use reasoning, public research and
code generation. Actual training, GPU execution, clean Windows environments and desktop interaction need real
new adapters, enforcement, evidence and appropriate authorization before becoming available. Merely finding
an installed program is insufficient.

## One operation, one grant

Before a model call, the engine validates its requested capabilities and records `capability_attached`.
The existing provider adapter enforces shell/file-write/MCP restrictions and the selected web flag. A successful
`call` links the grant to the provider that actually ran, including quota failover. `finally` records
`capability_revoked` on success, failure or cancellation. No grant token can be reused by a later stage.

Verification selects only the needed harnesses from the declared runtime mode/probes. Generated-code processes
remain contained and cleaned up. These leases are process-local adapter selections, not OS privilege changes.
If a worker dies without its finally block, the next worker closes the orphan audit entry while holding the
project lock; no actual authority survives for it to reuse. For forced worker exits, existing provider process
Job Object behavior remains the process cleanup mechanism.

The attempt ledger, durable strategy review, independent verifier routing and preserved acceptance checks remain
the existing mechanisms for true replanning. A changed pipeline is staffed and executed rather than treated
as a textual recommendation. The demo records plan_version 2 after two failures, then a successful third build.

## Reproduce

Use Python 3.11+ and the existing sibling `cheongwol/ceo` dependency, as in README. From a detached development
copy, set PYTHONPATH to that existing dependency. No additional package installation is required.

```
python -X utf8 -m unittest tests.test_capabilities tests.test_resources tests.test_sandbox -v
python -X utf8 -m unittest discover -s tests -t . -v
python -X utf8 -m axbranch.demo --root <isolated-demo-folder>
python -X utf8 -m axbranch.demo --live --root <different-isolated-demo-folder>
```

The default demo scripts model decisions and injected faults but executes the real engine, SQLite commits,
generated Python self-tests and runtime launches. It verifies FAIL/FAIL/PASS with a changed pipeline, unsupported
ML training refused before building, and interruption recovery with a fresh database session. All grants must
have revocations and artifact consistency must pass. evidence.json identifies scripted vs real-provider mode.
The live smoke uses a tiny arithmetic CLI goal and existing subscriptions. It can pause honestly on quota or
provider problems; a pause is never reported as successful model execution.

## Limits

- The planner may omit a needed capability. The gate validates declared needs and known harness requirements;
  it is not a complete semantic classifier of arbitrary goals.
- No new authority, paid service, installation or OS account/firewall change is introduced.
- Generated code uses the current OS account. No filesystem/network isolation guarantee (D-SEC-1).
- DOM-based browser observations can be forged by page code; they are not security proof.
- The active large production project has product and evidence gaps beyond this change. Existing evidence
  and approval boundaries remain intact; this release does not claim that project is resolved.
