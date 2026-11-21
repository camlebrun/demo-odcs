# data-contracts

Data contracts [ODCS v3.2.0](https://github.com/bitol-io/open-data-contract-standard/tree/v3.2.0) du data mesh (lot 1) et outillage de validation. Le dépôt ne contient que des contrats et leurs contrôles : ni dbt, ni pipeline, ni données.

## Périmètre du lot 1 : 17 contrats

- **14 contrats raw**, un par table source, nommés `raw__<table>__<source>` : shopify (4), pos (4), ga4 (2), googleads (2), metaads (2).
- **3 contrats customer**, nommés `<purpose>__<sources triées>` : `customer_kpis__pos_shopify`, `customer_audiences__ga4_pos_shopify`, `customer_acquisition__ga4_googleads_metaads_shopify`. Ils ne référencent que des raw.

## Structure

```
contracts/raw/<source>/       contrats raw (un dossier par source = un domaine)
contracts/customer/           contrats customer
schema/                       JSON Schema officiel ODCS v3.2.0 (non modifié)
docs/conventions.md           conventions de nommage, lineage, versionnement, PII
docs/use-cases/               cas d'usage (à venir)
tools/validate_schema.py      validation de chaque contrat contre le schéma ODCS
tools/validate_lineage.py     validation du lineage et des conventions
tests/                        tests pytest, fixtures valides et cassées
```

Contrat modèle : `contracts/raw/shopify/raw__orders__shopify.odcs.yaml`.

## Valider

Python 3.12 ou plus.

```bash
make install      # crée .venv et installe les dépendances (pyproject.toml)
make check-wip    # schéma + lineage sans décompte + tests (repo en construction)
make check        # schéma + lineage strict (14 raw + 3 customer) + tests : contrôle final, utilisé par la CI
```

Cibles unitaires : `make schema`, `make lineage` (strict), `make lineage-wip`, `make test`. Les outils se lancent aussi directement : `python tools/validate_lineage.py --no-count`.

Les erreurs de lineage sont préfixées par un code de règle (`L001` à `L014`, listées en tête de `tools/validate_lineage.py` et détaillées dans `docs/conventions.md`).

## Contribuer

1. Créer une branche, ajouter ou modifier le contrat dans le bon dossier. Partir du contrat modèle.
2. Respecter `docs/conventions.md` : nommage, descriptions en français, classification et tag `pii`, lineage complet pour un customer.
3. Bumper `version` du contrat selon semver ; un breaking change impose un MAJOR (définition dans les conventions).
4. Lancer `make check-wip` (ou `make check` quand les 17 contrats sont présents).
5. Ouvrir une PR avec le modèle fourni. Les CODEOWNERS demandent la revue de l'équipe du domaine ; `docs/`, `tools/`, `schema/` relèvent de `@org/data-platform`.

Ne jamais éditer `schema/odcs-v3.2.0.schema.json` : il est versionné tel que publié au tag `v3.2.0` du dépôt bitol-io. Pour changer de version du standard, ajouter le nouveau fichier et migrer les contrats.

## Limites du lot 1

- Aucun contrôle de conformité avec les tables BigQuery réelles ; les `quality` et `slaProperties` sont déclaratifs et non exécutés.
- Le lineage est déclaré au niveau champ pour les customer ; les expressions SQL ne sont pas exécutées ni analysées, seule leur forme est contrôlée.
- La propagation des PII vers les customer est revue manuellement.
- Valeurs fictives à remplacer avant mise en production : organisation GitHub `@org`, projet GCP `retail-data-prod`, adresses `retail.example`.

La liste complète des limites est dans `docs/conventions.md`.
