"""Testes da coleta NBA: sem internet e sem alterações na agenda."""
import datetime as dt
import unittest
from agenda_nba import parse_nba, collect_nba

D = dt.date(2026, 10, 26)


def event(event_id="1", when="2026-10-27T02:30:00Z", home="Boston Celtics",
          away="Los Angeles Lakers", status="STATUS_SCHEDULED", state="pre"):
    return {"id": event_id, "date": when,
            "status": {"type": {"state": state, "name": status}},
            "competitions": [{"competitors": [
                {"homeAway": "away", "team": {"displayName": away}},
                {"homeAway": "home", "team": {"displayName": home}}]}]}


def payload(events):
    return {"leagues": [{"slug": "nba"}], "events": events}


class NBAAgendaTests(unittest.TestCase):
    def test_utc_next_day_belongs_to_brazilian_day(self):
        self.assertEqual(parse_nba(payload([event()]), D), {
            "nba:1": {"time": "23:30", "desc": "Boston Celtics x Los Angeles Lakers - NBA"}})

    def test_early_utc_same_day_belongs_to_previous_brazilian_day(self):
        self.assertEqual(parse_nba(payload([event(when="2026-10-26T02:30:00Z")]), D), {})

    def test_adjacent_dates_avoid_omitting_midnight_games(self):
        by_date = {D - dt.timedelta(days=1): payload([]),
                   D: payload([event(event_id="2", when="2026-10-26T23:00:00Z")]),
                   D + dt.timedelta(days=1): payload([event(event_id="1")])}
        result = collect_nba(D, lambda date: by_date[date])
        self.assertEqual([x["time"] for x in result], ["20:00", "23:30"])

    def test_cancelled_game_is_ignored(self):
        self.assertEqual(parse_nba(payload([event(status="STATUS_CANCELED")]), D), {})

    def test_wrong_competition_rejected(self):
        with self.assertRaises(ValueError):
            parse_nba({"leagues": [{"slug": "wnba"}], "events": []}, D)

    def test_undefined_time_rejected(self):
        with self.assertRaises(ValueError):
            parse_nba(payload([event(status="STATUS_TBD")]), D)

    def test_no_partial_result_if_one_day_fails(self):
        def loader(day):
            if day == D + dt.timedelta(days=1):
                raise RuntimeError("ESPN temporariamente indisponível")
            return payload([event()])
        with self.assertRaises(RuntimeError):
            collect_nba(D, loader)

    def test_conflicting_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            parse_nba(payload([event(), event(home="New York Knicks")]), D)

    def test_no_games_valid(self):
        self.assertEqual(collect_nba(D, lambda day: payload([])), [])

    def test_no_missing_away(self):
        e = event()
        e["competitions"][0]["competitors"][0]["homeAway"] = "home"
        with self.assertRaises(ValueError):
            parse_nba(payload([e]), D)


if __name__ == "__main__":
    unittest.main()
