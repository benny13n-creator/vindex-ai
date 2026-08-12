# REGISTAR ODLOŽENIH KVAROVA

> **Pravilo 6 (Vindex standard, 2026-08-12)**
> Poznat kvar izvan trenutnog scope-a mora imati **izričit status, vlasnika i
> dokaz reprodukcije**. „Nije u scope-u" ne znači „nije problem".

Ovaj dokument je objašnjenje. **Brava je `tests/test_deferred_defects.py`** —
svaki zapis ovde ima izvršiv dokaz da se kvar i dalje reprodukuje. Čim se
popravi, test pada i tera brisanje zapisa. Zapis ne može da nadživi svoje
rešenje, ni u jednom smeru.

## Zašto zaseban registar, a ne `_EVIDENTIRANI_KVAROVI`

`_EVIDENTIRANI_KVAROVI` u `tests/test_p0_hit_area_invariant.py` prima samo kvar
koji **opšti invariant ume da reprodukuje**. P0F-002 to ne može — jezgro
kontrole je čisto, pa ga invariant s pravom ne smatra kvarom.

Da je ipak upisan tamo, brava `test_evidentirani_kvarovi_se_i_dalje_reprodukuju`
bi pala i naterala bi nas da je oslabimo. Time bismo dobili najgori mogući
ishod: savršen sistem za zatvaranje kvarova iz kog ispadaju baš oni kvarovi koji
se ne uklapaju u trenutni invariant.

---

# P0F-002 — leva kolona plutajućih dugmadi pada preko polja za pravni upit

| | |
|---|---|
| **Status** | `DEFERRED` · `VERIFIED` · `OUT-OF-SCOPE` |
| **Vlasnik** | founder — odluka o mobilnom rasporedu |
| **Nađeno** | 2026-08-12, u toku P0F-001 sprinta |
| **Poreklo** | **naša regresija**, uvedena u P0-2 (`41de2f79`) |
| **Težina** | niža od P0F-001 — jezgro kontrole je 100% dostupno |
| **Zaključano testom** | `tests/test_deferred_defects.py::test_odlozeni_kvar_se_i_dalje_reprodukuje[P0F-002]` |

## Šta se dešava

`#feedback-fab` (y 686–730) i `#vx-voice-fab` (y 744–792) padaju preko uglova
polja `#qi` (y 673–773, puna širina ekrana). Dodir u krajnjem uglu polja otvara
povratnu informaciju umesto da fokusira polje.

Izmereno na 375 / 390 / 412:

| Žrtva | Presretač | Tačaka od 49 | Jezgro |
|---|---|---|---|
| `#qi` | `#feedback-fab` | 3 | **100% čisto** |
| `#qi` | `#vx-voice-fab` | 1–3 | **100% čisto** |

Za poređenje, P0F-001 je bio **0 od 49** — potpuna nedostupnost i pogrešna
radnja. Ovo je drugi razred.

## Poreklo — naše, ne zatečeno

