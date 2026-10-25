"""淸月's particle sphere: motion only from the state it is given, still when stopped, nothing while hidden."""
import gc
import tkinter as tk
import unittest

from axbranch import orb as O


class OrbTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('+0+0')
        self.panel = O.OrbPanel(self.root, size=120, count=60, low_count=30)
        self.panel.pack()
        self.root.update()
        self.orb = self.panel.orb

    def tearDown(self):
        self.orb._cancel()
        self.root.destroy()
        # Collect this root's Tk reference cycles HERE, on the Tk thread. Left to the cyclic GC they can be freed on a
        # later test's worker thread, which aborts Tcl ("Tcl_AsyncDelete: async handler deleted by the wrong thread",
        # single-process full run 2026-10-25) - the same reason App.destroy collects.
        gc.collect()

    def finish(self):
        self.orb._settle_until, self.orb._impulse, self.orb._burst = 0, 0, 0
        self.orb._cancel()
        self.orb._tick()

    def test_every_state_has_readable_text_and_no_voice_states(self):
        self.assertEqual(set(O.TEXT), set(O._P))
        for state, (label, what, nxt) in O.TEXT.items():
            self.assertTrue(label and what and nxt, state)
        words = ' '.join(' '.join(v) for v in O.TEXT.values())
        for voice in ('듣', '말하', '음성'):
            self.assertNotIn(voice, words)                 # no voice I/O is connected, so none is shown
        self.panel.set_state('limit')
        self.assertEqual(self.panel.title.cget('text'), O.TEXT['limit'][0])
        self.assertTrue(self.panel.next.cget('text').startswith('다음: '))

    def test_working_states_flow_and_stopped_states_freeze(self):
        self.orb.set_state('planning')
        self.orb._tick()
        self.assertIsNotNone(self.orb._job)
        frames = self.orb.frames
        for stopped in O.STOPPED:
            self.orb.set_state(stopped)
            self.finish()
            self.assertIsNone(self.orb._job, stopped)
        self.assertGreater(self.orb.frames, frames)

    def test_completion_is_one_burst_then_still(self):
        self.orb.set_state('done')
        self.orb.complete()
        self.assertGreater(self.orb._burst, 0)
        for _ in range(60):
            self.orb._step(1 / 20)
        self.assertEqual(self.orb._burst, 0)
        self.finish()
        self.assertIsNone(self.orb._job)

    def test_hidden_or_minimised_renders_nothing_and_resumes_on_map(self):
        self.orb.set_state('planning')
        self.orb._tick()
        self.root.withdraw()
        self.root.update()
        frames = self.orb.frames
        self.orb._cancel()
        self.orb._tick()
        self.assertEqual((self.orb.frames, self.orb._job), (frames, None))   # no frame, no timer
        self.root.deiconify()
        self.root.update()
        self.orb._wake()
        self.root.after(80)
        self.root.update()
        self.assertTrue(self.orb._job is not None or self.orb.frames > frames)

    def test_motion_off_and_low_power(self):
        self.orb.set_state('verifying', motion=False)
        self.finish()
        self.assertIsNone(self.orb._job)
        self.orb.set_low_power(True)
        self.assertEqual(len(self.orb.items), 30)
        self.orb.set_low_power(False)
        self.assertEqual(len(self.orb.items), 60)

    def test_delegation_links_are_drawn_and_capped(self):
        self.orb.set_state('delegating')
        for name in ('리서치', '운영', '리서치', 'a', 'b', 'c'):
            self.orb.delegate(name)
        self.assertEqual([n for n, _ in self.orb.departments], ['운영', 'a', 'b', 'c'])   # no duplicates, last 4
        self.orb._render()
        texts = [self.orb.itemcget(i, 'text') for i in self.orb.overlay if self.orb.type(i) == 'text']
        self.assertEqual(texts, [n for n, _ in self.orb.departments])
        self.orb.set_state('verifying')
        self.assertEqual(self.orb.departments, [])


if __name__ == '__main__':
    unittest.main()
