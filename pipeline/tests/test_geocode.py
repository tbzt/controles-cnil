"""Tests de geocode.py : normalisation des noms, résolution, lieu du contrôle,
et propriétés globales sur les données réelles."""

import csv
import unittest

from pipeline import geocode
from pipeline.commun import PROCESSED

TABLES = geocode.charger_tables()


def enregistrement(**champs):
    base = {"id": "2023-00000000-1", "annee": 2023, "modalite": "sur_place", "ville_source": "PARIS",
            "departement": "75", "departement_source": "75", "pays": "FR"}
    base.update(champs)
    return base


class TestCleVille(unittest.TestCase):
    def test_normalisation(self):
        self.assertEqual(geocode.cle_ville("Saint-Maur des Fossés"), "ST MAUR DES FOSSES")
        self.assertEqual(geocode.cle_ville("Marcq-en-Barœul"), "MARCQ EN BAROEUL")
        self.assertEqual(geocode.cle_ville("LYON CEDEX 03"), "LYON")
        self.assertEqual(geocode.cle_ville("Paris 15e"), "PARIS 15")
        self.assertEqual(geocode.cle_ville("PARIS 8EME"), "PARIS 8")
        self.assertEqual(geocode.cle_arrondissement("Paris 1er Arrondissement"), "PARIS 1")
        self.assertIsNone(geocode.cle_arrondissement("Paris"))


class TestResolution(unittest.TestCase):
    def test_commune_exacte(self):
        r = geocode.localiser_organisme(enregistrement(ville_source="Courbevoie", departement="92", departement_source="92"), TABLES)
        self.assertEqual((r["code_insee"], r["org_precision"], r["org_methode"], r["region"]), ("92026", "commune", "referentiel_communes", "11"))

    def test_paris_et_arrondissement(self):
        r = geocode.localiser_organisme(enregistrement(), TABLES)
        self.assertEqual(r["code_insee"], "75056")
        r = geocode.localiser_organisme(enregistrement(ville_source="PARIS 15"), TABLES)
        self.assertEqual(r["code_insee"], "75115")

    def test_departement_ambigu_corse_et_outre_mer(self):
        r = geocode.localiser_organisme(enregistrement(ville_source="AJACCIO", departement="20", departement_source="20"), TABLES)
        self.assertEqual((r["code_insee"], r["departement"]), ("2A004", "2A"))
        r = geocode.localiser_organisme(enregistrement(ville_source="Sainte-Marie", departement="97", departement_source="97"), TABLES)
        self.assertEqual(r["org_precision"], "commune")
        self.assertIn(r["departement"], ("971", "972", "973", "974", "976"))

    def test_ville_unique_prime_sur_departement_errone(self):
        r = geocode.localiser_organisme(enregistrement(ville_source="ROUBAIX", departement="75", departement_source="75"), TABLES)
        self.assertEqual(r["code_insee"], "59512")
        self.assertIn("departement_contredit_par_ville", r["drapeaux"])

    def test_alias_commune_et_alias_pays(self):
        r = geocode.localiser_organisme(enregistrement(ville_source="Anthony", departement="92", departement_source="92"), TABLES)
        self.assertEqual((r["code_insee"], r["org_methode"]), ("92002", "alias"))
        r = geocode.localiser_organisme(enregistrement(ville_source="LONDRES", departement="", departement_source=""), TABLES)
        self.assertEqual((r["pays"], r["org_precision"], r["org_methode"]), ("GB", "pays", "centroide_pays"))
        self.assertIn("pays_corrige_par_alias", r["drapeaux"])

    def test_ville_inconnue_retombe_au_departement(self):
        r = geocode.localiser_organisme(enregistrement(ville_source="VILLE QUI N EXISTE PAS", departement="33", departement_source="33"), TABLES)
        self.assertEqual((r["org_precision"], r["org_methode"]), ("departement", "centroide_departement"))
        self.assertIn("ville_non_resolue", r["drapeaux"])
        self.assertTrue(-1.5 < float(r["org_lon"]) < 0.5 and 44 < float(r["org_lat"]) < 46)

    def test_etranger_sans_ville_connue(self):
        r = geocode.localiser_organisme(enregistrement(ville_source="SAN FRANCISCO", departement="", departement_source="", pays="US"), TABLES)
        self.assertEqual((r["org_precision"], r["org_methode"]), ("pays", "centroide_pays"))

    def test_rien_du_tout(self):
        r = geocode.localiser_organisme(enregistrement(ville_source="", departement="", departement_source=""), TABLES)
        self.assertEqual(r["org_precision"], "aucune")

    def test_lieu_du_controle_selon_modalite(self):
        org = geocode.localiser_organisme(enregistrement(), TABLES)
        for modalite in ("en_ligne", "sur_pieces", "sur_audition"):
            c = geocode.localiser_controle(enregistrement(modalite=modalite), org, TABLES["lieux"])
            self.assertEqual((c["ctrl_lieu"], c["ctrl_precision"]), ("cnil", "institution"))
        c = geocode.localiser_controle(enregistrement(modalite="sur_place"), org, TABLES["lieux"])
        self.assertEqual((c["ctrl_lieu"], c["ctrl_lon"], c["drapeaux"]), ("organisme", org["org_lon"], []))
        c = geocode.localiser_controle(enregistrement(modalite="non_renseignee"), org, TABLES["lieux"])
        self.assertEqual((c["ctrl_lieu"], c["drapeaux"]), ("organisme", ["lieu_controle_inconnu"]))


class TestDonneesReelles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chemin = PROCESSED / "localisations.csv"
        if not chemin.exists():
            raise unittest.SkipTest("localisations.csv absent")
        with open(chemin, encoding="utf-8", newline="") as f:
            cls.lignes = list(csv.DictReader(f))
        with open(PROCESSED / "controles.csv", encoding="utf-8", newline="") as f:
            cls.controles = {r["id"]: r for r in csv.DictReader(f)}

    def test_une_localisation_par_controle(self):
        self.assertEqual(sorted(l["id"] for l in self.lignes), sorted(self.controles))

    def test_taux_de_resolution_france(self):
        france = [l for l in self.lignes if l["pays"] == "FR"]
        precis = [l for l in france if l["org_precision"] in ("commune", "adresse")]
        self.assertGreaterEqual(len(precis) / len(france), 0.99)

    def test_coordonnees_dans_les_bornes(self):
        for l in self.lignes:
            for lon, lat in ((l["org_lon"], l["org_lat"]), (l["ctrl_lon"], l["ctrl_lat"])):
                if lon:
                    self.assertTrue(-180 <= float(lon) <= 180 and -90 <= float(lat) <= 90, l["id"])
            if l["pays"] == "FR" and l["org_precision"] in ("commune", "adresse"):
                lon, lat = float(l["org_lon"]), float(l["org_lat"])
                metropole = -5.5 <= lon <= 10 and 41 <= lat <= 51.5
                outre_mer = l["departement"].startswith("97")
                self.assertTrue(metropole or outre_mer, l)

    def test_controles_a_distance_a_la_cnil(self):
        for l in self.lignes:
            modalite = self.controles[l["id"]]["modalite"]
            if modalite in ("en_ligne", "sur_pieces", "sur_audition"):
                self.assertEqual(l["ctrl_lieu"], "cnil", l["id"])
            else:
                self.assertEqual(l["ctrl_lieu"], "organisme", l["id"])


if __name__ == "__main__":
    unittest.main()
