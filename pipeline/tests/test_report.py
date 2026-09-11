"""Tests de report.py (comparaison d'états) et de verification.py."""

import unittest

from pipeline import report, verification

ENTETE_C = "id,annee,fondement,fondement_source,modalite,modalite_source,organisme,organisme_norm,ville_source,departement,departement_source,pays,pays_source,secteur,famille,secteur_source,source_fichier,source_ligne,qualite\n"
ENTETE_L = "id,pays,code_insee,commune,departement,region,org_lon,org_lat,org_precision,org_methode,org_adresse,org_source,ctrl_lieu,ctrl_lon,ctrl_lat,ctrl_precision,drapeaux\n"


def controle(i, annee="2023", secteur="Commerce"):
    return f"2023-{i:08x}-1,{annee},rgpd,RGPD,sur_place,sur place,X,X,PARIS,75,75,FR,FRANCE,commerce,commerce,{secteur},f.csv,{i},\n"


def localisation(i, precision="commune"):
    return f"2023-{i:08x}-1,FR,75056,Paris,75,11,2.3470,48.8589,{precision},referentiel_communes,,src,organisme,2.3470,48.8589,{precision},\n"


def etat(n, precision="commune", secteur="Commerce", manifest='{"ressources": {}}', qualite='{"resultat": "ok", "nb_fatal": 0, "nb_alerte": 0, "constats": []}'):
    return {
        "controles.csv": ENTETE_C + "".join(controle(i, secteur=secteur) for i in range(n)),
        "localisations.csv": ENTETE_L + "".join(localisation(i, precision) for i in range(n)),
        "manifest.json": manifest,
        "quality-report.json": qualite,
    }


class TestComparer(unittest.TestCase):
    def test_aucun_changement(self):
        d = report.comparer(etat(3), etat(3))
        self.assertFalse(d["donnees_changees"])
        self.assertEqual((d["controles"]["ajoutes"], d["controles"]["retires"]), (0, 0))
        self.assertIn("Aucun changement", report.en_markdown(d, "2026-09-11", "t"))

    def test_lignes_ajoutees(self):
        d = report.comparer(etat(3), etat(5))
        self.assertTrue(d["donnees_changees"])
        self.assertEqual(d["controles"]["ajoutes"], 2)
        self.assertEqual(d["controles"]["ajoutes_par_annee"], {"2023": 2})
        self.assertIn("3 → 5", report.en_markdown(d, "2026-09-11", "donnees-2026-09-11"))

    def test_premiere_publication(self):
        vide = {"controles.csv": "", "localisations.csv": "", "manifest.json": "", "quality-report.json": ""}
        d = report.comparer(vide, etat(4))
        self.assertTrue(d["donnees_changees"])
        self.assertEqual((d["controles"]["avant"], d["controles"]["apres"]), (0, 4))
        self.assertEqual(d["nouveaux_libelles"], {}, "pas de « nouveaux libellés » quand il n'y avait rien avant")

    def test_nouveau_libelle_et_localisation(self):
        d = report.comparer(etat(3), etat(3, precision="adresse", secteur="Cookies"))
        self.assertTrue(d["donnees_changees"])
        self.assertEqual(d["nouveaux_libelles"]["secteur_source"], ["Cookies"])
        self.assertEqual(d["localisation"]["apres"], {"adresse": 3})

    def test_ressources(self):
        avant = etat(3, manifest='{"ressources": {"a": {"titre": "2023", "versions": [{"sha256": "x"}]}}}')
        apres = etat(3, manifest='{"ressources": {"a": {"titre": "2023", "versions": [{"sha256": "x"}, {"sha256": "y"}]}, "b": {"titre": "2024", "versions": [{"sha256": "z"}]}}}')
        d = report.comparer(avant, apres)
        self.assertEqual(d["ressources"]["nouvelles"], ["2024"])
        self.assertEqual(d["ressources"]["modifiees"], ["2023"])
        self.assertTrue(d["donnees_changees"])

    def test_qualite_dans_le_rapport(self):
        q = '{"resultat": "alerte", "nb_fatal": 0, "nb_alerte": 1, "constats": [{"niveau": "alerte", "message": "291 doublons"}]}'
        d = report.comparer(etat(3), etat(3, qualite=q))
        texte = report.en_markdown(d, "2026-09-11", None)
        self.assertIn("alerte (0 fatal, 1 alerte)", texte)
        self.assertIn("291 doublons", texte)


class TestVerification(unittest.TestCase):
    def test_doit_ecrire(self):
        self.assertTrue(verification.doit_ecrire(None, "2026-09-11", False))
        self.assertTrue(verification.doit_ecrire({"derniere_verification": "2026-09-01"}, "2026-09-11", True))
        self.assertFalse(verification.doit_ecrire({"derniere_verification": "2026-09-01"}, "2026-09-11", False))
        self.assertTrue(verification.doit_ecrire({"derniere_verification": "2026-09-28"}, "2026-10-05", False))


if __name__ == "__main__":
    unittest.main()
