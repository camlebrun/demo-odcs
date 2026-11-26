# Use case : indicateurs clients mensuels omnicanal (`kpis_monthly`)

Contrat : `contracts/customer/kpis_monthly.odcs.yaml` (table `customer.customer_kpis_monthly`).

## Sponsor

DAF / contrôle de gestion. Équipe propriétaire : `team-customer`.

## Décision supportée

Piloter chaque mois la santé de la base clients et le chiffre d'affaires net de retours des 40 magasins et du web : le CA se fait-il avec des clients nouveaux ou fidèles, quelle part du CA est rattachée à un client identifié, où le panier moyen évolue-t-il. Ces chiffres alimentent le comex et servent de base aux arbitrages fidélité et marketing.

## Situation actuelle

Le CA est suivi par canal (caisse d'un côté, Shopify de l'autre) sans vue client commune. Les retours en magasin d'achats web ne sont rattachés à aucun canal de façon cohérente. Aucun indicateur de nouveaux clients, de réachat ou d'omnicanalité n'existe de manière fiable ; les écarts avec le CA comptable sont constatés à la main.

## Grain

Une ligne par **mois x canal x magasin**. Clé : `month_date`, `channel` (`store` ou `web`), `store_code`.

Convention web : le canal web n'a pas de magasin, `store_code` vaut `WEB` et `store_id` est NULL. Un retour en magasin d'un achat web est imputé au canal web (`store_code = WEB`), à la date du retour.

## SLA

- Mise à jour quotidienne, latence J+1.
- Mois figé à M+3 jours **ouvrés** (3 jours ouvrés, pas calendaires) : avant le gel, un mois peut encore bouger (retours, remboursements tardifs).
- Historique conservé 3 ans.

## Consommateurs

Power BI comex.

## Définitions des métriques

Tous les montants sont en EUR décimal **TTC**. Les mois sont calculés sur la date locale du magasin pour la caisse (sans conversion de fuseau) et en Europe/Paris pour le web (Shopify est en UTC).

| Champ | Définition |
|---|---|
| `active_customers_count` | Clients identifiés distincts avec au moins une vente dans la ligne. Non additif entre lignes. |
| `new_customers_count` | Clients actifs dont la première vente identifiée (tous canaux) tombe dans le mois. |
| `repeat_customers_count` | Clients actifs dont la première vente est antérieure au mois. Actifs = nouveaux + réachat. |
| `omnichannel_customers_count` | Clients actifs ayant acheté en magasin et sur le web sur les 12 mois glissants. |
| `sales_orders_count` | Tickets de vente et commandes, identifiés ou anonymes. |
| `gross_sales_amount` | CA brut des ventes avant retours. |
| `returns_amount` | Retours et remboursements (valeur positive). |
| `net_revenue_amount` | CA net de retours = ventes brutes - retours. |
| `identified_net_revenue_amount`, `anonymous_net_revenue_amount` | CA net rattaché ou non à un client identifié. |
| `identified_revenue_share_pct` | Part du CA identifié, de 0 à 100. |
| `avg_basket_amount` | Ventes brutes / nombre de ventes (retours exclus). |

Normalisation : la caisse est en centimes TTC et heure locale du magasin (date locale retenue telle quelle), Shopify en décimal TTC et UTC. Le CA web est le `total_price` des commandes payées, hors commandes de test, annulées ou nées en caisse Shopify.

Retours : retours caisse (tickets de type `return`), retours en magasin d'achats web (`original_web_order_id`) et remboursements Shopify (transactions de remboursement réussies). Si Shopify a déjà un remboursement pour la même commande, le ticket de retour caisse est ignoré pour éviter un double compte.

## Règle qualité

Écart au CA comptable inférieur à 0,5 % (seuil 0,005) par mois figé, canal et magasin, avec un rapprochement en jointure externe complète : un mois, un canal ou un magasin présent d'un seul côté, ou un CA comptable à 0, fait échouer le contrôle. La référence comptable est hors lot 1 : c'est un contrôle de réconciliation fourni par le contrôle de gestion (table indicative `finance_controlling.accounting_revenue_monthly`). Contrôles complémentaires : unicité de la clé, CA net = CA identifié + CA anonyme.

## Limites assumées du lot 1

- Identité client déterministe : `customer_key = SHA256(LOWER(TRIM(email)))`. La clé est calculée dans la couche core (`core__sales_events`, `core__customers`) : côté caisse l'e-mail vient de la carte fidélité, côté Shopify de la commande ou du client.
- Environ 50 % des tickets sont anonymes (sans carte) : comptés dans le CA, pas au niveau client. Un client sans carte en magasin puis acheteur web est vu comme nouveau.
- Seules les lignes en EUR sont retenues. CA TTC uniquement ; le rapprochement comptable se fait en TTC.
- Pas de consentement, d'audience ni d'attribution marketing ici.
- Les expressions de transformation sont déclaratives (non exécutées dans le lot 1).
