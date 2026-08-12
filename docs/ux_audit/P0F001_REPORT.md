> # ⚠ ISPRAVKA — OVAJ IZVEŠTAJ JE DELOM NETAČAN
>
> Zaključak „P0F-001 CLOSED" iz ovog dokumenta **nije bio tačan**. Popravka je
> merena samo na visini ekrana 860px; na 740px i 667px sudar se vraćao.
>
> Dve tvrdnje odavde su takođe netačne i ispravljene su:
> * „panel se ne skroluje" — merio sam `.vx-body`; stvarni skrol kontejner je
>   `.vx-panels-wrap` (`scrollHeight 1147 / clientHeight 726`);
> * popravka `align-items: flex-start` — mutacija je kasnije pokazala da ne radi
>   ništa, pa je uklonjena.
>
> Važeće stanje i konačna popravka (vodoravno razdvajanje) su u
> **`REAUDIT_CRITICAL_CONTROLS.md`**. Ovaj dokument se zadržava kao trag
> pogrešnog zaključka, ne kao izvor istine.

# P0F-001 — MOBILE ACTION COLLISION

**Polazno:** `41de2f79` · 5054 passed / 1 skipped
**Završno:** **5069 passed / 1 skipped / 0 failed**, zeleno na `no:randomly` i `seed=11`
**Scope:** isključivo sudar. Nula redizajna mobilnog rasporeda.

---

# 1. PRE FIX — IZMERENO, NE PROCENJENO

Ekran **Vindex Intelligence** (`#tab-aiws`), gde `#mic-qi` živi:

| Širina | `#mic-qi` | `#vx-mobile-fab` | Dostupno |
|---|---|---|---|
| **375** | `[309, 733, 44, 44]` | `[305, 732, 52, 52]` | **0 / 49** — potpuno prekriven |
| **390** | `[324, 709, 44, 44]` | `[320, 732, 52, 52]` | 21 / 49 (43%) |
| **412** | `[346, 709, 44, 44]` | `[342, 732, 52, 52]` | 21 / 49 (43%) |

Posledica nije bila „mikrofon se ne vidi". Korisnik traži **diktat**, sistem
izvršava **kreiranje predmeta**.

## Šta je merenje još pokazalo — cela zona, ne samo prijavljeni par

| Kontrola | Presreće | Jezgro |
|---|---|---|
| `#mic-qi` | `vx-mobile-fab` 49/49 (375px) | **0%** |
| `#qi` (polje za upit) | `feedback-fab` 3/49, `vx-voice-fab` 1–3/49 | 100% |
| `#feedback-fab` | `qi` 3/49 | 100% |

Druga dva sudara su **moja regresija iz P0-2** — leva kolona plutajućih dugmadi
je pala preko polja za upit. O njima §5.

---

# 2. KOREN

`.mic-input-wrap { display: flex; align-items: flex-end; }`

Mikrofon je flex-brat polja za unos, poravnat uz **dno** kompozera. Kompozer je
100px visok i završava na `y=773`; mikrofon je 44px i seda na `733–777` — dakle
i malo **ispod** samog polja. `#vx-mobile-fab` drži `right:18px; bottom:76px`,
tj. `y=732–784`. Isti pojas, ista kolona.

## Zašto ovo nije rešivo pomeranjem plutajućih dugmadi

Merenjem utvrđeno, pre izbora popravke:

```
kompozer #qi        y 673 … 773     (puna širina ekrana)
mobilna navigacija  y 800 … 860
slobodan procep     y 773 … 800  =  27px
```

Pojas plutajućih dugmadi traži **52px**. Ispod kompozera ga nema. Iznad
kompozera znači `bottom ≥ 187px`, gde bi dugmad plutala preko sadržaja na
svakom drugom ekranu.

Pomeranje kompozera naviše takođe otpada: panel se **ne skroluje**
(`scrollHeight 795 < clientHeight 804`), pa `padding-bottom` ne pomera sadržaj
— samo dodaje prazan prostor ispod njega. Provereno, ne pretpostavljeno.

