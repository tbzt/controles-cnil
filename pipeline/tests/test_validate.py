"""Tests de validate.py : chaque règle sur un contexte synthétique, puis
l'ensemble sur les données réelles (aucun constat fatal attendu)."""

import unittest

from pipeline import validate


def controle(**c):
    base = {"id": "2023-0123abcd-1", "annee": "2023", "fondement": "rgpd", "modalite": "sur_place",
            "organisme": "X", "secteur_source": "Commerce", "famille": "commerce", "qualite": ""}
    base.update(c)
    return base


def localisation(**l):
    base = {"id": "2023-0123abcd-1", "pays": "FR", "departement": "75", "org_lon": "2.3470", "org_lat": "48.8589",
            "org_precision": "commune", "ctrl_lieu": "organisme", "ctrl_lon": "2.3470", "ctrl_lat": "48.8589",
            "ctrl_precision": "commune"}
    base.update(l)
    return base


def contexte(**k):
    ctx = {
        "annee_courante": 2026, "manifeste": {"ressources": {}}, "fichiers_courants": [], "tables_transform": {"entetes": {}},
        "controles": [controle()], "localisations": [localisation()], "modalites": {"2023-0123abcd-1": "sur_place"},
        "secteurs": [{"secteur_source": "Commerce"}], "familles": [{"code": "commerce"}],
        "departements": [{"code": "75"}, {"code": "976"}], "surcouche": [], "propositions": [],
        "geocodage_rapport": {}, "totaux_officiels": {},
    }
    ctx.update(k)
    return ctx


def niveaux(constats):
    return [c.niveau for c in constats]


