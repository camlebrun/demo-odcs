## Objet

<!-- Contrats ajoutés ou modifiés, et pourquoi. -->

## Checklist

- [ ] Breaking change ? (voir `docs/conventions.md`, section Versionnement) : oui / non. Si oui, MAJOR bumpée et consommateurs prévenus.
- [ ] Version du contrat bumpée selon semver (`version`) et `CHANGELOG.md` mis à jour si le dépôt évolue.
- [ ] Lineage : chaque champ customer a `transformLogic`, `transformDescription`, `transformSourceObjects` (et `transformExpression` pour `transform`) ; le nom du contrat reflète ses sources. Raw : chaque champ est `map` depuis la source externe (`meta_*` en `create`).
- [ ] PII : toute donnée personnelle porte `classification: restricted` et le tag `pii` ; les champs customer dérivés d'une PII sont revus.
- [ ] `make check` vert en local.
