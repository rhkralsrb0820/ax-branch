"""Standing Owner permissions: only public read access can carry across projects."""
import time


RISKS = ('public_read', 'api_key', 'login', 'paid', 'personal_data', 'posting')
_KEYWORDS = (
    ('api_key', ('key', 'token', 'apikey')),
    ('login', ('login', 'account', 'oauth', 'password')),
    ('paid', ('paid', 'subscription', 'billing', 'price plan')),
    ('personal_data', ('email', 'personal', 'user data', 'upload')),
    ('posting', ('post', 'publish', 'send', 'tweet', 'trade', 'order')),
)


def classify(entry):
    """Escalate declared risk; unknown labels fail closed at the highest risk."""
    risk = entry.get('risk', 'public_read')
    if risk not in RISKS:
        return RISKS[-1]
    text = (entry.get('domain', '') + ' ' + entry.get('purpose', '')).lower()
    # Substring matches deliberately include compounds/plurals and ignore negation.
    for candidate, words in _KEYWORDS:
        if any(word in text for word in words) and RISKS.index(candidate) > RISKS.index(risk):
            risk = candidate
    return risk


def _ensure_table(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS standing_permissions('
                     'domain TEXT, risk TEXT, granted REAL, project_id TEXT, PRIMARY KEY(domain, risk))')


def grant(store, pid, entries):
    """Record reusable scope from entries already approved by the Owner."""
    domains = list(dict.fromkeys(entry['domain'].lower() for entry in entries
                                if classify(entry) == 'public_read' and entry.get('domain', '').strip()))
    with store.tx():
        _ensure_table(store)
        for domain in domains:
            store.db.execute('INSERT OR REPLACE INTO standing_permissions(domain,risk,granted,project_id) '
                             'VALUES(?,?,?,?)', (domain, 'public_read', time.time(), pid))
        store.event(pid, 'permission_granted', domains=domains, risk='public_read')


def evaluate(store, entries):
    """Partition original entries, preserving order; only exact domains can reuse."""
    _ensure_table(store)
    domains = {row['domain'] for row in store.db.execute(
        "SELECT domain FROM standing_permissions WHERE risk='public_read'")}
    result = {'reused': [], 'ask': []}
    for entry in entries:
        domain = entry.get('domain', '').lower()
        reused = classify(entry) == 'public_read' and bool(domain.strip()) and domain in domains
        result['reused' if reused else 'ask'].append(entry)
    return result
