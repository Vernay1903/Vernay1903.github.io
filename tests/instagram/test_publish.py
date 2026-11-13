import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).resolve().parents[2] / 'scripts/instagram/publish_test.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class PublishingTests(unittest.TestCase):
    def test_stale_day_wrong_account_and_changed_data_rejected(self):
        for day, account in [('2026-11-14', p.ACCOUNT), (p.DAY, '999')]:
            with self.assertRaises(p.SafeError):
                p.verify_inputs(day, b'{}', b'bad image', account)
        with self.assertRaises(p.SafeError):
            p.verify_inputs(p.DAY, b'{}', b'bad image', p.ACCOUNT)

    def test_existing_claim_prevents_any_meta_call(self):
        calls = []
        def blocked(*args):
            raise p.SafeError('existing marker')
        with self.assertRaises(p.SafeError):
            p.publish_once(lambda *a: calls.append(a), blocked, {})
        self.assertEqual(calls, [])

    def test_publishes_once_and_persists_before_post(self):
        events = []
        def persist(state, sha=None):
            events.append(state['status'])
            return 'sha'
        def api(path, body=None):
            events.append(path)
            if path.endswith('/media'): return {'id': '123'}
            if '?fields=' in path: return {'status_code': 'FINISHED'}
            return {'id': '456'}
        self.assertEqual(p.publish_once(api, persist, {'status': 'claimed'}), '456')
        self.assertLess(events.index('publishing'), events.index(p.ACCOUNT + '/media_publish'))
        self.assertEqual(events.count(p.ACCOUNT + '/media_publish'), 1)
        self.assertEqual(events[-1], 'published')

    def test_publish_timeout_keeps_intent_and_never_retries(self):
        statuses, posts = [], []
        def persist(state, sha=None):
            statuses.append(state['status'])
            return 'sha'
        def api(path, body=None):
            if path.endswith('/media'): return {'id': '123'}
            if '?fields=' in path: return {'status_code': 'FINISHED'}
            posts.append(path)
            raise p.SafeError('timeout')
        with self.assertRaises(p.SafeError):
            p.publish_once(api, persist, {'status': 'claimed'})
        self.assertEqual(statuses[-1], 'publishing')
        self.assertEqual(len(posts), 1)

    def test_failed_processing_never_publishes(self):
        posts = []
        def api(path, body=None):
            if body: posts.append(path)
            return {'id': '123'} if path.endswith('/media') else {'status_code': 'ERROR'}
        with self.assertRaises(p.SafeError):
            p.publish_once(api, lambda *a: 'sha', {'status': 'claimed'})
        self.assertEqual(posts, [p.ACCOUNT + '/media'])

class WindowTests(unittest.TestCase):
    def test_sao_paulo_cutoff_and_day(self):
        from datetime import datetime
        p.ensure_window(datetime.fromisoformat('2026-11-13T23:59:59+00:00'))
        for instant in ['2026-11-14T00:00:00+00:00', '2026-11-14T23:00:00+00:00']:
            with self.assertRaises(p.SafeError):
                p.ensure_window(datetime.fromisoformat(instant))

    def test_deadline_reached_during_processing_prevents_publish(self):
        calls = []
        checks = []
        def window():
            checks.append(True)
            if len(checks) == 2:
                raise p.SafeError('deadline')
        def api(path, body=None):
            calls.append(path)
            return {'id': '123'} if path.endswith('/media') else {'status_code': 'FINISHED'}
        with self.assertRaises(p.SafeError):
            p.publish_once(api, lambda *a: 'sha', {'status': 'claimed'}, check_window=window)
        self.assertNotIn(p.ACCOUNT + '/media_publish', calls)

if __name__ == '__main__':
    unittest.main()
