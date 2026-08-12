# FAZA 2.1 — UNRESOLVED RESOLUTION

**Polazno:** `771eb068` · 5178 passed
**Završno:** **5195 passed / 1 skipped / 0 failed**, `no:randomly` i `seed=11`
**Scope:** stavke **2, 3, 4**. Stavka 1 nije dirnuta.

---

# ISHOD

```
UNRESOLVED  4  →  0  unutar scope-a
STAVKA 1       prebačena u registar odloženih kao F2-001 (DEFERRED / VERIFIED)
```

**FAZA 2 JE ZATVORENA** — po kriterijumu „nula unresolved stavki **unutar
scope-a**", uz stavku 1 izričito odloženu i **izvršno zaključanu**.

---

# NAJVAŽNIJI NALAZ: SVE TRI SU IMALE KANONSKO ODREDIŠTE U KODU

Nijedno odredište nije birano procenom. Sva tri su **deklarisana u samom
`vindex.js`**, i testovi ih čitaju odatle — pa ako se deklaracija promeni a
poziv ne, test pada.

| Stavka | Izvor istine | Nalazi se |
|---|---|---|
| 2 | `_intakeKreiraj` — jedini tok sa punim lancem | `vindex.js:21258` |
| 3 | `_AIWS_MODES` + `_selectPodnesakOption()` | `vindex.js:2250` |
| 4 | `_AIWS_MODES = { …, n:'nacrti', t:'strategija' }` | `vindex.js:2250` |

Isti obrazac kao `_legacyMap = { ccc:'pregled' }` u Fazi 2. **Kad se traži
naslednik, kod ga po pravilu već ima — treba ga pronaći, ne izmisliti.**

---

# CLOSURE MATRIX

| | Stavka 2 | Stavka 3 | Stavka 4 |
|---|---|---|---|
| **Kontrola** | „Sačuvaj u predmet" | glasovna komanda „generiši dokument" | „Generiši nacrt tužbe" · „Pošalji u Strategiju" |
| **Reprodukcija pre** | prebaci na Predmete → **ništa**; `#pred-novi-btn` ne postoji, **oba** rezervna selektora pogađaju 0 elemenata | `pred_subtabSwitch('nacrti')` — `'nacrti'` **nije** u `VALID` ni u `_legacyMap` → tiho padne na `pregled`, uz poruku „Otvaram generator dokumenata" | `_analizaSwitchTab('n')` traži `.t-tab` sa `onclick` koji sadrži `'n'`; takvog taba nema → tiho ništa |
| **Root cause** | ulazna tačka uklonjenog modala | zastareo naziv podtaba + `#tip-podneska` zamenjen | tabovi `n`/`t` zamenjeni AIWS modovima |
| **Popravka** | `intakeOtvori()` + prenos analize u `#intake-opis` | `openAITool('n')` + `_selectPodnesakOption()` | `openAITool('n')` / `openAITool('t')` |
| **Granični uslovi** | čarobnjak se otvara svež · **ne kreira predmet direktno** | bez otvorenog predmeta i dalje upozorava · tip se bira preko kanonskog postavljača | **PRO kapija sačuvana** · tekst prenet u oba moda |
| **Mutacija** | vraćen stari tok → **5 palo** | vraćen `pred_subtabSwitch('nacrti')` → **1 pao** | vraćen `_analizaSwitchTab('n')` → **4 pala** |
| **Runtime** | ✓ | ✓ | ✓ |
| **Status** | **CLOSED** | **CLOSED** | **CLOSED** |

---

# STAVKA 2 — bez drugog puta ka kreiranju

Vaša odluka je bila: Intake, i **nikakav direktni `POST /api/predmeti`**.
Pre implementacije sam potvrdio da je Intake zaista kanonski pisac:

```
_intakeKreiraj()
  POST /api/intake/conflict-check
  POST /api/intake/kreiraj              ← vezuje klijenta
  POST /api/predmeti/{id}/pipeline
```

Nasuprot tome, uklonjeni `pred_kreiraj` je slao **go** `POST /api/predmeti` bez
klijenta, roka i dokumenata — što je i bio razlog za njegovo uklanjanje.

Test `test_s2_ne_kreira_predmet_direktno` presreće svaki `fetch` i pada ako se
pojavi poziv ka `/api/predmeti`. **Drugi put ka kreiranju ne može da se uvuče.**

## Mrtva zaštita koju je test otkrio

Napisao sam `if (opis.value.trim()) return;` — „ne gazi korisnikov unos".
Test je pao i pokazao da premisa nije tačna: `intakeOtvori()` po svom ugovoru
**resetuje sva polja** (otvara NOV predmet), pa ta grana nikad ne bi opalila.

Uklonjena je. Isto kao `align-items: flex-start` u Fazi 1.5 — pravilo koje ne
radi ništa se ne zadržava „za svaki slučaj".

---

# STAVKA 3 — poruka je bila netačna, ne samo neprecizna

