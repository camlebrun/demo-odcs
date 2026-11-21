# Changelog

Ce fichier suit le format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Il décrit l'évolution du dépôt (outillage, conventions, ensemble des contrats). Chaque contrat porte sa propre version semver dans son champ `version` (voir `docs/conventions.md`).

## [Unreleased]

### Ajouté
- 14 contrats raw (shopify 4, pos 4, ga4 2, googleads 2, metaads 2) et 3 contrats customer avec lineage par property, et leurs fiches `docs/use-cases/`.
- Catalogue de données : `tools/build_catalog.py` génère le JSON et le dashboard statique de [dbt-colibri](https://github.com/b-ned/dbt-colibri) (MIT) à partir des contrats, sans dbt (`make catalog`).
- Règles L015 (nommage des properties) et L016 (`customer_key` pseudonymisé).

### Modifié
- Customer : un sous-dossier par flux métier (`acquisition/`, `audiences/`, `sales/`) et noms courts (`acquisition_monthly`, `audiences`, `kpis_monthly`) sans les sources ; L009 vérifie désormais le dossier de flux.
- Raw : chaque champ de premier niveau porte `transformLogic` (`map`, `create` pour `meta_*`), `transformSourceObjects` (champ de la source externe) et `transformDescription` ; la règle L006 est inversée en conséquence.
- Champs techniques préfixés `meta_` : `meta_loaded_at`, `meta_source_file`, `meta_computed_at`. Aucun nom ne commence par `_`.
- GA4 : `raw__purchases__ga4` et `raw__pages_views__ga4` pointent des vues filtrées (`purchase_events`, `page_view_events`).
- Audiences : `audience_date` fait partie de la clé primaire (historique de 30 jours).
- Montants customer en `NUMERIC` explicite (`CAST(... AS NUMERIC)`).

### Backlog catalogue
Comparaison avec `main` (changements cassants dans la PR), glossaire des KPI, indicateurs de complétude, recherche et filtres par domaine, équipe, statut.

## [0.1.0]

### Ajouté
- Socle du dépôt : schéma JSON officiel ODCS v3.2.0 (`schema/odcs-v3.2.0.schema.json`), conventions (`docs/conventions.md`), outils `tools/validate_schema.py` et `tools/validate_lineage.py`, tests pytest avec fixtures valides et cassées, `Makefile`, CI GitHub Actions, `CODEOWNERS`, modèle de PR.
- Contrat témoin `raw__orders__shopify` (1.0.0), modèle des contrats suivants.
