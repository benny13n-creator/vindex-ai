# VINDEX AI — NIGHT STABILIZATION SPRINT 001

**Datum:** 2026-08-16
**Baseline commit:** `e608b5a8`
**Metod:** pravi HTTP server, prava Supabase baza, pravi Pinecone, pravi Supabase
ES256 tokeni, dva jednokratna naloga (A i B). Nijedan zaključak u ovom izveštaju
ne potiče iz čitanja koda — svi potiču iz izmerenog ponašanja.

---

## 1. FINALNI VERDIKT

# 🔴 BETA NO-GO

Jedan P0 tok nije dokazano PASS: **odgovor na pitanje čiji odgovor postoji samo
u dokumentu advokata nije pouzdan** — ista pitanja daju odgovor sa činjenicom iz
dokumenta u **1 od 3 pokušaja**, uz identičan, dokazano ispravan retrieval.
Detalji: §7, `NS001-P0-001`.

Sve ostalo iz mandata je zatvoreno i dokazano. Devet ranije nepoznatih kvarova
nađeno je i popravljeno, od kojih su **tri potpuno blokirala osnovni poslovni
tok**.

---

## 2. COMMIT-OVI

| Faza | Commit | Sadržaj |
|---|---|---|
| Baseline | `e608b5a8` | stanje pre sprinta |
| FAZA 1 — BR-002 | `4d986b6b` | klijent↔predmet + 4 kvara |
| FAZA 2 — BR-004 | `e5962f37` | brisanje dokumenta, pun ciklus |
| FAZA 3 — BR-005 | `0b3cd7f8` | jedna kanonska šema namespace-a |
| FAZA 4 — E2E | (v. §7) | brisanje izvedenih tragova + nalaz |

---

## 3. FAZA 1 — BR-002: KLIJENT ↔ PREDMET · 🟢 GREEN

### Kvar 1 — `POST /klijenti` je vraćao HTTP 500 **svaki put**

`klijenti/router.py:248` — guard protiv dvoklika je gađao kolonu
`klijenti.created_at`, koja **ne postoji** (tabela ima `kreirano`). PostgREST
odbija ceo upit sa 42703 i ruta puca. `_dedup_key` je neprazan kad god ime nije
prazno, a ime je obavezno — dakle **nijedan korisnik nije mogao da napravi
klijenta**, prvi korak celog poslovnog toka.

Uveden 2026-08-07 (`207b828d`). Nijedan klijent nije nastao posle 2026-07-19.

Isti drift na `klijenti/router.py:1589`: „dana saradnje" je bilo **0 za svakog
klijenta, uvek**.

### Kvar 2 — predmet bez klijenta prijavljivan kao pun uspeh

`routers/intake.py` — upis veze je padao u `logger.warning`, a ruta je vraćala
`success: True` i `predmet_id`. `static/vindex.js::_intakeKreiraj` čita **samo**
`d.predmet_id`; `klijent_povezan` **ne čita niko**.

Izmereno stanje baze: `predmet_klijenti` **0 redova** uz 19 predmeta i 5
klijenata. Istorijski uzrok: do 2026-07-19 je payload sadržao `user_id`, kolonu
koju ta tabela nema → 42703 → tiho progutano.

Sada: klijent je za ovaj tok obavezan, pa se upravo kreiran predmet uklanja i
vraća 404 (tuđi klijent) ili 500 (upis veze pao) — isti obrazac koji `api.py`
upload ruta već koristi kad obavezan sledeći upis padne.

### Kvar 3 — otvaranje predmeta je vraćalo HTTP 500 **svakom novom korisniku**

`postgrest 2.28.3` vraća **`None`** iz `maybe_single().execute()` kad nema reda.
Prebrojano u repozitorijumu: **230 poziva, 201 bez zaštite** — svaki odmah čita
`.data`. Prvi koji pukne je `UsageService.consume` →
`_claim_cooldown_atomic` (`shared/usage.py:168`), jer red `feature_usage` za
novog korisnika ne postoji.

