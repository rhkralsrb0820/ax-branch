"""Project-wide usage accounting and conservative completion reservations.

Reservations are estimates from observed calls, never provider generation caps.
No helper here launches a model or grants execution authority.
"""
import math

from . import governance as gov
from .state import Rejected


BUDGET_RESERVE = {'ceo': 14906, 'worker': 15636, 'verify': 20080}


TIME_BASES = ('wall_clock', 'call_seconds')


def configure(store, pid, *, max_calls=12, max_seconds=1200, max_prompt_chars=32000,
              max_reported_tokens=60000, local_documents=False, profile=None, time_basis='wall_clock'):
    """Persist one budget before execution; callers can include it in their creation transaction."""
    if store.events(pid, {'execution_budget', 'call_start', 'call', 'call_failed'}):
        raise Rejected('Execution budget must be fixed once before execution.')
    values = dict(max_calls=max_calls, max_seconds=max_seconds, max_prompt_chars=max_prompt_chars,
                  max_reported_tokens=max_reported_tokens)
    if any(type(value) is not int or value <= 0 for value in values.values()):
        raise Rejected('Execution budget values must be positive integers.')
    if profile is not None and (not isinstance(profile, str) or not profile.strip()):
        raise Rejected('Execution budget profile must be a nonempty name.')
    if time_basis not in TIME_BASES:
        raise Rejected(f'Execution budget time basis must be one of {TIME_BASES}.')
    return store.event(pid, 'execution_budget', **values, local_documents=bool(local_documents),
                       **({'profile': profile} if profile is not None else {}), time_basis=time_basis,
                       token_enforcement='completion reserve before each turn; reported usage after each turn; '
                                         'not a provider hard generation cap',
                       provider_attempt_upper_bound_per_turn=len(gov.PROVIDERS))


def usage_tokens(detail):
    """Count reported totals without counting Codex cache/reasoning subsets twice."""
    usage = detail.get('tokens')
    if not isinstance(usage, dict):
        return None
    keys = ['input_tokens', 'output_tokens']
    if str(usage.get('source', '')).lower().startswith('claude'):
        keys += ['cache_creation_input_tokens', 'cache_read_input_tokens']
    total = 0
    for key in keys:
        value = usage.get(key, 0 if key.startswith('cache_') else None)
        if value is None and key.startswith('cache_'):
            value = 0  # older CLI records omit cache fields when there was no cache usage
        if (not isinstance(value, (int, float)) or isinstance(value, bool) or
                not math.isfinite(value) or value < 0):
            return None
        total += value
    return total


def ledger_usage(events):
    """Return a cumulative snapshot, including failed/interrupted turns.

    New terminal events pair with call_start_id. Old sequential events pair in
    order; standalone legacy call records remain countable. An unmatched start
    or malformed/unknown terminal usage never becomes a free turn on resume.
    """
    pending, closed_ids = [], set()
    total = unknown = started = completed = failed = unmatched = legacy_terminal = 0
    for event in events:
        kind, detail = event.get('kind'), event.get('detail') or {}
        if kind == 'call_start':
            started += 1
            pending.append(event.get('id'))
            continue
        if kind not in ('call', 'call_failed'):
            continue
        if kind == 'call':
            completed += 1
        else:
            failed += 1
        start_id = detail.get('call_start_id')
        if start_id is not None:
            if start_id in pending and start_id not in closed_ids:
                pending.remove(start_id)
                closed_ids.add(start_id)
            else:
                unmatched += 1  # corrupted or duplicated pairing; do not silently trust it
        elif pending:
            pending.pop(0)
        else:
            legacy_terminal += 1
        amount = usage_tokens(detail)
        if kind == 'call_failed' and detail.get('usage_complete') is not True:
            # A failed turn may report one attempt while another attempt consumed
            # unknown tokens. A number alone does not establish complete accounting.
            amount = None
        if amount is None:
            unknown += 1
        else:
            total += amount
    interrupted = len(pending)
    return {'reported_tokens': None if unknown or interrupted or unmatched else total,
            'known_tokens': total, 'unknown_calls': unknown + interrupted + unmatched,
            'interrupted_calls': interrupted, 'unmatched_calls': unmatched,
            'started_calls': started + legacy_terminal,
            'completed_calls': completed, 'failed_calls': failed}


