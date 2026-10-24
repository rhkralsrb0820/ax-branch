import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from axbranch.home import parse_feed


class FeedTests(unittest.TestCase):
    def test_dashboard_counts_every_state_without_claiming_success(self):
        from axbranch.home import state_groups
        rows = [{'state': s} for s in ('EXECUTING', 'OWNER_REVIEW', 'PAUSED', 'CLOSED', 'ARCHIVING')]
        groups = state_groups(rows)
        self.assertEqual(sum(n for _, n, _ in groups), len(rows))
        self.assertEqual(dict((label, n) for label, n, _ in groups)['종료'], 1)
        self.assertEqual(state_groups([])[0][1], 0)
    def test_sorted_deduplicated_and_no_script_links(self):
        raw = b'''<rss><channel>
        <item><title>Older</title><link>https://example.com/old</link><pubDate>Mon, 19 Oct 2026 10:00:00 GMT</pubDate></item>
        <item><title>New</title><link>https://example.com/new</link><pubDate>Tue, 20 Oct 2026 10:00:00 GMT</pubDate></item>
        <item><title>Duplicate</title><link>https://example.com/new</link></item>
        <item><title>Unsafe</title><link>javascript:alert(1)</link></item>
        <item><title>Unknown</title><link>https://example.com/unknown</link></item>
        </channel></rss>'''
        rows = parse_feed(raw, 'AI 동향')
        self.assertEqual([r['title'] for r in rows], ['New', 'Older', 'Unknown'])
        self.assertIsNone(rows[-1]['published'])

    def test_jobs_match_ai_not_substrings(self):
        raw = b'''<rss><channel>
        <item><title>Email engineer</title><link>https://example.com/a</link></item>
        <item><title>ML engineer</title><link>https://example.com/b</link></item>
        </channel></rss>'''
        self.assertEqual([r['title'] for r in parse_feed(raw, 'AI 취업')], ['ML engineer'])

    def test_fetch_failure_is_explicit(self):
        from axbranch.home import fetch_feeds
        with patch('urllib.request.urlopen', side_effect=OSError('offline')):
            results = fetch_feeds()
        self.assertTrue(all(r['error'] == 'offline' and not r['items'] for r in results.values()))

    def test_stale_or_missing_collection_is_stated(self):
        from axbranch.home import freshness
        now = 1_800_000_000
        self.assertEqual(freshness(None, now), '수집 전')
        self.assertNotIn('오래된', freshness(now - 3600, now))
        self.assertIn('오래된 정보 (3일 전)', freshness(now - 3 * 86400 - 5, now))
