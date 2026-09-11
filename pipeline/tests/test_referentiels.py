"""Cohérence des référentiels entre eux et avec les données produites."""

import csv
import unittest

from pipeline.commun import PROCESSED, REFERENTIELS_SOURCE, lire_json

REF = PROCESSED / "referentiels"


def lire_csv(chemin):
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class TestSecteurs(unittest.TestCase):
    def setUp(self):
        self.secteurs = lire_csv(REF / "secteurs.csv")
        self.familles = {f["code"]: f for f in lire_json(REF / "familles.json")["familles"]}

    def test_chaque_famille_existe(self):
        for s in self.secteurs:
            self.assertIn(s["famille"], self.familles, s["secteur_source"])

    def test_libelles_sources_uniques(self):
        sources = [s["secteur_source"] for s in self.secteurs]
        self.assertEqual(len(sources), len(set(sources)))

    def test_un_secteur_fin_a_une_seule_famille(self):
        par_secteur = {}
        for s in self.secteurs:
            par_secteur.setdefault(s["secteur"], set()).add(s["famille"])
        for secteur, familles in par_secteur.items():
            self.assertEqual(len(familles), 1, secteur)

    def test_seize_familles_ordonnees(self):
        ordres = [f["ordre"] for f in self.familles.values()]
        self.assertEqual(sorted(ordres), list(range(1, 17)))

    def test_tous_les_libelles_des_donnees_sont_couverts(self):
        if not (PROCESSED / "controles.csv").exists():
            self.skipTest("controles.csv absent")
        connus = {s["secteur_source"] for s in self.secteurs}
        for r in lire_csv(PROCESSED / "controles.csv"):
            self.assertIn(r["secteur_source"], connus)


class TestOrganismesAlias(unittest.TestCase):
    def test_alias_bien_formes(self):
        alias = lire_csv(REF / "organismes-alias.csv")
        variantes = [a["organisme_norm"] for a in alias]
        self.assertEqual(len(variantes), len(set(variantes)), "chaque variante n'apparaît qu'une fois")
        cles = {a["organisme_cle"] for a in alias}
        for a in alias:
            self.assertNotEqual(a["organisme_norm"], a["organisme_cle"], a)
            self.assertNotIn(a["organisme_norm"], cles, f"{a['organisme_norm']} est à la fois variante et clé")
            self.assertEqual(a["organisme_norm"], a["organisme_norm"].upper())


class TestTerritoires(unittest.TestCase):
    def test_departements_pointent_vers_des_regions(self):
        regions = {r["code"] for r in lire_json(REF / "regions.json")["regions"]}
        deps = lire_json(REF / "departements.json")["departements"]
        self.assertEqual(len(deps), 101)
        for d in deps:
            self.assertIn(d["region"], regions, d)

    def test_communes_extrait_coherent(self):
        chemin = REFERENTIELS_SOURCE / "communes.json"
        if not chemin.exists():
            self.skipTest("communes.json absent")
        ref = lire_json(chemin)
        deps = {d["code"] for d in lire_json(REF / "departements.json")["departements"]}
        champs = ref["_champs"]
        self.assertEqual(champs[:2], ["code", "nom"])
        codes = set()
        for c in ref["communes"]:
            ligne = dict(zip(champs, c))
            # Les collectivités d'outre-mer (975 à 989) sont dans l'API communes mais pas dans /departements.
            com = ligne["departement"].startswith("9") and len(ligne["departement"]) == 3
            self.assertTrue(ligne["departement"] in deps or com, ligne)
            self.assertTrue(-180 <= ligne["lon"] <= 180 and -90 <= ligne["lat"] <= 90, ligne)
            codes.add(ligne["code"])
        self.assertIn("75056", codes)
        self.assertGreater(len(codes), 34000)


if __name__ == "__main__":
    unittest.main()
