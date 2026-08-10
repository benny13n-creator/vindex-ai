# VINDEX AI — REVIZIJA TVRDNJI NA TRENUTNO JAVNOJ STRANI

Predmet: `landing.html`, servira se na `/` (`api.py:1478`). **Strana je javna sada.**
Merilo: `docs/website/VINDEX_AI_PUBLIC_CLAIMS.md`. **Audit only — ništa nije menjano.**

---

## P0 — POTENCIJALNO OBMANJUJUĆE, JAVNO DANAS

| Tvrdnja | Dokaz | Status | Akcija |
|---|---|---|---|
| **„Nikad više propuštenih rokova."** | garancija ishoda; kvalitet ekstrakcije rokova nikad meren | **NEPODRŽANO** | **UKLONITI** |
| **„Simulacija sudskog postupka i verovatnoće ishoda"** | predviđanje ishoda spora; nijedna tačnost izmerena | **NEPODRŽANO** | **UKLONITI ili PREPISATI** kao „pomoć u proceni" |
| **„Počni besplatno — 15 upita bez kartice"** | samouslužna registracija; proizvod je pre-beta, naplatni sloj ima 59 preskočenih testova | **NEPODRŽANO** | **UKLONITI** |
| **Sekcija `cenovnik`** | u repozitorijumu **više neusaglašenih varijanti cene** | **NEPODRŽANO** | **UKLONITI do odluke** |

## P1 — ISPRAVITI PRE ZAMENE

| Tvrdnja | Dokaz | Status | Akcija |
|---|---|---|---|
| „Vindex AI — **Pravni** operativni sistem" | „operativni sistem" arhitektura ne podržava; „pravni" zaključava u jednu delatnost | **NEPODRŽANO** | PREPISATI |
| „Otvori predmet, pusti AI da radi, donesi odluku." | implicira automatizovan tok bez provere | USLOVNO | PREPISATI |
| „Analiza iskaza svedoka i procena verodostojnosti" | procena verodostojnosti iskaza — nikad validirana | **NEPODRŽANO** | PREPISATI |
| „Identifikuje pravne rupe i preporučuje korake zaštite" | tvrdnja o kvalitetu pravne analize | USLOVNO | PREPISATI uz ogradu |

## P2 — NISKI PRIORITET

| Tvrdnja | Status |
|---|---|
| „Vaša kancelarija na jednom ekranu" | USLOVNO — opisno |
| „Živi sat, breadcrumb navigacija, personalizovani pozdrav" | ODOBRENO — proverljivo iz UI-ja |
| „Četiri AI alata, uvek dostupna" | NEPOZNATO — nije prebrojano |
| „Svaki predmet, kompletno" | USLOVNO — marketinško uopštavanje |

---

## ZBIR
**NEPODRŽANO: 6** (4 na nivou P0) · USLOVNO: 4 · ODOBRENO: 1 · NEPOZNATO: 1

## NAPOMENA O HITNOSTI

Ovo **nije** pitanje budućeg sajta. Četiri P0 tvrdnje stoje na **javno dostupnoj strani u ovom
trenutku**: garancija da rokovi neće biti propušteni, predviđanje ishoda sudskog postupka,
poziv na besplatno korišćenje proizvoda koji nije spreman za samoposluživanje, i objavljena
cena koju sam repozitorijum ne potvrđuje.

Za proizvod namenjen advokatima, garancija o rokovima je tvrdnja sa najvećom posledicom na
listi.

**Odluka o uklanjanju je vaša** — mandat ove misije je izričito zabranio izmenu strane.