P0-2 je `#feedback-fab` i `#vx-voice-fab` premestio u levu kolonu da bi se
razdvojili od `#vx-mobile-fab` („Novi predmet") u desnoj. Time je rešen sudar u
desnom uglu i **napravljen** ovaj u levom. Zapisano bez ublažavanja.

## Zašto je odloženo

Uzrok nije pozicija nego arhitektura mobilnog rasporeda. Izmereno, ne
pretpostavljeno:

```
polje za upit #qi      y 673 … 773     (puna širina ekrana)
mobilna navigacija     y 800 … 860
slobodan procep        27px
potreban pojas         52px
```

Polje za upit zauzima ceo donji pojas punom širinom, pa **svako** plutajuće
dugme u tom pojasu pada preko njega. Pomeranje bilo kog dugmeta samo bira koji
će ugao biti pogođen.

ISPRAVKA (re-audit, 2026-08-12): ranija verzija ovog zapisa je tvrdila da se
panel „ne skroluje". To je bilo **netačno** — merio se `.vx-body`. Stvarni skrol
kontejner je `.vx-panels-wrap` (`scrollHeight 1147` vs `clientHeight 726`).
Zaključak o odloženosti se ne menja: na vrhu skrola kompozer i dalje zauzima ceo
donji pojas, pa svako plutajuće dugme u njemu pada preko polja.

## Uslov zatvaranja

> Plutajuća dugmad dobijaju **rezervisanu geometriju koju sadržaj ne sme da
> zauzme** (*dedicated interaction zone*), umesto da plutaju preko toka
> sadržaja.

Tada:
* `#qi` više ne deli prostor ni sa jednim plutajućim dugmetom;
* vertikalni položaj `#mic-qi` prestaje da zavisi od količine sadržaja iznad
  njega — čime nestaje i preostalo ograničenje P0F-001 popravke.

To je **arhitektonsko rešenje, ne UX poliranje.** Trenutni sistem je
`content-dependent → collision-prone`; traženi je
`reserved geometry → content cannot enter`.

## Šta NE raditi

Ne pomerati `#feedback-fab` ili `#vx-voice-fab` „da se skloni sa polja".
To je već dva puta u ovom repou proizvelo nov sudar umesto rešenja — jednom u
P0-2, jednom u prvoj verziji P0F-001 popravke. Oba puta ga je uhvatio geometrijski
invariant, ne pregled koda.

---

# F2-001 — 23 mrtve DOM reference iz obrisane landing stranice

| | |
|---|---|
| **Status** | `DEFERRED` · `VERIFIED` |
| **Vlasnik** | founder — odobrenje zasebnog dead-code prolaza |
| **Nađeno** | 2026-08-12, Faza 2 (forensic cleanup) |
| **Poreklo** | `landing.html` obrisan u Website sprintu (`f1865d4b`), init rutine ostale u `vindex.js` |
| **Težina** | **nema korisničkog uticaja** — tehnički dug, ne kvar |
| **Zaključano testom** | `tests/test_deferred_defects.py::test_odlozeni_kvar_se_i_dalje_reprodukuje[F2-001]` |

## Šta je dokazano

23 `getElementById` / `querySelector` reference ka ID-jevima koji ne postoje ni
statički ni dinamički:

```
hero · nav · ni · tog · p1 · p2 · pp1 · pp2 · demo · demoConf · demoTxt
hamburger · mobile-menu · sphereCanvas · sphereWrap · para-canvas
srp-content · srp-typing · modBody · modLabel · modShowcase · modTabs
aic3-btn · aic3-q · aic3-result · vx-topbar-settings-btn
```

Sve imaju **nula dostižnosti** do `index.html` (provereno rekurzivno kroz lanac
pozivalaca, dubina 4) i **nula pojava kao niska** (`window['ime']`).

Kod se izvršava, vraća `null`, i tu se zaustavlja. **Nijedna kontrola ne zavisi
od njega** — zato je ovo dug, ne kvar.

## Zašto nije obrisano odmah

Brisanje traži uklanjanje ~8 funkcija (`toggleMenu`, `focusInput`,
`toggleAnnual`, `_setPrices`, `aic3_submit`, `pred_submitProcena`, …) i
nekoliko blokova na najvišem nivou.

**Presedan je skup i svež.** U P0-0 je uklanjanje „zasenčenog mrtvog koda"
(`kalendarLoad`) ostavilo red koji ga čita — `ReferenceError` na najvišem nivou
oborio je izvršavanje **9.469 od 23.681 reda**, a nijedan statički audit to nije
video jer se deklaracije funkcija podižu.

Masovno brisanje samo da bi brojač `UNRESOLVED` pao na nulu bilo bi tačno ona
greška koju ovaj program lovi.

## Uslov zatvaranja

> Zaseban **DEAD-CODE FORENSICS** prolaz koji za **svaku funkciju posebno**
> dokazuje: nula statičkih pozivalaca, nula dinamičkih, nula u runtime-u — pa je
> ukloni i pokrene punu regresiju uz proveru da `static/vindex.js` i dalje nema
> **nijednu** grešku pri učitavanju.

Brava meri broj mrtvih referenci; kad padne ispod 20, test pada i tera brisanje
zapisa.

---

# ISTORIJA REGISTRA

| Datum | Šifra | Događaj |
|---|---|---|
| 2026-08-12 | P0F-002 | otvoren, `DEFERRED / VERIFIED / OUT-OF-SCOPE` |
| 2026-08-12 | F2-001 | otvoren, `DEFERRED / VERIFIED` |

Zatvaranje zapisa se ne upisuje ručno: kad kvar prestane da se reprodukuje,
brava pada i zapis se briše iz `_ODLOZENI` i odavde u istom commit-u.
