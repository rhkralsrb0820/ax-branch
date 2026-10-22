"""Upgrade Proposal: always a draft only — never a purchase; past satisfaction does not block proposing."""
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import upgrade
from axbranch.state import Store


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.calls = []

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def llm(self, prompt, schema, prefer='claude'):
        self.calls.append(prompt)
        return {k: (['keep subscriptions'] if k == 'alternatives' else f'{k} text') for k in schema['required']}, 'claude', []

    def closed(self, satisfaction):
        pid = self.store.new_project('g')
        self.store.update(pid, state='CLOSED', satisfaction=satisfaction)

    def test_low_or_missing_satisfaction_does_not_block_a_proposal(self):
        # Owner decision 2026-10-22: proposing is allowed; the former 90% gate blocked even drafts.
        status, path = upgrade.propose(self.store, self.tmp / 'ws', self.llm)          # no closed project at all
        self.assertEqual(status, 'drafted')
        self.assertIn('n/a (no closed projects)', path.read_text(encoding='utf-8'))
        self.closed(40)
        status, path = upgrade.propose(self.store, self.tmp / 'ws', self.llm)
        self.assertIn('40% over 1 closed projects', path.read_text(encoding='utf-8'))
        self.assertEqual(len(self.calls), 2)

    def test_draft_only_never_a_purchase(self):
        self.closed(95); self.closed(90)
        status, path = upgrade.propose(self.store, self.tmp / 'ws', self.llm)
        self.assertEqual(status, 'drafted')
        text = path.read_text(encoding='utf-8')
        self.assertIn('DRAFT, NOT APPROVED', text)
        self.assertIn('Nothing has been purchased', text)
        for section in ('Problem', 'Estimated Cost', 'Roi', 'Security Impact', 'Alternatives', 'Vendor Lock In'):
            self.assertIn(f'## {section}', text)


if __name__ == '__main__':
    unittest.main()
