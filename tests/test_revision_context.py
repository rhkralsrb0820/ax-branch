"""An Owner revision is verified against the version the Owner reviewed (diff), so preservation can be judged."""
import json
import unittest

from axbranch import engine as E
from tests import test_engine as TE
from tests.test_engine import GOOD, Script

REVISED = GOOD + '\n# Owner asked for this comment line\n'


def verdict_contexts(script):
    out = []
    for schema, _, prompt in script.prompts:
        if schema is E.VERDICT:
            out.append(json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1]
                                  .rsplit('\n\nReturn exactly', 1)[0]))
    return out


class RevisionContextTests(unittest.TestCase):
    setUp, tearDown, engine = TE.EngineTests.setUp, TE.EngineTests.tearDown, TE.EngineTests.engine

    def test_revision_verifier_sees_the_diff_from_the_reviewed_version(self):
        script = Script([GOOD, REVISED], ['PASS', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        eng.owner_review(pid, text='Add a comment line; keep everything else.')
        eng.run(pid)       # later routing depends on scripted harness probes; only the verifier's context is judged here
        contexts = verdict_contexts(script)
        self.assertGreaterEqual(len(contexts), 2)
        first, second = contexts[0], contexts[-1]
        self.assertNotIn('previous_verified_version', first)                 # nothing to compare on the first build
        prev = second['previous_verified_version']
        self.assertEqual(prev['iteration'], 1)
        self.assertIn('+# Owner asked for this comment line', prev['diff'])
        self.assertFalse(prev['diff_truncated'])
        self.assertNotIn('-def add', prev['diff'])                           # unchanged code is not shown as removed


if __name__ == '__main__':
    unittest.main()
