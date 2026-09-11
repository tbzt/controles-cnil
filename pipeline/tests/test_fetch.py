"""Tests de fetch.py : décisions de téléchargement, nommage, idempotence.

Aucun accès réseau : le téléchargeur est remplacé par une fonction qui sert
des octets en mémoire.
"""

import tempfile
import unittest
from pathlib import Path

from pipeline import fetch


def ressource(rid, titre, url, last_modified="2024-10-18T08:47:41", fmt="csv", checksum="abc"):
    return {
        "id": rid, "title": titre, "url": url, "format": fmt,
        "last_modified": last_modified, "filesize": 123,
        "checksum": {"type": "sha1", "value": checksum},
    }


def dataset(*ressources):
    return {"id": "d", "title": "Contrôles", "page": "p", "license": "fr-lo",
            "organization": {"name": "CNIL"}, "last_modified": "2024-10-18",
            "resources": list(ressources)}


class TelechargeurFictif:
    def __init__(self, contenus):
        self.contenus = contenus
        self.appels = []

    def __call__(self, url):
        self.appels.append(url)
        return self.contenus[url]


class TestFonctionsPures(unittest.TestCase):
    def test_annee_depuis_le_nom_de_fichier(self):
        r = ressource("1", "Liste des contrôles réalisés par la CNIL en 2014",
                      "https://x/OpenCNIL_Liste_controles_2014_VD_20150604.csv")
        self.assertEqual(fetch.annee_de(r), "2014")

    def test_annee_depuis_le_titre_si_absente_du_nom(self):
        r = ressource("1", "Liste 2017", "https://x/liste.csv")
        self.assertEqual(fetch.annee_de(r), "2017")

    def test_tableau_1990(self):
        r = ressource("1", "x", "https://x/opencnil-nombre-controles-depuis-1990-maj-oct-2024.csv")
        self.assertEqual(fetch.annee_de(r), "nombre-controles-1990")

    def test_nom_original_decode(self):
        r = ressource("1", "x", "https://x/a/b/Liste%20contr%C3%B4les%202016.csv")
        self.assertEqual(fetch.nom_original(r), "Liste contrôles 2016.csv")

    def test_nom_fichier_brut(self):
        r = ressource("1", "x", "https://x/fichier.csv")
        self.assertEqual(fetch.nom_fichier_brut(r, "0123456789abcdef"), "01234567__fichier.csv")

    def test_doit_telecharger(self):
        r = ressource("1", "x", "https://x/f.csv")
        self.assertTrue(fetch.doit_telecharger(None, r, False))
        entree = {"versions": [{"sha256": "s"}], "signature_source": fetch.signature_source(r)}
        self.assertFalse(fetch.doit_telecharger(entree, r, False))
        self.assertTrue(fetch.doit_telecharger(entree, r, True))
        r2 = dict(r, last_modified="2025-01-01")
        self.assertTrue(fetch.doit_telecharger(entree, r2, False))


class TestTraitement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "raw"

    def tearDown(self):
        self.tmp.cleanup()

    def test_premiere_execution_archive_les_csv_et_ignore_les_xlsx(self):
        r_csv = ressource("a", "Liste 2023", "https://x/liste-2023.csv")
        r_xlsx = ressource("b", "Liste 2023 xlsx", "https://x/liste-2023.xlsx", fmt="xlsx")
        tel = TelechargeurFictif({"https://x/liste-2023.csv": b"a;b\n1;2\n"})
        manifeste = {}
        resume = fetch.traiter(dataset(r_csv, r_xlsx), manifeste, tel, "2026-09-11", racine_raw=self.raw)
        self.assertEqual(resume["nouvelles"], ["Liste 2023"])
        self.assertEqual(resume["ignorees_non_csv"], ["Liste 2023 xlsx"])
        entree = manifeste["ressources"]["a"]
        self.assertEqual(entree["dossier"], "2023")
        self.assertEqual(len(entree["versions"]), 1)
        fichier = self.raw / entree["versions"][0]["fichier"]
        self.assertTrue(fichier.exists())
        self.assertEqual(fichier.read_bytes(), b"a;b\n1;2\n")
        self.assertEqual(entree["versions"][0]["recupere_le"], "2026-09-11")

    def test_deuxieme_execution_sans_changement_ne_telecharge_rien(self):
        r = ressource("a", "Liste 2023", "https://x/liste-2023.csv")
        tel = TelechargeurFictif({"https://x/liste-2023.csv": b"x"})
        manifeste = {}
        fetch.traiter(dataset(r), manifeste, tel, "2026-09-11", racine_raw=self.raw)
        avant = repr(manifeste)
        resume = fetch.traiter(dataset(r), manifeste, tel, "2026-09-18", racine_raw=self.raw)
        self.assertEqual(resume["inchangees"], ["Liste 2023"])
        self.assertEqual(len(tel.appels), 1)
        self.assertEqual(repr(manifeste), avant)

    def test_ressource_modifiee_ajoute_une_version_sans_ecraser(self):
        r1 = ressource("a", "Liste 2022", "https://x/liste-2022.csv", last_modified="2023-06-22")
        r2 = ressource("a", "Liste 2022", "https://x/liste-2022-v2.csv", last_modified="2023-10-03")
        tel = TelechargeurFictif({"https://x/liste-2022.csv": b"v1", "https://x/liste-2022-v2.csv": b"v2"})
        manifeste = {}
        fetch.traiter(dataset(r1), manifeste, tel, "2023-07-01", racine_raw=self.raw)
        resume = fetch.traiter(dataset(r2), manifeste, tel, "2023-10-10", racine_raw=self.raw)
        self.assertEqual(resume["modifiees"], ["Liste 2022"])
        versions = manifeste["ressources"]["a"]["versions"]
        self.assertEqual(len(versions), 2)
        self.assertTrue((self.raw / versions[0]["fichier"]).exists(), "l'ancienne version reste archivée")
        self.assertTrue((self.raw / versions[1]["fichier"]).exists())

    def test_forcer_retelecharge_mais_ne_duplique_pas_un_contenu_identique(self):
        r = ressource("a", "Liste 2023", "https://x/liste-2023.csv")
        tel = TelechargeurFictif({"https://x/liste-2023.csv": b"x"})
        manifeste = {}
        fetch.traiter(dataset(r), manifeste, tel, "2026-09-11", racine_raw=self.raw)
        resume = fetch.traiter(dataset(r), manifeste, tel, "2026-09-18", forcer=True, racine_raw=self.raw)
        self.assertEqual(resume["identiques_apres_telechargement"], ["Liste 2023"])
        self.assertEqual(len(manifeste["ressources"]["a"]["versions"]), 1)
        self.assertEqual(len(list(self.raw.rglob("*.csv"))), 1)

    def test_ressource_disparue_est_marquee_pas_supprimee(self):
        r = ressource("a", "Liste 2023", "https://x/liste-2023.csv")
        tel = TelechargeurFictif({"https://x/liste-2023.csv": b"x"})
        manifeste = {}
        fetch.traiter(dataset(r), manifeste, tel, "2026-09-11", racine_raw=self.raw)
        resume = fetch.traiter(dataset(), manifeste, tel, "2026-09-18", racine_raw=self.raw)
        self.assertEqual(resume["disparues"], ["Liste 2023"])
        self.assertEqual(manifeste["ressources"]["a"]["disparue_le"], "2026-09-18")
        self.assertTrue((self.raw / manifeste["ressources"]["a"]["versions"][0]["fichier"]).exists())


if __name__ == "__main__":
    unittest.main()
