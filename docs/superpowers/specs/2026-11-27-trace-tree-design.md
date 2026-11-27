# Onglet Trace : une colonne, des sources au mart

## Intention
Un data steward choisit une colonne et comprend ce qui a été fait, des sources au mart, pour juger sa classification.

## Approches
- **Arbre depuis le résultat** : parenté visible, mais trop long à lire comme vue principale. Gardé en option.
- **Colonnes par couche, de gauche à droite** : écarté, traits à dessiner et croisements dès 15 contrats.
- **Fiche de colonne assemblée depuis les contrats (retenue)** : lisible, avec l'arbre pour creuser.
- **Résumé rédigé dans un nouveau champ de contrat** : écarté, les contrats ne changent pas.

## Écran
Liste des colonnes à gauche, avec leur classification déclarée. À droite, de haut en bas :
1. Colonne et table ; classification déclarée et la plus haute en amont (un signal, pas un verdict).
2. `description` de la colonne.
3. « Transformation » avec `transformLogic`, puis `transformDescription`, `transformExpression` et `transformSourceObjects`.
4. Ces trois champs sont nommés et toujours présents, pour la colonne comme pour chaque étape ; l'absence est écrite.
5. « Sources » : champs sources par niveau puis système, PII signalée. C1 et moins repliés seulement s'il y a plus sensible ; les champs non classés restent visibles.
6. « Transformations » : par table, de la plus proche à la plus lointaine, sans les recopies `map` ; les trois mêmes champs à chaque étape.
7. « Full table SQL » (replié) : `transformInputs` de chaque table, lignes de la colonne surlignées.
8. « Lineage tree » (replié) : arbre jusqu'aux systèmes sources, avec le détail de la ligne choisie ; une colonne partagée n'est dépliée qu'une fois.

## Règles
- Rien n'est masqué, même un `transformExpression` qui reprend le nom de la colonne.
- Colonne sans amont ni source externe : un seul avertissement.
- Limite de 400 lignes : message visible.
- Assemblé par le code depuis les champs existants : aucun contrat modifié, aucune IA.

## Limites
- `transformSourceObjects` ne distingue pas les champs de valeur, de jointure et de filtre.
- La qualité du texte est celle des contrats.

## Fichiers
- `tools/build_catalog.py` : sources externes des raw (`externalSources`).
- `tools/catalog_assets/column_info.{js,css}`, `tools/catalog_template.py` (commentaires).
- `tests/test_catalog.py`, `README.md`, `CHANGELOG.md`.

## Hors périmètre
Distinction direct / indirect (OpenLineage), contenu des contrats, onglets Lineage et Model Info, CI.