`case 'generate_document'` je zvao `pred_subtabSwitch('nacrti')`. Ta funkcija
ima `VALID` listu od 13 podtabova; **`'nacrti'` nije među njima**, niti je u
`_legacyMap`. Rezultat: tiho padne na `pregled`.

Korisnik izgovori „generiši tužbu", dobije poruku **„Otvaram generator
dokumenata"** i — ekran Pregleda predmeta.

Pre-selekcija tipa je bila dvostruko slomljena: `#tip-podneska` je zamenjen
skrivenim `#podnesak-tip` uz **24 dugmeta** sa `data-value`, i vrednost se **ne
sme** postavljati direktno — kanonski postavljač `_selectPodnesakOption()` uz
vrednost ažurira i izabrano dugme i objašnjenje ispod njega. Stari kod je radio
`sel.options`, što na skrivenom `<input>` ne postoji.

**Verdict za stavku 3 je KEEP + REWIRE, ne REMOVE** — kako ste i tražili.
Glasovni tok „podnesak" je živ deo proizvoda; nedostajala mu je veza.

---

# STAVKA 4 — `tab-n` nije obrisan, nego zamenjen

Forenzika je pokazala:

```
#tab-n u DOM-u             0
#tab-t u DOM-u             0
setTab(…, 'n') poziva      0
setTab(…, 't') poziva      0
_analizaSwitchTab('n')     2 živa pozivaoca (analiza workflow traka)
```

Dakle **nije** slučaj „nula live callera → REMOVE". Postoje dva živa pozivaoca;
zastareo je bio *način* navigacije, ne funkcija.

`_AIWS_MODES` deklariše naslednike, a `openAITool()` je kanonski ulaz koji uz
prebacivanje moda **čuva i PRO kapiju** (`t === 'n' || t === 't'`). Test
`test_s4_pro_kapija_je_sacuvana` proverava da rewire nije otvorio PRO funkciju
korisniku bez PRO statusa.

`#strat-tekst` je i pre popravke dobijao tekst — ali korisnik nikad nije bio
odveden do njega, pa je dugme izgledalo mrtvo. Sada radi oboje.

---

# STAVKA 1 — ODLOŽENA, NE OBRISANA

Prebačena u registar kao **`F2-001`**, status `DEFERRED / VERIFIED`, vlasnik:
founder.

Brava: `test_odlozeni_kvar_se_i_dalje_reprodukuje[F2-001]` broji mrtve DOM
reference nad izvorom. Kad ih bude manje od 20, test pada i **tera brisanje
zapisa** — zapis ne može da nadživi svoje rešenje.

Uslov zatvaranja je zapisan doslovno: zaseban prolaz sa dokazom **po funkciji**,
ne masovno brisanje.

> Registar je morao da nauči nov oblik dokaza. `P0F-002` se reprodukuje
> geometrijski (u pregledaču), `F2-001` statički (nad izvorom). Brava sada ima
> obe grane — jer bi inače drugi zapis morao da se odbije, a to je tačno onaj
> propust zbog kog je Pravilo 6 i uvedeno.

---

# ISPRAVLJENA ZASTARELA TVRDNJA

`DEFERRED_DEFECTS.md` je za `P0F-002` i dalje tvrdio da se panel „ne skroluje
(`scrollHeight 795 < clientHeight 804`)". To je bilo netačno — merio se
`.vx-body`, a stvarni skrol kontejner je `.vx-panels-wrap`
(`scrollHeight 1147 / clientHeight 726`). Ispravljeno na mestu.

Zaključak o odloženosti se **ne menja**: na vrhu skrola kompozer i dalje zauzima
ceo donji pojas.

---

# STANJE

```
static/vindex.js   3 REWIRE-a, 1 mrtva zaštita uklonjena
static/sw.js       v131 → v132
tests/             +1 fajl (13 testova), registar dopunjen F2-001
docs/              +1 izveštaj, DEFERRED_DEFECTS.md dopunjen i ispravljen

Testovi:  5178 → 5195 passed / 1 skipped / 0 failed
Redosled: no:randomly · seed=11
```

Mrtve DOM reference: **30 → 27** (uklonjeni `pred-novi-btn`, `tip-podneska`,
`tab-n`).

---

# DESETO PRAVILO

> **Kad se traži naslednik, kod ga po pravilu već ima.**

Četiri puta zaredom u ova dva sprinta odredište nije trebalo izmisliti nego
pronaći: `_legacyMap` za `ccc`, `_AIWS_MODES` za `n` i `t`,
`_selectPodnesakOption` za tip podneska, `_intakeKreiraj` za kreiranje predmeta.

Svaki put kad se naslednik **izmisli**, nastaje paralelni tok — tačno ono što je
`pred_kreiraj` bio prema Intake čarobnjaku. Zato test mora da čita deklaraciju,
a ne da je prepiše: veza tada ostaje živa i puca kad se izvor promeni.
