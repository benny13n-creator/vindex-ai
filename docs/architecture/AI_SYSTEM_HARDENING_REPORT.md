# AI System Hardening Report — Program Beta (Masterprompt 002), Phase 9

**Naziv/placement napomena:** `docs/architecture/SYSTEM_HARDENING_REPORT.md`
već postoji (Program Alpha, 2026-08-04) i pokriva strukturnu/duplikacionu
otpornost sistema pri skaliranju. Ovaj dokument je namerno ODVOJEN fajl
(ne dodatak/nastavak) jer pokriva drugačije pitanje — AI-REZONOVANJE
specifičnu otpornost — i piše ga druga misija istog dana. Gde se preklapaju
(npr. audit trail storage), ovaj dokument upućuje na Alpha-in umesto da
ponavlja.

**Skala:** 10 / 500 / 5.000 korisnika, 50.000 predmeta, 1.000.000 AI analiza.
**Pitanje:** da li isti AI princip ostaje važeći na svakoj skali? Ako ne, zašto?

## Deterministički mehanizmi — princip se NE menja skalom (potvrđeno)

`compute_snaga_score`, `_calc_confidence_nivo`, `validate_dok_reference`,
`_snaga_iz_lokacije`, `_lociraj_tvrdnju`, `quality_gate` — svi su čiste
funkcije nad već-fetch-ovanim podacima. Trošak po pozivu je O(1) u odnosu
na broj korisnika/predmeta u sistemu (ne pretražuju globalno stanje, samo
podatke jednog predmeta/tvrdnje). **Na 1.000.000 analiza, ova klasa
mehanizama se ponaša identično kao na 10 — nula dodatnih LLM poziva, nula
dodatne latencije po analizi, nula rizika od "drifta" jer nema šta da
drift-uje (ista formula, isti ulaz → isti izlaz, uvek).** Ovo je DIREKTNA
posledica principa "platforma računa" — determinizam je sam po sebi
skaliranje-otporan svojstvom, ne slučajno.

## Nedeterministički mehanizmi — rizik RASTE sa skalom, ne opada

Ovo je centralni nalaz Faze 9. Strategy Engine-ova 4 nezavisna procenta
(PROGBETA-001) i Genome-ov heatmap/najslabija_tacka (PROGBETA-004) NISU statični
rizik — svaka dodatna analiza je nova prilika za istu klasu defekta da se
manifestuje:

- Na 10 korisnika / niskom volumenu: nizak rizik da advokat primeti 2
  kontradiktorna procenta za isti predmet (retko pokreće više od jednog
  Strategy Engine endpointa na istom slučaju u kratkom periodu).
- Na 5.000 korisnika / 1.000.000 analiza: statistički izvesno da će se
  desiti stotine ili hiljade slučajeva gde isti predmet dobije 2+
  međusobno kontradiktorna AI procenta preko različitih endpointa —
  svaki takav slučaj je potencijalni trust incident (advokat gubi
  poverenje u platformu kad vidi da mu ista stvar daje 35% na jednom mestu
  i 68% na drugom).
- **Zaključak koji potvrđuje misijinu premisu:** eliminisanje CELE KLASE
  defekta (ne pojedinačne instance) je jedini pristup koji skalira. Fix
  na jednom endpointu bi ostavio 3 druga da nastave da proizvode
  incidente proporcionalno volumenu — zato je Fork C-ovo (i ovog
  dokumenta) odlaganje implementacije opravdano SAMO uz obavezu da se
  `PROGBETA-001` prioritizuje pre bilo kog daljeg rasta volumena na Strategy
  Engine-u, ne odloži neograničeno.

## Evidence Chain gap-ovi — rizik menja KARAKTER sa skalom, ne samo intenzitet

Na niskom volumenu, nepopunjen RAG provenance (`PROGBETA-002`) je nevidljiv
trošak — niko ne audituje. Na 5.000 korisnika / 50.000 predmeta, ovo
postaje operativni rizik druge vrste: kad advokat ospori AI odgovor
("otkud ovaj zaključak?"), platforma danas NE MOŽE rekonstruisati koji su
konkretni RAG chunk-ovi doveli do tog odgovora — podatak postoji u
`retrieval_meta` u trenutku poziva, ali se gubi jer se ne upisuje. Na skali,
ovo prelazi iz "teorijski gap" u "predvidljiv support/pravni-rizik trošak"
— broj spornih AI odgovora raste linearno sa brojem analiza, i svaki
sporni odgovor bez evidence chain-a je nerešiv slučaj.

## Olympus governance kao skaliranje-mehanizam

Mission Olympus-ov upravljački sloj (19 novih agenata, Faza 10 ove misije)
je direktno namenjen ovom problemu: umesto da svaka buduća AI funkcija
prolazi kroz ad-hoc review, 9 imenovanih agenata (AI Quality Auditor, AI
Explainability, AI Grounding, Evidence Integrity, Workflow Integrity,
Architecture Review, Security Review, Metrics Guardian, Legal Domain
Expert) postoji upravo da uhvati regresiju OVIH principa PRE nego što
dostigne produkciju na skali. Faza 10 ove misije (ispod) je prvi realan
test da li taj sloj hvata AI-rezonovanje-specifične probleme, ne samo
strukturne.

## Zaključak Faze 9

Isti AI princip (Facts Before AI, Deterministic Core, Evidence Chain,
Explainability) ostaje važeći na SVAKOJ skali — nijedan princip ne treba
redizajn. Ono što se menja sa skalom je CENA nepoštovanja principa: na
niskom volumenu, nedostatak determinizma je estetski nedostatak; na
1.000.000 analiza, isti nedostatak je predvidljiv, kvantifikovan izvor
trust/support/pravnog rizika. Ovo je razlog zašto Program Beta prioritizuje
eliminaciju KLASA (Strategy Engine-ov deljeni scorer, RAG provenance
threading) nad pojedinačnim popravkama — na skali, klasa-nivo fix je jedini
koji ima konstantan (ne rastući) preostali rizik.
