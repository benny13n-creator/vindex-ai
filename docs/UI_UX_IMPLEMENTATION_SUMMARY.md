# Vindex AI — UI/UX Refactoring Implementation Summary (Opcija B, 2026-07-26)

**Sprovodi:** `docs/UI_UX_SIMPLIFICATION_PLAN.md` (Opcija A za FAZA 3, kako
je i preporučeno — prečica ka Nacrti/Podnesci, ne puna konsolidacija).
**Status:** Implementirano, statički verifikovano, nula regresija u pytest
suite-u (2242 passed, 1 skipped — identično kao pre ove izmene, pošto je
ovo čisto frontend refaktor bez novih backend testova).

---

## 1. Reorganizacija u 4 faze (`index.html:1117-1270`)

Flat skrolujuća lista (5 labela, 11 kartica) zamenjena sa `.vx-phase-tabs`
navigacijom + 4 `.vx-phase-panel` sekcije:

| Faza | Kartice |
|---|---|
| 1 — Intake & Analiza | Revizija dokumenta, Analiza rizika |
| 2 — Strategija & Svedoci | Analiza crvenog tima, Analiza svedoka |
| 3 — Izrada Nacrta | 1 prečica-kartica → "Otvori Nacrti & Podnesci" (Opcija A) |
| 4 — Simulacija Suda | Sudija, Sudija v2, Litigation, Predikcija ishoda (**nova kartica** — postojala je samo kao pill u alatu, nikad kao kartica), Hearing Command Center, Digital Twin |

"Inteligencija kancelarije" (Outcome Intel) ostaje van 4 faze, kao
zasebna sekcija ispod — nije korak u životnom ciklusu jednog predmeta
(v. plan §1.1).

Nova `predStratPhaseSwitch(phase, btn)` funkcija (`vindex.js`) — isti
show/hide + toggle-active obrazac kao postojeći `pred_subtabSwitch`.

**Nusputno otkriven i ispravljen pravi bug:** hero dugme "Kompletna
analiza predmeta" je pozivalo `pred_openStrat('kompletna_analiza')` —
funkciju koja traži `.strat-btn[data-modul="kompletna_analiza"]`, koji
**nikad nije postojao**. Rezultat: klik na najistaknutije dugme na celom
ekranu je tiho otvarao pogrešan alat (Red Team, default aktivna pilula)
umesto stvarne kompletne analize. Postojala je već ispravna, posvećena
funkcija `pred_launchKompletnaAnaliza()` (auto-popunjava opis, skroluje
do "Pokreni" dugmeta, već ima toast) — hero onclick prebačen na nju.

## 2. Eliminacija tihog preusmeravanja (`vindex.js`)

`pred_openStrat` sada prikazuje `showToast('Otvaram: ' + naziv + '…',
'info')` PRE `openAITool('t')` skoka — korisnik zna KUDA ide i ZAŠTO, ne
samo da se "cela aplikacija promenila". Nova `pred_openDraftEngine()`
funkcija (za FAZA 3 prečicu) radi isto pre `openAITool('n')`.

**Namerno NEPROMENJENO:** sam skok na `aiws` top-level tab i dalje
postoji (Opcija A, plan §1.2/§3.3) — puna in-context integracija bez
napuštanja "Pregled predmeta" bi zahtevala premeštanje cele
tip-selektor/textarea/rezultat UI logike, veći zahvat van obima ovog
sprinta.

## 3. Vizuelna hijerarhija (`vindex.css`)

- `.sfc-desc` — sada `max-height:0;opacity:0` po default-u, otkriva se na
  `:hover` **i** `:focus-within` (obavezno oba — bez `:focus-within`
  tastatura/screen-reader korisnici nikad ne bi videli opis).
- `data-tip="analitika|simulacija|pisanje"` atribut dodat na svih 11
  kartica + `border-left` akcenat po tipu (plavo/ljubičasto/zeleno — sve
  već postojeće boje u kodu, ne novi tokeni, u skladu sa Bloomberg-stil
  standardom).
- `.vx-phase-tab`/`.vx-phase-panel` — izvedeno iz `.pred-subtab-btn`
  vizuelnog jezika, `min-height:44px` (dodirni cilj).
- `.vx-insight-hero` — hero panel dobija ojačan border (samo
  top/right/bottom, `border-left` ostaje netaknut sa postojećim
  `--vx-accent`) da se vizuelno odvoji od kartica ispod, sad kad obe
  dele isti nivo (ikonica+tekst). Rešeno dvostrukim selektorom
  (`.vx-insight-panel.vx-insight-hero`) umesto `!important`, da se
  izbegne cascade-kolizija sa baznim pravilom kasnije u fajlu.

## 4. Verifikacija

| Provera | Rezultat |
|---|---|
| Div balans u izmenjenoj sekciji | ✓ 103 otvaranja = 103 zatvaranja |
| Lenient HTML parse (`index.html`) | ✓ Bez grešaka |
| CSS brace balans (`vindex.css`) | ✓ 3505 = 3505 |
| `node --check static/vindex.js` | ✓ Validno |
| Duplikat ID (`twin-card`) | Otkriven tokom implementacije (nenamerna posledica prve izmene), odmah ispravljen — potvrđeno jedinstven |
| `tests/test_xss_sanitization_sweep.py` + `tests/test_word_addin_taskpane.py` | ✓ 65/65 |
| Pun pytest suite | ✓ 2242 passed, 1 skipped — identično stanje kao pre izmene |

**Iskreno priznato ograničenje:** nije bilo moguće vizuelno renderovati
i ručno isprobati ekran u pravom browseru iz ovog okruženja (Playwright/
Chromium nisu unapred instalirani, a instaliranje bi zahtevalo veliko
preuzimanje + real login + otvoren predmet da bi se stiglo do ovog
konkretnog, duboko ugnježdenog ekrana — van razumnog budžeta za ovaj
zadatak). Verifikacija iznad je isključivo statička (sintaksa, struktura,
postojeći testovi) — **nije isto što i vizuelna/funkcionalna potvrda u
browseru.** Preporuka: pre javnog objavljivanja, founder (ili budući
sprint sa Playwright-om) treba ručno otvoriti "Pregled predmeta →
Strategija" i kliknuti kroz sve 4 faze + hero dugme.
