# B4-M2 — LIVE E2E VERIFICATION (A / J)

**Datum:** 2026-08-21 · **Tip:** RELEASE EVIDENCE, ne development

---

## 1. VERDICT

🟡 **BLOCKED**

A i J su **stvarno izvedeni uživo** i prošli 10/10. Negativna verifikacija je
prošla 5/5. UI je dokazan nad stvarnim produkcionim odgovorima.

Verdikt ipak nije 🟢 zato što **dve stavke Definition of Done nisu dokazane**:

1. **`blocked=True` se nije desio nijednom u 10 živih J pokušaja.** Pravni deo
   jeste padao (`confidence = LOW`), ali specifični guard-block izlazi koje je
   NALAZ 2 popravio (`r4011`, `r4022`) **u produkciji nisu pređeni**. Oni ostaju
   dokazani samo deterministički. Ovo je tačno zamka koju je NS002B već jednom
   platio: 20/20 na putu koji nikad nije opalio.
2. **Negativna provera „pre retrieval-a"** nije izvodljiva spolja — interna
   grana; označena kao NOT EXECUTABLE, nije simulirana.

Ono što JESTE dokazano: **kada pravni deo sistema ne proizvede normalan odgovor,
činjenica iz advokatovog dokumenta preživi — u API-ju i na ekranu.**

---

## 2. EXACT ENVIRONMENT

| | |
|---|---|
| URL | `https://vindex-ai.onrender.com` |
| environment | `production` |
| Python | 3.11.16 · sw_cache `vindex-v146` |
| tenant | jednokratan, `b4m2.live.*@vindex-benchmark.invalid` |
| ingest | stvarni `POST /api/predmeti/{id}/upload`, HTTP 200 |
| retrieval | stvarni Pinecone, owner namespace |
| model | stvaran, bez mock-a |
| keš | zaobiđen postojećim mehanizmom (marker `KONTEKST PREDMETA:`, NIGHT-007) |

---

## 3. COMMIT

**`6458587`**, `identity_proven: true`, `commit_source: RENDER_GIT_COMMIT`.

**Nije `03548304`.** Manuelni deploy nije izvršen; produkcija se pomerila zbog
push-a NS003 protokola. Diff `03548304 → 6458587` menja **0 produkcionih
fajlova** (samo `docs/`, `scripts/`, `tests/`), pa je izvršeni kod isti — ali to
je navedeno kao činjenica, ne kao zamena za identitet.

**Zamrznuti NS003 runner ostaje NEIZVRŠEN** — njegova identity provera i dalje
traži `0354830` i nije dirana.

---

## 4. TEST DOCUMENT

`tests/fixtures/ns003/dokument_a.txt`, sha256 `2294912a692f11f9…` (zamrznut u
`e55279bf`, nepromenjen).

Produkcija prima isključivo PDF/DOCX (HTTP 415 za `.txt` — izmereno), pa je
napravljen DOCX kontejner čiji je tekst **doslovno** preuzet iz fixture-a.
Provereno pre slanja: svi redovi očuvani, DOCUMENT FACT prisutan.

---

## 5. DOCUMENT FACT

**`847.250,00`** (dinara, ugovorna kazna)

Eksplicitna, nedvosmislena, **dokazano jedinstvena u repozitorijumu**, i nije
izvodiva iz opšteg pravnog znanja.

Pitanja (doslovno):
* **A** — „Koliko iznosi ugovorna kazna prema mom ugovoru?"
* **J** — „Sta tacno propisuje clan 99987 Zakona o obligacionim odnosima i koliko iznosi ugovorna kazna prema mom ugovoru?"
* **NEG** — isto kao A, na tenantu bez ijednog dokumenta

---

## 6. SCENARIO A — 10 attempts

Svih 10: `legal status = normalan`, `document fact = 847.250,00 DA`,
`provenance = OK`, `API = 200`, **PASS**.

**A = 10/10**

---

## 7. SCENARIO J — 10 attempts

| # | legal status | document fact | provenance | API | result |
|---|---|---|---|---|---|
| 1 | `normalan` | 847.250,00 DA | OK | 200 | **PASS** |
| 2–10 | `A_pravni_LOW` | 847.250,00 DA | OK | 200 | **PASS** |

