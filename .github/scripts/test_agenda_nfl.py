"""Testes da coleta NFL: sem internet e sem alterações na agenda."""
import datetime as dt
import unittest
from agenda_nfl import parse_nfl, collect_nfl

D = dt.date(2026, 10, 26)


def event(event_id="1", when="2026-10-27T02:30:00Z", home="Philadelphia Eagles",
          away="Dallas Cowboys", status="STATUS_SCHEDULED", state="pre"):
    return {"id": event_id, "date": when,
            "status": {"type": {"state": state, "name": status}},
            "competitions": [{"competitors": [
                {"homeAway": "away", "team": {"displayName": away}},
                {"homeAway": "home", "team": {"displayName": home}}]}]}


def payload(events):
    return {"leagues": [{"slug": "nfl"}], "events": events}


class NFLAgendaTests(unittest.TestCase):
    def test_utc_next_day_belongs_to_brazilian_day(self):
        self.assertEqual(parse_nfl(payload([event()]), D), {
            "nfl:1": {"time": "23:30", "desc": "Philadelphia Eagles x Dallas Cowboys - NFL"}})

    def test_early_utc_same_day_belongs_to_previous_brazilian_day(self):
        self.assertEqual(parse_nfl(payload([event(when="2026-10-26T02:30:00Z")]), D), {})

    def test_adjacent_dates_avoid_omitting_midnight_games(self):
        by_date = {D - dt.timedelta(days=1): payload([]),
                   D: payload([event(event_id="2", when="2026-10-26T23:00:00Z")]),
                   D + dt.timedelta(days=1): payload([event(event_id="1")])}
        result = collect_nfl(D, lambda date: by_date[date])
        self.assertEqual([x["time"] for x in result], ["20:00", "23:30"])

    def test_cancelled_game_is_ignored(self):
        self.assertEqual(parse_nfl(payload([event(status="STATUS_CANCELED")]), D), {})

    def test_wrong_competition_rejected(self):
        with self.assertRaises(ValueError):
            parse_nfl({"leagues": [{"slug": "wnfl"}], "events": []}, D)

    def test_undefined_time_rejected(self):
        with self.assertRaises(ValueError):
            parse_nfl(payload([event(status="STATUS_TBD")]), D)

    def test_no_partial_result_if_one_day_fails(self):
        def loader(day):
            if day == D + dt.timedelta(days=1):
                raise RuntimeError("ESPN temporariamente indisponível")
            return payload([event()])
        with self.assertRaises(RuntimeError):
            collect_nfl(D, loader)

    def test_conflicting_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            parse_nfl(payload([event(), event(home="Green Bay Packers")]), D)

    def test_no_games_valid(self):
        self.assertEqual(collect_nfl(D, lambda day: payload([])), [])

    def test_no_missing_away(self):
        e = event()
        e["competitions"][0]["competitors"][0]["homeAway"] = "home"
        with self.assertRaises(ValueError):
            parse_nfl(payload([e]), D)

    def test_monday_night_falls_on_brazilian_monday(self):
        self.assertEqual(parse_nfl(payload([event(
            when="2026-10-27T00:15:00Z")]), D)["nfl:1"]["time"], "21:15")

    def test_international_game_sunday_morning(self):
        sunday = dt.date(2026, 10, 25)
        self.assertEqual(parse_nfl(payload([event(
            when="2026-10-25T13:30:00Z")]), sunday)["nfl:1"]["time"], "10:30")

    def test_daylight_saving_change_in_us_does_not_change_brazil_clock(self):
        sunday = dt.date(2026, 11, 1)
        game = event(when="2026-11-02T01:20:00Z")
        self.assertEqual(parse_nfl(payload([game]), sunday)["nfl:1"]["time"], "22:20")
        self.assertEqual(parse_nfl(payload([game]), sunday + dt.timedelta(days=1)), {})

    def test_away_home_order_and_label(self):
        self.assertEqual(parse_nfl(payload([event()]), D)["nfl:1"]["desc"],
                         "Philadelphia Eagles x Dallas Cowboys - NFL")


if __name__ == "__main__":
    unittest.main()
