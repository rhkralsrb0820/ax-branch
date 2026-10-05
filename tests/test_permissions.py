"""Standing permissions retain Owner approval boundaries across projects."""
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch.permissions import RISKS, classify, evaluate, grant
from axbranch.state import Store


class PermissionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / 'axbranch.sqlite3'
        self.store = Store(self.path)
        self.pid = self.store.new_project('read public statistics')
        self.public = {'domain': 'DATA.EXAMPLE.ORG', 'purpose': 'Read official public statistics'}

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reuse_in_later_project_and_session(self):
        grant(self.store, self.pid, [self.public])
        self.store.close()
        self.store = Store(self.path)
        later = self.store.new_project('read updated statistics')
        entry = {'domain': 'data.example.org', 'purpose': 'Read updated public statistics'}
        self.assertNotEqual(later, self.pid)
        self.assertEqual(evaluate(self.store, [entry]), {'reused': [entry], 'ask': []})
        row = self.store.db.execute('SELECT * FROM standing_permissions').fetchone()
        self.assertEqual(row['project_id'], self.pid)
        self.assertGreater(row['granted'], 0)
        event = self.store.events(self.pid, ['permission_granted'])[0]
        self.assertEqual(event['detail'], {'domains': ['data.example.org'], 'risk': 'public_read'})

    def test_different_domains_ask(self):
        grant(self.store, self.pid, [self.public])
        entries = [{'domain': domain, 'purpose': 'Read public statistics'} for domain in
                   ('other.example.org', 'sub.data.example.org', 'data.example.org.evil', 'data.example.org ')]
        self.assertEqual(evaluate(self.store, entries), {'reused': [], 'ask': entries})

    def test_new_store_asks_and_empty_input_works(self):
        self.assertEqual(evaluate(self.store, []), {'reused': [], 'ask': []})
        self.assertEqual(evaluate(self.store, [self.public]), {'reused': [], 'ask': [self.public]})

    def test_escalated_purpose_asks_on_approved_domain(self):
        grant(self.store, self.pid, [self.public])
        for purpose, risk in (('Use an API key', 'api_key'), ('LOGIN to read statistics', 'login')):
            with self.subTest(purpose=purpose):
                entry = {**self.public, 'purpose': purpose}
                self.assertEqual(classify(entry), risk)
                self.assertEqual(evaluate(self.store, [entry]), {'reused': [], 'ask': [entry]})

    def test_keyword_escalation_in_domain_and_purpose(self):
        examples = {
            'api_key': ('key', 'token', 'apikey', 'API_KEY'),
            'login': ('login', 'account', 'oauth', 'password'),
            'paid': ('paid', 'subscription', 'billing', 'price plan'),
            'personal_data': ('email', 'personal', 'user data', 'upload'),
            'posting': ('post', 'publish', 'send', 'tweet', 'trade', 'order'),
        }
        for risk, words in examples.items():
            for word in words:
                for field in ('domain', 'purpose'):
                    with self.subTest(risk=risk, word=word, field=field):
                        self.assertEqual(classify({**self.public, field: word.upper()}), risk)
        self.assertEqual(classify({**self.public, 'purpose': 'post using login and API key'}), 'posting')

    def test_declared_risk_never_downgraded_or_reused(self):
        grant(self.store, self.pid, [self.public])
        for risk in RISKS[1:]:
            with self.subTest(risk=risk):
                entry = {**self.public, 'risk': risk}
                self.assertEqual(classify(entry), risk)
                self.assertEqual(classify({**entry, 'purpose': 'key'}), risk)
                self.assertEqual(evaluate(self.store, [entry]), {'reused': [], 'ask': [entry]})
        self.assertEqual(classify({**self.public, 'risk': 'api_key', 'purpose': 'login'}), 'login')

    def test_grant_never_stores_higher_risk(self):
        entries = [{**self.public, 'risk': risk} for risk in RISKS[1:]]
        entries += [{'domain': 'login.example.org', 'purpose': 'Read statistics'},
                    {**self.public, 'purpose': 'Use a token'}]
        grant(self.store, self.pid, entries)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM standing_permissions').fetchone()[0], 0)
        self.assertEqual(self.store.events(self.pid, ['permission_granted'])[0]['detail']['domains'], [])

    def test_mixed_entries_preserve_order_and_are_not_modified(self):
        grant(self.store, self.pid, [self.public, self.public])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM standing_permissions').fetchone()[0], 1)
        risky = {**self.public, 'purpose': 'upload'}
        other = {**self.public, 'domain': 'other.example.org'}
        entries = [risky, self.public, other, dict(self.public)]
        before = [dict(entry) for entry in entries]
        result = evaluate(self.store, entries)
        self.assertEqual(result, {'reused': [self.public, self.public], 'ask': [risky, other]})
        self.assertIs(result['reused'][0], self.public)
        self.assertEqual(entries, before)

    def test_unknown_risks_and_empty_domains_are_not_reusable(self):
        grant(self.store, self.pid, [self.public])
        entries = [{**self.public, 'risk': risk} for risk in ('unknown', '', None)]
        entries += [{**self.public, 'domain': domain} for domain in ('', ' ')]
        grant(self.store, self.pid, entries)
        self.assertEqual(evaluate(self.store, entries), {'reused': [], 'ask': entries})
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM standing_permissions').fetchone()[0], 1)

    def test_risk_ordering_and_default(self):
        self.assertEqual(RISKS, ('public_read', 'api_key', 'login', 'paid', 'personal_data', 'posting'))
        self.assertEqual(classify(self.public), 'public_read')


if __name__ == '__main__':
    unittest.main()