class TestRegles(unittest.TestCase):
    def test_identifiants_en_double_fatal(self):
        ctx = contexte(controles=[controle(), controle()])
        self.assertIn("fatal", niveaux(validate.regle_identifiants(ctx)))

    def test_identifiant_mal_forme_fatal(self):
        self.assertIn("fatal", niveaux(validate.regle_identifiants(contexte(controles=[controle(id="x")]))))

    def test_champs_obligatoires(self):
        ok = validate.regle_champs_obligatoires(contexte())
        self.assertEqual(niveaux(ok), ["ok"])
        lignes = [controle(id=f"2023-0000000{i}-1") for i in range(10)]
        lignes[0]["organisme"] = ""
        self.assertIn("fatal", niveaux(validate.regle_champs_obligatoires(contexte(controles=lignes))))
        lignes = [controle(id=f"2023-{i:08d}-1") for i in range(200)]
        lignes[0]["secteur_source"] = ""
        self.assertEqual(niveaux(validate.regle_champs_obligatoires(contexte(controles=lignes))), ["alerte"])

    def test_volume(self):
        peu = [controle(id=f"2023-{i:08d}-1") for i in range(5)]
        self.assertIn("fatal", niveaux(validate.regle_volume(contexte(controles=peu))))
        assez = [controle(id=f"2023-{i:08d}-1") for i in range(300)]
        self.assertEqual(niveaux(validate.regle_volume(contexte(controles=assez, totaux_officiels={2023: 300}))), ["ok"])
        self.assertEqual(niveaux(validate.regle_volume(contexte(controles=assez, totaux_officiels={2023: 310}))), ["alerte"])
        self.assertEqual(niveaux(validate.regle_volume(contexte(controles=assez, totaux_officiels={2023: 400}))), ["alerte"])

    def test_annees(self):
        self.assertEqual(niveaux(validate.regle_annees(contexte())), ["ok"])
        self.assertIn("fatal", niveaux(validate.regle_annees(contexte(controles=[controle(annee="2031")]))))
        self.assertIn("fatal", niveaux(validate.regle_annees(contexte(controles=[controle(annee="2009")]))))

    def test_enumerations(self):
        self.assertEqual(niveaux(validate.regle_enumerations(contexte())), ["ok"])
        self.assertIn("fatal", niveaux(validate.regle_enumerations(contexte(controles=[controle(fondement="autre")]))))
        self.assertIn("fatal", niveaux(validate.regle_enumerations(contexte(controles=[controle(secteur_source="Inédit")]))))
        self.assertIn("fatal", niveaux(validate.regle_enumerations(contexte(controles=[controle(famille="inedite")]))))

    def test_doublons_alerte(self):
        self.assertEqual(niveaux(validate.regle_doublons(contexte(controles=[controle(qualite="ligne_dupliquee")]))), ["alerte"])

    def test_coordonnees(self):
        self.assertEqual(niveaux(validate.regle_coordonnees(contexte())), ["ok"])
        self.assertIn("fatal", niveaux(validate.regle_coordonnees(contexte(localisations=[localisation(org_lon="0", org_lat="0")]))))
        self.assertIn("fatal", niveaux(validate.regle_coordonnees(contexte(localisations=[localisation(org_lon="200", org_lat="0")]))))
        # Point « France » en Amérique : fatal.
        self.assertIn("fatal", niveaux(validate.regle_coordonnees(contexte(localisations=[localisation(org_lon="-73.5", org_lat="45.5", ctrl_lon="-73.5", ctrl_lat="45.5")]))))
        # Mayotte dans l'emprise de Mayotte : ok ; et le siège de la CNIL reste en métropole même pour un organisme à Mayotte.
        mayotte = localisation(departement="976", org_lon="45.1964", org_lat="-12.7875", ctrl_lieu="cnil",
                               ctrl_lon="2.307276", ctrl_lat="48.850654", ctrl_precision="institution")
        self.assertEqual(niveaux(validate.regle_coordonnees(contexte(localisations=[mayotte]))), ["ok"])
        # Organisme étranger : pas de contrainte d'emprise.
        self.assertEqual(niveaux(validate.regle_coordonnees(contexte(localisations=[localisation(pays="US", org_lon="-95.7", org_lat="37.1", org_precision="pays", ctrl_lon="-95.7", ctrl_lat="37.1", ctrl_precision="pays")]))), ["ok"])

    def test_geocodage_seuil(self):
        locs = [localisation(id=f"2023-{i:08d}-1", org_precision="departement") for i in range(10)]
        self.assertIn("fatal", niveaux(validate.regle_geocodage(contexte(localisations=locs))))
        self.assertEqual(niveaux(validate.regle_geocodage(contexte()))[0], "ok")
        rapport = {"villes_non_resolues": [{"departement_source": "33", "ville_source": "INCONNUE", "occurrences": 1}]}
        self.assertIn("alerte", niveaux(validate.regle_geocodage(contexte(geocodage_rapport=rapport))))

    def test_coherence_temporelle(self):
        self.assertEqual(niveaux(validate.regle_coherence_temporelle(contexte())), ["ok"])
        self.assertIn("alerte", niveaux(validate.regle_coherence_temporelle(contexte(controles=[controle(annee="2016", fondement="rgpd")]))))
        self.assertIn("alerte", niveaux(validate.regle_coherence_temporelle(contexte(controles=[controle(annee="2021", fondement="loi78")]))))

    def test_localisations_completes(self):
        self.assertEqual(niveaux(validate.regle_localisations_completes(contexte())), ["ok"])
        self.assertIn("fatal", niveaux(validate.regle_localisations_completes(contexte(localisations=[]))))
        ctx = contexte(localisations=[localisation(ctrl_lieu="cnil")])
        self.assertIn("fatal", niveaux(validate.regle_localisations_completes(ctx)))

    def test_surcouche_orpheline(self):
        ctx = contexte(surcouche=[{"id": "2019-deadbeef-1", "statut": "valide"}])
        self.assertEqual(niveaux(validate.regle_surcouche(ctx)), ["alerte"])

    def test_totaux_officiels(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.csv"
            p.write_bytes("﻿Année ;2021;2022;2022;2023\r\nContrôles réalisés;384;345;345;342\r\nDont vidéo;;;;13\r\n".encode("utf-8"))
            self.assertEqual(validate.totaux_officiels(p), {2021: 384, 2022: 345, 2023: 342})
        self.assertEqual(validate.totaux_officiels(None), {})

    def test_rapport_resultat(self):
        r = validate.rapport([validate.ok("a", "x"), validate.alerte("b", "y")])
        self.assertEqual((r["resultat"], r["nb_alerte"], r["nb_ok"]), ("alerte", 1, 1))
        self.assertEqual(validate.rapport([validate.fatal("a", "x")])["resultat"], "fatal")


class TestDonneesReelles(unittest.TestCase):
    def test_aucun_constat_fatal(self):
        ctx = validate.charger_contexte(annee_courante=2026)
        if not ctx["controles"]:
            self.skipTest("données absentes")
        constats = validate.valider(ctx)
        fatals = [c.message for c in constats if c.niveau == "fatal"]
        self.assertEqual(fatals, [])


if __name__ == "__main__":
    unittest.main()