def seconds_left(events, budget, at, now):
    """Seconds this budget still allows. wall_clock (experiments): since the budget was fixed. call_seconds (Owner
    task profiles): provider time actually spent by recorded turns, so a revision days later is not refused merely
    because the calendar moved on."""
    if budget.get('time_basis') == 'call_seconds':
        spent = sum(float((e.get('detail') or {}).get('seconds') or 0) for e in events
                    if e.get('kind') in ('call', 'call_failed'))
        return budget['max_seconds'] - spent
    return at + budget['max_seconds'] - now


def role_for(who):
    return 'ceo' if who == 'CEO' else 'verify' if who == 'Verification' else 'worker'


def call_reserve(events, role):
    """A larger observed call of the same role raises all that role's reservations."""
    if role not in BUDGET_RESERVE:
        raise ValueError(f'Unknown budget role: {role}')
    seen = [usage_tokens(event.get('detail') or {}) for event in events
            if event.get('kind') in ('call', 'call_failed')
            and role_for((event.get('detail') or {}).get('who')) == role]
    return max([BUDGET_RESERVE[role], *[value for value in seen if value is not None]])


def completion_reserve(events, phase, pending_workers=0):
    """Reserve this call and the first-pass path to executive acceptance.

    production: pending_workers counts producers AFTER the current call.
    planning/decision: it counts TOTAL producers after the decision, at least 1
    while no plan is known. verification is the final artifact verifier, not a
    proposal-equivalence check; the latter uses verification_repair.
    No future retry is promised to fit. Recompute after every recorded call.
    """
    if type(pending_workers) is not int or pending_workers < 0:
        raise ValueError('pending_workers must be a nonnegative integer')
    roles = {'planning': 'ceo', 'decision': 'ceo', 'production': 'worker',
             'verification': 'verify', 'verification_repair': 'verify', 'acceptance': 'ceo', 'evaluation': 'verify'}
    if phase not in roles:
        raise ValueError(f'Unknown budget phase: {phase}')
    role = roles[phase]
    future = []
    if phase in ('planning', 'decision', 'production'):
        count = pending_workers if phase == 'production' else max(1, pending_workers)
        future.extend(('production', 'worker') for _ in range(count))
        future.append(('verification', 'verify'))
    if phase == 'verification_repair':
        future.append(('verification', 'verify'))
    if phase not in ('acceptance', 'evaluation'):   # an independent evaluation is one call with its own budget
        future.append(('acceptance', 'ceo'))
    current = call_reserve(events, role)
    downstream = [{'phase': name, 'role': next_role, 'tokens': call_reserve(events, next_role)}
                  for name, next_role in future]
    return {'phase': phase, 'current_role': role, 'current_tokens': current, 'downstream': downstream,
            'reserve_tokens': current + sum(step['tokens'] for step in downstream),
            'reserve_calls': 1 + len(downstream), 'estimate_kind': 'observed_role_maximum_not_hard_cap'}


def assess_budget(events, budget, phase, pending_workers=0):
    """Pure token/call feasibility; elapsed-time/prompt limits remain the engine's checks."""
    ledger = ledger_usage(events)
    reserve = completion_reserve(events, phase, pending_workers)
    remaining = (budget['max_reported_tokens'] - ledger['reported_tokens']
                 if ledger['reported_tokens'] is not None else None)
    calls_left = budget['max_calls'] - ledger['started_calls']
    reason = ('unknown_usage' if remaining is None else
              'completion_tokens' if remaining < reserve['reserve_tokens'] else
              'completion_calls' if calls_left < reserve['reserve_calls'] else None)
    return {**ledger, **reserve, 'remaining': remaining, 'remaining_calls': calls_left,
            'allowed': reason is None, 'reason': reason}
