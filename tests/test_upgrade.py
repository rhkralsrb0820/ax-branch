"""Upgrade Proposal: locked below the satisfaction gate; above it, a draft only — never a purchase."""
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

    def test_locked_without_enough_satisfaction(self):
        self.assertEqual(upgrade.propose(self.store, self.tmp / 'ws', self.llm)[0], 'locked')   # no data at all
        self.closed(95); self.closed(80)
        status, facts = upgrade.propose(self.store, self.tmp / 'ws', self.llm)
        self.assertEqual((status, facts['average_satisfaction']), ('locked', 87.5))
        self.assertEqual(self.calls, [])                       # the CEO is not even asked

    def test_draft_only_above_gate(self):
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
