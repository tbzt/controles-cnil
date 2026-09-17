"""Tests de outils/agreger-sirene.py : section NAF, date du stock, lecture
d'un zip minimal, comptage des sièges de personnes morales."""

import csv
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from pipeline.commun import RACINE

spec = importlib.util.spec_from_file_location("agreger_sirene", RACINE / "outils" / "agreger-sirene.py")
sirene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sirene)


def zip_csv(chemin: Path, entete: list[str], lignes: list[list[str]]) -> Path:
    tampon = io.StringIO(newline="")
    w = csv.writer(tampon, lineterminator="\n")
    w.writerow(entete)
    w.writerows(lignes)
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("stock.csv", tampon.getvalue())
    return chemin


class TestFonctionsPures(unittest.TestCase):
    def test_section_naf(self):
        self.assertEqual(sirene.section_naf("8411Z"), "O")
        self.assertEqual(sirene.section_naf("0111Z"), "A")
        self.assertEqual(sirene.section_naf("6910Z"), "M")
        self.assertEqual(sirene.section_naf("9900Z"), "U")
        self.assertEqual(sirene.section_naf("4711D"), "G")
        self.assertEqual(sirene.section_naf(""), "")
        self.assertEqual(sirene.section_naf("3400Z"), "")  # division 34 n'existe pas

    def test_date_stock(self):
        self.assertEqual(sirene.date_stock("Sirene : Fichier StockUniteLegale - 01 septembre 2026"), "2026-09-01")
        self.assertEqual(sirene.date_stock("Sirene : Fichier StockEtablissement - 1er février 2027 (format parquet)"), "2027-02-01")
        self.assertEqual(sirene.date_stock("sans date"), "")

    def test_bits(self):
        b = sirene.Bits()
        b.poser("110000122")
        self.assertIn("110000122", b)
        self.assertNotIn("110000123", b)
        self.assertEqual(b.n, 1)


class TestPasses(unittest.TestCase):
    def test_comptage_sieges_personnes_morales(self):
        with tempfile.TemporaryDirectory() as tmp:
            ul = zip_csv(Path(tmp) / "ul.zip", ["siren", "etatAdministratifUniteLegale", "categorieJuridiqueUniteLegale"], [
                ["100000001", "A", "5710"],   # SAS active
                ["100000002", "A", "1000"],   # entrepreneur individuel actif
                ["100000003", "C", "5710"],   # cessée
                ["100000004", "A", "7210"],   # commune
            ])
            etab = zip_csv(Path(tmp) / "etab.zip", ["siren", "etablissementSiege", "etatAdministratifEtablissement", "codeCommuneEtablissement", "activitePrincipaleEtablissement"], [
                ["100000001", "true", "A", "75108", "6201Z"],
                ["100000001", "false", "A", "75108", "6201Z"],  # établissement secondaire, ignoré
                ["100000002", "true", "A", "75108", "6201Z"],
                ["100000003", "true", "A", "75108", "6201Z"],   # UL cessée, ignorée
                ["100000004", "true", "A", "80001", "8411Z"],
                ["100000004", "true", "F", "80001", "8411Z"],   # établissement fermé, ignoré
            ])
            actives, morales = sirene.passe_unites_legales(ul)
            self.assertEqual((actives.n, morales.n), (3, 2))
            total, pm, mesures = sirene.passe_etablissements(etab, actives, morales)
        self.assertEqual(total[("75108", "J")], 2)
        self.assertEqual(pm[("75108", "J")], 1)
        self.assertEqual(total[("80001", "O")], 1)
        self.assertEqual(pm[("80001", "O")], 1)
        self.assertEqual(mesures["sieges_actifs"], 3)

    def test_colonne_absente_est_fatale(self):
        with tempfile.TemporaryDirectory() as tmp:
            ul = zip_csv(Path(tmp) / "ul.zip", ["siren", "etat"], [["1", "A"]])
            with self.assertRaises(SystemExit):
                sirene.passe_unites_legales(ul)


if __name__ == "__main__":
    unittest.main()
