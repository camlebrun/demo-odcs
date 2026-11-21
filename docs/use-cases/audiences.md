# Use case : audiences marketing consentantes (`audiences`)

Contrat : `contracts/customer/audiences.odcs.yaml` (table `customer.customer_audiences`).

## Sponsor

CRM / marketing. Équipe propriétaire : `team-customer`.

## Décision supportée

Qui cibler, exclure ou relancer dans les campagnes Google et Meta : exclure les acheteurs récents de l'acquisition, réactiver les clients dormants, relancer les visiteurs de fiches produit sans achat, et alimenter les audiences lookalike avec les meilleurs clients.

## Situation actuelle

Les listes sont construites à la main à partir d'exports Shopify et caisse, sans règle de consentement commune ni vue omnicanale. Un client qui achète en magasin est encore ciblé par l'acquisition web.

## Grain

Une ligne par **client (`customer_key`) x segment (`segment_name`) x jour de calcul (`audience_date`)**. Clé : `customer_key`, `segment_name`, `audience_date`. Instantané recalculé chaque jour, 30 jours conservés. Un client peut figurer dans plusieurs segments. Seuls les clients consentants sont présents.

## Segments

| Segment | Règle | Usage |
|---|---|---|
| `buyers_90d` | Au moins une vente dans les 90 derniers jours | Exclusion acquisition |
| `inactive_12m` | Déjà acheteur, aucune vente depuis plus de 12 mois | Réactivation |
| `product_viewers_no_purchase` | Fiche produit vue (GA4 `view_item`) dans les 14 derniers jours, sans achat depuis | Retargeting |
| `top_customers` | 10 % des clients au CA net 12 mois le plus élevé, parmi ceux ayant au moins 2 achats sur 12 mois | Graine lookalike |

## SLA

Recalcul quotidien, disponible à J+1 pour `buyers_90d`, `inactive_12m` et `top_customers`. Le segment `product_viewers_no_purchase` dépend de l'export GA4 (jusqu'à 24 h de latence) : son SLA est dégradé à **J+2**. Instantanés conservés 30 jours (minimisation).

## Consommateurs

Google Customer Match et Meta Custom Audiences.

## Consentement et PII

Consentement = `accepts_marketing` Shopify + opt-in fidélité en caisse (`marketing_opt_in`). Le signal horodaté le plus récent l'emporte ; sans signal connu, le client est exclu (cas des commandes invité Shopify). Règle qualité : aucune ligne avec `is_marketing_consented` différent de vrai.

Seule `customer_key` (hash SHA-256 de l'e-mail normalisé) est exposée, jamais l'e-mail en clair. Tous les champs de la table (rattachés à un client) sont `C2` avec le tag `pseudonymized` : une clé hachée et les données qui lui sont jointes restent des données personnelles. Le consentement porte sur l'e-mail : son usage pour le ciblage publicitaire reste une décision juridique du propriétaire.

## Limite du lien GA4 vers client identifié

GA4 ne contient aucun e-mail. Un visiteur n'est rattaché à un client que :
1. s'il a déjà acheté sur le web : le pont `ecommerce.transaction_id` (identifiant de commande Shopify, rapproché de `orders.id` ou `orders.name`, avec ou sans `#`) donne l'e-mail, puis le `user_pseudo_id` de l'achat relie ses autres visites ;
2. ou s'il s'est connecté : `user_id` est supposé égal à l'identifiant client Shopify (**hypothèse à confirmer par team-ga4**).

Les visiteurs anonymes, sans consentement analytics ou sans cookie ne sont pas rattachables. Le segment `product_viewers_no_purchase` couvre donc une minorité des visiteurs réels.

## Définitions des métriques

- `last_order_at` : dernière vente tous canaux, en UTC.
- `orders_12m_count` : ventes sur 365 jours.
- `net_revenue_12m_eur` : CA net de retours sur 365 jours, EUR TTC.
- `last_product_view_at` : dernière vue de fiche produit rattachée (segment retargeting uniquement).

## Limites assumées du lot 1

- Identité déterministe `customer_key = SHA256(LOWER(TRIM(email)))` ; côté caisse l'e-mail vient de `raw__loyalty_members__pos` via `loyalty_card_id`, côté Shopify de `customers` et `orders`.
- Environ 50 % des tickets sont anonymes : aucune audience possible sans e-mail.
- Pas de CRM ni d'ESP. Les plateformes normalisent l'e-mail à leur façon (ex. Gmail), ce qui peut réduire le taux de correspondance.
- La table ne gère pas les retraits côté plateformes : la resynchronisation complète est à la charge de l'activation.
- Montants en EUR TTC, dates en UTC ; lignes EUR uniquement ; retours déduits du CA net.