**Zato je popravka lokalna za sadržaj, a ne još jedno pomeranje FAB-ova.**

---

# 3. FIX — JEDNA LINIJA, U OKVIRU POSTOJEĆEG PONAŠANJA

```css
@media (max-width: 768px) {
  .mic-input-wrap { align-items: flex-start; }
}
```

Mikrofon se na uskim ekranima poravnava uz **vrh** kompozera i time izlazi iz
pojasa plutajućih dugmadi.

Sačuvano: isto dugme, isti rukovalac (`micToggle('qi')`), ista veličina
(44×44, iznad praga dodira), isto mesto u DOM-u, isti redosled za tastaturu.
Menja se **samo vertikalno poravnanje unutar sopstvenog reda, i samo ≤768px.**

Pogođena su dva `.mic-input-wrap` elementa u aplikaciji — oba su kompozeri iste
vrste, pa je ponašanje ujednačeno.

---

# 4. POSLE FIX-A

```
375px   #mic-qi  →  ne pojavljuje se u spisku sudara uopšte
390px   #mic-qi  →  ne pojavljuje se
412px   #mic-qi  →  ne pojavljuje se
```

Pravougaonici `#mic-qi` i `#vx-mobile-fab` se **ne seku** ni na jednoj od tri
širine (izmereno kao presek površina, ne kao razlika `bottom` vrednosti).

---

# 5. TEST

`tests/test_p0f001_mobile_collision.py` — **15 testova** (3 širine × 5).

## Šta test namerno NE radi

Ne pominje `align-items`, ne čita nijednu CSS deklaraciju. Da tvrdi „mikrofon je
poravnat uz vrh", zaključao bi jednu implementaciju i pao bi na svaku drugu
ispravnu popravku.

Meri **ishod**: svaka tačka u meti mora pripadati nameravanoj kontroli.

| Test | Šta dokazuje |
|---|---|
| `test_mikrofon_ne_deli_metu_sa_dugmetom_novi_predmet` | ni jedna od 49 tačaka mete mikrofona ne pripada dugmetu Novi predmet |
| `test_mikrofon_i_novi_predmet_se_geometrijski_ne_seku` | uzrok, ne posledica — presek pravougaonika je 0 px² |
| `test_svaka_kontrola_akcione_zone_ima_cistu_metu` | sve četiri kontrole zone (`mic-qi`, `vx-mobile-fab`, `vx-voice-fab`, `feedback-fab`) imaju čisto jezgro |
| `test_nijedna_kontrola_ekrana_nije_potpuno_prekrivena` | popravka jednog para ne stvara drugi — baš ovo je uhvatilo grešku u prvoj verziji P0-2 |
| `test_meri_se_pravi_ekran` | negativna kontrola nad postavkom: ekran Vindex Intelligence otvoren, mobilna navigacija i FAB prikazani. Bez nje bi svi testovi „prolazili" nad ekranom na kom se kontrole i ne pojavljuju |

## Mutacije — tačno tri, kako je traženo

| Mutacija | Očekivano | Ishod |
|---|---|---|
| **vraćen stari raspored** (popravka uklonjena) | test mora pasti | **10 od 15 palo** ✓ |
| **pomeren mikrofon** (isporučena popravka) | test prolazi | **15 prošlo** ✓ |
| **pomereno „Novi predmet"** (`bottom: 76px → 200px`, uz uklonjenu popravku mikrofona) | test prolazi | **15 prošlo** ✓ |

Treća mutacija je najvažnija: dokazuje da test meri **sudar**, a ne konkretnu
popravku. Obe ispravne popravke ga zadovoljavaju.

---

# 6. EVIDENTIRANO, NE POPRAVLJENO

## P0F-002 — leva kolona plutajućih dugmadi preko polja za upit

