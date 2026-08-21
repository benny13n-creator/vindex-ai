# B4-M2 — LIVE E2E VERIFICATION (A / J / GUARD BLOCK)

**Datum:** 2026-08-21 · **Tip:** RELEASE EVIDENCE, ne development

---

## 1. VERDICT

🟢 **VERIFIED** — za sve stavke koje su spolja izvršive.

`blocked = True` je **stvarno opalio uživo, 10/10**, i **svih 10 blokiranih
odgovora nosi činjenicu iz dokumenta** sa ispravnim provenance-om. Pređene su
**dve različite** blokirane grane, obe iz skupa koji je NALAZ 2 popravio.

Jedina stavka koja ostaje otvorena je `PRE-RETRIEVAL`, koja **nije spolja
izvršiva** i eksplicitno je označena kao **NOT LIVE VERIFIED** — što samo po sebi
nije dokaz kvara.

### ISPRAVKA PRETHODNOG IZVEŠTAJA

Prethodna verzija ovog dokumenta tvrdila je: *„`blocked=True` se nije desio
nijednom u 10 živih J pokušaja."* **Ta tvrdnja je bila netačna.**

Uzrok je moja merna greška: `api.py::normalizuj_rezultat` je **bela lista** i
**ne prosleđuje polje `blocked`** (0 pojava u whitelist-i). Merio sam polje koje
API nikad ne šalje, pa sam `None` pročitao kao „guard nije opalio".

Guard **jeste** opalio. Dokaz je u samom tekstu odgovora, koji je bajt-potpis
funkcija koje se pozivaju **isključivo** sa blokiranih izlaza.

---

## 2. PRODUCTION IDENTITY

| | | Status |
|---|---|---|
| commit | `6458587` | **PROVEN** (`identity_proven: true`, `RENDER_GIT_COMMIT`) |
| branch / env | `main` / `production` | PROVEN |
| Python / sw_cache | 3.11.16 / `vindex-v146` | PROVEN |
| deployovani kod == analizirani | **0 razlike** u produkcionim modulima (`6458587` ↔ lokalni HEAD) | PROVEN |
| lokalne promene koje utiču na rezultat | 0 (`git status` čist) | PROVEN |
| tenant izolacija | jednokratni nalozi, obrisani i provereni | PROVEN |
| model | pravi, bez mock-a | PROVEN |
| Pinecone | produkcioni indeks, owner namespace | PROVEN |
| cache bypass | postojeći mehanizam — marker `KONTEKST PREDMETA:` (NIGHT-007) | PROVEN |

---

## 3. EXACT COMMIT MEASURED

**`6458587`.** Nije `03548304` — manuelni deploy nije izvršen. Diff
`03548304 → 6458587` menja **0 produkcionih fajlova**. Navedeno kao činjenica,
ne kao zamena za identitet. Zamrznuti NS003 runner ostaje **NEIZVRŠEN**.

---

## 4. GUARD TRIGGER

Forenzički mapirano pre merenja, bez izmene koda.

**Ulaz u guard:** `ask_agent` KORAK 1.5 (`main.py:3662`) →
`ekstrakcija_clana(pitanje_api)` → ako je član prepoznat →
`_direktan_fetch_clana(..., raise_on_error=True)` → **ako je rezultat prazan →
`blocked: True`** i `_format_refusal`.

Bitno: KORAK 1.5 je **pre** KORAK 2 (LOW), pa se guard izvršava bez obzira na
pojas pouzdanosti.

Izmereno lokalno pre živog testa (samo čitanje iz Pinecone-a):

| Ulaz | `ekstrakcija_clana` | `_direktan_fetch_clana` |
|---|---|---|
| `clan 99987 Zakona o obligacionim odnosima` | `('Član 99987', 'zakon o obligacionim odnosima')` | **0 matcheva** |
| `Član 262` (kontrola) | prepoznat | 5 matcheva |

Trigger je dakle **deterministički po konstrukciji**, ne nasumično pogađanje.
Nijedan prag, klasifikator, prompt ni guard nije menjan; ništa nije
monkeypatch-ovano.

### Mapa blokiranih izlaza

| PATH | TRIGGER | STATUS | blocked | document fact | legal content | citations |
|---|---|---|---|---|---|---|
| `r3706` E5 HARD_REFUSAL | citiran član nije u korpusu | success | **True** | očekivan | nema tvrdnje | nema |
| `r3899` E10 COMMIT3 BLOCK (MEDIUM) | `_parsiraj_strukturni_odgovor` → ok=False | success | **True** | očekivan | blokiran | nema |
| `r4053` E15 COMMIT3 BLOCK (downgrade) | isto, posle downgrade-a | success | **True** | očekivan | blokiran | nema |
| `r3911` / `r4065` E11/E16 | `_verifikuj_pravne_greske` → False | success | **True** | očekivan | blokiran | nema |

