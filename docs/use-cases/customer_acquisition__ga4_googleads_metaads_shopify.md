# Use case : acquisition de nouveaux clients par campagne (`customer_acquisition__ga4_googleads_metaads_shopify`)

Contrat : `contracts/customer/customer_acquisition__ga4_googleads_metaads_shopify.odcs.yaml` (table `customer.customer_acquisition_monthly`).

## Sponsor

Acquisition (paid media). Équipe propriétaire : `team-customer`.

## Décision supportée

Où investir ou couper le budget Google Ads et Meta : combien coûte un nouveau client par campagne, quel CA il rapporte au premier achat, et ce qu'il vaut à 90 jours.

## Situation actuelle

Chaque plateforme publie son propre ROAS et ses propres conversions, non dédupliqués : une même vente est revendiquée par plusieurs canaux et le CA est surestimé. Rien ne distingue un nouveau client d'un client existant.

## Grain

Une ligne par **mois x canal x campagne**. Clé : `month_date`, `channel` (`google_ads`, `meta_ads`, `other_web`), `campaign_id`. `other_web` regroupe le trafic web sans clic payant reconnu (sans dépense). `campaign_id = 0` quand l'achat n'est rapproché d'aucune campagne.

## SLA

Mise à jour quotidienne, latence J+1, revue hebdomadaire. Les jours récents restent révisés par les plateformes. Historique 3 ans.

## Consommateurs

Power BI, revue paid media hebdomadaire.

## Définitions des métriques (EUR)

| Champ | Définition |
|---|---|
| `spend_amount` | Dépense : micros Google Ads / 1 000 000 + `spend` Meta. |
| `new_customers_count` | Clients dont la première commande Shopify identifiée est attribuée à la campagne. |
| `cac_amount` | Dépense / nouveaux clients (NULL sans nouveau client). |
| `first_order_revenue_amount` | CA TTC du premier achat, avant retours. |
| `new_customer_roas` | CA du premier achat / dépense. |
| `cohort_value_90d_amount` | CA net de retours des commandes web des nouveaux clients sur 90 jours après leur première commande. NULL tant que la cohorte n'a pas 90 jours de recul (`is_cohort_90d_mature`). |

**Le ROAS plateforme n'est pas utilisé** (conversions Google Ads, `actions`, `action_values`, `purchase_roas` de Meta) : il n'est pas dédupliqué entre canaux.

## Attribution et jointures

- Web uniquement, **last-click GA4**, approximé par `collected_traffic_source` (UTM et `gclid`) de l'événement `purchase`. Les ventes en magasin ne sont jamais attribuées.
- Pont GA4 vers Shopify : `ecommerce.transaction_id` est l'identifiant de commande Shopify (chaîne), rapproché de `orders.id` converti en texte ou de `orders.name` avec ou sans `#`. GA4 pouvant dupliquer un achat, l'événement le plus ancien par transaction est retenu.
- Campagne : rapprochement par nom UTM (ou identifiant de campagne Meta), sans table officielle de correspondance.

## Limites assumées du lot 1

- Identité déterministe `customer_key = SHA256(LOWER(TRIM(email)))` (e-mail de `orders`, sinon `customers`).
- La caisse n'est pas dans ce contrat : un client ayant déjà acheté en magasin est compté à tort comme nouveau. Les tickets sans carte sont anonymes (environ 50 %). Une commande sans e-mail ne compte pas.
- Sans consentement analytics ou avec bloqueur, l'achat échappe à GA4 et tombe en `other_web`.
- Valeur de cohorte limitée au web (pas de CA magasin).
- Montants en EUR ; devises autres ignorées.