`#feedback-fab` (`y 686–730`) i `#vx-voice-fab` (`y 744–792`) padaju preko
uglova polja `#qi` (`y 673–773`, puna širina). Izmereno: **3/49** i **1–3/49**
tačaka, sve izvan jezgra.

**Ovo je moja regresija iz P0-2**, kad su oba dugmeta premeštena u levu kolonu.

**Nije popravljeno, i to namerno.** Uzrok je isti kao u §2: polje za upit je
puna širina i zauzima ceo donji pojas, pa **svako** plutajuće dugme u tom pojasu
pada preko njega. Uklanjanje traži mobilni raspored — dakle upravo ono što je
izvan scope-a ovog mini-sprinta.

**Zašto nije upisano u `_EVIDENTIRANI_KVAROVI`:** jezgro je 100% čisto na obe
strane, pa opšti invariant ovo ne smatra kvarom — a lažan zapis u evidenciji bi
oborio `test_evidentirani_kvarovi_se_i_dalje_reprodukuju`. Stoji ovde, u
izveštaju, imenovano.

**Praktična težina:** polje je 297×100 sa 100% dostupnim jezgrom; pogođeni su
krajnji uglovi. Nije isti razred kao P0F-001 (0% dostupno).

## Ograničenje ove popravke — rečeno otvoreno

Mikrofon je poravnat uz vrh kompozera, a vertikalni položaj kompozera zavisi od
količine sadržaja iznad njega. Izmereno je i dokazano na **375 / 390 / 412** u
zatečenom stanju ekrana. Ako sadržaj iznad kompozera značajno naraste, kompozer
se spušta i mikrofon može ponovo ući u pojas.

Test to hvata jer meri stvarne pravougaonike — ali hvata **u tom stanju**.
Trajno rešenje je rezervisana traka za plutajuća dugmad u koju sadržaj ne ulazi,
i pripada mobilnom rasporedu.

---

# 7. `_EVIDENTIRANI_KVAROVI` ISPRAŽNJENA

`mic-qi` je bio jedini zapis. Obrisan je, kako brava i nalaže — zapis ne sme da
nadživi svoju popravku. Opšti invariant iz
`tests/test_p0_hit_area_invariant.py` sada **ponovo čuva** `#mic-qi` bez ijednog
izuzetka.

---

# 8. STANJE

```
static/vindex.css   +1 pravilo (+22 reda komentara sa merenjima)
static/sw.js        v127 → v128
tests/              +1 fajl (15 testova); evidencija kvarova ispražnjena

Testovi:  5054 → 5069 passed / 1 skipped / 0 failed
Redosled: no:randomly · seed=11 — oba zelena
```

**REMOVE lista je i dalje zaključana.** `pred_openNewModal`, `qiOtvori`,
`bulkOtvori`, 31 mrtav DOM ID — nedirnuti.

---

# 9. ČETIRI PRAVILA KOJA SU SE OVDE POTVRDILA

Ovaj sprint je peti put zaredom potvrdio istu stvar: **jedna strana ugovora
ništa ne dokazuje.**

| Pravilo | Kako se potvrdilo ovde |
|---|---|
| **Postojanje u izvoru ≠ zdravlje u izvršavanju** | mikrofon je postojao, bio vidljiv, imao rukovaoca — i pokretao tuđu radnju |
| **CSS deklaracija ≠ vizuelna dostupnost** | `align-items: flex-end` je legitimna deklaracija koja je proizvela 0/49 dostupnih tačaka |
| **`onclick` ≠ radna interakcija** | `micToggle('qi')` je bio ispravan i nedostižan |
| **„Nema prikazane greške" ≠ obrađeno stanje** | nije bilo nikakve greške — bio je uspeh pogrešne radnje |

Peto, koje je dodao ovaj sprint: **popravka sudara mora biti merena kao ishod, a
ne kao pozicija.** Test koji tvrdi „mikrofon je gore" pada na svaku drugu
ispravnu popravku. Test koji tvrdi „meta pripada svom vlasniku" prihvata obe —
i to je dokazano, ne pretpostavljeno.
