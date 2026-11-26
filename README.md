# data-contracts

Data contracts [ODCS v3.2.0](https://github.com/bitol-io/open-data-contract-standard/tree/v3.2.0) du data mesh (lot 1) et outillage de validation. Le dépôt ne contient que des contrats et leurs contrôles : ni dbt, ni pipeline, ni données.

## Périmètre du lot 1 : 22 contrats

- **14 contrats raw**, un par table source, nommés `raw__<table>__<source>` : shopify (4), pos (4), ga4 (2), googleads (2), metaads (2).
- **5 contrats core** (`core__<nom>`) : les règles métier partagées, écrites une seule fois. Ils lisent des raw ou d'autres core.
- **3 contrats customer**, rangés par flux métier (`acquisition/`, `audiences/`, `sales/`) : `acquisition_monthly`, `audiences`, `kpis_monthly`. Ils ne référencent que des core.

## Structure

```
contracts/raw/<source>/       contrats raw (un dossier par source = un domaine)
contracts/core/               contrats core (règles métier partagées)
contracts/customer/<flux>/    contrats customer (un dossier par flux métier)
schema/                       JSON Schema officiel ODCS v3.2.0 (non modifié)
docs/conventions.md           conventions de nommage, lineage, versionnement, PII
docs/use-cases/               fiches de cadrage des 3 produits customer
tools/validate_schema.py      validation de chaque contrat contre le schéma ODCS
tools/validate_lineage.py     validation du lineage et des conventions
tools/build_catalog.py        génération du catalogue de données (dashboard dbt-colibri) depuis les contrats
tests/                        tests pytest, fixtures valides et cassées
```

Contrat modèle : `contracts/raw/shopify/raw__orders__shopify.odcs.yaml`.

## Valider

Python 3.12 ou plus.

```bash
make install      # crée .venv et installe les dépendances (pyproject.toml)
make check-wip    # schéma + lineage sans décompte + tests (repo en construction)
make check        # schéma + lineage strict (14 raw + 5 core + 3 customer) + tests : contrôle final, utilisé par la CI
```

Cibles unitaires : `make schema`, `make lineage` (strict), `make lineage-wip`, `make test`. Les outils se lancent aussi directement : `python tools/validate_lineage.py --no-count`.

Les erreurs de lineage sont préfixées par un code de règle (`L001` à `L020`, listées en tête de `tools/validate_lineage.py` et détaillées dans `docs/conventions.md`).

## Catalogue de données

Dashboard statique (lineage colonne à colonne, types, SQL de transformation, mode expert) généré directement depuis les contrats, sans dbt ni base de données. Il s'appuie sur [dbt-colibri](https://github.com/b-ned/dbt-colibri) (MIT), épinglé en version 0.3.6 : seule l'interface est réutilisée.

```bash
make catalog-open   # installe ce qu'il faut, génère dist/catalog/index.html et l'ouvre
make catalog        # génère sans ouvrir
```

`make catalog`, `make catalog-open` et `make publish` valident d'abord les contrats (`make schema lineage`) et s'arrêtent à la première étape en échec.

Démo publique : https://demo-odcs.camillelebrun.fr, hébergée sur Cloudflare Pages (projet `demo-odcs`, plan gratuit, aussi sur https://demo-odcs.pages.dev). Déployé à chaque push sur `main` par `.github/workflows/pages.yml`. La licence MIT de dbt-colibri est jointe à la page (`THIRD_PARTY_LICENSES.txt`).

Publier sur le domaine : `make publish` (génère le catalogue puis lance `wrangler pages deploy`, voir `wrangler.jsonc` ; nécessite `wrangler login`).

Tout collaborateur peut le générer avec cette seule commande (Python 3.12 ou plus). La CI le construit à chaque PR et le publie en artefact `catalogue`. La sortie `dist/catalog/colibri-manifest.json` est le JSON consommé par l'interface. Dans le panneau d'un contrat, le "Expert mode" affiche dans les fiches de colonne la transformation (description et SQL) et les contrôles qualité avec leur SQL.

L'onglet **Trace** du panneau d'un contrat liste les colonnes du contrat sélectionné. Le clic sur une colonne affiche toutes les transformations qui lui sont appliquées, des contrats raw jusqu'à elle : contrats amont groupés par couche (raw, core, customer), une colonne amont listée une fois même quand plusieurs chemins y mènent, étape non documentée signalée au lieu d'être masquée.

## Contribuer

1. Créer une branche, ajouter ou modifier le contrat dans le bon dossier. Partir du contrat modèle.
2. Respecter `docs/conventions.md` : nommage, descriptions en français, classification et tag `pii`, lineage complet pour un core et un customer.
3. Bumper `version` du contrat selon semver ; un breaking change impose un MAJOR (définition dans les conventions).
4. Lancer `make check-wip` (ou `make check` quand les 22 contrats sont présents).
5. Ouvrir une PR avec le modèle fourni. Les CODEOWNERS demandent la revue de l'équipe du domaine ; `docs/`, `tools/`, `schema/` relèvent de `@org/data-platform`.

Ne jamais éditer `schema/odcs-v3.2.0.schema.json` : il est versionné tel que publié au tag `v3.2.0` du dépôt bitol-io. Pour changer de version du standard, ajouter le nouveau fichier et migrer les contrats.

## Limites du lot 1

- Aucun contrôle de conformité avec les tables BigQuery réelles ; les `quality` et `slaProperties` sont déclaratifs et non exécutés.
- Le lineage est déclaré au niveau champ pour les core et les customer ; les expressions SQL ne sont pas exécutées ni analysées, seule leur forme est contrôlée.
- La propagation des PII vers les customer est revue manuellement.
- Valeurs fictives à remplacer avant mise en production : organisation GitHub `@org`, projet GCP `retail-data-prod`, adresses `retail.example`.

La liste complète des limites est dans `docs/conventions.md`.