**J = 10/10.** U **9 od 10** pokušaja pravni retrieval je pao na `LOW` — dakle
pravni deo nije proizveo normalan odgovor — a dokumentarna činjenica je izašla
svaki put, doslovno i sa ispravnim `source_type` / `verification_state`.

Pod-slučajevi:

| Pod-slučaj | Živo pređen |
|---|---|
| A) pravni retrieval LOW | **DA — 9/10** |
| B) prazan filtrirani pravni kontekst | NOT EXECUTABLE spolja |
| C) pravna/retrieval greška | NOT EXECUTABLE spolja (traži infrastrukturni kvar) |
| D) guard block (`blocked=True`) | **NIJE pređen ni jednom** |

---

## 8. NEGATIVE / PRE-RETRIEVAL TESTS

Izvedeno na **zasebnom tenantu bez ijednog dokumenta** — jedini način da se
stvarno izmeri „nema validnog dokumentarnog izvora".

| # | API | kanal | izmišljena činjenica | result |
|---|---|---|---|---|
| 1–5 | 200 | prazan/odsutan | **NE** | **PASS** |

**NEG = 5/5.** Sistem ne izmišlja provenance.

**Pre-retrieval grana: NOT EXECUTABLE.** Interna je i nije dostupna kroz javni
API bez patch-ovanja produkcije. Nije simulirana.

---

## 9. UI VERIFICATION

`tests/test_b4m2_live_ui_verification.py` — **5/5 passed**.

Ulaz nisu sintetički objekti nego **doslovni produkcioni odgovori** snimljeni
tokom ovog merenja (`live_response_A.json`, `live_response_J.json`), pri čemu je
J snimak baš onaj sa `confidence = LOW`, tj. sa palim pravnim delom.

Dokazano u pravom Chromium-u nad pravim `index.html`:

* advokat vidi **„Činjenica iz vašeg dokumenta"** i kada pravni deo padne
* vrednost **847.250,00** je na ekranu
* izvor je imenovan: **`dokument_a.docx`**
* blok je stvarno vidljiv (`display != none`)
* uz njega stoji ograda **„nije pravno potvrđen"**
* navod je iscrtan **izvan** bloka pravnih izvora
* kada je kanal prazan, UI **ne iscrtava** blok i ne izmišlja ništa

Test `test_fixture_su_stvarni_produkcioni_odgovori` zaključava poreklo dokaza —
ako neko zameni fixture sintetikom, UI dokaz pada.

---

## 10. J TEXT SCORE — ODVOJENO

**Nije mereno i nije predmet ovog gate-a.**

B4-M2 se bavi strukturalnim očuvanjem činjenice, ne kvalitetom formulacije.
Tekstualni skor se **ne spaja** sa skorom preživljavanja činjenice.

Istorijski NS002 `J = 1/10` je **HISTORICAL / NON-REPRODUCIBLE** i ovde se ne
koristi kao baseline niti se sa bilo čim numerički poredi.

---

## 11. FACT SURVIVAL SCORE

| | |
|---|---|
| A — činjenica prisutna | **10/10** |
| A — provenance ispravan | **10/10** |
| J — strukturalno preživljavanje kroz pali pravni deo | **10/10** |
| J — provenance ispravan | **10/10** |
| NEG — bez izvora nema činjenice | **5/5** |
| UI prikaz | **5/5** |

---

## 12. REGRESSION RESULTS

| | passed | failed | skipped |
|---|---|---|---|
| baseline | 6230 | 8 | 2 |
| posle | **6267** | 8 | 2 |

`6267 = 6230 + 37` (32 NS003 protokol + 5 UI). Lista padova **identična**
baseline-u: 8 `[trio]` varijanti koje padaju jer `trio` nije instaliran.
Pre-existing.

**Produkcioni kod: 0 izmena.** Novi su samo `scripts/` i `tests/`.

---

## 13. FAILURES / ANOMALIES

### A1 — moj harness je HTTP 402 ocenio kao PASS *(ispravljeno)*

U prvom prolazu 4 od 5 NEG pokušaja vratilo je **HTTP 402 (NO_CREDITS)**.
Verifikator ih je označio kao PASS — „kanala nema i činjenica nije izmišljena"
je tačno za poruku o grešci, a besmisleno kao dokaz. Ti pokušaji nikad nisu
stigli do sistema.

