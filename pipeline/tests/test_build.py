"""Tests de build.py : cohérence du GeoJSON, des statistiques et du schéma
avec les tables CSV publiées."""

import csv
import json
import unittest

from pipeline import build
from pipeline.commun import METADATA, PROCESSED


def lire_csv(chemin):
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class TestFonctions(unittest.TestCase):
    def test_feature_sans_coordonnees(self):
        c = {"id": "2023-0123abcd-1", "annee": "2023", "fondement": "rgpd", "modalite": "sur_place", "famille": "commerce",
             "secteur": "commerce", "organisme": "X"}
        l = {"org_lon": "", "org_lat": "", "commune": "", "code_insee": "", "departement": "", "region": "", "pays": "FR",
             "org_precision": "aucune", "ctrl_lieu": "organisme"}
        self.assertIsNone(build.feature(c, l))
        l.update(org_lon="2.3470", org_lat="48.8589", org_precision="commune")
        f = build.feature(c, l)
        self.assertEqual(f["geometry"]["coordinates"], [2.347, 48.8589])
        self.assertEqual(f["properties"]["annee"], 2023)
        self.assertEqual(set(f["properties"]), set(build.PROPRIETES))

    def test_organismes_recurrents(self):
        rows = [{"organisme": "X", "organisme_norm": "X", "annee": a} for a in ("2019", "2020", "2021")]
        rows += [{"organisme": "Y", "organisme_norm": "Y", "annee": "2019"}]
        r = build.organismes_recurrents(rows, minimum=3)
        self.assertEqual([x["organisme"] for x in r], ["X"])
        self.assertEqual(r[0]["annees"], [2019, 2020, 2021])


class TestDonneesReelles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (PROCESSED / "controles.geojson").exists():
            raise unittest.SkipTest("controles.geojson absent")
        cls.controles = lire_csv(PROCESSED / "controles.csv")
        cls.localisations = lire_csv(PROCESSED / "localisations.csv")
        with open(PROCESSED / "controles.geojson", encoding="utf-8") as f:
            cls.geojson = json.load(f)
        with open(PROCESSED / "stats.json", encoding="utf-8") as f:
            cls.stats = json.load(f)
        with open(METADATA / "schema.json", encoding="utf-8") as f:
            cls.schema = json.load(f)

    def test_geojson_valide_et_complet(self):
        self.assertEqual(self.geojson["type"], "FeatureCollection")
        localises = [l for l in self.localisations if l["org_lon"]]
        self.assertEqual(len(self.geojson["features"]), len(localises))
        ids = {f["id"] for f in self.geojson["features"]}
        self.assertEqual(ids, {l["id"] for l in localises})
        for f in self.geojson["features"][:200]:
            self.assertEqual(f["geometry"]["type"], "Point")
            lon, lat = f["geometry"]["coordinates"]
            self.assertTrue(-180 <= lon <= 180 and -90 <= lat <= 90)
            self.assertEqual(set(f["properties"]), set(build.PROPRIETES))

    def test_stats_coherentes(self):
        n = len(self.controles)
        self.assertEqual(self.stats["couverture"]["nb_controles"], n)
        for cle in ("par_annee", "par_famille", "par_modalite", "par_fondement", "par_lieu_controle", "par_precision"):
            self.assertEqual(sum(self.stats[cle].values()), n, cle)
        for cle in ("annee_x_famille", "annee_x_modalite", "annee_x_fondement"):
            self.assertEqual(sum(sum(v.values()) for v in self.stats[cle].values()), n, cle)
        self.assertEqual(self.stats["couverture"]["nb_cartographies"], len(self.geojson["features"]))
        self.assertEqual(sum(c["n"] for c in self.stats["par_commune"]), sum(1 for l in self.localisations if l["code_insee"]))

    def test_schema_correspond_aux_csv(self):
        par_nom = {r["name"]: r for r in self.schema["resources"]}
        for nom, chemin in (("controles", PROCESSED / "controles.csv"), ("localisations", PROCESSED / "localisations.csv")):
            with open(chemin, encoding="utf-8", newline="") as f:
                entetes = next(csv.reader(f))
            self.assertEqual([c["name"] for c in par_nom[nom]["schema"]["fields"]], entetes, nom)
        # Les énumérations du schéma couvrent les valeurs présentes.
        champs = {c["name"]: c for c in par_nom["controles"]["schema"]["fields"]}
        for champ in ("fondement", "modalite"):
            valeurs = {r[champ] for r in self.controles}
            self.assertTrue(valeurs <= set(champs[champ]["constraints"]["enum"]), champ)


if __name__ == "__main__":
    unittest.main()
