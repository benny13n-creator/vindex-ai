# V2 NS006 — Living Matter / Professional Case Genome

**DRAFT. DO NOT MERGE. DO NOT DEPLOY.**
Base: `main` (`99d2c6b9`) · Head: `feature/vindex-v2-ns006-living-matter`
PR nije otvoren automatski (u okruženju nema `gh`); ovaj tekst je spreman za lepljenje.
Puni dokazi po zadatku: `docs/v2-recovery/NS006_OVERNIGHT_EVIDENCE.md`. Zaključana odluka: `docs/v2/VINDEX_V2_PRODUCT_ARCHITECTURE_DECISION_PAD_001.md`.

## Šta advokat dobija

- **Pregled predmeta**: „Stanje predmeta" — šta se promenilo od prošle verzije analize, šta traži pažnju, sledeći korak (sa razlogom i rokom).
- **Nova kartica „Analiza"** (jedina nova kartica; bočni meni nepromenjen): Genome, dokazi sa poreklom svake stavke, protivrečnosti sa izvorom i procenjenom stranom, rizici i spremnost, promene po verzijama. Analiza (AI) je vizuelno i rečima odvojena od činjenica iz dokumenata. Nijedan broj nije verovatnoća ishoda.
- **Danas**: radna lista iz postojeće table — radnje sistema, zadaci i dokumenti za pregled, svaka sa „Zašto".
- **Živi predmet**: nov dokument ili ročište → kanonski događaj → analiza, protivrečnost, spremnost i radnje se ažuriraju same, bez klika na „osveži".
- Otvaranje bilo kog od ovih ekrana: **0 poziva modela**, konstantan broj upita.

## Zadaci

| Task | Commit | Sposobnost | Mutacije |
|---|---|---|---|
| 0 | `2fbb9459` | PAD-001 zaključan; mapa vlasnika | — |
| 1 | `a107bc53` | ulazna granica (JWT alg-confusion, pypdf 6.19) | 2/2 |
| 2 | `633683d2` | ručni dokaz → događaj sa identitetom, 3 pokušaja | 6 + 1 druga brava |
| 3 | `5644bbde` | profesionalni ugovor Genome-a + poreklo | 10/10 |
| 4 | `631b01ba` | graf dokaza; migracija 135 (`izvor_tvrdnje`) primenjena 2026-10-09 | 8/8 |
| 5 | `b79c12c2` | životni ciklus protivrečnosti (V2 ili analiza, nikad oba) | 8/8 |
| 6 | `23d11a23` | determinističke promene verzija (stabilan identitet) | 8 + 1 po dizajnu |
| 7 | `30b9bd99` | deterministička spremnost (FAILED ≠ EMPTY) | 7/7 |
| 8 | `3b2b4104` | radnje: pad izvora ne menja akcije | 8/8 |
| 9 | `4edc9551` | `GET genome-v2`, `GET genome-v2/promene` | 5/5 |
| 10 | `f956715d` | V2 Analiza | 9 + dokaz dvostruke brave |
| 11 | `67b28c72` | V2 Pregled svestan događaja | 12/13 + druga brava |
| 12 | `e31ab7a3` | V2 Danas ↔ kanonska tabla | 12/13 + druga brava |
| 13 | `efdf8b69` | autonomni lanac (ročište → … → V2) | 5/6 + druga brava |
| 14 | `562a2b12` | realan predmet od prvog dokumenta | 2/2 |
| 15 | `f4b8ba76` | matrica zakupaca; filter vlasnika za V2 sporne tačke | 7/7 |
| 16 | `85c5ddcc` | haos: model / V2 paket / dead-letter | 3/3 |
| 17 | `49763ccb` | cena: 0 modela, bez N+1, bez upisa | 3/3 |
| 18–19 | `ebe4de9b` | koherentnost asseta (dokaz); sajt preskočen | — |
| 20 | `bbd6d4f6`, `b724d6be` | adversarial: skraćenje se kaže, metrike sa skalom, stranke bez duplikata; jutarnji demo | 4/4 |

## Rute
Nove (samo čitanje): `GET /api/predmeti/{id}/genome-v2`, `GET /api/predmeti/{id}/genome-v2/promene`.
Ponovo korišćene: `GET /api/case-actions/predmeti/{id}`, `GET /api/workspace`. Aditivno polje odgovora: `POST …/dokaz` → `dogadjaj`.

## Migracije
`135_predmet_dokazi_izvor_tvrdnje.sql` — **primenjena na produkciji 2026-10-09 (potvrdio founder)**. Od tada nove tvrdnje nose autora (advokat / AI); stari redovi ostaju „autor nije poznat". Kod radi i bez nje (dokazan fallback).

## Demo (< 5 min)
`python tests/ns006_demo.py` · `cd frontend-v2-ng && npm run demo:ns006` → `shots/ns006-demo/`.

## Poznat dug
Vidi „KNOWN DEBT" u završnom izveštaju i `NS006_OVERNIGHT_EVIDENCE.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
