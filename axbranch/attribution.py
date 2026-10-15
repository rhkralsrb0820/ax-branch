"""Outcome Attribution (observational): what CAUSED an observed outcome, kept apart from the outcome itself.

Deterministic evidence decides VERIFIED causes; model judgments (the Verification agent's finding kinds) can only add
ESTIMATED candidates; the CEO's self-assessment is never a source. Without a VERIFIED cause the PRIMARY is UNKNOWN.
Nothing here feeds routing, verdicts, budget, criteria or governance. Records are append-only: a later fact (a
validated harness repair, an engine invariant breach) adds a new attribution that supersedes the earlier one."""
import re

from . import runtime

RULES_VERSION = 1
CLASSES = ('CEO_DECISION', 'PRODUCT', 'AGENT', 'HARNESS', 'ENGINE', 'PROVIDER', 'INFRA', 'EVIDENCE', 'GOVERNANCE',
           'OWNER_CONSTRAINT', 'EXTERNAL_DEPENDENCY', 'UNKNOWN')
# PRIMARY among VERIFIED causes: a verified product defect is what the gate acts on; then the blocking layers.
_PRIMARY_ORDER = ('PRODUCT', 'GOVERNANCE', 'OWNER_CONSTRAINT', 'PROVIDER', 'INFRA', 'ENGINE', 'AGENT', 'HARNESS',
                  'EXTERNAL_DEPENDENCY', 'EVIDENCE', 'CEO_DECISION')


def cause(cls, status, rule, evidence, role=None, **responsible):
    assert cls in CLASSES and status in ('VERIFIED', 'ESTIMATED', 'UNKNOWN')
    return {'class': cls, 'status': status, 'role': role, 'source': f'{rule}@{RULES_VERSION}' if rule.startswith('rule:')
            else rule, 'evidence': [str(e)[:200] for e in evidence][:6],
            **{k: v for k, v in responsible.items() if v is not None}}


def finalize(causes):
    """Roles: RULED_OUT stays; PRIMARY = the highest VERIFIED cause, else an explicit UNKNOWN; the rest CONTRIBUTING."""
    ruled_out = [c for c in causes if c['role'] == 'RULED_OUT']
    active = [c for c in causes if c['role'] != 'RULED_OUT']
    verified = sorted((c for c in active if c['status'] == 'VERIFIED'), key=lambda c: _PRIMARY_ORDER.index(c['class']))
    if verified:
        primary = verified[0]
    else:
        primary = cause('UNKNOWN', 'UNKNOWN', 'rule:no-verified-cause',
                        ['no deterministic evidence decides the cause; candidates are ESTIMATED only'])
        active = [primary] + active
    for c in active:
        c['role'] = 'PRIMARY' if c is primary else 'CONTRIBUTING'
    return {'primary': primary['class'], 'primary_status': primary['status'], 'causes': active + ruled_out}


def _responsible(store, pid, artifact_id):
    art = next((a for a in store.artifacts(pid) if a['id'] == artifact_id), None)
    agent = art and next((a for a in store.agents(pid, active_only=False) if a['id'] == art['agent_id']), None)
    # The provider that actually ran the final stage (failover may differ from the configured one), as engine._actual_producer.
    row = art and store.db.execute('SELECT provider FROM stage_outputs WHERE project_id=? AND iteration=? '
                                   'ORDER BY stage DESC LIMIT 1', (pid, art['iteration'])).fetchone()
    return {'agent_role': agent and agent['role'], 'provider': row['provider'] if row else agent and agent['provider']}


_ANY_STATUS = re.compile(r'status \d+, expected (-\d+|0)\b')


def _step_class(st):
    """runtime.classify_step, plus the canonical-probe rule: expect_status <= 0 means ANY status, so a step that
    failed only because a status differed from such an expectation shows an invalid check (Test #3), not the product."""
    cls = runtime.classify_step(st) or 'ambiguous'
    problems = st.get('problems', [])
    if cls == 'ambiguous' and problems and all(_ANY_STATUS.search(p) for p in problems):
        return 'harness'
    return cls


