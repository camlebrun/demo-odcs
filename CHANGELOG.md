# Changelog

Ce fichier suit le format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Il décrit l'évolution du dépôt (outillage, conventions, ensemble des contrats). Chaque contrat porte sa propre version semver dans son champ `version` (voir `docs/conventions.md`).

## [Unreleased]

### Ajouté
- 14 contrats raw (shopify 4, pos 4, ga4 2, googleads 2, metaads 2) et 3 contrats customer avec lineage par property, et leurs fiches `docs/use-cases/`.
- Catalogue de données : `tools/build_catalog.py` génère le JSON et le dashboard statique de [dbt-colibri](https://github.com/b-ned/dbt-colibri) (MIT) à partir des contrats, sans dbt (`make catalog`).
- Couche core : 5 contrats (`core__sales_events`, `core__customers`, `core__ad_spend`, `core__campaigns`, `core__web_events`) et règle L019 (clé primaire en core).
- Règles L015 (nommage des properties) et L016 (`customer_key` pseudonymisé).
- Catalogue : page d'explication du lineage en anglais (`lineage.html`) et en français (`lineage.fr.html`), liée depuis le dashboard.
- Catalogue : onglet « Trace » dans le panneau d'un contrat, à côté de « Model Info » et « Lineage ». Il liste les colonnes du contrat et affiche, pour la colonne choisie, toute la chaîne qui la produit : le résultat en tête, puis les couches en remontant (customer, core, raw en dernier), les recopies repliées par contrat et les étapes non documentées signalées.

### Modifié
- **Cassant** : les 3 contrats customer passent en 2.0.0 et ne lisent plus que core (L004) ; colonnes inchangées. Un customer reprend `customer_key` sans le recalculer (L012). L004 contrôle aussi le SQL ; nouvelle règle L020 (aucun e-mail en core) ; L012 et L016 couvrent tout champ finissant par `customer_key`.
- Catalogue : page Doc réécrite, limitée à un sujet : comment ODCS et `transformSourceObjects` produisent le data catalogue.
- Catalogue : l'onglet Doc ouvre la version française (`lineage.fr.html`).
- `make catalog` et `make publish` valident schéma et lineage avant de générer.
- Catalogue : interface en anglais (hors contenu des contrats), bloc « Quality checks » lisible (règle, dimension, SQL), bloc « BigQuery schema » sans retour à ligne avec type de l'objet et stratégie de chargement lus dans les contrats.
- Catalogue : `transformLogic` et `lineageType` ne sont plus affichés dans les fiches de colonne (ils restent dans `colibri-manifest.json`).
- Contrats : `customProperties.loadStrategy: full_refresh` sur les objets dont le SLA décrit un chargement complet ; `raw__pages_views__ga4` et `raw__purchases__ga4` passent en `physicalType: view` ; nouvelle règle L018.
- Customer : un sous-dossier par flux métier (`acquisition/`, `audiences/`, `sales/`) et noms courts (`acquisition_monthly`, `audiences`, `kpis_monthly`) sans les sources ; L009 vérifie désormais le dossier de flux.
- Raw : chaque champ de premier niveau porte `transformLogic` (`map`, `create` pour `meta_*`), `transformSourceObjects` (champ de la source externe) et `transformDescription` ; la règle L006 est inversée en conséquence.
- Champs techniques préfixés `meta_` : `meta_loaded_at`, `meta_source_file`, `meta_computed_at`. Aucun nom ne commence par `_`.
- GA4 : `raw__purchases__ga4` et `raw__pages_views__ga4` pointent des vues filtrées (`purchase_events`, `page_view_events`).
- Audiences : `audience_date` fait partie de la clé primaire (historique de 30 jours).
- Montants customer en `NUMERIC` explicite (`CAST(... AS NUMERIC)`).
- Contrats : suppression de `customProperties.consumers` et `customProperties.details` ; la réserve juridique sur le consentement passe dans `description.limitations` d'`audiences`.

### Backlog catalogue
Comparaison avec `main` (changements cassants dans la PR), glossaire des KPI, indicateurs de complétude, recherche et filtres par domaine, équipe, statut.

## [0.1.0]

### Ajouté
- Socle du dépôt : schéma JSON officiel ODCS v3.2.0 (`schema/odcs-v3.2.0.schema.json`), conventions (`docs/conventions.md`), outils `tools/validate_schema.py` et `tools/validate_lineage.py`, tests pytest avec fixtures valides et cassées, `Makefile`, CI GitHub Actions, `CODEOWNERS`, modèle de PR.
- Contrat témoin `raw__orders__shopify` (1.0.0), modèle des contrats suivants.
