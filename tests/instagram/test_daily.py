import copy
import json
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/instagram'))
from daily import ACCOUNT, SafeError, check_plan, check_window, dated_source, publish_pages, verify_meta_identity


class DailyTests(unittest.TestCase):
    def state(self, count=1):
        return {'date': '2026-11-15', 'account': ACCOUNT, 'agenda_sha256': 'abc',
                'pages': [{'status': 'pending', 'image_url': 'https://example.com/' + str(i)} for i in range(count)]}

    def test_meta_identity_primary_success_no_fallback(self):
        with patch('daily.meta', return_value={'id': ACCOUNT, 'username': 'cortedosesportes'}) as primary, \
             patch('daily.request') as alternative:
            verify_meta_identity()
            primary.assert_called_once_with(ACCOUNT + '?fields=id,username')
            alternative.assert_not_called()

    def test_meta_identity_100_33_fallback_validates_same_account(self):
        identity = {'id': ACCOUNT, 'username': 'cortedosesportes'}
        with patch('daily.meta', side_effect=SafeError('HTTP 400 code=100 subcode=33')), \
             patch('daily.request', return_value=json.dumps(identity).encode()) as alternative, \
             patch.dict('daily.os.environ', {'INSTAGRAM_ACCESS_TOKEN': 'token-de-teste'}):
            verify_meta_identity()
            self.assertIn('/v26.0/' + ACCOUNT + '?fields=id,username', alternative.call_args.args[0])
            self.assertEqual(alternative.call_args.args[1], 'token-de-teste')

    def test_meta_identity_no_fallback_for_other_errors(self):
        with patch('daily.meta', side_effect=SafeError('HTTP 400 code=190')), \
             patch('daily.request') as alternative:
            with self.assertRaises(SafeError):
                verify_meta_identity()
            alternative.assert_not_called()

    def test_meta_identity_fallback_never_accepts_different_account(self):
        identity = {'id': '123456789', 'username': 'outroperfil'}
        with patch('daily.meta', side_effect=SafeError('HTTP 400 code=100 subcode=33')), \
             patch('daily.request', return_value=json.dumps(identity).encode()), \
             patch.dict('daily.os.environ', {'INSTAGRAM_ACCESS_TOKEN': 'token-de-teste'}):
            with self.assertRaises(SafeError):
                verify_meta_identity()

    def test_window_uses_brazil_and_reserves_response_time(self):
        for hhmm in ['03:40', '03:58']:
            check_window('2026-11-15', datetime.fromisoformat('2026-11-15T' + hhmm + ':59+00:00'))
        for stamp in ['2026-11-15T03:39:59+00:00', '2026-11-15T03:59:00+00:00',
                      '2026-11-15T04:00:00+00:00', '2026-11-16T03:40:00+00:00']:
            with self.assertRaises(SafeError):
                check_window('2026-11-15', datetime.fromisoformat(stamp))

    def test_dated_merged_agenda_required_not_just_timestamp(self):
        commit = {'sha': 'abc', 'commit': {'message': 'Atualiza agenda de 2026-11-15 (#132)',
                  'committer': {'date': '2026-11-15T03:15:00Z'}}}
        pr = {'merged': True, 'number': 132, 'merge_commit_sha': 'abc',
              'head': {'ref': 'agenda-auto-2026-11-15'}, 'base': {'ref': 'main'}}
        dated_source(commit, pr, '2026-11-15')
        for change in [{'merged': False}, {'merge_commit_sha': 'other'}, {'head': {'ref': 'manual'}}]:
            with self.assertRaises(SafeError):
                dated_source(commit, dict(pr, **change), '2026-11-15')
        with self.assertRaises(SafeError):
            dated_source(commit, pr, '2026-11-16')
        commit['commit']['message'] = 'Update agenda.json'
        with self.assertRaises(SafeError):
            dated_source(commit, pr, '2026-11-15')

    def test_changed_plan_cannot_resume(self):
        check_plan(self.state(), '2026-11-15', 'abc')
        for day, hash_ in [('2026-11-16', 'abc'), ('2026-11-15', 'changed')]:
            with self.assertRaises(SafeError):
                check_plan(self.state(), day, hash_)

    def test_pages_order_and_durable_intent_then_no_duplicate(self):
        state, saved, posted = self.state(3), [], []
        def api(path, payload=None):
            if path.endswith('/media'):
                return {'id': str(100 + len(posted))}
            if payload:
                self.assertEqual(saved[-1]['pages'][len(posted)]['status'], 'publishing')
                posted.append(payload['creation_id'])
                return {'id': str(200 + len(posted))}
            return {'status_code': 'FINISHED'}
        persist = lambda s: saved.append(copy.deepcopy(s))
        self.assertEqual(publish_pages(state, persist, api, lambda: None), 3)
        self.assertEqual(posted, ['100', '101', '102'])
        publish_pages(state, persist, lambda *a: self.fail('Already published'), lambda: None)

    def test_resume_partial_skips_successful_page(self):
        state = self.state(2)
        state['pages'][0].update(status='published', media_id='1')
        state['pages'][1].update(status='container_created', container_id='2')
        calls = []
        def api(path, payload=None):
            calls.append(path)
            return {'id': '3'} if payload else {'status_code': 'FINISHED'}
        publish_pages(state, lambda s: None, api, lambda: None)
        self.assertEqual(calls, ['2?fields=status_code', ACCOUNT + '/media_publish'])

    def test_lost_publish_response_does_not_repeat(self):
        state = self.state()
        def api(path, payload=None):
            if path.endswith('/media'):
                return {'id': '1'}
            if payload:
                raise SafeError('Timeout')
            return {'status_code': 'FINISHED'}
        with self.assertRaises(SafeError):
            publish_pages(state, lambda s: None, api, lambda: None)
        self.assertEqual(state['pages'][0]['status'], 'publishing')
        with self.assertRaises(SafeError):
            publish_pages(state, lambda s: None, api, lambda: None)
        # Later positive confirmation can reconcile, without a second POST.
        publish_pages(state, lambda s: None, lambda *a: {'status_code': 'PUBLISHED'}, lambda: None)
        self.assertEqual(state['pages'][0]['status'], 'published')

    def test_cutoff_after_processing_prevents_publish(self):
        state, closed, posts = self.state(), [False], []
        def check():
            if closed[0]:
                raise SafeError('Cutoff')
        def api(path, payload=None):
            if path.endswith('/media'):
                return {'id': '1'}
            if payload:
                posts.append(payload)
            closed[0] = True
            return {'status_code': 'FINISHED'}
        with self.assertRaises(SafeError):
            publish_pages(state, lambda s: None, api, check)
        self.assertEqual(posts, [])

    def test_storage_failure_blocks_publish(self):
        state = self.state()
        def persist(value):
            raise SafeError('Conflict')
        calls = []
        def api(path, payload=None):
            calls.append(path)
            return {'id': '1'}
        with self.assertRaises(SafeError):
            publish_pages(state, persist, api, lambda: None)
        self.assertEqual(calls, [ACCOUNT + '/media'])

    def test_pending_container_resumes_without_recreation(self):
        state = self.state()
        state['pages'][0].update(status='container_created', container_id='1')
        calls = []
        def api(path, payload=None):
            calls.append(path)
            return {'status_code': 'IN_PROGRESS'}
        with self.assertRaises(SafeError):
            publish_pages(state, lambda s: None, api, lambda: None, sleep=lambda s: None)
        self.assertTrue(all(path == '1?fields=status_code' for path in calls))
        self.assertEqual(state['pages'][0]['container_id'], '1')


if __name__ == '__main__':
    unittest.main()