Popravka je **jedna, na granici biblioteke**: `shared/postgrest_compat.py`
vraća ugovor (objekat sa `data=None`). Nekoliko fajlova je ovo već rešavalo za
sebe (`res.data if res else None`), svaki tek pošto bi pukao u produkciji — to
je 201 mesto na kome se mora zapamtiti isto pravilo. Zaštićeni kod radi
neizmenjeno.

### Kvar 4 — provera vlasništva je vraćala 500 umesto 404

`api.py:6025` i `klijenti/router.py` — `.single()` na 0 redova podiže grešku, pa
je `if not res.data: raise 404` bio **mrtav kod**. Podatak nije curio, ali je
klasa greške bila lažna, a namera koda se nikad nije izvršila.

### Runtime dokaz — 10/10

```
KLIJENT-CREATE 200 | PREDMET-CREATE 200 | klijent_povezan=true
DB veza 1 red | workspace stranke=1 | CRM aktivni_predmeti=1
A sa tudjim klijentom -> 404 i predmet NIJE kreiran
B -> A predmet 404 | B -> A klijent 404
```

### Usput popravljeno — GDPR/ZZPL export je bio potpuno mrtav

`routers/data_export.py` je sortirao `klijenti` i `predmet_komentari` po
nepostojećem `created_at` → 42703 → ceo ZIP se odbacuje. Mereno:
`GET /api/export/complete` → **HTTP 503**. Prenosivost podataka (ZZPL čl. 36 /
GDPR čl. 20) nije radila **ni za jednog korisnika**. Posle popravke: **200**,
ZIP sa svih 8 fajlova.

---

## 4. FAZA 2 — BR-004: BRISANJE DOKUMENTA · 🟢 GREEN

### Zatečeno

Nije postojala **nijedna** delete ruta za `predmet_dokumenti`, **nijedna**
kontrola u `vindex.js`, a kanonski `shared/vector_deletion.py::obrisi_vektore_dokumenta`
— napisan tačno za ovo — pozivan je isključivo iz `scripts/ingest_case_law.py`.
Dokument otpremljen greškom ostajao je zauvek.

### Dodato

`DELETE /api/predmeti/{predmet_id}/dokumenti/{dok_id}` + dugme u listi
dokumenata. **Redosled je deo ugovora**: vektori → original → red u bazi, uz
prekid na prvom neuspehu. Obrnut redosled je najgori mogući ishod — dokument
nestane iz liste, a i dalje ulazi u AI odgovore.

### P0 nađen tek stvarnim brisanjem

Prvi pun E2E prolaz je **pao**: ruta je vratila 409 „vektori nisu uklonjeni", a
vektor je **stvarno bio obrisan**. Pinecone `list()` je eventualno konzistentan,
pa je verifikacija odmah posle `delete()` još videla stari vektor. Sa tim
ponašanjem brisanje **ne bi uspelo nijednom**, a poruka „ništa nije promenjeno"
bila bi netačna.

`shared/vector_deletion.py` sada čeka u **ograničenom** prozoru (8 × 1,5 s) da
indeks stigne sebe. Prozor je ograničen namerno: posle njega se i dalje
prijavljuje neuspeh, jer „sačekaj još malo" bez granice je isto što i „proglasi
uspeh". `None` („ne znam") se **ne ponavlja** i ne degradira u „prazno".

