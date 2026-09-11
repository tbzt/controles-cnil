"""Relancer la transformation, la localisation et la validation sur les
mêmes entrées ne doit modifier aucun fichier produit.

Si ce test échoue, un script écrit quelque chose de non déterministe (ordre,
horodatage, flottant non arrondi) ou les fichiers commités ne sont plus
alignés avec les scripts : relancer le pipeline et commiter le résultat."""

import contextlib
import io
import unittest

from pipeline import geocode, transform, validate
from pipeline.commun import METADATA, PROCESSED

FICHIERS = [
    PROCESSED / "controles.csv", PROCESSED / "controles.json",
    PROCESSED / "localisations.csv",
    METADATA / "rejets.json", METADATA / "geocodage-rapport.json", METADATA / "quality-report.json",
]


class TestIdempotence(unittest.TestCase):
    def test_relance_sans_changement(self):
        if not (METADATA / "manifest.json").exists():
            self.skipTest("manifeste absent")
        avant = {f: f.read_bytes() for f in FICHIERS if f.exists()}
        with contextlib.redirect_stdout(io.StringIO()):
            transform.main([])
            geocode.main([])
            validate.main([])
        apres = {f: f.read_bytes() for f in FICHIERS if f.exists()}
        self.assertEqual(sorted(avant), sorted(apres))
        differents = [f.name for f in avant if avant[f] != apres[f]]
        self.assertEqual(differents, [])


if __name__ == "__main__":
    unittest.main()
