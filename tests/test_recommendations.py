import json
import sqlite3
import tempfile
import threading
import unittest
from collections import Counter
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from app.db import connect, seed
from app.recommend import recommendations
from app.server import handler_for


class RecommendationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name) / 'test.sqlite3'
        seed(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        # Each test gets a fresh writable copy; boundary cases cannot pollute the seed.
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        with closing(connect(self.path)) as source:
            source.backup(self.db)
        self.db.execute('PRAGMA foreign_keys = ON')
        self.addCleanup(self.db.close)

    def ids(self, uid, limit=5):
        return [r['circle']['id'] for r in recommendations(self.db, uid, limit)['recommendations']]

    def test_planted_scenarios(self):
        cold = recommendations(self.db, 42)
        self.assertEqual(cold['strategy'], 'explore')
        self.assertEqual(len(cold['recommendations']), 5)
        self.assertTrue({5, 6} <= set(self.ids(7)[:3]))
        self.assertLessEqual(len({10, 11, 12} & set(self.ids(15, 20))), 2)
        self.assertEqual(self.ids(23)[0], 22)
        self.assertFalse({20, 21} & set(self.ids(23, 20)))

    def test_every_user_eligibility_diversity_and_determinism(self):
        for user in self.db.execute('SELECT id FROM users'):
            uid = user[0]
            with self.subTest(user_id=uid):
                result = recommendations(self.db, uid, 20)
                self.assertEqual(result, recommendations(self.db, uid, 20))
                self.assertGreaterEqual(len(result['recommendations']), 5)
                joined = {r[0] for r in self.db.execute('SELECT circle_id FROM memberships WHERE user_id=?', (uid,))}
                ids = [r['circle']['id'] for r in result['recommendations']]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertFalse(joined & set(ids))
                counts = Counter()
                for item in result['recommendations']:
                    c = self.db.execute('SELECT * FROM circles WHERE id=?', (item['circle']['id'],)).fetchone()
                    self.assertEqual(c['access'], 'public')
                    self.assertTrue(c['max_members'] is None or c['member_count'] < c['max_members'])
                    self.assertGreater(c['feed_posts_30d'] + c['chat_messages_30d'], 0)
                    self.assertGreaterEqual(c['last_activity_at'], '2026-07-23')
                    self.assertTrue(item['explanation'])
                    if c['topic']:
                        counts[c['topic']] += 1
                self.assertTrue(all(n <= 2 for n in counts.values()))

    def test_inactive_filter_independent_of_visibility(self):
        self.db.execute("UPDATE circles SET access='public', last_activity_at='2026-02-01T00:00:00Z', feed_posts_30d=0, chat_messages_30d=3 WHERE id=21")
        self.assertNotIn(21, self.ids(23, 20))

    def test_capacity_boundary_and_uncapped(self):
        self.assertIn(1, self.ids(42, 20))  # null cap
        self.db.execute('UPDATE circles SET max_members=member_count WHERE id=1')
        self.assertNotIn(1, self.ids(42, 20))
        self.db.execute('UPDATE circles SET max_members=member_count+1 WHERE id=1')
        self.assertIn(1, self.ids(42, 20))

    def test_membership_fallback_and_no_profile_penalty(self):
        self.db.execute('DELETE FROM user_interests WHERE user_id=7')
        result = recommendations(self.db, 7)
        self.assertEqual(result['strategy'], 'membership_topics')
        before = recommendations(self.db, 42)
        self.db.execute("UPDATE users SET profile_completeness=1, has_photo=1, industry='Technology' WHERE id=42")
        self.assertEqual(before, recommendations(self.db, 42))

    def test_empty_pool_and_future_activity(self):
        self.db.execute("UPDATE circles SET last_activity_at='2026-09-22T00:00:00Z'")
        self.assertEqual(self.ids(42), [])

    def test_activity_time_boundaries(self):
        self.db.execute("UPDATE circles SET access='unlisted' WHERE id != 1")
        for timestamp, expected in (
            ('2026-07-23T00:00:00Z', [1]),  # Exactly 60 days is eligible.
            ('2026-07-22T23:59:59Z', []),
            ('2026-09-21T00:00:00Z', [1]),  # Same instant, without milliseconds.
            ('2026-09-21T00:00:00.000Z', [1]),
            ('2026-09-21T00:00:01Z', []),
        ):
            with self.subTest(timestamp=timestamp):
                self.db.execute('UPDATE circles SET last_activity_at=? WHERE id=1', (timestamp,))
                self.assertEqual(self.ids(42), expected)

    def test_no_volume_and_chat_only(self):
        self.db.execute('UPDATE circles SET feed_posts_30d=0, chat_messages_30d=0 WHERE id=1')
        self.assertNotIn(1, self.ids(42, 20))
        self.db.execute('UPDATE circles SET chat_messages_30d=100 WHERE id=1')
        self.db.execute("UPDATE circles SET access='unlisted' WHERE id != 1")
        result = recommendations(self.db, 42, 20)['recommendations']
        item = next(r for r in result if r['circle']['id'] == 1)
        self.assertIn('group chat', item['explanation'])

    def test_unknown_user_and_limits(self):
        with self.assertRaises(LookupError):
            recommendations(self.db, 999)
        with self.assertRaises(ValueError):
            recommendations(self.db, 2**63)
        for limit in (0, 21, -1):
            with self.assertRaises(ValueError):
                recommendations(self.db, 42, limit)
        self.assertEqual(len(self.ids(42, 1)), 1)

    def test_seed_constraints_and_overwrite_protection(self):
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.db.execute('SELECT count(*) FROM activity').fetchone()[0], 386)
        with self.assertRaises(FileExistsError):
            seed(self.path)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        path = Path(cls.directory.name) / 'http.sqlite3'
        seed(path)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(path))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def request(self, path):
        try:
            response = urlopen(self.base + path, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.headers.get_content_type(), 'application/json')
            return response.status, json.load(response)

    def test_http_success_and_health(self):
        self.assertEqual(self.request('/health'), (200, {'status': 'ok'}))
        status, body = self.request('/users/7/recommendations?limit=3')
        self.assertEqual(status, 200)
        self.assertEqual(len(body['recommendations']), 3)
        self.assertTrue({5, 6} <= {r['circle']['id'] for r in body['recommendations']})

    def test_http_input_errors(self):
        for query in ('limit=', 'limit=abc', 'limit=0', 'limit=21', 'limit=1&limit=2', 'extra=1', 'limit=1.5'):
            with self.subTest(query=query):
                self.assertEqual(self.request('/users/7/recommendations?' + query)[0], 400)
        self.assertEqual(self.request('/users/999/recommendations')[0], 404)
        self.assertEqual(self.request('/users/9223372036854775808/recommendations')[0], 400)
        self.assertEqual(self.request('/unknown')[0], 404)


if __name__ == '__main__':
    unittest.main()