---

## 5. LIVE ATTEMPTS

Pitanje (doslovno, isto u svih 10):

> „Sta tacno propisuje clan 99987 Zakona o obligacionim odnosima i koliko iznosi ugovorna kazna prema mom ugovoru?"

DOCUMENT FACT: **`847.250,00`**

| # | grana (`blocked=True`) | kanal | 847.250,00 | source_type | verif | izvori |
|---|---|---|---|---|---|---|
| 1 | COMMIT3 GUARD BLOCK | DA | DA | OK | OK | ZOO 270–276 (retrieval metapodaci) |
| 2 | HARD_REFUSAL | DA | DA | OK | OK | `None` |
| 3 | HARD_REFUSAL | DA | DA | OK | OK | `None` |
| 4 | HARD_REFUSAL | DA | DA | OK | OK | `None` |
| 5 | HARD_REFUSAL | DA | DA | OK | OK | `None` |
| 6 | HARD_REFUSAL | DA | DA | OK | OK | `None` |
| 7 | HARD_REFUSAL | DA | DA | OK | OK | `None` |
| 8 | HARD_REFUSAL | DA | DA | OK | OK | `None` |
| 9 | HARD_REFUSAL | DA | DA | OK | OK | `None` |
| 10 | HARD_REFUSAL | DA | DA | OK | OK | `None` |

Svih 10: HTTP 200, keš zaobiđen, nezavisni pokušaji.

---

## 6. BLOCKED RATE

**10 / 10** — `blocked = True` **LIVE VERIFIED**.

Dve različite grane pređene: `HARD_REFUSAL` 9×, `COMMIT3 GUARD BLOCK` 1×.
Obe su izlazi koje je NALAZ 2 popravio.

---

## 7. DOCUMENT FACT SURVIVAL

**10 / 10 blokiranih odgovora nosi `847.250,00`.**

Navod je **doslovan podniz** dokumenta (`dokument_a.docx`), ne parafraza.

| Mera | Rezultat | Status |
|---|---|---|
| A — dokument dostupan | 10/10 | LIVE VERIFIED |
| J — blokirani izlaz | 10/10 | LIVE VERIFIED |
| NEG — tenant bez dokumenta | 5/5 | LIVE VERIFIED |
| UI | 5/5 | LIVE VERIFIED |

---

## 8. PROVENANCE INTEGRITY

* `source_type = USER_DOCUMENT` — 10/10
* `verification_state = READ_OK` — 10/10
* navod doslovan podniz dokumenta — 10/10
* **kanali odvojeni:** `izvori` sadrži isključivo `{zakon, clan, score}`; nijedan
  deo teksta dokumenta nije u pravnom kanalu, i nijedan pravni tekst nije u
  dokumentarnom kanalu
* na 9/10 blokiranih odgovora `izvori` je `None` — nijedan pravni izvor nije
  predstavljen kao potvrđen

---

## 9. GUARD INTEGRITY

| Provera | Status |
|---|---|
| blocked threshold promenjen | **NE** — 0 izmena produkcionog koda od `03548304` |
| klasifikator promenjen | **NE** |
| guard prompt oslabljen | **NE** |
| guard zaobiđen | **NE** — opalio 10/10 |
| blokiran odgovor pretvoren u normalan | **NE** — svih 10 zadržalo tekst odbijanja/blokade |
| lažne pravne citate dodate | **NE** — `izvori` su stvarni retrieval metapodaci; tekst izričito kaže da je pravni deo blokiran |
| dokumentarna činjenica ubačena u pravni kanal | **NE** |
| provenance odvojen | **DA** |

Ništa nije monkeypatch-ovano; nijedan test ne simulira `blocked=True`.

---

## 10. PRE-RETRIEVAL STATUS

**NOT EXECUTABLE / NOT LIVE VERIFIED.**

Grana se izvršava pre nego što `docs` uopšte postoji i **nije dostupna kroz
normalan produkcioni E2E tok** bez internog instrumentiranja. Nije simulirana.

Deterministički je pokrivena u `tests/test_b4m2_fact_integrity.py`
(DETERMINISTICALLY VERIFIED). To **nije** dokaz produkcionog kvara, ali se ne
označava kao VERIFIED.

---