Poruka greške sada razlikuje `REFUSED` („ništa nije promenjeno") od
`PARTIAL_FAILURE`/`VERIFICATION_FAILED` („deo vektora je možda već uklonjen").

### Runtime dokaz — 13/13

```
upload 200 | status=indeksirano | ns=user_... | 1 vektor
semanticka pretraga NALAZI kontrolnu cinjenicu
B brise A-ov dokument -> 404, red i vektor netaknuti
A brise -> 200, vektori DELETED 1/1, storage OBRISAN
DB 0 redova | Pinecone prefiks prazan | pretraga VISE NE NALAZI
```

---

## 5. FAZA 3 — BR-005: JEDNA KANONSKA ŠEMA · 🟢 GREEN

### Legacy `pred_*` nije bila mrtva grana — **aktivno je kvarila trenutni tok**

| Put | Šta je FE slao | Ishod |
|---|---|---|
| Odmah posle uploada | `pred_` + `session_id` iz odgovora | **HTTP 404** |
| Klik na dokument u predmetu | `tmp_` + `user_<uid>` | **HTTP 404** |

Advokat **nije mogao** da postavi pitanje o dokumentu — ni na jedan od dva
načina koje UI nudi.

### Dokaz da je `pred_` bio mrtav (a ne „za svaki slučaj")

- nijedan pisac ne proizvodi `pred_` namespace
- u Pinecone-u postoji 6 `pred_*` namespace-ova; **nijednom** sufiks nije
  `predmeti.id`, a provera vlasništva je tražila baš to
- `predmet_dokumenti` referiše 43 `pred_*` namespace-a; **nijedan** ne postoji u
  Pinecone-u i nijednom sufiks nije `predmeti.id`

⇒ grana je mogla da vrati **isključivo 404**, ni za jedan postojeći podatak.

### Bezbednosni razlog, nezavisan od mrtvog koda

`/api/dokument/pitanje` pretražuje kroz `extra_namespaces`, a ta grana u
`app/services/retrieve.py` ide **bez metadata filtera** (namerno — za ad-hoc
`tmp_` dokument). Da vlasnički namespace ikad stigne tim putem, pretraga bi
**zaobišla `shared/rag_acl.py` kapiju**. Vlasnički prostor se sada odbija na
ulazu (422), a `namespace_prefix` iz tela zahteva nema uticaja.

### Klasifikacija svakog preostalog traga

| Klasa | Broj | Ishod |
|---|---|---|
| A — runtime kritično | 0 | — |
| B — runtime nekritično | 0 | — |
| C — kompatibilnost | 0 | — |
| D — dijagnostika/test | 6 testova | konvertovani uz OLD/NEW/WHY |
| E — mrtav kod | 7 mesta | uklonjeno |

Usput: preview fallback je za savremene dokumente gradio `tmp_` + **ceo**
namespace i tiho vraćao prazno. Sada čita iz pravog namespace-a.

---

## 6. FAZA 4 — E2E REALITY GATE

23-koračni scenario, dva jednokratna naloga, pravi AI. **29/30 provera PASS.**

| # | Tok | Ishod |
|---|---|---|
| 1 | Prijava (e-mail + lozinka, nov ES256 token) | PASS |
| 2 | Kreiranje klijenta | PASS |
| 3 | Kreiranje predmeta za klijenta | PASS |
| 4 | Veza u bazi + oba smera u UI podacima | PASS |
| 5–7 | Upload → `indeksirano` → kanonski ns → vektor | PASS |
| 8–10 | Pitanje čiji odgovor je samo u dokumentu → **tačan iznos** + provenance | PASS |
| 11–12 | Drugo pitanje → tačan datum | PASS |
| 13–15 | Drugi dokument → uporedno pitanje vraća **oba** izvora | PASS |
| 16–18 | Brisanje dok. 1 → vektori nestali, dok. 2 netaknut | PASS |
| 19 | Pitanje na koje odgovara samo dok. 2 | **FAIL** (§7) |
| 20 | Činjenica obrisanog dokumenta više nije dostupna | PASS *(posle popravke §7.1)* |
| 21–23 | Odjava → nova prijava → predmet/klijent/dokument prežive | PASS |
| CT | B ne dobija A-ovu tajnu, ne briše, ne otvara predmet | PASS (4/4) |

### Automation test — šta advokat mora ručno da uradi

Klik, unos podataka, izbor dokumenta, pitanje AI-u. **Ništa drugo.** Nije bilo
potrebno: ručno indeksiranje, Pinecone upsert, SQL, ručni namespace, refresh da
bi backend proradio, ručno povezivanje tabela, admin intervencija, restart
servera, pokretanje ingest skripte.

---

## 7. NALAZI IZ FAZE 4

### 7.1 Sadržaj obrisanog dokumenta je preživljavao brisanje · **ZATVORENO**

Korak 20 je u prvom prolazu **pao**: posle brisanja dokumenta AI je i dalje
odgovarao njegovom kontrolnom činjenicom (iznos 47.912 EUR). Vektori, original i
red u bazi bili su uklonjeni — ali je upload ruta pri obradi upisala **dva reda**
u `predmet_istorija`:

```
[Auto-analiza] <naziv_fajla>   -- puna AI analiza dokumenta
[Metapodaci]  <naziv_fajla>   -- izvuceni iznosi, stranke, datumi
```

a `api.py::pitanje` poslednjih 10 redova te tabele ubacuje **doslovno** u prompt
kao „KONTEKST PREDMETA".

Brisanje sada uklanja ta dva sistemska artefakta. Advokatova sopstvena pitanja i
odgovori se **ne diraju** — to je njegov radni trag, ne dokument.

**Ostatak koji nije zatvoren i jeste odluka vlasnika:** ranija pitanja koja je
advokat sam postavio dok je dokument postojao i dalje mogu da citiraju njegov
sadržaj. Tiho brisanje advokatove evidencije pri brisanju dokumenta je
proizvodna odluka koju ovaj sprint **nije doneo**.

### 7.2 `NS001-P0-001` — odgovor iz sopstvenog dokumenta nije pouzdan · **OTVORENO**

**Merenje.** Isto pitanje, tri puta, isti predmet, isti dokument:

| Pokušaj | HTTP | Sadrži činjenicu iz dokumenta |
|---|---|---|
| 1 | 200 | **NE** |
| 2 | 200 | DA |
| 3 | 200 | **NE** |

**Retrieval nije uzrok — dokazano.** Direktna semantička pretraga indeksa nalazi
pasus (`score=0.590`, tekst sadrži iznos). Log servera pokazuje **identičan**
retrieval u sva tri pokušaja:

```
[KANC_NS:user_bc8fb51c-...] 3 pasusa dodato u kontekst (od 3 rezultata)
[RETRIEVE] confidence=HIGH score=0.6574 article=Član 270 law=zakon o obligacionim odnosima
```

Dakle pasus dokumenta je **stigao u kontekst modela svaki put**. Varijansa je
isključivo u **sintezi odgovora**: model u 2 od 3 slučaja odgovara opštom
pravnom logikom i ne citira činjenicu iz priloženog dokumenta.

**Zašto nije popravljeno u ovom sprintu.** Uzrok je u oblikovanju odgovora
(system prompt insistira na citiranju isključivo članova zakona), a ne u
podacima, namespace-u, ACL-u ni brisanju. Promena te instrukcije menja ton i
sadržaj svakog pravnog odgovora u proizvodu — to je proizvodna odluka, i
mandat izričito zabranjuje improvizaciju (`RULE 12`, „ne improvizuj").

**Šta je potrebno da se zatvori:** odluka o prioritetu činjenica iz priloženih
dokumenata u odnosu na zakonske izvore, pa izmena system prompta i merenje na
najmanje 10 ponavljanja po pitanju (kriterijum: 10/10, ne „obično radi").

---

## 8. FALSE-GREEN AUDIT

Za svaki od 10 traženih slučajeva postoji provera koja bi PALA da je kvar
ponovo uveden:

| # | Slučaj | Gde se meri |
|---|---|---|
| 1 | DB kaže `indeksirano`, Pinecone prazan | `test_br001_ingest_chain.py::test_5`, E2E 7-VEKTOR |
| 2 | Vektor postoji, retrieval gleda pogrešan namespace | `test_br003_...::test_4`, FAZA 3 test 5 |
| 3 | AI odgovara iz `case_context` umesto iz dokumenta | **§7.1 — nađeno E2E prolaskom**, `test_7` |
| 4 | Nedostaje provenance | E2E 10-PROVENANCE |
| 5 | DB brisanje uspe, vektor preživi | `faza2::test_2b`, `test_3` (3 parametra) |
| 6 | UI kaže „klijent povezan", veze nema u DB | `faza1::test_3b/3d` |
| 7 | Korisnik A vidi svoj dokument | E2E 8–15 |
| 8 | Korisnik B pokušava isti retrieval | E2E CT-PITANJE (2 varijante) |
| 9 | Odjava/prijava lomi vlasništvo | E2E 21–23 |
| 10 | Drugi dokument zagađuje retrieval | E2E 15, 18, 20 |

---

## 9. IZMENJENI PRODUKCIJSKI FAJLOVI

| Fajl | Šta |
|---|---|
| `shared/postgrest_compat.py` | **nov** — ugovor `maybe_single()` |
| `shared/deps.py` | primena šima |
| `shared/vector_deletion.py` | verifikacija čeka eventualnu konzistentnost |
| `klijenti/router.py` | `kreirano` umesto `created_at` (2×), `maybe_single` |
| `routers/intake.py` | veza klijent↔predmet fail-closed + kompenzacija |
| `routers/data_export.py` | kolone sortiranja (GDPR export) |
| `routers/dokument.py` | `pred_` uklonjen, vlasnički ns odbijen |
| `uploaded_doc/ingest.py` | docstring koji je preporučivao mrtvu šemu |
| `api.py` | delete ruta, ownership 404, preview fallback, izvedeni tragovi |
| `static/vindex.js` | dugme za brisanje, 3 mesta legacy namespace-a |
| `static/sw.js` | `vindex-v140` → `vindex-v142` |

**Migracije:** nijedna. **Produkcione mutacije podataka:** nijedna nad
postojećim podacima (§11).

---

## 10. TESTOVI

| Fajl | Testova | Mutacije |
|---|---|---|
| `test_ns001_faza1_klijent_predmet.py` | 8 | 3/3 ubijeno |
| `test_ns001_faza2_brisanje_dokumenta.py` | 21 | 4/4 ubijeno |
| `test_ns001_faza3_namespace_kanonizacija.py` | 19 | 4/4 ubijeno |

Dve mutacije su **preživele prvi krug** i zahtevale novi test:
- FAZA 2 / M1 — vraćanje verifikacije na jedno čitanje (tačno originalni kvar)
  nije padalo, jer su testovi merili `_cekaj_da_nestanu` izolovano → `test_1d`
  vozi celu kanonsku funkciju sa indeksom koji kasni.
- FAZA 2 / M4 — uklanjanje UI dugmeta nije padalo dok mutacija nije primenjena
  ispravno (prva verzija mutacije nije menjala fajl).

**Konvertovana očekivanja uz OLD/NEW/WHY** (nijedan test nije obrisan):
`test_lambda002_ownership_idor_fixes.py` (1), `test_sprint6b_namespace_integrity.py`
(5), `test_lambda008_certification.py` (1). U svakom slučaju bezbednosna tvrdnja
je ostala merena, a dodata je po jedna koje ranije nije bilo.

---

## 11. ČIŠĆENJE — DOKAZANO

| Provera | Pre sprinta | Posle |
|---|---|---|
| Pinecone `total_vector_count` | 434.217 | **434.217** |
| Pinecone namespace-ova | 11 | **11** |
| `predmet_dokumenti` | 43 | **43** |
| `predmeti` | 19 | **19** |
| `klijenti` | 5 | **5** |
| testni auth nalozi | — | obrisani |
| izmenjenih postojećih redova | — | **0** |

Uklonjeno je i 16 `case_actions` redova koji su pripadali test-predmetima ovog
sprinta. Pinecone provera je ponavljana u petlji do odsustva namespace-a — jedno
čitanje posle brisanja nije dokaz.

---

## 12. PREOSTALO

**P0 (blokira betu):**
- `NS001-P0-001` — odgovor iz sopstvenog dokumenta nije pouzdan (§7.2)

**Odluka vlasnika:**
- ranija pitanja advokata i dalje mogu da citiraju obrisan dokument (§7.1)
- 43 istorijska dokumenta iz BR-001 (talog od pre 2026-07-26)

**Poznato, izvan obima ovog sprinta:**
- 6 orphan `pred_*` namespace-ova u Pinecone-u bez ijednog reda u bazi
- `case_actions` nema `user_id` — brisanje po korisniku nije moguće direktno
