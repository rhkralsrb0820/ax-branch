"""Owner governance. The CEO reads these values but has no path to change them:
no CEO response field maps here and the engine never writes this module.
Changing anything in this file is itself a governance change (Owner only)."""

MAX_ROUNDS = 6          # build attempts per budget; then the project PAUSES for the Owner. The bar never drops.
STRATEGY_EVERY = 2      # every N verification FAILs the CEO must review strategy (agent/provider/pipeline)
MAX_STAGES = 5
PROVIDERS = ('claude', 'codex')
PAID_EXPANSION_LOCKED = True   # no new paid API / plan / cloud / GPU / NIM
SATISFACTION_GATE = 90         # % average Owner satisfaction that permits an Upgrade *proposal* — never a purchase
CHECK_TIMEOUT = 120            # seconds a generated program may run during verification

# Actions only the Owner may authorize. The CEO's response schemas cannot express
# payments, publication, external contact or governance edits at all; the ones the
# engine can reach (tool installs, destructive close) stop and ask.
REQUIRES_OWNER = frozenset({
    'payment', 'paid_api', 'plan_upgrade', 'destructive', 'publish', 'external_contact',
    'sensitive_data', 'governance_change', 'install_tool', 'close_without_save',
})

SUMMARY = ('Governance (fixed; the CEO cannot change it): no payments, paid APIs, paid plans, '
           'publication, external contact or sensitive data movement. Missing tools and destructive '
           'closes need the Owner. Verification standards never drop after repeated failure.')


def upgrade_proposal_allowed(satisfactions):
    """True only when the Owner's average satisfaction meets the gate. Even then the
    CEO may only *propose*; purchase still needs explicit Owner approval."""
    return bool(satisfactions) and sum(satisfactions) / len(satisfactions) >= SATISFACTION_GATE
