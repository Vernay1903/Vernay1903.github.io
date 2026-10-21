import copy
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import selecionar_pos_jogos as s

DAY = date(2026, 10, 20)
NOW = datetime.fromisoformat('2026-10-21T10:00:00-03:00')


def event(home=359, away=382, status='STATUS_FULL_TIME', completed=True):
    names = {str(i): name for name, (i, _) in s.TEAMS.items()}
    return {'id': '123', 'league': {'slug': 'eng.1', 'name': 'Premier League'},
            'competitions': [{'date': '2026-10-20T22:00:00Z',
                'status': {'type': {'name': status, 'completed': completed}},
                'competitors': [{'homeAway': side, 'score': score,
                    'team': {'id': str(i), 'displayName': names[str(i)]}}
                    for side, i, score in [('home', home, '2'), ('away', away, '1')]]}]}


def snapshots(e=None):
    return {str(s.TEAMS[n][0]): {'team': {'id': str(s.TEAMS[n][0]), 'displayName': s.TEAMS[n][1]},
            'events': [copy.deepcopy(e)] if e and n in {'Arsenal', 'Manchester City'} else []} for n in s.PILOT}


class SelectionTest(unittest.TestCase):
    def run_selection(self, e=None, news=None, data=None):
        data = data if data is not None else snapshots(e)
        calls = []
        def query(url):
            key = url.split('/teams/')[1].split('/')[0]
            calls.append(key)
            return data[key]
        report = s.select(DAY, news or [], query, NOW)
        self.assertEqual(set(calls), {'819', '86', '359', '382'})
        return report

    def test_two_clubs_one_game(self):
        r = self.run_selection(event())
        self.assertEqual(len(r['selected']), 1)
        self.assertTrue(r['collection_complete'])
        self.assertFalse(r['publication_enabled'])

    def test_non_final_statuses(self):
        for status in ['STATUS_IN_PROGRESS', 'STATUS_SCHEDULED', 'STATUS_POSTPONED', 'STATUS_SUSPENDED', 'STATUS_CANCELED']:
            with self.subTest(status=status):
                self.assertEqual(self.run_selection(event(status=status))['selected'], [])

    def test_final_needs_completed(self):
        self.assertEqual(self.run_selection(event(completed=False))['selected'], [])

    def test_missing_score(self):
        e = event(); e['competitions'][0]['competitors'][0]['score'] = None
        self.assertFalse(self.run_selection(e)['collection_complete'])

    def test_provider_numeric_score(self):
        self.assertEqual(s.integer({'value': 4.0, 'displayValue': '4'}), 4)
        for value in [True, -1, 2.5, None]:
            with self.assertRaises(ValueError): s.integer(value)

    def test_preview_allowed_result_blocked(self):
        for title, count in [('Arsenal x Manchester City: horário, escalações e transmissão', 1),
                             ('Arsenal x Manchester City: resultado e gols', 0),
                             ('Arsenal 2 x 1 Manchester City', 0),
                             ('Arsenal x Manchester City: análise', 0)]:
            with self.subTest(title=title):
                news = [{'title': title, 'date': '21/10/2026', 'category': 'Futebol'}]
                self.assertEqual(len(self.run_selection(event(), news)['selected']), count)

    def test_explicit_identity_across_dates(self):
        news = [{'fixture_id': 'espn-123', 'article_type': 'post_match', 'category': 'Futebol', 'date': '01/01/2020'}]
        self.assertEqual(self.run_selection(event(), news)['selected'], [])

    def test_midnight_brasilia(self):
        e = event(); e['competitions'][0]['date'] = '2026-10-21T01:00:00Z'
        self.assertEqual(len(self.run_selection(e)['selected']), 1)
        e['competitions'][0]['date'] = '2026-10-21T04:00:00Z'
        self.assertEqual(self.run_selection(e)['selected'], [])

    def test_friendly(self):
        e = event(); e['league']['slug'] = 'club.friendly'
        self.assertEqual(self.run_selection(e)['selected'], [])

    def test_conflict(self):
        data = snapshots(event())
        data['382']['events'][0]['competitions'][0]['competitors'][0]['score'] = '3'
        r = self.run_selection(data=data)
        self.assertEqual(r['selected'], [])
        self.assertEqual(r['blocked'][0]['reason'], 'conflicting_calendar_data')

    def test_empty_and_error_distinct(self):
        r = self.run_selection()
        self.assertTrue(r['collection_complete'])
        data = snapshots(); del data['819']['events']
        self.assertFalse(self.run_selection(data=data)['collection_complete'])

    def test_all_four_clubs(self):
        for home in [819, 86, 359, 382]:
            row = s.normalize(event(home=home, away=83), DAY, home, NOW)
            self.assertIsNotNone(row)

    def test_future_and_timezone(self):
        e = event(); e['competitions'][0]['date'] = '2026-10-20T22:00:00'
        with self.assertRaises(ValueError): s.normalize(e, DAY, 359, NOW)
        with self.assertRaises(ValueError): s.normalize(event(), DAY, 359, datetime.fromisoformat('2026-10-20T01:00:00Z'))


if __name__ == '__main__':
    unittest.main()
