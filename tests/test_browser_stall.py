"""B6: only the observed post-output browser shutdown hang is accepted; every other stall still fails."""
import unittest

from axbranch import runtime

DOM = '<html><head></head><body><p>3 items</p></body></html>\n'
HUNG = {'processes': [{'role': 'browser'}, {'role': 'crashpad-handler'}],
        'connections': [{'state': 'Listen'}, {'state': 'TimeWait'}]}


class ShutdownHangTests(unittest.TestCase):
    def test_complete_dom_and_only_the_main_process_left(self):
        self.assertTrue(runtime.shutdown_hang(DOM, HUNG))

    def test_everything_else_is_still_a_failure(self):
        self.assertFalse(runtime.shutdown_hang('<html><body><p>partial', HUNG))             # DOM not complete
        self.assertFalse(runtime.shutdown_hang('', HUNG))                                  # nothing printed
        renderer = {**HUNG, 'processes': HUNG['processes'] + [{'role': 'renderer'}]}
        self.assertFalse(runtime.shutdown_hang(DOM, renderer))                             # page still working
        busy = {**HUNG, 'connections': [{'state': 'Established'}]}
        self.assertFalse(runtime.shutdown_hang(DOM, busy))                                 # a request in flight
        self.assertFalse(runtime.shutdown_hang(DOM, {'error': 'snapshot failed: TimeoutExpired'}))
        self.assertFalse(runtime.shutdown_hang(DOM, None))
        self.assertFalse(runtime.shutdown_hang(DOM, {'processes': [], 'connections': []}))  # no evidence at all


if __name__ == '__main__':
    unittest.main()
