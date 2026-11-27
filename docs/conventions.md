# Conventions des data contracts

Ce document est la référence unique pour écrire, versionner et relire un contrat. Les règles marquées `Lxxx` sont vérifiées par `tools/validate_lineage.py` ; les autres sont vérifiées en revue de PR.

Standard : [Open Data Contract Standard (ODCS) v3.2.0](https://github.com/bitol-io/open-data-contract-standard/tree/v3.2.0). Le JSON Schema officiel est versionné tel quel dans `schema/odcs-v3.2.0.schema.json` (draft 2019-09). Aucun champ ne doit être inventé : si un besoin n'est pas couvert, il passe par `customProperties`.

## 1. Organisation et nommage

### Arborescence

```
contracts/raw/<source>/raw__<table>__<source>.odcs.yaml
contracts/core/core__<nom>.odcs.yaml
contracts/customer/<flux>/<objet>.odcs.yaml
```

Sources du lot 1 : `shopify`, `pos`, `ga4`, `googleads`, `metaads`. Un fichier par contrat, nommé `<id>.odcs.yaml`.

### Raw (L002)

- Un contrat par table source, id `raw__<table>__<source>` (`raw__orders__shopify`).
- `<table>` et `<source>` en snake_case minuscule ; `<source>` est identique au dossier et au `domain`.
- `id == name ==` nom du fichier sans `.odcs.yaml`. (Écart assumé : ODCS recommande un UUID pour `id`, nous utilisons le nom lisible, stable et unique, afin que le lineage soit lisible.)
- Le schéma de données d'un raw reflète la source sans transformation métier : noms de champs de la source en snake_case, aucune jointure, aucun calcul.
- Le nom de l'objet de schéma (`schema[].name`) est le nom de la table physique dans le dataset (ex. `orders`). Il peut différer de `<table>` quand la source l'impose (ex. `events` pour GA4). Il ne contient jamais de `.`.

### Core (L002, L019)

- Couche entre raw et customer : chaque règle métier partagée y est écrite une seule fois.
- Id `core__<nom>` (`core__sales_events`), sans sous-dossier ; `domain: core` et dataset `core`. L'objet de schéma porte le nom sans `core__` (`sales_events`).
- Chaque objet déclare sa clé primaire (L019). Aucun e-mail : seulement des clés hachées (L020).
- Exception : GA4 n'a pas d'identifiant d'événement, la clé composée de `core__web_events` est déclarée mais non garantie (unicité en avertissement).
- Un core lit des raw ou d'autres core, sans cycle (L004, L005).

### Customer (L002, L009)

- Un sous-dossier par flux métier sous `contracts/customer/` : `acquisition`, `audiences`, `sales` (L009). Un nouveau flux s'ajoute à `FLOWS` dans `tools/validate_lineage.py`.
- id `<objet>` en snake_case sans `__` : `acquisition_monthly` (`acquisition/`), `audiences` (`audiences/`), `kpis_monthly` (`sales/`). Les sources ne figurent pas dans le nom : elles sont portées par le lineage.
- `domain: customer` et dataset `customer` pour tous les flux.
- Un customer ne référence que des core (L004), jamais un raw ni un autre customer.

### Domaines, équipes, datasets

| Couche | domain | dataset BigQuery | team.name | CODEOWNERS |
|---|---|---|---|---|
| raw shopify | `shopify` | `raw_shopify` | `team-shopify` | `@org/team-shopify` |
| raw pos | `pos` | `raw_pos` | `team-pos` | `@org/team-pos` |
| raw ga4 | `ga4` | `raw_ga4` | `team-ga4` | `@org/team-ga4` |
| raw googleads | `googleads` | `raw_googleads` | `team-googleads` | `@org/team-googleads` |
| raw metaads | `metaads` | `raw_metaads` | `team-metaads` | `@org/team-metaads` |
| core | `core` | `core` | `team-core` | `@org/team-core` |
| customer | `customer` | `customer` | `team-customer` | `@org/team-customer` |

Une équipe propriétaire par domaine. `docs/`, `tools/`, `tests/`, `schema/` et la CI appartiennent à `@org/data-platform`.

## 2. Forme des champs ODCS v3.2.0 retenue

Écarts et précisions relevés dans le schéma officiel v3.2.0 :

| Champ | Forme dans 3.2.0 | Choix du dépôt |
|---|---|---|
| `apiVersion` | enum (`v3.2.0`, `v3.1.0`, ...) | toujours `v3.2.0` (L013) |
| `kind` | enum `DataContract` | `DataContract` |
| `id`, `name` | chaînes libres | `id == name ==` nom de fichier (L002) |
| `version` | chaîne libre | semver `MAJOR.MINOR.PATCH` (L013) |
| `status` | chaîne libre (exemples du schéma) | `proposed`, `draft`, `active`, `deprecated`, `retired` (L013) |
| `domain` | chaîne | voir tableau ci-dessus (L013) |
| `dataProduct` | **déprécié depuis 3.1.0** | non utilisé. Le rattachement à un produit passe par `domain` et le nom du contrat |
| `description` | **objet** `{purpose, usage, limitations, ...}` (pas une chaîne) | `purpose` obligatoire (L014), `usage` et `limitations` recommandés |
| `servers` | **liste** d'objets ; pour `type: bigquery`, `project` et `dataset` sont requis | un serveur `bigquery_prod`, `environment: prod`, `project: retail-data-prod` (projet fictif, à remplacer), `dataset` du tableau ci-dessus (L013) |
| `team` | **objet** `{name, description, members[]}` depuis 3.1.0 ; la liste de membres directe est dépréciée (suppression prévue en 4.0) | objet, `name: team-<domain>`, au moins un membre `role: owner` ; `members[].username` est requis, nous y mettons le handle d'équipe GitHub (`@org/team-shopify`) (L013) |
| `support` | **liste** de canaux `{channel, tool, scope, url, description}` ; seul `channel` est requis | au moins un canal e-mail par contrat (L013) |
| `slaProperties` | **liste** `{property, value, unit, element, driver, description, ...}` ; `property` et `value` requis | voir section 7 |
| `tags` | liste de chaînes, valable à tout niveau | contrat : couche + source (`[raw, shopify]`, `[customer]`) |
| `schema[]` | objets avec `name`, `physicalName`, `physicalType: table`, `description`, `properties`, `quality` | `description` obligatoire (L014) |
| `quality` | liste de contrôles `DataQuality` ; `type` parmi `text`, `library`, `sql`, `custom` ; `library` exige `metric` (`nullValues`, `missingValues`, `invalidValues`, `duplicateValues`, `rowCount`) et un opérateur (`mustBe`, `mustBeGreaterThan`, ...) | `library` en priorité, `sql` si nécessaire (`${table}`, `${column}`), avec `dimension` et `severity` |
| `classification` | **chaîne libre** par property | valeurs du tableau de la section 6 (L014) |
| `required` | booléen, `true` = la colonne ne contient pas de NULL (la description du schéma est ambiguë) | `true` seulement si la source garantit l'absence de NULL |
| `transformLogic` | **chaîne libre** (3.2.0 l'utilise aussi pour les mesures) | convention maison : `map`, `transform`, `create` (L007) |
| `schema[].physicalType` et `customProperties` de l'objet | `physicalType` : `table` ou `view` ; `loadStrategy` (facultatif) : `full_refresh`, `incremental` ou `append` ; `incrementalKey` : property de l'objet, obligatoire si `incremental` | affichés dans le bloc « BigQuery schema » du catalogue (L018) |
| `transformSourceObjects` | liste de chaînes libres | customer : `<contract_id>#<objet>.<property>` (L003) ; raw : `<système>#<objet>.<champ>` de la source externe (L006) |
| `transformDescription` | chaîne | une phrase |
| Nesting | `object` : `properties` ; `array` : `items.properties` ; `map` : `map.key` / `map.value` | un chemin de lineage traverse `items` sans le nommer |

Les contraintes de structure (champs inconnus refusés par `unevaluatedProperties: false`, types, énumérations) sont vérifiées par `tools/validate_schema.py`. `customProperties` est toujours une liste `{property, value}` avec `property` en camelCase.

## 3. Conventions de nommage des properties

- snake_case minuscule, ASCII, sans accent. Commence par une lettre. Tout champ technique ou de métadonnée (ingestion, calcul, fichier source) porte le préfixe `meta_` (ex. `meta_loaded_at`, `meta_source_file`, `meta_computed_at`) et aucun nom ne commence par `_`. Les dates issues de la source (`created_at`, `updated_at`...) gardent leur nom.
- **Raw** : on garde le nom de la source converti en snake_case, on ne renomme pas.
- **Customer** (noms que l'on contrôle) :
  - timestamps : suffixe `_at` (`first_order_at`), type `TIMESTAMP`, toujours en UTC ;
  - dates calendaires : suffixe `_date`, type `DATE` ;
  - montants : suffixe `_amount` (ou `_price` pour un prix unitaire), type `NUMERIC`, accompagné d'une colonne `currency` (code ISO 4217) ou d'un suffixe de devise explicite (`_eur`) quand la conversion est faite ;
  - booléens : préfixe `is_` ou `has_` ;
  - compteurs : préfixe `nb_` ou suffixe `_count` ; pourcentages : suffixe `_pct` (0 à 100) ;
  - identifiants : suffixe `_id` (technique, issu de la source) ou `_key` (clé construite par le dépôt, voir `customer_key`).
- Types : `logicalType` ODCS (`string`, `integer`, `number`, `boolean`, `timestamp`, `date`, `array`, `object`) **et** `physicalType` BigQuery (`STRING`, `INT64`, `NUMERIC`, `BOOL`, `TIMESTAMP`, `DATE`, `ARRAY<...>`, `STRUCT<...>`, `JSON`) renseignés sur chaque property.
- Champs techniques présents sur chaque table raw : `meta_loaded_at` (TIMESTAMP UTC, chargement dans BigQuery) et `meta_source_file` (STRING, URI du fichier de dépôt d'origine, y compris pour une ingestion par API). Ils portent `transformLogic: create` et `transformDescription`, sans source.

Contrôlé par `tools/validate_lineage.py` : L015 (snake_case ; en core et customer `_at` = `TIMESTAMP`, `_date` = `DATE`, `_amount`/`_eur` = `NUMERIC`, `is_`/`has_` = `BOOL`, `meta_` réservé aux champs `create`) et L016 (`customer_key` confidentiel et pseudonymisé).

## 4. Lineage (core et customer)

Le lineage est porté **au niveau property** des contrats core et customer. Chacun de leurs champs de premier niveau porte :

| Champ | Contenu |
|---|---|
| `transformLogic` | `map`, `transform` ou `create` |
| `transformSourceObjects` | liste de `<contract_id>#<schema_object_name>.<property_name>` ; imbriqué : `raw__pages_views__ga4#events.event_params.key` |
| `transformDescription` | une phrase en français (L008) |
| `customProperties` | `transformExpression` : l'expression SQL de la colonne ; obligatoire pour `transform`. Les contrats ne portent pas de requête de table (`transformInputs` retiré) |

Une source est un champ qui fournit la valeur de la colonne. Les champs qui ne servent qu'à joindre ou filtrer ne sont pas listés dans `transformSourceObjects` : la jointure ou le filtre s'écrit en français dans `transformDescription`. Pour une valeur constante selon l'origine, on liste l'identifiant (ou le champ type) de chaque table d'origine.

Exemple :

```yaml
- name: first_order_at
  logicalType: timestamp
  physicalType: TIMESTAMP
  description: Date de la première commande du client.
  classification: internal
  transformLogic: transform
  transformSourceObjects:
    - raw__orders__shopify#orders.created_at
  transformDescription: Plus ancienne date de création parmi les commandes du client.
  customProperties:
    - property: transformExpression
      value: MIN(created_at)
```

### Règles par `transformLogic` (L007, L011)

| Valeur | Sources | Expression | Usage |
|---|---|---|---|
| `map` | exactement 1 | facultative ; si présente, un renommage (`total_price`) ou un cast (`CAST(x AS STRING)`, `SAFE_CAST(...)`) trivial uniquement (L011) | recopie du champ source |
| `transform` | au moins 1 | `transformExpression` non vide, SQL BigQuery exact | calcul, agrégation, jointure, nettoyage |
| `create` | aucune (`transformSourceObjects` absent ou vide) | facultative (`CURRENT_TIMESTAMP()`) | valeur sans source (horodatage de calcul, constante) |

Autres règles :
- tout champ core ou customer de premier niveau a `transformLogic` et `transformDescription` (L008) ;
- toutes les références doivent exister : contrat, objet de schéma, property, y compris chemins imbriqués (L003) ;
- pas de cycle (L005) ; un core lit des raw ou des core, un customer uniquement des core ; la règle porte sur les sources déclarées et sur le SQL (`transformInputs`, `transformExpression`) (L004) ;
- raw (L006) : tout champ de premier niveau porte `transformLogic: map`, une source externe `<système>#<objet>.<champ>` et `transformDescription` ; `meta_loaded_at` et `meta_source_file` sont en `create`, sans source. Systèmes : `shopify_admin_api`, `pos_export`, `ga4_bigquery_export`, `googleads_api`, `metaads_api`. Pas de `transformExpression` ni de calcul.

### Règle `customer_key` (définie ici, une seule fois) (L012)

`customer_key = SHA256(LOWER(TRIM(email)))`, encodée en hexadécimal minuscule (STRING de 64 caractères). Expression BigQuery canonique, où `email` est la colonne source (qualifiée si besoin, ex. `o.email`) :

```sql
IF(NULLIF(TRIM(email), '') IS NULL, NULL, TO_HEX(SHA256(LOWER(TRIM(email)))))
```

- `SHA256` renvoie des `BYTES` ; `TO_HEX` produit la chaîne.
- Email `NULL` ou vide (après `TRIM`) : `customer_key` vaut `NULL`. On ne hache jamais la chaîne vide, sinon tous les clients sans e-mail partageraient la même clé.
- Aucune normalisation supplémentaire (pas de suppression de `+tag`, pas de traitement du domaine) : ce que la règle ne dit pas n'est pas fait.
- Tout champ dont le nom finit par `customer_key` dans un core reprend cette expression à l'identique (même colonne aux deux emplacements), ou porte son propre nom quand le calcul est écrit dans `transformInputs`. Un customer ne la recalcule pas : son expression est `customer_key`, avec pour source le `customer_key` d'un core. Les espaces et retours à la ligne sont libres. `tools/validate_lineage.py` le vérifie. Classification : `C2`, tag `pseudonymized` (une clé hachée reste une donnée personnelle au sens RGPD).

## 5. Versionnement et breaking changes

Chaque contrat porte sa version semver dans `version` (démarrage à `1.0.0` en statut `active`, `0.x.y` en `draft`). Le dépôt lui-même suit `CHANGELOG.md`.

| Bump | Quand |
|---|---|
| MAJOR | breaking change (ci-dessous) |
| MINOR | ajout rétrocompatible : nouvelle property optionnelle, nouveau contrôle de qualité, nouvelle source dans un raw |
| PATCH | correction sans effet sur les consommateurs : description, exemples, tags, typos |

**Breaking changes** (MAJOR, revue du domaine propriétaire et des consommateurs avant fusion) :
- suppression ou renommage d'une property, d'un objet de schéma ou d'un contrat ;
- changement de `logicalType` ou de `physicalType` incompatible (rétrécissement, changement de famille) ;
- passage d'une property en `required: true` alors que la table peut contenir des NULL, ou toute contrainte plus stricte sur les valeurs (`enum`, `logicalTypeOptions`) ;
- changement de sémantique d'une property (unité, fuseau, devise, règle de calcul, `transformExpression` modifiant le résultat) ;
- changement de clé primaire ;
- changement du jeu de sources d'un customer ;
- dégradation d'un SLA (`slaProperties`) ;
- passage en `deprecated` ou `retired`.

Un contrat `deprecated` reste publié au moins une version MAJOR avant `retired`. Un renommage de contrat crée un nouveau contrat (nouvel id) ; l'ancien passe en `deprecated`.

## 6. Descriptions, PII et classification

### Descriptions (L014)

- Français, une à deux phrases, sans jargon d'implémentation. Termine par un point.
- Obligatoires : `description.purpose` du contrat, `description` de chaque objet de schéma et de chaque property (y compris imbriquée).
- On y précise l'unité, la devise, le fuseau, le sens des NULL quand c'est utile.
- `description.limitations` du contrat liste ce que la donnée ne garantit pas.

### Classification et tags PII (L010, L014)

`classification` (chaîne libre dans ODCS, restreinte ici à l'échelle de confidentialité C0 à C3), obligatoire sur chaque property de premier niveau :

| Valeur | Usage |
|---|---|
| `C0` | public : publiable sans restriction |
| `C1` | interne : donnée d'entreprise non personnelle (défaut) |
| `C2` | confidentiel : donnée sensible pour le business ou identifiant pseudonymisé (`customer_key`, `customer_id`) |
| `C3` | restreint : donnée personnelle directe (e-mail, téléphone, nom, adresse) |

Tags de property : `pii` (donnée personnelle directe), `pseudonymized` (identifiant haché ou technique rattachable à une personne). Règle PII : `classification: C3` **et** `tags: [pii]` vont toujours ensemble ; l'un sans l'autre est une erreur (L010). Le contenu d'un champ texte libre susceptible de contenir des données personnelles (note client, commentaire) est traité comme `pii`.

Un champ customer dérivé d'une PII n'hérite pas automatiquement de la classification : l'auteur et le relecteur décident (le hachage de `customer_key` la fait passer à `C2`, vérifié par L016). Dans une table dont le grain est le client (`customer_key`), tous les champs comportementaux rattachés à la clé sont `C2` avec le tag `pseudonymized`. Cette revue est dans la checklist de PR.

## 7. SLA et support

`slaProperties` (liste `{property, value, unit, element, driver, description}`) : on utilise `frequency` (fréquence de mise à jour), `latency` (délai maximal entre la source et la table), `retention` (durée de conservation) avec `unit` ISO (`d`, `h`, `y`) et `driver: analytics`. Propriété maison `monthClosingDelay` (contrats de reporting mensuel) : délai de gel d'un mois clos, exprimé en **jours ouvrés** (`unit: businessDays`). Un SLA hebdomadaire se déclare par `frequency` avec `value: 1`, `unit: w`. Ce sont des **engagements déclaratifs** : le lot 1 ne les mesure pas.

`support` : au moins un canal avec `tool: email` et une adresse de l'équipe propriétaire.

## 8. Qualité

Les `quality` décrivent des attentes testables par un outil de qualité futur ; le lot 1 ne les exécute pas. Pour chaque raw : clé primaire (`duplicateValues`, `nullValues` à 0), `rowCount > 0` par objet, valeurs invalides sur les statuts énumérés. Chaque contrôle porte `dimension` et `severity`.

## 9. Limites assumées du lot 1

- Les contrats décrivent des tables ; aucune donnée, aucun pipeline, aucun dbt dans ce dépôt.
- La conformité entre contrat et table BigQuery réelle n'est pas vérifiée.
- Les contrôles `quality` et les `slaProperties` ne sont pas exécutés.
- Le lineage est déclaratif et au niveau champ : `transformExpression` n'est pas analysée ni exécutée. Seule la forme est contrôlée (`map` trivial, `customer_key` canonique).
- La propagation de PII d'un raw vers un customer est revue à la main.
- `team` et `support` ne sont pas rapprochés de l'annuaire réel ni du fichier CODEOWNERS ; les handles `@org/...`, l'e-mail `retail.example` et le projet `retail-data-prod` sont des valeurs fictives.
- Un seul environnement de serveur (`prod`).
- `status` n'est pas typé par le schéma ODCS ; la liste de la section 2 est notre convention.
