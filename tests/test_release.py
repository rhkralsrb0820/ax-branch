"""Release discipline: the package version must have a complete CHANGELOG entry."""
import re
import unittest
from pathlib import Path

from axbranch import __version__

CHANGELOG = Path(__file__).resolve().parents[1] / 'CHANGELOG.md'


class ReleaseTests(unittest.TestCase):
    def test_version_has_changelog_entry(self):
        text = CHANGELOG.read_text(encoding='utf-8')
        m = re.search(rf'^## \[{re.escape(__version__)}\] - (\d{{4}}-\d{{2}}-\d{{2}})\n(.*?)(?=^## \[|\Z)', text, re.M | re.S)
        self.assertIsNotNone(m, f'CHANGELOG.md has no entry for {__version__}')
        for section in ('Added', 'Changed', 'Fixed', 'Verification', 'Known issues'):
            self.assertIn(f'### {section}', m.group(2), f'{__version__} entry lacks "{section}"')


if __name__ == '__main__':
    unittest.main()
