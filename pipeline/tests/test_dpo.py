"""Tests de dpo.py : reconnaissance des en-têtes, suppression des contacts,
normalisations (code postal, pays, date, type), résolution des communes.

Le référentiel des communes est un extrait construit en mémoire ; aucun
fichier du dépôt n'est lu, sauf la table des pays."""

import csv
import io
import tempfile
import unittest
from pathlib import Path

from pipeline import dpo, geocode
from pipeline.commun import RACINE, lire_json

ENTETE_SOURCE = [
    "SIREN organisme désignant", "Nom organisme désignant", "Secteur activité organisme désignant",
    "Code NAF organisme désignant", "Adresse postale organisme désignant", "Code postal organisme désignant",
    "Ville organisme désignant", "Pays organisme désignant", "Type de DPO", "Date de la désignation",
    "SIREN organisme désigné", "Nom organisme désigné", "Secteur activité organisme désigné",
    "Code NAF organisme désigné", "Adresse postale organisme désigné", "Code postal organisme désigné",
    "Ville organisme désigné", "Pays organisme désigné", "Moyen contact DPO email", "Moyen contact DPO url",
    "Moyen contact DPO téléphone", "Moyen contact DPO adresse postale", "Moyen contact DPO code postal",
    "Moyen contact DPO ville", "Moyen contact DPO pays", "Moyen contact DPO autre",
]


def ligne(**champs):
    """Une ligne source complète (26 champs), les absents vides."""
    defauts = {
        "siren": "110000122", "nom": "COMMISSION NATIONALE DE L'INFORMATIQUE ET DES LIBERTES", "section": "O",
        "naf": "8411Z", "adresse": "3 PLACE DE FONTENOY", "cp": "75007", "ville": "PARIS", "pays": "France",
        "type": "Personne physique", "date": "25/05/2018",
        "siren_d": "", "nom_d": "", "section_d": "", "naf_d": "", "adresse_d": "", "cp_d": "", "ville_d": "", "pays_d": "",
        "email": "dpo@exemple.fr", "url": "", "tel": "0153732222", "c_adresse": "", "c_cp": "", "c_ville": "", "c_pays": "", "autre": "",
    }
    defauts.update(champs)
    return list(defauts.values())


def tables_fictives():
    communes = {
        "_champs": ["code", "nom", "departement", "region", "lon", "lat", "population", "type"],
        "_extrait_le": "2026-09-11",
        "communes": [
            ["75056", "Paris", "75", "11", 2.3488, 48.8534, 2100000, "commune"],
            ["75108", "Paris 8e Arrondissement", "75", "11", 2.31, 48.87, 36000, "arrondissement"],
            ["2A004", "Ajaccio", "2A", "94", 8.7386, 41.9192, 70000, "commune"],
            ["2B033", "Bastia", "2B", "94", 9.45, 42.7, 48000, "commune"],
            ["97411", "Saint-Denis", "974", "04", 55.45, -20.88, 150000, "commune"],
            ["93066", "Saint-Denis", "93", "11", 2.3574, 48.9362, 112000, "commune"],
            ["92062", "Puteaux", "92", "11", 2.2389, 48.8846, 45000, "commune"],
            ["80001", "Abbeville", "80", "32", 1.8342, 50.1054, 23000, "commune"],
        ],
    }
    departements = {"75": {"code": "75", "region": "11"}, "2A": {"code": "2A", "region": "94"}, "2B": {"code": "2B", "region": "94"},
                    "974": {"code": "974", "region": "04"}, "93": {"code": "93", "region": "11"}, "92": {"code": "92", "region": "11"},
                    "80": {"code": "80", "region": "32"}}
    pays = lire_json(RACINE / "pipeline" / "mappings" / "pays.json")["pays"]
    alias = {("92", geocode.cle_ville("PARIS LA DEFENSE CEDEX")): {"code_insee": "92062"}}
    return {"referentiel": geocode.Referentiel(communes, departements), "pays": pays, "alias": alias}


def transformer(lignes):
    entete = [dpo.cle_normalisee(h) for h in ENTETE_SOURCE]
    return dpo.transformer(entete, lignes, "2026-07-06", tables_fictives())


