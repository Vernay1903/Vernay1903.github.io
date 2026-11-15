import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/instagram'))
from launch_window import await_window, TZ
from daily import retry, SafeError


class LaunchTests(unittest.TestCase):
    def test_agenda_completion_0024_waits_until_0040(self):
        current = [datetime(2026, 11, 15, 0, 24, tzinfo=TZ)]
        waits = []
        def sleep(seconds):
            waits.append(seconds)
            current[0] += timedelta(seconds=seconds)
        self.assertTrue(await_window(True, 'workflow_run', lambda: current[0], sleep))
        self.assertEqual(current[0].strftime('%H:%M'), '00:40')
        self.assertEqual(sum(waits), 16 * 60)
        self.assertLessEqual(max(waits), 30)

    def test_late_event_never_publishes_or_waits_until_tomorrow(self):
        for event in ['schedule', 'workflow_run', 'workflow_dispatch']:
            self.assertFalse(await_window(True, event, lambda: datetime(2026, 11, 15, 8, 29, tzinfo=TZ),
                                          lambda s: self.fail('No overnight wait')))

    def test_dry_run_does_not_wait(self):
        self.assertTrue(await_window(False, 'push', lambda: datetime(2026, 11, 15, 12, tzinfo=TZ)))

    def test_same_runner_retry_recovers_without_another_cron(self):
        calls = []
        def operation():
            calls.append(1)
            if len(calls) == 1:
                raise SafeError('Temporary error')
            return 'ok'
        with patch.dict(os.environ, PUBLISH_DAILY='true'):
            self.assertEqual(retry(operation, lambda: datetime(2026, 11, 15, 0, 45, tzinfo=TZ), lambda s: None), 'ok')
        self.assertEqual(len(calls), 2)

    def test_retry_stops_at_cutoff(self):
        current = [datetime(2026, 11, 15, 0, 58, 50, tzinfo=TZ)]
        calls = []
        def operation():
            calls.append(1)
            raise SafeError('Temporary error')
        def sleep(seconds):
            current[0] += timedelta(seconds=seconds)
        with patch.dict(os.environ, PUBLISH_DAILY='true'), self.assertRaises(SafeError):
            retry(operation, lambda: current[0], sleep)
        self.assertEqual(len(calls), 1)
