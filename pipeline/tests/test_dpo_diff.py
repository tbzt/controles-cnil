"""Tests de dpo_diff.py : clé d'organisme, comparaison de deux empreintes,
ordre des versions, écriture."""

import unittest

from pipeline import dpo_diff


class TestComparaison(unittest.TestCase):
    def test_cle_organisme(self):
        self.assertEqual(dpo_diff.cle_organisme({"siren": "110000122", "nom_norm": "CNIL", "code_postal": "75007"}), "110000122")
        self.assertEqual(dpo_diff.cle_organisme({"siren": "", "nom_norm": "CNIL", "code_postal": "75007"}), "CNIL|75007")

    def test_comparer(self):
        avant = {"a": frozenset({("2018-05-25", "personne_physique", "")}),
                 "b": frozenset({("2019-01-01", "personne_morale", "CDG")}),
                 "c": frozenset({("2020-01-01", "personne_physique", "")})}
        apres = {"a": frozenset({("2018-05-25", "personne_physique", "")}),        # inchangé
                 "b": frozenset({("2026-06-01", "personne_morale", "ADNOV")}),    # re-désigné ailleurs
                 "d": frozenset({("2026-07-01", "personne_physique", "")})}        # nouveau ; c retiré
        self.assertEqual(dpo_diff.comparer(avant, apres), {"nouvelles": 1, "retirees": 1, "modifiees": 1, "solde": 0})

    def test_versions_triees_par_publication(self):
        manifeste = {"ressources": {"r": {"format": "csv", "versions": [
            {"fichier": "dpo/b.csv", "publie_le": "2026-08-03T09:00:00"},
            {"fichier": "dpo/a.csv", "publie_le": "2026-07-06T08:37:30"},
        ]}, "x": {"format": "xlsx", "versions": [{"fichier": "dpo/x.xlsx"}]}}}
        v = dpo_diff.versions_archivees(manifeste)
        self.assertEqual([x["publie_le"] for x in v], ["2026-07-06", "2026-08-03"])
        self.assertEqual(v[0]["fichier"].name, "a.csv")


if __name__ == "__main__":
    unittest.main()
