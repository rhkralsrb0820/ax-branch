"""The project page's one-line summary: current stage, stop reason and next action from recorded state."""
import unittest

from axbranch import web

PIPE = [{'title': '[리서치] 조사', 'engine': 'Claude', 'mark': '✓'}, {'title': '[제작] 앱', 'engine': 'Codex', 'mark': '●'}]


class NowTests(unittest.TestCase):
    def test_running_shows_stage_without_a_stop(self):
        n = web._now({'state': 'EXECUTING', 'pause_reason': None}, 'ACTIVE', PIPE)
        self.assertEqual((n['stage'], n['engine']), ('[제작] 앱', 'Codex'))
        self.assertNotIn('next', n)

    def test_stops_map_to_a_next_action(self):
        cases = {'RateLimited: claude 5h window': '사용량 한도', 'NEEDS_DECISION: the same failure (x) recurred': '같은 실패',
                 '4 builds failed verification.': '재작업 횟수', 'Owner stopped from the web': '멈춘 지점부터'}
        for reason, text in cases.items():
            n = web._now({'state': 'PAUSED', 'pause_reason': reason}, 'WAITING_FOR_OWNER', PIPE)
            self.assertIn(text, n['next'], reason)
        n = web._now({'state': 'OWNER_REVIEW', 'pause_reason': '', 'report': {}}, 'WAITING_FOR_OWNER', PIPE)
        self.assertEqual(n['stop'], 'VERIFIED')


if __name__ == '__main__':
    unittest.main()
