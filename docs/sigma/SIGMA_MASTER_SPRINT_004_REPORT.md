# Mission Report — Program Sigma, Master Sprint 004: Legal Case Readiness & Action Planning Engine

**Datum**: 2026-08-06
**Program**: Sigma (četvrti sprint)
**Tim**: uloge izvedene direktno u ovoj sesiji (2 forenzička foreka + direktna implementacija/testiranje).

---

## Zatvorenje misije

Cilj: izgraditi JEDAN kanonski mehanizam koji odgovara "šta advokat sada treba da uradi" — svaka
preporučena akcija sa razlogom/izvorom/dokazom/prioritetom/statusom/vlasnikom/vezom sa predmetom — bez
pravljenja novog Task/Action/Priority/Recommendation sistema, isključivo reuse-om Case Actions/Workspace/
Event Bus/Genome/Gap Engine/Strategy Engine/Case Evolution.

## Otkriveno

**Najveći, najozbiljniji nalaz cele ove Sigma serije do sada**: `routers/case_commander.py` je ceo modul sa
**8 nezavisnih GPT generatora preporuka** — `NEDOSTAJE`/`RIZICI`/`PREPORUCENI POTEZ`/`VREMENSKI PRITISAK`
unutar sopstvenog `_COMMANDER_SYSTEM` prompta, `commander_quick_check`, `commander_checklist`,
`_cross_case_analiza`-ina sopstvena portfolio `"prioritet"` odluka, `commander_jutarnji` — nijedan ne čita
`case_actions`, Genome, niti `identify_case_problems`. Sopstveni `_dohvati_predmet_kontekst` čita sirove
`predmeti`/`rokovi`/`predmet_dokumenti`/`predmet_komentari` direktno.

**2 dodatna, manja ali konkretna nalaza, popravljena ovog sprinta**: `routers/case_intelligence.py`-ova AI
Briefing (`sledeci_korak`/`hitnost`) i `routers/copilot.py::_handle_analiza_predmeta`-ov sopstveni
`sledeci_korak` — oba nezavisno GPT-generisana "jedna najhitnija akcija" + hitnost tier, oba diskonektovana
od `case_actions`.

**`routers/morning_briefing.py`** — 2 nezavisne GPT sinteze "izaberi JEDNU najvazniju akciju" u ISTOM
fajlu, nijedna čita `case_actions`. Potvrđeno, nije popravljeno ovog sprinta.

**4 preklapajuća "koliko je predmet spreman" koncepta već postoje** (Case Ready Score, `procesni_rizik.nivo`,
Uncertainty Score, i **Pre-Flight `status` — GPT-generisan 3-state klasifikator**, najbliži postojeći
ekvivalent onome što Faza 4 traži) — dizajn novog modela morao je da ih imenuje, ne ignoriše.

**Faza 3 (Action Evidence Chain) potvrđena već čistom**: tačno 1 mesto u celom repou piše u `case_actions`;
sva 3 pravila popunjavaju stvaran `dokaz`. Nula popravki potrebno.

## Popravljeno

1. **`shared/case_readiness.py`** (novo) — `top_open_action()` (kanonski čitač "šta je sledeće" preko
   `case_actions`-a, koristi `shared/attention_priority.py`-ov već kanonski redosled) i
   `compute_case_readiness()` (Faza 4 model — READY/PARTIALLY_READY/BLOCKED/CRITICAL_GAP/UNKNOWN,
   isključivo deterministički, preko `case_actions.prioritet` + `shared/gap_engine.py`-ovih gap zapisa,
   nula GPT poziva).
2. **`routers/case_intelligence.py`** — AI Briefing sada čita `case_actions`-ov najviši prioritet umesto
   GPT-ove sopstvene nezavisne procene; fallback na GPT samo kad `case_actions` nema otvorenih redova.
3. **`routers/copilot.py::_handle_analiza_predmeta`** — isto, za sopstveni `sledeci_korak`.

## Dokazano

**16 novih testova** (`tests/test_sigma_sprint004_case_readiness.py`): `top_open_action` (prazna lista,
sortiranje po kanonskom prioritetu, isključivanje zatvorenih redova, tiebreak po roku), svih 5 stanja
`compute_case_readiness`-a pojedinačno uključujući 2 negativne kontrole (visok-prioritet-ali-ne-blokirajući
tip ne sme okinuti BLOCKED; deterministički gap bez odgovarajuće akcije ne sme sam okinuti PARTIALLY_READY),
i direktan dokaz oba live baga: GPT-ova sopstvena nezavisna vrednost mora biti IGNORISANA kad `case_actions`
postoji (2 dedikovana testa po popravci), fallback kad ne postoji (2 testa po popravci).

**Regresija**: 0. Puna test suita: **2.775 passed, 1 skipped, 0 failed** (bilo 2.759 na kraju Sigma Master
Sprint 003).

## Faza 6 — Workspace integracija

Workspace već pokriva 4 od 5 traženih bucket-a (danas/kriticno/na_cekanju/zavrseno_nedavno), sa već
solidnim poreklom (`_normalize_case_action`-ov `izvor` field). Nedostaje dedikovan ŠTA NEDOSTAJE bucket koji
bi izlagao Gap Engine-ove nalaze direktno — nije dodat ovog sprinta (zahteva portfolio-širok fetch Genome-a
za SVAKI predmet advokata, stvarna performance odluka, ne mehanička dopuna).

## Faza 7 — Forenzički napad

Duple akcije (potvrđeno kroz surface-e, 2 od 3 popravljene); akcije bez dokaza (nemoguće za `case_actions`
samo, potvrđeno prisutno za Case Commander); zastarele akcije (nemoguće — reconcile loop zatvara ih
automatski); pogrešan prioritet (2 mesta gde je GPT prioritet mogao da se ne slaže sa `case_actions`-om,
oba popravljena); kontradiktorne akcije (nije nađen konkretan primer unutar `case_actions`-a, moguć rizik
kroz Case Commander, nije nezavisno reprodukovan); AI izmišljene preporuke (tačno ono što je ovaj sprint
zatvorio za 2 od 3 pronađena mesta).

## Odloženo

`SIGMA-018` (Case Commander — 8 nezavisnih GPT preporuka, bez dokaznog lanca, najveći nalaz ove sesije,
zahteva sopstveni budući sprint), `SIGMA-019` (Workspace nema ŠTA NEDOSTAJE bucket, zahteva portfolio-širok
performance dizajn).

## Zaključak

Ovaj sprint ne tvrdi lažnu potpunu pobedu. Popravlja 2 konkretna, live baga po već-dokazanom Sprint 003
obrascu, gradi Faza 4-ov deterministički Readiness model bez postajanja 5. konkurentskog sistema, i
imenuje — precizno, sa punom težinom, ne umanjeno — najveći pojedinačni nalaz cele Sigma serije do sada:
ceo Case Commander modul kao nekonektovan, dokaz-slep generator preporuka, ostavljen za sopstveni budući
sprint umesto rizičnog žurnog popravljanja.