**Uzrok:** krediti su postavljani PRE nego što je red u `profiles` postojao
(`_ensure_profile` ga pravi lenjo, na prvom API pozivu), pa je `update()`
pogodio 0 redova.

**Ispravka:** krediti se postavljaju posle kreiranja predmeta i **čitaju
nazad**; svaki ne-200 je sada `NOT_EXECUTED`, nikad PASS.

### A2 — negativni test je prvo merio pogrešnu stvar *(ispravljeno)*

Negativni predmet je bio u **istom tenantu** koji već ima dokument. Jedini
izvršeni pokušaj vratio je činjenicu — ali sa `dokument = 'dokument_a.docx'`,
doslovnim navodom i ispravnim oznakama. To **nije izmišljanje**:
`retrieve_documents` namerno ne filtrira rezultate iz ostalih predmeta istog
vlasnika (institucionalna memorija, 2026-07-26). Test je premešten na **zaseban
tenant bez ijednog dokumenta**.

### A3 — ulazni blokatori, van B4-M2 *(zaobiđeni bez izmene proizvoda)*

* `HTTP 403` — `predmet_upload_ai` traži `minimum_plan='professional'`; plan
  podignut **samo benchmark nalogu** (provizioniranje tenanta)
* `HTTP 415` — produkcija prima samo PDF/DOCX; napravljen DOCX kontejner sa
  doslovnim tekstom fixture-a

### A4 — jedan `DELETE /api/predmeti` vratio 409

U prvom prolazu. Naknadna provera pokazuje **0 predmeta, 0 profila, nalog
obrisan** za oba benchmark naloga. Vektori u Pinecone-u za taj predmet nisu
zasebno verifikovani — vodi se kao **NOT VERIFIED**, ne kao počišćeno.

---

## 14. ROOT CAUSE

**Nema novog kvara u proizvodu.** Sve tri anomalije su bile u harnessu ili u
ulaznim uslovima. Produkcioni kod nije menjan.

---

## 15. FINAL DEFINITION OF DONE

| | Stavka | Status |
|---|---|---|
| ✅ | stvarni dokument ingestovan | DOCX, HTTP 200 |
| ✅ | stvarni tenant | jednokratan, obrisan |
| ✅ | stvarni Pinecone retrieval | owner namespace |
| ✅ | stvarni LLM | bez mock-a |
| ✅ | A izveden 10/10 | svih 10 HTTP 200 |
| ✅ | J izveden 10/10 | svih 10 HTTP 200 |
| ✅ | činjenica preživljava pravni failure path | 9/10 `A_pravni_LOW` |
| ✅ | činjenica ima validan dokumentarni source | doslovan podniz, `dokument_a.docx` |
| ⬜ | činjenica se ne pojavljuje pre retrieval-a | **NOT EXECUTABLE** |
| ✅ | činjenica se ne pojavljuje kada source nije dostupan | NEG 5/5 |
| ⬜ | **blocked** API odgovor nosi kanal | **`blocked=True` se nije desio uživo** |
| ✅ | *rejected* (LOW) API odgovor nosi kanal | 9/10 |
| ✅ | UI prikazuje kanal | 5/5, stvarni odgovori |
| ✅ | nema regresije | 6267 / 8 / 2, ista lista padova |
| ✅ | nema izmene guard-a | 0 izmena produkcionog koda |
| ✅ | nema promene prompt governance-a | 0 |
| ✅ | nema promene control flow-a | 0 |

**Dve stavke nisu dokazane → GREEN se ne proglašava.**

---

## 16. FINAL VERDICT

🟡 **BLOCKED**

Odgovor na pitanje gate-a — *„Da li B4-M2 sada zaista radi u produkcionom
runtime-u kada pravni deo sistema padne?"* — je: **za pali pravni retrieval
(LOW), DA, dokazano uživo 10/10, uključujući i ono što advokat vidi na ekranu.**
Za **guard-block granu** odgovor i dalje ne postoji iz živog izvora.

**SLEDEĆA AKCIJA:** izazvati `blocked=True` uživo. Guard opali kada model
citira član kojeg nema u kontekstu — treba pronaći pitanje koje to pouzdano
izaziva na produkciji, pa ponoviti 10 pokušaja i izmeriti nosi li blokiran
odgovor kanal. Bez toga `r4011` i `r4022` ostaju dokazani samo determinističkim
testovima.
