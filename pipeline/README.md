# Pipeline

Scripts Python 3, bibliothèque standard uniquement, exécutables un par un
dans cet ordre :

1. `fetch.py` : récupère les ressources CSV du jeu de données data.gouv.fr,
   archive toute version nouvelle dans `data/raw/`, met à jour le manifeste.
2. `transform.py` : lit `data/raw/`, applique le mapping d'en-têtes par
   année, produit `data/processed/controles.csv` et `.json`.
3. `geocode.py` : produit `data/processed/localisations.csv` à partir de la
   surcouche validée, du référentiel communes et des alias, hors ligne.
4. `validate.py` : contrôles de qualité, `data/metadata/quality-report.json`,
   code de sortie non nul sur règle fatale.
5. `build.py` : GeoJSON, statistiques, journal des changements.

État : `fetch.py`, `transform.py` et `geocode.py` sont écrits et testés,
les référentiels sont en place (`data/processed/referentiels/`) ;
`validate.py` et `build.py` sont à venir.

```bash
python3 pipeline/fetch.py              # récupère ce qui a changé
python3 pipeline/fetch.py --forcer     # retélécharge tout, sans dupliquer un contenu identique
python3 pipeline/fetch.py --hors-ligne # vérifie seulement que data/raw/ correspond au manifeste
python3 pipeline/transform.py          # data/raw/ → data/processed/controles.csv et .json
python3 pipeline/geocode.py            # controles.csv → data/processed/localisations.csv (hors ligne)
python3 outils/importer-umap.py <export.umap> --adresse-inverse   # ponctuel : surcouche d'adresses depuis uMap
python3 -m unittest discover -s pipeline/tests -t .
```

## Comment transform.py lit un fichier

1. Décodage : UTF-8 (avec ou sans BOM), sinon Windows-1252.
2. Séparateur point-virgule obligatoire ; en-têtes et valeurs sur plusieurs
   lignes acceptés (vrai parseur CSV) ; colonnes vides d'export Excel
   retirées ; lignes vides ignorées.
3. Chaque en-tête est normalisé (sans accents, minuscules, espaces réduites)
   et cherché dans `mappings/entetes.json`. Un en-tête inconnu arrête tout,
   avec la clé exacte à ajouter. L'ordre des colonnes n'a aucune importance.
4. Les libellés de fondement, de modalité et de pays passent par
   `mappings/fondements.json`, `modalites.json`, `pays.json` ; un libellé
   inconnu arrête tout. Le libellé source est toujours conservé dans une
   colonne `*_source`.
5. Une ligne dont seule la première colonne est remplie est une ligne de
   total : rejetée et listée dans `data/metadata/rejets.json`.
6. Identifiant : `annee-hash8-rang`, où le hachage SHA-1 porte sur le contenu
   source de la ligne et le rang distingue les lignes strictement identiques
   (contrôles multiples d'un même organisme, conservés).

Les drapeaux de la colonne `qualite` disent ce qui a été déduit ou corrigé :
`annee_source_absente`, `modalite_deduite_du_type`, `modalite_non_renseignee`,
`departement_corrige`, `departement_multiple`, `departement_a_preciser`,
`departement_vide`, `departement_invalide`, `pays_deduit`, `pays_vide`,
`organisme_vide`, `organisme_multiligne`, `ville_vide`, `secteur_vide`,
`ligne_dupliquee`.

`fetch.py` ne touche jamais à un fichier existant de `data/raw/` : une
ressource modifiée côté CNIL donne une version de plus dans le manifeste et
un fichier de plus, l'ancien restant en place.

## Comment geocode.py localise un contrôle

Deux localisations par ligne, voir `data/geocoding/README.md` pour les
tables. Le **lieu de l'organisme** est cherché dans l'ordre : alias écrit à
la main, référentiel des communes (département + nom normalisé ; pour les
départements ambigus 20 et 97, tous les départements possibles ; si le
département de la source contredit une ville unique en France, la ville
prime et la ligne reçoit `departement_contredit_par_ville`), surcouche
d'adresses validées, puis centroïde du département, du pays, ou rien. Le
**lieu du contrôle** dépend de la modalité : en ligne, sur pièces et sur
audition se déroulent au siège de la CNIL (précision `institution`) ; sur
place chez l'organisme ; modalité non renseignée (2014-2016) chez
l'organisme avec `lieu_controle_inconnu`.

Précisions possibles : `adresse`, `commune`, `departement`, `pays`,
`institution`, `aucune`. Coordonnées à 4 décimales pour une commune, 6 pour
une adresse. Le rapport `data/metadata/geocodage-rapport.json` compte tout
et liste les villes non résolues.