def verification_causes(store, pid, v):
    """Causes of one FAIL verification, from its stored evidence."""
    from .engine import product_failure                # lazy: engine imports state, state imports this module
    if v['verdict'] != 'FAIL':
        return None
    if v['provider'] == 'engine':                      # the build itself was rejected: no artifact to blame
        # The rejection recorded with this FAIL (same transaction), never a later one (history replay).
        rejected = [e['detail'] for e in store.events(pid, {'build_rejected'}) if e['at'] <= v['created']]
        last = rejected[-1] if rejected else {}
        # A missing deliverable proves only that there is no artifact. Why is not decided by the record: transport or
        # timeout limits (P-bbad3c v15-v20, full-file regeneration of a 115-164 KB file), a deliberate "no change"
        # (P-cfa1d6 v6) or the agent. So the agent is a candidate, never VERIFIED.
        return finalize([
            cause('AGENT', 'ESTIMATED', 'rule:no-deliverable', [f"build rejected: {last.get('reason', v['checks'].get('output', ''))}"],
                  agent_role=last.get('agent'), provider=last.get('provider')),
            cause('PRODUCT', 'VERIFIED', 'rule:no-deliverable', ['no artifact was produced'], role='RULED_OUT')])
    checks = v['checks'] or {}
    failed = [st for st in (checks.get('runtime') or {}).get('steps', []) if not st.get('ok')]
    by_class = {}
    for st in failed:
        by_class.setdefault(_step_class(st), []).append(st)
    det_product = product_failure({**v, 'result': {'findings': [], 'criteria': []}})   # self-test / product steps only
    causes = []
    if det_product:
        steps = [st['name'] for st in by_class.get('product', [])] or ['self-test failed']
        causes.append(cause('PRODUCT', 'VERIFIED', 'rule:product-evidence', steps,
                            artifact=v['artifact_id'], **_responsible(store, pid, v['artifact_id'])))
    if by_class.get('harness'):
        causes.append(cause('HARNESS', 'VERIFIED', 'rule:probe-misconfigured',
                            [f"{st['name']}: {'; '.join(st.get('problems', []))}" for st in by_class['harness']]))
    if by_class.get('infra'):
        causes.append(cause('INFRA', 'VERIFIED', 'rule:runtime-infra',
                            [f"{st['name']}: {'; '.join(st.get('problems', []))}" for st in by_class['infra']]))
    if not det_product and failed and set(by_class) <= {'harness', 'infra'}:
        causes.append(cause('PRODUCT', 'VERIFIED', 'rule:non-product-only', ['every failed step is harness/infra'],
                            role='RULED_OUT'))
    if not det_product:
        # Model judgment (independent verifier) may only nominate ESTIMATED candidates.
        n = len((store.project(pid)['plan'] or {}).get('acceptance_criteria') or []) or None
        kinds = {f.get('kind', 'product') for f in (v['result'] or {}).get('findings', [])
                 if f.get('severity') in ('critical', 'major') and not str(f.get('issue', '')).startswith('Gate failed: ')
                 and 0 <= f.get('criterion', 0) < (n or 10 ** 6)}
        unmet = [c for c in (v['result'] or {}).get('criteria', []) if not c.get('met')]
        if unmet and not failed:
            kinds.add('product')
        for kind in sorted(kinds & {'product', 'harness', 'infra'}):
            if not any(c['class'] == kind.upper() for c in causes):
                causes.append(cause(kind.upper(), 'ESTIMATED', 'model:Verification', ['verifier finding kind / unmet criterion']))
    if by_class.get('ambiguous') and not any(c['status'] == 'VERIFIED' and c['role'] != 'RULED_OUT' for c in causes):
        causes.append(cause('HARNESS', 'ESTIMATED', 'rule:ambiguous-mismatch',
                            [st['name'] for st in by_class['ambiguous']]))
    return finalize(causes)


_PAUSE_RULES = (     # (pattern on the pause reason, class, status, rule, provider_state)
    (r'^Owner (stopped|chose PAUSE)|오너가 중단', 'OWNER_CONSTRAINT', 'VERIFIED', 'rule:owner-stop', None),
    (r'^Owner approval needed', 'GOVERNANCE', 'VERIFIED', 'rule:approval-gate', None),
    (r'builds failed verification\. The standard is not lowered', 'GOVERNANCE', 'VERIFIED', 'rule:budget', None),
    (r'^Owner action needed \(install_tool\)', 'INFRA', 'VERIFIED', 'rule:missing-tool', None),
    (r'메모리가 .*부족|low memory', 'INFRA', 'VERIFIED', 'rule:low-memory', None),
    (r'^INFRA_FAILED', 'INFRA', 'VERIFIED', 'rule:infra-only-fail', None),
    (r'^Internal error', 'ENGINE', 'VERIFIED', 'rule:internal-error', None),
    (r'RateLimited|usage limit|quota|사용 한도|rate limit', 'PROVIDER', 'VERIFIED', 'rule:provider-refusal', 'from-text'),
    (r'시간 초과|timed out|timeout', 'PROVIDER', 'ESTIMATED', 'rule:timeout', 'UNKNOWN'),
    (r'^Rejected: (Claude Code|Codex)', 'PROVIDER', 'ESTIMATED', 'rule:provider-reply', 'UNKNOWN'),
)


def provider_state(text):
    t = text.lower()
    if 'auth' in t or 'login' in t or 'credential' in t:
        return 'AUTH_FAILURE'
    if 'usage limit' in t or 'quota' in t or '사용 한도' in t:
        return 'QUOTA_EXHAUSTED'
    if 'rate limit' in t:
        return 'RATE_LIMITED'
    if 'unavailable' in t or 'overloaded' in t:
        return 'TEMP_UNAVAILABLE'
    return 'UNKNOWN'


