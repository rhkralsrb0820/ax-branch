"""Phase B: truthful verifier independence and sanitized provider failure records."""
import json
import unittest

from axbranch import engine as E, providers
from tests import test_engine as TE
from tests.test_engine import GOOD, Script

RAW = 'codex: You have hit your usage limit. Echo of the private prompt: SECRET-PROMPT-TEXT'


class FallbackScript(Script):
    """The verifier falls back to the producer's provider (claude) after a recorded codex usage-limit refusal."""
    def __call__(self, prompt, schema, *args, **kw):
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        if schema is E.VERDICT:
            return result, 'claude', [RAW]
        return result, used, notes


class VerificationPolicyTests(unittest.TestCase):
    setUp, tearDown, engine = TE.EngineTests.setUp, TE.EngineTests.tearDown, TE.EngineTests.engine

    def test_failure_categories_keep_no_raw_output(self):
        self.assertEqual(providers.failure_category(RAW),
                         {'provider': 'codex', 'category': 'usage_limit', 'evidence': 'usage limit'})
        self.assertEqual(providers.failure_category('codex: CLI not installed')['category'], 'cli_not_installed')
        self.assertEqual(providers.failure_category('claude: Not logged in · Please run /login')['category'], 'auth')
        self.assertEqual(providers.failure_category('codex: exit 3, something odd')['category'], 'unknown')

    def test_required_cross_provider_stops_acceptance_on_fallback(self):
        pid = self.store.new_project('make an add tool')
        self.store.event(pid, 'verification_policy', cross_provider='required', by='owner-cli')
        p = self.engine(FallbackScript([GOOD], ['PASS'])).run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('Independent verification unavailable', p['pause_reason'])
        self.assertIn('usage_limit', p['pause_reason'])
        self.assertEqual(self.store.verifications(pid), [])                # the same-provider verdict was not accepted
        self.assertTrue(self.store.events(pid, {'independent_verification_unavailable'}))
        self.assertNotIn('SECRET-PROMPT-TEXT', json.dumps([e['detail'] for e in self.store.events(pid)]))

    def test_allowed_fallback_is_labelled_with_the_observed_cause(self):
        pid = self.store.new_project('make an add tool')
        p = self.engine(FallbackScript([GOOD], ['PASS'])).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p.get('pause_reason'))
        decision = next(e['detail'] for e in self.store.events(pid, {'decision'})
                        if e['detail'].get('what') == "verification ran on the producer's engine")
        self.assertEqual(decision['level'], 'SAME_PROVIDER_ROLE_SEPARATED')
        self.assertEqual(decision['failures'][0]['category'], 'usage_limit')
        self.assertIn('usage_limit', decision['why'])
        self.assertNotIn('SECRET-PROMPT-TEXT', json.dumps([e['detail'] for e in self.store.events(pid)]))
        self.assertEqual(self.store.verifications(pid)[-1]['checks']['verifier_provenance']['verifier'], 'claude')


if __name__ == '__main__':
    unittest.main()
