"""Tests de transform.py.

Deux familles : des cas construits en mémoire (encodages, en-têtes, lignes
parasites, identifiants) et une vérification sur les fichiers réels archivés
dans data/raw/, qui fixe les volumes attendus par année.
"""

import unittest
from collections import Counter

from pipeline import transform
from pipeline.commun import METADATA, lire_json

TABLES = transform.charger_tables()


def csv_2014(*lignes):
    tete = "Année;Type de contrôle;Nom de l'organisme contrôlé ou nom de domaine;Lieu de contrôle;Département;Secteur d'activité"
    return ("﻿" + tete + "\r\n" + "\r\n".join(lignes) + "\r\n").encode("utf-8")


def csv_2023(*lignes):
    tete = 'Catégorie de contrôle;Organismes contrôlés;"Modalité\n de contrôle";Dépt.;Ville;Pays;"Activité\n de l\'organisme";;;'
    return (tete + "\r\n" + "\r\n".join(lignes) + "\r\n").encode("cp1252")


class TestLecture(unittest.TestCase):
    def test_utf8_bom_et_colonnes_ordinaires(self):
        enr, rejets = transform.transformer_fichier(
            csv_2014("2014;Loi 1978;Groupon France;Paris;75;Commerce"), "t.csv", 2014, TABLES)
        self.assertEqual(rejets, [])
        e = enr[0]
        self.assertEqual((e["fondement"], e["modalite"], e["organisme"], e["departement"], e["pays"]),
                         ("loi78", "non_renseignee", "Groupon France", "75", "FR"))
        self.assertIn("pays_deduit", e["qualite"])
        self.assertIn("modalite_non_renseignee", e["qualite"])
        self.assertEqual(e["source_ligne"], 2)

    def test_cp1252_entetes_multilignes_et_colonnes_vides_excel(self):
        enr, rejets = transform.transformer_fichier(
            csv_2023("RGPD;GAMELOFT;en ligne;75;PARIS;FRANCE;Commerce;;;",
                     "VIDEOPROTECTION;COMMUNE DE NÎMES;sur place;30;NÎMES;FRANCE;Collectivités territoriales;;;"),
            "t.csv", 2023, TABLES)
        self.assertEqual(len(enr), 2)
        self.assertEqual(enr[0]["modalite"], "en_ligne")
        self.assertEqual(enr[1]["fondement"], "videoprotection")
        self.assertEqual(enr[1]["organisme"], "COMMUNE DE NÎMES")
        self.assertIn("annee_source_absente", enr[0]["qualite"])

    def test_modalite_deduite_du_type_2015(self):
        octets = ("Année;Type de contrôle;Organismes;Lieu de contrôle;Département;\"Secteur d'activité \nde l'organisme\"\r\n"
                  "2015;contrôle en ligne;ONLINE.NET;Paris;75;Télécommunications\r\n").encode("cp1252")
        enr, _ = transform.transformer_fichier(octets, "t.csv", 2015, TABLES)
        self.assertEqual((enr[0]["fondement"], enr[0]["modalite"]), ("loi78", "en_ligne"))
        self.assertIn("modalite_deduite_du_type", enr[0]["qualite"])

    def test_ligne_parasite_rejetee(self):
        octets = ("Type de contrôle;Modalité de contrôle;Organismes;Département;Lieu;Secteur d'activité\r\n"
                  "LOI 78;sur place;YATEDO;75;PARIS;Commerce\r\n"
                  "341;;;;;\r\n").encode("utf-8")
        enr, rejets = transform.transformer_fichier(octets, "t.csv", 2017, TABLES)
        self.assertEqual(len(enr), 1)
        self.assertEqual(len(rejets), 1)
        self.assertEqual(rejets[0]["source_ligne"], 3)

    def test_colonne_vide_en_tete_2016(self):
        octets = ("﻿;Année;Type de contrôle;Organismes;Lieu de contrôle;Département;Secteur d'activité de l'organisme;;\r\n"
                  ";2016;loi 78;CARREFOUR BANQUE;COURCOURONNES;91;Commerce;;\r\n").encode("utf-8")
        enr, _ = transform.transformer_fichier(octets, "t.csv", 2016, TABLES)
        self.assertEqual(enr[0]["organisme"], "CARREFOUR BANQUE")

    def test_organisme_multiligne_nettoye_et_norm(self):
        enr, _ = transform.transformer_fichier(
            csv_2014('2014;Loi 1978;"MINISTÈRE DE LA JUSTICE \n- FIJAISV";Paris;75;Police/justice/sécurité'),
            "t.csv", 2014, TABLES)
        self.assertEqual(enr[0]["organisme"], "MINISTÈRE DE LA JUSTICE - FIJAISV")
        self.assertEqual(enr[0]["organisme_norm"], "MINISTERE DE LA JUSTICE FIJAISV")
        self.assertIn("organisme_multiligne", enr[0]["qualite"])

    def test_departements(self):
        for brut, attendu, drapeau in (("6", "06", "departement_corrige"), ("75-92", "75", "departement_multiple"),
                                       ("20", "20", "departement_a_preciser"), ("", "", "departement_vide"),
                                       ("2A", "2A", None), ("974", "974", None), ("ZZ", "ZZ", "departement_invalide")):
            d, dr = transform.normaliser_departement(brut)
            self.assertEqual(d, attendu)
            if drapeau:
                self.assertIn(drapeau, dr)
            else:
                self.assertEqual(dr, [])

    def test_identifiants_stables_et_doublons_distingues(self):
        octets = csv_2014("2014;Loi 1978;OPTICAL CENTER;Paris;75;Commerce",
                          "2014;Loi 1978;OPTICAL CENTER;Paris;75;Commerce",
                          "2014;Loi 1978;AUTRE;Lyon;69;Commerce")
        enr, _ = transform.transformer_fichier(octets, "t.csv", 2014, TABLES)
        self.assertEqual(enr[0]["id"][:-2], enr[1]["id"][:-2])
        self.assertTrue(enr[0]["id"].endswith("-1") and enr[1]["id"].endswith("-2"))
        self.assertIn("ligne_dupliquee", enr[1]["qualite"])
        self.assertNotIn("ligne_dupliquee", enr[0]["qualite"])
        # Même contenu, autre ordre : mêmes identifiants (le hachage ne dépend pas de la position).
        enr2, _ = transform.transformer_fichier(csv_2014("2014;Loi 1978;AUTRE;Lyon;69;Commerce"), "t.csv", 2014, TABLES)
        self.assertEqual(enr2[0]["id"], enr[2]["id"])

    def test_cle_organisme(self):
        alias = {"FACEBOOK IRELAND": "FACEBOOK"}
        for brut, attendu in (("CDISCOUNT FR", "CDISCOUNT"), ("CDISCOUNT COM", "CDISCOUNT"), ("ACCOR SA", "ACCOR"),
                              ("SARL MORGANE", "MORGANE"), ("BOUYGUES TELECOM S A", "BOUYGUES TELECOM"),
                              ("WWW REDON FR", "REDON"), ("FACEBOOK IRELAND", "FACEBOOK"), ("SOCIETE GENERALE", "SOCIETE GENERALE"),
                              ("FR", "FR"), ("UNSA ORG", "UNSA")):
            self.assertEqual(transform.cle_organisme(brut, alias), attendu, brut)

    def test_entete_inconnu_est_fatal(self):
        octets = "Année;Type de contrôle;Organisme;Ville;Département;Secteur\r\n2014;Loi 1978;X;Paris;75;Commerce\r\n".encode("utf-8")
        with self.assertRaises(SystemExit):
            transform.transformer_fichier(octets, "t.csv", 2014, TABLES)

    def test_secteur_inconnu_est_fatal(self):
        with self.assertRaises(SystemExit):
            transform.transformer_fichier(csv_2014("2014;Loi 1978;X;Paris;75;Secteur jamais vu"), "t.csv", 2014, TABLES)

    def test_type_inconnu_est_fatal(self):
        with self.assertRaises(SystemExit):
            transform.transformer_fichier(csv_2014("2014;NOUVEAU TYPE;X;Paris;75;Commerce"), "t.csv", 2014, TABLES)

    def test_annee_incoherente_est_fatale(self):
        with self.assertRaises(SystemExit):
            transform.transformer_fichier(csv_2014("2015;Loi 1978;X;Paris;75;Commerce"), "t.csv", 2014, TABLES)

    def test_separateur_virgule_est_fatal(self):
        octets = "Année,Type de contrôle,Organismes,Lieu,Département,Secteur d'activité\r\n2014,Loi 1978,X,Paris,75,Commerce\r\n".encode("utf-8")
        with self.assertRaises(SystemExit):
            transform.transformer_fichier(octets, "t.csv", 2014, TABLES)


