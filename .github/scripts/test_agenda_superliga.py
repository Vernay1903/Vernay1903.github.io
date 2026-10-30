"""Testes locais da coleta CBV; não acessam a rede."""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agenda_superliga import parse_superliga, collect_both, format_team_name

D = dt.date(2026, 10, 30)


def match(game_id, raw="2026-10-30T22:30:00+01:00", home="DENTIL PRAIA CLUBE",
          away="PAULISTANO BARUERI", postponed=False):
    return {
        "ChampionshipMatch_ID": game_id, "MatchDateTime": raw,
        "HomeTeam": home, "GuestTeam": away, "postponed": postponed,
    }


def html(gender="feminina", extra=None):
    base = [match(100 + n, raw=f"2026-11-{(n+1):02d}T21:00:00+01:00",
                  home=f"Equipe {n}A", away=f"Equipe {n}B") for n in range(11)]
    allgames = base + (extra if extra is not None else [match(1000)])
    stream = '1:["$","$L46",null,{"matchesByRound":' + json.dumps(
        {"TURNO - RODADA 3": allgames}, ensure_ascii=False) + '}]'
    return (f"<h1>Superliga <span>{gender.capitalize()}</span></h1>"
            + "<script>self.__next_f.push(" + json.dumps([1, stream], ensure_ascii=False) + ")</script>")


class TestSuperliga(unittest.TestCase):
    def test_female_real_timezone(self):
        games = parse_superliga(html(), "feminina", D)
        self.assertEqual(games, [{"time": "18:30",
            "desc": "Dentil Praia Clube x Paulistano Barueri - Superliga Feminina"}])

    def test_male_identity(self):
        games = parse_superliga(html("masculina"), "masculina", D)
        self.assertEqual(len(games), 1)
        self.assertTrue(games[0]["desc"].endswith(" - Superliga Masculina"))

    def test_names_normalized_every_time(self):
        checks = {
            "DENTIL PRAIA CLUBE": "Dentil Praia Clube",
            "PAULISTANO  BARUERI": "Paulistano Barueri",
            "E.C. PINHEIROS": "E.C. Pinheiros",
            "BRUSQUE VÔLEI": "Brusque Vôlei",
            "SESI VOLEI BAURU": "Sesi Vôlei Bauru",
            "FLUMINENSE F.C.": "Fluminense F.C.",
            "SADA CRUZEIRO VOLEI": "Sada Cruzeiro Vôlei",
            "AZULIM/SICOOB/MONTE": "Azulim/Sicoob/Monte",
            "SESC RJ FLAMENGO": "Sesc RJ Flamengo",
            "BRASÍLIA VÔLEI / BRB": "Brasília Vôlei / BRB",
        }
        for raw, expected in checks.items():
            with self.subTest(raw=raw):
                self.assertEqual(format_team_name(raw), expected)

    def test_gender_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            parse_superliga(html("masculina"), "feminina", D)

    def test_cancelled_postponed_excluded(self):
        self.assertEqual(parse_superliga(html(extra=[match(1000, postponed=True)]), "feminina", D), [])

    def test_target_day_empty_valid(self):
        self.assertEqual(parse_superliga(html(), "feminina", dt.date(2026, 10, 29)), [])

    def test_missing_timezone_rejected(self):
        with self.assertRaises(ValueError):
            parse_superliga(html(extra=[match(1000, raw="2026-10-30T18:30:00")]), "feminina", D)

    def test_empty_teams_rejected(self):
        with self.assertRaises(ValueError):
            parse_superliga(html(extra=[match(1000, home=" ")]), "feminina", D)

    def test_unknown_postponement_rejected(self):
        with self.assertRaises(ValueError):
            parse_superliga(html(extra=[match(1000, postponed=None)]), "feminina", D)

    def test_duplicate_id_conflict_rejected(self):
        with self.assertRaises(ValueError):
            parse_superliga(html(extra=[match(1000), match(1000, away="OTHER")]), "feminina", D)

    def test_duplicate_description_rejected(self):
        with self.assertRaises(ValueError):
            parse_superliga(html(extra=[match(1000), match(1001)]), "feminina", D)

    def test_new_season_year_rejected(self):
        with self.assertRaises(ValueError):
            parse_superliga(html(), "feminina", dt.date(2029, 1, 1))

    def test_missing_json_rejected(self):
        with self.assertRaises(ValueError):
            parse_superliga("<h1>Superliga <span>Feminina</span></h1>", "feminina", D)

    def test_status_isolation_female_unavailable(self):
        def loader(gender):
            if gender == "feminina":
                raise RuntimeError("Fonte feminina indisponível")
            return html(gender)
        games, statuses = collect_both(D, loader=loader)
        self.assertEqual(len(games), 1)
        self.assertEqual(statuses["masculina"]["status"], "ok")
        self.assertEqual(statuses["feminina"]["status"], "unavailable")

    def test_status_isolation_male_unavailable(self):
        def loader(gender):
            if gender == "masculina":
                raise RuntimeError("Fonte masculina indisponível")
            return html(gender)
        games, statuses = collect_both(D, loader=loader)
        self.assertEqual(len(games), 1)
        self.assertEqual(statuses["masculina"]["status"], "unavailable")
        self.assertEqual(statuses["feminina"]["status"], "ok")

    def test_date_crosses_to_next_calendar_year(self):
        games = parse_superliga(html(extra=[match(1000,raw="2027-01-02T01:30:00+01:00")]),
                                "feminina", dt.date(2027,1,1))
        self.assertEqual(games[0]["time"], "21:30")


if __name__ == "__main__":
    unittest.main()
