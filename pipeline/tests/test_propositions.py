"""Tests des fonctions pures de outils/proposer-adresses.py (classement des
réponses de l'annuaire des entreprises). Aucun appel réseau."""

import importlib.util
import unittest
from pathlib import Path

CHEMIN = Path(__file__).resolve().parents[2] / "outils" / "proposer-adresses.py"
spec = importlib.util.spec_from_file_location("proposer_adresses", CHEMIN)
pa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pa)


def entite(nom, siren, commune_siege, lon=2.33, lat=48.86, etablissements=()):
    return {
        "nom_complet": nom, "nom_raison_sociale": nom, "siren": siren,
        "siege": {"commune": commune_siege, "siret": siren + "00011", "adresse": f"1 RUE X {commune_siege}",
                  "longitude": str(lon), "latitude": str(lat)},
        "matching_etablissements": [
            {"commune": c, "siret": siren + "00022", "adresse": f"2 RUE Y {c}", "longitude": "1.0", "latitude": "44.0",
             "liste_enseignes": []} for c in etablissements],
    }


class TestFiltres(unittest.TestCase):
    def test_interrogeable(self):
        self.assertTrue(pa.interrogeable("GAMELOFT"))
        self.assertTrue(pa.interrogeable("COMMUNE DE NÎMES"))
        for nom in ("www.ville-evian.fr", "APEC.FR", "GHAZLI.COM", "PARTICULIER", "AUDITION MONSIEUR B...", "M."):
            self.assertFalse(pa.interrogeable(nom), nom)

    def test_nettoyer_requete(self):
        self.assertEqual(pa.nettoyer_requete("MONDIAL ASSISTANCE FRANCE SAS- PARIS (75)"), "MONDIAL ASSISTANCE FRANCE SAS")
        self.assertEqual(pa.nettoyer_requete("CGI FRANCE - COURBEVOIE (92)"), "CGI FRANCE")

    def test_coord(self):
        self.assertEqual(pa.coord("2.5"), 2.5)
        self.assertIsNone(pa.coord("[NON-DIFFUSIBLE]"))
        self.assertIsNone(pa.coord(None))

    def test_meme_commune_arrondissements(self):
        self.assertTrue(pa.meme_commune("75108", "75056"))
        self.assertTrue(pa.meme_commune("69383", "69123"))
        self.assertTrue(pa.meme_commune("13201", "13055"))
        self.assertTrue(pa.meme_commune("92026", "92026"))
        self.assertFalse(pa.meme_commune("92026", "92062"))
        self.assertFalse(pa.meme_commune("", "92026"))


class TestClassement(unittest.TestCase):
    def test_haut_siege_unique_nom_identique(self):
        p = pa.classer("GAMELOFT", "75056", [entite("GAMELOFT SE", "429338130", "75109")])
        self.assertEqual((p["niveau"], p["methode"], p["siren"]), ("haut", "siege", "429338130"))
        self.assertGreaterEqual(p["score"], 0.97)

    def test_moyen_si_seulement_un_etablissement_dans_la_commune(self):
        p = pa.classer("CARREFOUR", "33063", [entite("CARREFOUR HYPERMARCHES", "451321335", "91228", etablissements=("33063",))])
        self.assertEqual((p["niveau"], p["methode"]), ("moyen", "etablissement"))

    def test_moyen_si_nom_seulement_proche(self):
        p = pa.classer("AMAZON", "75056", [entite("AMAZONE", "422342337", "75109")])
        self.assertEqual(p["niveau"], "moyen")

    def test_moyen_si_plusieurs_homonymes_au_siege(self):
        p = pa.classer("ALAN", "75056", [entite("ALAN", "1", "75110"), entite("ALAN", "2", "75111")])
        self.assertEqual(p["niveau"], "moyen")
        self.assertIn("homonymes", p["commentaire"])

    def test_rien_si_siege_ailleurs_et_pas_d_etablissement(self):
        self.assertIsNone(pa.classer("CARREFOUR", "33063", [entite("CARREFOUR HYPERMARCHES", "451321335", "91228")]))

    def test_rien_si_nom_trop_eloigne(self):
        self.assertIsNone(pa.classer("GAMELOFT", "75056", [entite("SOCIETE GENERALE", "552120222", "75109")]))

    def test_coordonnees_non_diffusibles_ignorees(self):
        e = entite("GAMELOFT", "429338130", "75109")
        e["siege"]["longitude"] = "[NON-DIFFUSIBLE]"
        self.assertIsNone(pa.classer("GAMELOFT", "75056", [e]))

    def test_forme_juridique_ignoree_dans_la_similarite(self):
        self.assertGreaterEqual(pa.similarite("ACCOR", entite("ACCOR SA", "1", "92040")), 0.92)


if __name__ == "__main__":
    unittest.main()