class TestDonneesReelles(unittest.TestCase):
    """Volumes attendus sur les fichiers archivés. À mettre à jour, en
    connaissance de cause, quand la CNIL publie ou corrige une année."""

    ATTENDU = {2014: 421, 2015: 496, 2016: 430, 2017: 341, 2018: 310,
               2019: 301, 2020: 247, 2021: 384, 2022: 345, 2023: 342}

    @classmethod
    def setUpClass(cls):
        manifeste = lire_json(METADATA / "manifest.json")
        if not manifeste:
            raise unittest.SkipTest("manifeste absent")
        cls.resultats = {}
        cls.rejets = []
        for annee, chemin in transform.fichiers_courants(manifeste):
            enr, rej = transform.transformer_fichier(chemin.read_bytes(), chemin.name, annee, TABLES)
            cls.resultats[annee] = enr
            cls.rejets += rej

    def test_volumes_par_annee(self):
        self.assertEqual({a: len(e) for a, e in self.resultats.items()}, self.ATTENDU)

    def test_deux_lignes_parasites_seulement(self):
        self.assertEqual(sorted(r["source_fichier"][-8:-4] for r in self.rejets), ["2017", "2018"])

    def test_identifiants_uniques(self):
        ids = [e["id"] for enr in self.resultats.values() for e in enr]
        self.assertEqual(len(ids), len(set(ids)))

    def test_modalite_presente_a_partir_de_2017(self):
        for annee, enr in self.resultats.items():
            manquantes = sum(1 for e in enr if e["modalite"] == "non_renseignee")
            if annee >= 2017:
                self.assertEqual(manquantes, 0, annee)
            else:
                self.assertGreater(manquantes, 0, annee)

    def test_secteur_et_famille_toujours_renseignes(self):
        for enr in self.resultats.values():
            for e in enr:
                self.assertTrue(e["secteur"] and e["famille"], e["id"])

    def test_pays_hors_france_depuis_2021(self):
        hors = Counter(e["annee"] for enr in self.resultats.values() for e in enr if e["pays"] != "FR")
        self.assertEqual(set(hors), {2021, 2022, 2023})
        self.assertEqual(sum(hors.values()), 46)


if __name__ == "__main__":
    unittest.main()