def pause_causes(store, pid, reason):
    """Causes of a pause, from its recorded reason (and, for HARNESS_BLOCKED, the attribution of the FAIL behind it)."""
    reason = str(reason or '')
    if reason.startswith('HARNESS_BLOCKED'):
        fails = [a for a in store.attributions(pid) if str(a['detail'].get('subject', '')).startswith('V-')]
        latest = fails[-1] if fails else None       # the FAIL behind the block
        verified = bool(latest and latest['detail']['primary'] == 'HARNESS' and latest['detail']['primary_status'] == 'VERIFIED')
        return finalize([cause('HARNESS', 'VERIFIED' if verified else 'ESTIMATED', 'rule:harness-blocked', [reason]),
                         cause('PRODUCT', 'VERIFIED', 'rule:harness-blocked', ['no product failure recorded'],
                               role='RULED_OUT')])
    for pattern, cls, status, rule, state in _PAUSE_RULES:
        if re.search(pattern, reason, flags=re.I):
            extra = {'provider_state': provider_state(reason) if state == 'from-text' else state} if state else {}
            return finalize([cause(cls, status, rule, [reason], **extra)])
    return finalize([])                                 # NEEDS_DECISION, recovery checkpoints...: UNKNOWN, honestly


def engine_breach(store, pid, artifact):
    """ENGINE invariant: a new version built right after a FAIL that showed NO product failure, with no Owner
    feedback or CEO product order in between, means AX Branch rebuilt for a non-product reason. Returns the
    FAIL verification it applies to, else None."""
    from .engine import product_failure
    before = [v for v in store.verifications(pid) if v['created'] < artifact['created']]
    if not before or before[-1]['verdict'] != 'FAIL' or before[-1]['provider'] == 'engine' or product_failure(before[-1]):
        return None
    fail = before[-1]
    if any(fail['created'] < f['created'] < artifact['created'] for f in store.feedback(pid)
           if f['verdict'] in ('problem', 'request')):
        return None
    if any(fail['created'] < e['at'] < artifact['created']
           for e in store.events(pid, {'decision'}) if e['detail'].get('what') == 'executive rework'):
        return None
    return fail


def history(store, pid):
    """Read-only replay of v1 rules over a project's stored history (no writes): per FAIL its causes, plus ENGINE
    invariant breaches and validated harness repairs as they would supersede."""
    out = {}
    for v in store.verifications(pid):
        if v['verdict'] == 'FAIL':
            out[v['id']] = verification_causes(store, pid, v)
    for a in store.artifacts(pid):
        rebuild = rebuild_attribution(store, pid, a)
        if rebuild:
            out[a['id']] = rebuild
    for v in store.verifications(pid):
        if v['verdict'] == 'PASS':
            for fid in repaired_fails(store, pid, v):
                out[fid] = harness_validated(fid, v)
    return out


def rebuild_causes(fail, artifact):
    """Causes of a rebuild (the artifact_built outcome) that followed a non-product FAIL: the FAIL keeps its own
    cause; the unnecessary rebuild is the engine's."""
    return finalize([cause('ENGINE', 'VERIFIED', 'rule:rebuild-after-non-product-fail',
                           [f"v{artifact['iteration']} built after FAIL {fail['id']} showed no product failure"],
                           artifact=artifact['id'])])


def rebuild_attribution(store, pid, artifact):
    fail = engine_breach(store, pid, artifact)
    return fail and rebuild_causes(fail, artifact)


def repaired_fails(store, pid, passed):
    """FAILs of the same artifact that a validated harness repair (probe review HARNESS_REPAIR, accepted) explains,
    now that the same artifact PASSED after it. A repair explains only the FAIL its review was opened for, and never
    one with an independently VERIFIED non-harness cause (e.g. INFRA: a missing browser is not a probe error)."""
    from .engine import product_failure
    pending = {e['id']: e['detail'].get('verification') for e in store.events(pid, {'probe_review_pending'})}
    explained = {pending.get(e['detail'].get('pending')) for e in store.events(pid, {'probe_review'})
                 if e['detail'].get('artifact') == passed['artifact_id'] and e['detail'].get('repaired')
                 and e['at'] <= passed['created']}
    out = []
    for v in store.verifications(pid):
        if v['id'] in explained and v['artifact_id'] == passed['artifact_id'] and v['verdict'] == 'FAIL' \
                and v['created'] < passed['created'] and not product_failure(v):
            own = verification_causes(store, pid, v)['causes']
            if not any(c['status'] == 'VERIFIED' and c['role'] != 'RULED_OUT' and c['class'] != 'HARNESS' for c in own):
                out.append(v['id'])
    return out


def harness_validated(fail_id, passed):
    return finalize([cause('HARNESS', 'VERIFIED', 'rule:validated-harness-repair',
                           [f'same artifact PASSED ({passed["id"]}) after an accepted harness repair of {fail_id}']),
                     cause('PRODUCT', 'VERIFIED', 'rule:validated-harness-repair',
                           ['unchanged artifact passed once the check was repaired'], role='RULED_OUT')])