class TestEntetes(unittest.TestCase):
    def test_signature_reconnue(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dpo.csv"
            tampon = io.StringIO(newline="")
            w = csv.writer(tampon, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
            w.writerow(ENTETE_SOURCE)
            w.writerow(ligne())
            p.write_text("﻿" + tampon.getvalue(), encoding="utf-8")
            entete, lignes = dpo.lire_brut(p)
        self.assertEqual(len(entete), 26)
        self.assertEqual(len(lignes), 1)

    def test_entete_inconnu_est_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dpo.csv"
            p.write_text(";".join(ENTETE_SOURCE[:-1] + ["Colonne nouvelle"]) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                dpo.lire_brut(p)


class TestTransformation(unittest.TestCase):
    def test_aucune_colonne_de_contact_en_sortie(self):
        s = transformer([ligne()])[0]
        for c in dpo.COLONNES:
            self.assertFalse(c.startswith("_contact"))
        self.assertNotIn("dpo@exemple.fr", "".join(str(v) for v in s.values()))
        self.assertNotIn("0153732222", "".join(str(v) for v in s.values()))
        self.assertEqual(len(dpo.COLONNES_CONTACT), 8)

    def test_normalisations_de_base(self):
        s = transformer([ligne()])[0]
        self.assertEqual(s["snapshot"], "2026-07-06")
        self.assertEqual(s["pays"], "FR")
        self.assertEqual(s["type_dpo"], "personne_physique")
        self.assertEqual(s["date_designation"], "2018-05-25")
        self.assertEqual(s["departement"], "75")
        self.assertEqual(s["code_insee"], "75056")
        self.assertEqual(s["region"], "11")
        self.assertEqual(s["nom_norm"], "COMMISSION NATIONALE DE L INFORMATIQUE ET DES LIBERTES")
        self.assertEqual(s["drapeaux"], "")

    def test_arrondissement_et_cedex(self):
        s = transformer([ligne(cp="75008", ville="PARIS 8"), ligne(cp="75008", ville="PARIS CEDEX 08")])
        self.assertEqual(s[0]["code_insee"], "75108")
        self.assertEqual(s[1]["code_insee"], "75056")

    def test_code_postal_a_quatre_chiffres(self):
        s = transformer([ligne(cp="2004", ville="AJACCIO")])[0]
        self.assertEqual(s["code_postal"], "02004")
        self.assertIn("code_postal_corrige", s["drapeaux"])

    def test_corse(self):
        s = {x["code_postal"]: x for x in transformer([ligne(cp="20000", ville="AJACCIO"), ligne(cp="20200", ville="BASTIA"), ligne(cp="20100", ville="INCONNUE")])}
        self.assertEqual({cp: x["departement"] for cp, x in s.items()}, {"20000": "2A", "20200": "2B", "20100": "2A"})
        self.assertIn("corse_departement_postal", s["20100"]["drapeaux"])

    def test_outre_mer_sur_trois_chiffres(self):
        s = transformer([ligne(cp="97400", ville="SAINT-DENIS")])[0]
        self.assertEqual(s["departement"], "974")
        self.assertEqual(s["code_insee"], "97411")

    def test_null_et_pays_deduit(self):
        s = transformer([ligne(pays="NULL", ville="null", cp="80100")])[0]
        self.assertEqual(s["ville_source"], "")
        self.assertEqual(s["pays"], "FR")
        self.assertIn("pays_deduit", s["drapeaux"])
        self.assertIn("ville_absente", s["drapeaux"])

    def test_pays_etranger(self):
        s = transformer([ligne(pays="ETATS-UNIS D'AMÉRIQUE", cp="CA 94080", ville="SOUTH SAN FRANCISCO")])[0]
        self.assertEqual(s["pays"], "US")
        self.assertEqual(s["departement"], "")
        self.assertEqual(s["code_insee"], "")
        self.assertEqual(s["code_postal"], "CA 94080")

    def test_pays_inconnu_signale(self):
        s = transformer([ligne(pays="ATLANTIDE")])[0]
        self.assertEqual(s["pays"], "")
        self.assertIn("pays_inconnu", s["drapeaux"])

    def test_alias_de_ville(self):
        s = transformer([ligne(cp="92400", ville="PARIS LA DEFENSE CEDEX")])[0]
        self.assertEqual(s["code_insee"], "92062")
        self.assertIn("alias", s["drapeaux"])

    def test_departement_contredit_par_ville(self):
        s = transformer([ligne(cp="75001", ville="ABBEVILLE")])[0]
        self.assertEqual(s["departement"], "80")
        self.assertIn("departement_contredit_par_ville", s["drapeaux"])

    def test_personne_morale_et_structure_designee(self):
        s = transformer([ligne(type="Personne morale", siren_d="878307073", nom_d="ACS RGPD", section_d="M", naf_d="6910Z", pays_d="France")])[0]
        self.assertEqual(s["type_dpo"], "personne_morale")
        self.assertEqual(s["nom_designe_norm"], "ACS RGPD")
        self.assertEqual(s["pays_designe"], "FR")

    def test_section_inconnue_et_siren_mal_forme(self):
        s = transformer([ligne(section="Z", siren="12345")])[0]
        self.assertEqual(s["section_naf"], "")
        self.assertIn("section_naf_inconnue", s["drapeaux"])
        self.assertIn("siren_mal_forme", s["drapeaux"])

    def test_tri_deterministe(self):
        a = transformer([ligne(siren="200000000", nom="B"), ligne(siren="100000000", nom="A"), ligne(siren="", nom="SANS SIREN")])
        self.assertEqual([x["siren"] for x in a], ["100000000", "200000000", ""])


if __name__ == "__main__":
    unittest.main()