## 11. NEGATIVE CONTROL

**5 / 5 PASS**, svih 5 HTTP 200, na **zasebnom tenantu bez ijednog dokumenta**.
Kanal prazan/odsutan, nijedna činjenica izmišljena.

---

## 12. UI VERIFICATION

**5 / 5 PASS.** Pravi `index.html` u Chromium-u, nad **doslovnim produkcionim
odgovorom koji JESTE blokiran** (`HARD_REFUSAL`, `izvori: None`).

Advokat vidi: **„Činjenica iz vašeg dokumenta → 847.250,00 → dokument_a.docx"**,
uz ogradu „nije pravno potvrđen", izvan bloka pravnih izvora. Kada je kanal
prazan, blok se ne iscrtava.

---

## 13. REGRESSION

| | passed | failed | skipped |
|---|---|---|---|
| baseline | 6230 | 8 | 2 |
| current | **6267** | 8 | 2 |

Lista padova **identična** baseline-u (8 × `[trio]`, paket nije instaliran).
`6267 = 6230 + 37`. **0 izmena produkcionog koda.**

---

## 14. HARNESS ANOMALIES

| # | Anomalija | Status |
|---|---|---|
| H1 | **Merio sam `blocked`, polje koje API ne šalje.** `normalizuj_rezultat` je bela lista bez `blocked`. Zbog toga je prethodni izveštaj pogrešno tvrdio da guard nije opalio. | **REŠENO** — grana se sada utvrđuje po bajt-potpisu teksta |
| H2 | HTTP 402 ocenjen kao PASS; krediti postavljani pre nego što red u `profiles` postoji (`_ensure_profile` ga pravi lenjo) | REŠENO — čitanje nazad; ne-200 = `NOT_EXECUTED` |
| H3 | Negativni test u istom tenantu koji dokument ima; `retrieve_documents` namerno ne filtrira ostale predmete istog vlasnika | REŠENO — zaseban tenant |
| H4 | Ulazni blokatori: `predmet_upload_ai` traži `professional` (403), upload prima samo PDF/DOCX (415) | REŠENO provizioniranjem tenanta i DOCX kontejnerom |
| H5 | Jedan `DELETE /api/predmeti` vratio 409; DB čist, **Pinecone vektori nisu zasebno provereni** | **NOT VERIFIED** |

---

## 15. DEFINITION OF DONE

| Stavka | Status |
|---|---|
| production identity dokazan | **PROVEN** |
| `blocked=True` stvarno opalio | **LIVE VERIFIED** |
| ≥10 validnih live blocked pokušaja | **LIVE VERIFIED** (10) |
| svaki blocked output nosi document fact | **LIVE VERIFIED** (10/10) |
| provenance ispravan | **LIVE VERIFIED** |
| legal/document kanali odvojeni | **LIVE VERIFIED** |
| guard integrity | **PROVEN** (0 izmena koda; guard opalio) |
| NEG čist | **LIVE VERIFIED** (5/5) |
| UI potvrđen | **LIVE VERIFIED** (5/5) |
| nema novih regresija | **PROVEN** |
| pre-retrieval | **NOT LIVE VERIFIED** (eksplicitno) |

---

## 16. ROOT CAUSE

**Nema produkcionog kvara.** Sve anomalije su bile u harnessu ili u ulaznim
uslovima. Produkcioni kod nije menjan ni jednom linijom.

---

## 17. EVIDENCE

```
scripts/b4m2_live_e2e.py                     runner A/J/NEG
scripts/b4m2_live_negative.py                ispravljena negativna verifikacija
tests/test_b4m2_live_ui_verification.py      UI dokaz nad stvarnim odgovorima
tests/fixtures/ns003/live_response_A.json    doslovan produkcioni odgovor
tests/fixtures/ns003/live_response_J.json    doslovan produkcioni odgovor (BLOKIRAN)
tests/fixtures/ns003/dokument_a.txt          zamrznut fixture, sha256 2294912a...
```

---

## 18. NEXT ACTION

**Push `1b311dec` + ovaj izveštaj**, uz svest da Render auto-deploy pomera build.
Merenje je završeno, pa pomeranje više ne šteti ovom gate-u.

Zabeleženo za kasnije, **van opsega**: `blocked` ne prelazi API granicu. Nije
kvar B4-M2 — ali znači da nijedan klijent ne može da razlikuje blokiran od
normalnog odgovora osim po tekstu, i da je svako buduće merenje te grane
osuđeno na potpis teksta. Dodavanje polja bilo bi izmena API ugovora.
