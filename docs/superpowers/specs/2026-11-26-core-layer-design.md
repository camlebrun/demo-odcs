# Couche core : raw → core → customer

Statut : proposé, à valider avant toute implémentation.

## Intention

Les trois contrats customer lisent les raw directement et redéfinissent chacun les mêmes règles. Le lineage est illisible et rien ne garantit que les règles restent identiques. On ajoute une couche core : **chaque règle métier partagée est écrite une seule fois**.

## Objectifs et non-objectifs

- Objectifs : trois couches strictes, une définition par règle, lineage par colonne lisible de gauche à droite, résultats customer inchangés.
- Non-objectifs : écrire le pipeline (ce dépôt ne contient que des contrats), ajouter des indicateurs, modifier les raw.
- Échec même si la validation passe : une règle encore dupliquée dans un customer, un e-mail en clair dans core, un résultat customer différent d'aujourd'hui.

## Démo : compréhensible en une minute

- La démo se fait dans l'onglet **Lineage** natif du catalogue : raw → core → customer, lu de gauche à droite.
- **Pas de graphe maison** dans la page Doc (essayé puis retiré à la demande).
- Chaque contrat core a une description d'une phrase compréhensible sans connaître SQL.
- La page Doc tient d'abord en un écran (la règle et les trois couches) ; le détail technique est replié.

## Approches

- **A. Core complet (retenue)** : tout customer passe par core. Plus de travail, aucune exception.
- B. Core partagé (ventes et clients) : moitié moins de travail, publicité et GA4 sautent la couche.

## Règles de couches

- `raw` ne lit que les systèmes externes.
- `core` lit `raw`, et d'autres `core` sans cycle.
- `customer` lit **uniquement** `core`.

## Modèles (dataset `core`, dossier `contracts/core/`)

| Contrat | Une ligne par | Clé primaire |
|---|---|---|
| `core__sales_events` | vente ou retour | `event_id` |
| `core__customers` | client identifié | `customer_key` |
| `core__ad_spend` | jour × plateforme × campagne | `spend_date`, `platform`, `campaign_id` |
| `core__campaigns` | plateforme × campagne | `platform`, `campaign_id` |
| `core__web_events` | achat web ou consultation produit GA4 | `event_id` |

### core__sales_events
| Colonne | Type | Règle |
|---|---|---|
| `event_id` | STRING | préfixe `pos:`, `web:` ou `refund:` + identifiant source |
| `source_system` | STRING | `shopify` ou `pos` |
| `event_type` | STRING | `sale` ou `return` |
| `channel` | STRING | `store` ou `web` ; un ticket lié à une commande web est `web` |
| `store_id`, `store_code` | STRING | magasin ; `store_id` NULL et `store_code` = `WEB` pour le web |
| `event_at` | TIMESTAMP | UTC (heure locale du magasin convertie par son fuseau) |
| `event_date` | DATE | date locale du magasin, Europe/Paris pour le web |
| `amount_eur` | NUMERIC | négatif pour un retour |
| `customer_key` | STRING | e-mail fidélité, sinon e-mail de la commande web d'origine ; NULL si anonyme |
| `web_order_id` | INT64 | commande Shopify liée |

Règles écrites ici et nulle part ailleurs : commande web valide (non test, non annulée, EUR, source différente de `pos`, payée ou remboursée), tickets en EUR, remboursements `success` en EUR, exclusion du ticket magasin qui double un remboursement Shopify.

### core__customers
`customer_key` (STRING), `is_marketing_consented` (BOOL, NULL sans signal), `consent_source` (STRING), `consent_updated_at` (TIMESTAMP), `first_sale_date` (DATE, tous canaux), `first_web_order_at` (TIMESTAMP, commandes Shopify seules).

Le signal de consentement le plus récent gagne (Shopify ou fidélité en caisse). Les deux dates rendent explicites les deux définitions de « nouveau client » déjà en usage (KPI et acquisition).

### core__ad_spend
`spend_date` (DATE, fuseau du compte), `platform` (`google_ads`, `meta_ads`), `campaign_id` (INT64), `spend_eur` (NUMERIC ; micros Google divisés par 1 000 000, lignes en EUR seulement).

### core__campaigns
`platform`, `campaign_id`, `campaign_name`.

### core__web_events
`event_id`, `event_type` (`purchase`, `view_item`), `event_at`, `user_pseudo_id`, `web_order_id` (achat rapproché d'une commande valide), `user_id_customer_key` (client connu par `user_id`), `marketing_channel` (règle gclid / source / medium actuelle), `utm_campaign` (minuscules, sans espaces), `is_analytics_consented` (BOOL).

Le dédoublonnage « premier achat GA4 par commande » reste dans `acquisition_monthly`.

## Exigences de qualité (gold standard)

Pour chaque contrat core :
- grain en une phrase, clé primaire déclarée ;
- `quality` : unicité et non-nullité de la clé, valeurs autorisées des énumérations, cohérence du signe des montants ;
- SLA de fraîcheur et de rétention au moins égaux à ceux des customer qui le lisent ;
- `loadStrategy` renseigné ;
- aucun e-mail : seulement `customer_key`, classée C2 avec le tag `pseudonymized` ;
- lineage par colonne (`transformLogic`, sources, description, SQL).

## Outillage

- `validate_lineage.py` : L001 compte 5 core ; L002 nomme `core__<nom>` ; L004 impose les règles de couches ; L008, L012 et L016 s'appliquent à core ; nouvelle règle : clé primaire obligatoire en core. Fixtures de test pour chaque règle.
- `build_catalog.py` : couche core reconnue (type de nœud et arborescence).
- `docs/conventions.md`, README, page Doc, CHANGELOG mis à jour.

## Versions

Core en `1.0.0`. Les trois customer passent en `2.0.0` (sources changées), leur SQL est réécrit sur core, leurs colonnes ne changent pas.

## Vérification

`make check` et `make catalog`. Aucune donnée n'est exécutée : l'équivalence des résultats est relue règle par règle contre le SQL actuel, elle n'est pas prouvée.

## Choix faits par défaut (à corriger si besoin)

- Équipe propriétaire de core : `team-core`.
- Core autorisé à lire core.
- Livraison sur une branche séparée, après le travail en cours.

## Laissé à l'implémentation

Texte des descriptions, SLA exacts, découpage des commits (soumis avant tout commit).
