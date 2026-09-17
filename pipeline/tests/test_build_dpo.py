"""Tests de build_dpo.py : agrégats sur un jeu synthétique, repli des
arrondissements, taux de désignation, structure dominante, couverture des
communes, déterminisme."""

import json
import unittest

from pipeline import build_dpo


def designation(**d):
    base = {"snapshot": "2026-07-06", "siren": "110000122", "nom": "CNIL", "nom_norm": "CNIL", "section_naf": "O",
            "code_naf": "8411Z", "code_postal": "75007", "ville_source": "PARIS", "code_insee": "75056", "commune": "Paris",
            "departement": "75", "region": "11", "pays": "FR", "type_dpo": "personne_physique",
            "date_designation": "2018-05-25", "siren_designe": "", "nom_designe": "", "nom_designe_norm": "",
            "section_naf_designe": "", "code_naf_designe": "", "code_postal_designe": "", "ville_designe": "",
            "pays_designe": "", "drapeaux": ""}
    base.update(d)
    return base


COMMUNES = {
    "75056": {"code": "75056", "nom": "Paris", "departement": "75", "region": "11", "lon": 2.35, "lat": 48.85, "population": 2100000, "type": "commune"},
    "75108": {"code": "75108", "nom": "Paris 8e Arrondissement", "departement": "75", "region": "11", "lon": 2.31, "lat": 48.87, "population": 36000, "type": "arrondissement"},
    "80001": {"code": "80001", "nom": "Abbeville", "departement": "80", "region": "32", "lon": 1.83, "lat": 50.1, "population": 23000, "type": "commune"},
    "80002": {"code": "80002", "nom": "Ablaincourt", "departement": "80", "region": "32", "lon": 2.8, "lat": 49.8, "population": 100, "type": "commune"},
}
DEPARTEMENTS = [{"code": "75", "nom": "Paris", "region": "11", "population": 2100000},
                {"code": "80", "nom": "Somme", "region": "32", "population": 570000}]
SECTIONS = {"O": {"libelle": "Administration publique"}, "J": {"libelle": "Information et communication"}}


def construire(organismes, sirene_commune=None, sirene_commune_section=None):
    sirene_commune = sirene_commune or {}
    sirene_commune_section = sirene_commune_section or {}
    meta = {"date_stock": "2026-09-01", "mesures": {"sieges_personnes_morales": 10, "sieges_actifs": 20}} if sirene_commune else None
    return build_dpo.construire(organismes, sirene_commune, sirene_commune_section, meta, DEPARTEMENTS, COMMUNES,
                                {"dataset": {"page": "p", "last_modified_source": "2026-07-06"}, "ressources": {"r": {"versions": [{}]}}}, [], SECTIONS)


class TestFonctionsPures(unittest.TestCase):
    def test_commune_parente(self):
        self.assertEqual(build_dpo.commune_parente("75108"), "75056")
        self.assertEqual(build_dpo.commune_parente("69383"), "69123")
        self.assertEqual(build_dpo.commune_parente("13201"), "13055")
        self.assertEqual(build_dpo.commune_parente("80001"), "80001")

    def test_departement_du_code(self):
        self.assertEqual(build_dpo.departement_du_code("97411"), "974")
        self.assertEqual(build_dpo.departement_du_code("2A004"), "2A")
        self.assertEqual(build_dpo.departement_du_code("80001"), "80")

    def test_taux(self):
        self.assertEqual(build_dpo.taux(5, 1000), 5.0)
        self.assertIsNone(build_dpo.taux(5, 0))


class TestConstruire(unittest.TestCase):
    def test_agregats(self):
        organismes = [
            designation(),
            designation(siren="200000001", nom="COMMUNE D'ABBEVILLE", nom_norm="COMMUNE D ABBEVILLE", code_postal="80100", code_insee="80001",
                        commune="Abbeville", departement="80", region="32", type_dpo="personne_morale", nom_designe="CDG 80", nom_designe_norm="CDG 80",
                        date_designation="2019-09-10"),
            designation(siren="300000001", nom="X", nom_norm="X", section_naf="J", code_naf="6201Z", code_postal="75008", code_insee="75108",
                        type_dpo="personne_morale", nom_designe="Cdg 80", nom_designe_norm="CDG 80", date_designation="2019-09-12"),
            designation(siren="400000001", nom="Y", nom_norm="Y", section_naf="", code_naf="", code_postal="", code_insee="", departement="",
                        region="", pays="US", ville_source="NEW YORK", date_designation="2020-01-01"),
        ]
        sirene_commune = {"75056": 900, "75108": 100, "80001": 50}
        sirene_section = {("75056", "O"): 10, ("75056", "J"): 200, ("75108", "J"): 100, ("80001", "O"): 2}
        stats, communes = construire(organismes, sirene_commune, sirene_section)

        c = stats["couverture"]
        self.assertEqual((c["nb_designations"], c["nb_france"], c["nb_communes_resolues"]), (4, 3, 3))
        self.assertEqual(c["sirene"]["date_stock"], "2026-09-01")
        self.assertEqual(stats["par_type"], {"personne_morale": 2, "personne_physique": 2})

        d75 = stats["departements"]["75"]
        self.assertEqual((d75["total"], d75["personne_morale"], d75["sieges_pm"]), (2, 1, 1000))
        self.assertEqual(d75["taux"], 2.0)
        self.assertEqual(d75["par_section"]["J"], {"n": 1, "sieges_pm": 300, "taux": round(1000 / 300, 2)})
        self.assertEqual(d75["structure_dominante"]["cle"], "CDG 80")
        self.assertEqual(stats["departements"]["80"]["structure_dominante"]["part_externes"], 1.0)

        self.assertEqual(stats["structures"][0]["cle"], "CDG 80")
        self.assertEqual(stats["structures"][0]["n"], 2)
        self.assertEqual(stats["structures"][0]["nom"], "CDG 80", "la graphie la plus fréquente, à égalité la première rencontrée")
        self.assertEqual(stats["nb_externes"], 2)

        self.assertEqual(stats["couverture_communes"]["80"], {"communes": 2, "declarantes": 1, "taux": 0.5})
        self.assertEqual(stats["par_pays"], [{"pays": "US", "n": 1}])
        self.assertEqual([m["mois"] for m in stats["par_mois"]], ["2018-05", "2019-09", "2020-01"])
        self.assertEqual(stats["par_annee"]["2019"], {"personne_morale": 2})
        self.assertEqual(stats["par_section"]["O"]["taux"], round(1000 * 2 / 12, 2))

        codes = {l[0]: l for l in communes["communes"]}
        self.assertEqual(set(codes), {"75056", "80001"}, "l'arrondissement est replié sur Paris")
        self.assertEqual(codes["75056"][5:], [2, 1, 1000])

    def test_sans_sirene(self):
        stats, _ = construire([designation()])
        self.assertIsNone(stats["couverture"]["sirene"])
        self.assertIsNone(stats["departements"]["75"]["taux"])

    def test_deterministe(self):
        organismes = [designation(siren=str(100000000 + i), nom_norm=f"N{i}") for i in range(20)]
        a = json.dumps(construire(organismes), sort_keys=True)
        b = json.dumps(construire(list(reversed(organismes))), sort_keys=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
