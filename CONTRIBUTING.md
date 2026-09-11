# Contribuer

## La CNIL a changé le format d'un fichier : que faire

Le pipeline s'arrête volontairement quand un fichier source a une structure
inconnue. Voici la marche à suivre, en cinq étapes.

1. Lire le message d'erreur du job GitHub Actions : il liste les en-têtes
   rencontrés et le fichier concerné.
2. Ouvrir `pipeline/mappings/entetes.json` et ajouter une entrée pour la
   nouvelle signature d'en-têtes, en associant chaque en-tête à un champ
   canonique (`annee`, `type`, `modalite`, `organisme`, `ville`,
   `departement`, `pays`, `secteur`).
3. Si un nouveau libellé de secteur, de fondement ou de modalité apparaît,
   l'ajouter dans `data/processed/referentiels/secteurs.csv` ou dans
   `pipeline/mappings/`, avec sa famille harmonisée.
4. Ajouter un extrait du nouveau fichier dans `pipeline/tests/fixtures/` et
   relancer `python3 -m unittest discover -s pipeline/tests -t .`.
5. Relancer le workflow « Actualiser les données » manuellement.

## Règles

- Ne jamais modifier un fichier de `data/raw/`.
- Ne jamais écrire de coordonnées à la main dans `data/processed/` : passer
  par `data/geocoding/`.
- Aucune dépendance Python hors bibliothèque standard.
- Messages de commit en français, à l'infinitif ou au présent, sans trailer.
