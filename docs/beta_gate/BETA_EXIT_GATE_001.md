# BETA-EXIT-GATE-001 — CRITICAL BETA SURFACE TRIAGE

Baseline `935f4bba`. **Nijedan nalaz nije popravljen, nijedna migracija
pokrenuta, nijedna izmena koda ni baze.** Ovo je klasifikacija već izmerenih
nalaza iz 13 prethodnih sprintova — **bez ijednog novog otkrivanja.**

---

# 1. BETA GO DEFINITION

Vindex sme u ograničenu betu sa stvarnim advokatima i poverljivim dokumentima
kada su ispunjena **tri uslova**, i nijedan više:

1. **Nijedan ekran ne prikazuje pozitivan rezultat provere koja nije izvršena.**
2. **Nijedan dokument jednog advokata nije dohvatljiv drugom** — dokazano, ne
   pretpostavljeno.
3. **Svako obećanje u UI-ju je istinito** ili je zamenjeno poštenom porukom o
   ograničenju.

Sve što ne pada pod ta tri uslova je **posle bete**.

---

# 2. BETA SURFACE

18 tokova iz mandata. Sve ostalo je van opsega osim ako dodiruje poverljivost,
integritet ili autorizaciju.

---

# 3. P0 BLOKATORI — **3**

| # | Nalaz | Zašto P0 |
|---|---|---|
| **P0-1** | **Provera sukoba interesa vraća „nema sukoba" uvek** (`klijenti/router.py:692` + `static/vindex.js:5027`) | **opasan lažno-negativan pravni rezultat.** Advokat vidi `✅ Nije pronađen sukob interesa.` na ekranu čija je jedina svrha upozorenje. Posledica je disciplinska odgovornost i licenca |
| **P0-2** | **Dešifrovan JMBG / pasoš / PIB bez audit zapisa** (`klijenti/audit.py:47-66`; pozivaoci `router.py:415`, `:954`) | poverljivost + dokazivost. Ne može se rekonstruisati ko je i kada video najosetljivije podatke klijenta |
| **P0-3** | **Obrisana beleška ostaje pretraživa u celosti** (`routers/knowledge_base.py:381-404`) | poverljivost. Korisnik izvrši brisanje, sadržaj i dalje izlazi kroz pretragu |

**FS-P0-04 (fail-open rola) je klasifikovan `C`** — danas nedostižan, imenovan,
ne blokira betu.

---

# 4. P1 BLOKATORI — **5**

| # | Nalaz | Zašto blokira |
|---|---|---|
| **P1-1** | **Rokovi se nikad ne sačuvaju.** `predmet_hronologija` ima 52 reda sa šemskim vrednostima, **nula** sa kod-ovim → CHECK obara upis. Dugme „Sačuvaj" **ne javlja ni grešku ni uspeh** | rok je egzistencijalna funkcija advokata; tiho odbacivanje je gore od nepostojanja funkcije |
| **P1-2** | **Obe prijave netačnog odgovora se gube.** Primarna vidljivo (sirov engleski PostgREST tekst, pa `return` preskoči fallback), rezervna tiho (`/api/feedback` piše `q_hash` — kolona ne postoji — a vraća `{"status":"ok"}`) | jedini kanal kojim advokat prijavljuje pogrešan pravni sadržaj; sistem tvrdi da je primljeno |
| **P1-3** | **Klijentski portal 100% mrtav.** `GET /api/portal/predmet` je javna neautentifikovana ruta; poziv ka nepostojećoj `rokovi` je u `asyncio.gather` **bez `return_exceptions`** i van `try` | advokat pošalje klijentu link, klijent dobije grešku |
| **P1-4** | **100 `select()` poziva imenuje nepostojeću kolonu** → PostgREST odbija **ceo zahtev (400)**. Najgušće: `billing_reports.py` 11, `decision_replay.py` 12 | izveštavanje o naplati ne može da se izvrši |
| **P1-5** | **Brisanje dokumenta i predmeta ne postoji**, a GDPR brisanje ne dodiruje ni Storage ni Pinecone | ne može se istinito obećati brisanje |

---

# 5. POTREBNE MITIGACIJE — **3** (umesto popravki)

| # | Rizik | Mitigacija za betu |
|---|---|---|
| **M-1** | **Klijentski portal upload ne šifruje** (jedini od 4 puta) | **Isključiti portal upload za betu.** Bucket **jeste privatan** (izmereno), a portal **nema download putanju** — ali podatak stoji nešifrovan. Isključivanje je jeftinije od rewire-a |
| **M-2** | **Pun tekst dokumenta stoji nešifrovan u Pinecone metapodacima** dok je isti sadržaj u Storage-u AES-GCM šifrovan | **Reći kancelariji doslovno.** Tehnički rewire je van beta opsega; prećutati ga nije opcija |
| **M-3** | **Nijedna tehnička kontrola retencije kod provajdera** — 0 pogodaka za `store=`, ZDR, `organization=` u celom repou | **Pisano objašnjenje u ugovoru.** Retencija počiva 100% na politici provajdera, 0% na kontroli Vindexa |

---

# 6. ODLOŽENI DUG (posle bete)

`api_costs` (koristiti `ai_forensics`) · `ratio_decidendi` keš · `rokovi`
runtime refactor · 92 „schema match only" migracije · 12 `UNKNOWN` migracija ·
`023` prepisati · orphan vektori (dokazano nedohvatljivi) · `feature_usage_log`
prazan · F1-01 odjava no-op · F20-03 cron zelen bez slanja · FS-P2 (26) ·
FS-P3 (7) · 14 tabela koje niko ne referencira.

---

# 7. FALSE-SUCCESS RELEVANTAN ZA BETU

Od **79** nalaza, betu dodiruje **8**: P0-1, P0-3, P1-1, P1-2, P1-3, P1-5, plus
dva koja ulaze u mitigaciju (blokiran AI odgovor vraćen kao `status: "success"`,
i ispad Pinecone-a prikazan kao tvrdnja o srpskom pravu).

**Ostalih 71 je van beta opsega** — ne zato što su bezopasni nego zato što ne
dodiruju poverljivost, autorizaciju ni obećanje dato advokatu.

---

# 8. STATUS POVERLJIVOSTI

| Kontrola | Status |
|---|---|
| Tenant izolacija (cross-tenant **read**) | **PROVEN** — 0 curenja na 297 ruta |
| Tenant izolacija (cross-tenant **write**) | **PROVEN** — 6 rupa zatvoreno, mutacijom dokazano |
| Autorizacija predmeta | **PROVEN** — `get_predmet` ogledalo u `rag_acl` |
| RAG filtriranje | **PROVEN** — F-01 zatvoren, mutacija obara 4 testa |
| Privatnost bucket-a | **PROVEN** — oba `public=false`, izmereno dvaput |
| Enkripcija dokumenata | **PARTIAL** — 3 od 4 puta; portal ne šifruje |
| Pinecone namespace izolacija | **PROVEN** između kancelarija |
| Identitet vektora | **PROVEN** za nove, **FAILED** za 30 postojećih |
| Dohvatljivost orphan vektora | **PROVEN nedohvatljivi** — 5 putanja, disjunktni prostori ID-eva |
| Granica prema provajderu | **FAILED** — 0 tehničkih kontrola; retencija **UNKNOWN** |

---

# 9. ŽIVOTNI CIKLUS DOKUMENTA

| Faza | Može li se istinito obećati |
|---|---|
| UPLOAD | **DA** |
| STORED | **DA** (uz M-1 za portal) |
| PROCESSED | **DA** — OCR je jedini tok koji radi u celosti |
| INDEXED | **NE** — 43/43 dokumenta imaju `status='sacuvano'`, nijedan `indeksirano` |
| RETRIEVABLE | **NE** — presek baze i Pinecone-a je **0** |
| DELETABLE | **NE** — endpoint ne postoji |

**Minimalni skup za zatvaranje:** P1-5 (brisanje) + istinita poruka o
indeksiranju. Dok INDEXED ne radi, UI ne sme tvrditi da je dokument pretraživ —
a od sprinta 004 i ne tvrdi (Playwright dokaz).

---

# 10. GDPR BRISANJE

| Sloj | Status |
|---|---|
| DB zapis | **PARTIAL** — samo `profiles.email/full_name`, rezultat se ne proverava |
| Storage objekat | **NOT IMPLEMENTED** |
| Pinecone vektori | **NOT IMPLEMENTED** — `shared/vector_deletion.py` je potpun i testiran, sa **nula produkcionih pozivalaca** |
| Provenance / audit | **NAMERNO ZADRŽANO** — nepromenljiv zapis |
| Podaci kod provajdera | **PROVIDER DEPENDENT** — bez tehničke kontrole |

**Reč „obrisano" se ne sme koristiti.** 30 orphan vektora je dokazano
**nedohvatljivo**, ali **fizički postoji**.

---

# 11. STATUS 18 TOKOVA

| Tok | Status |
|---|---|
| 1 AUTH | **WORKS WITH MITIGATION** — odjava je no-op |
| 2 TENANT ISOLATION | **WORKS** |
| 3 CLIENTS | **DANGEROUS** — P0-2 |
| 4 CASES | **WORKS** |
| 5 DOCUMENT UPLOAD | **WORKS** |
| 6 DOCUMENT STORAGE | **WORKS WITH MITIGATION** — M-1 |
| 7 OCR / EXTRACTION | **WORKS** |
| 8 EMBEDDING | **BLOCKED** |
| 9 RAG RETRIEVAL | **WORKS** (nad `tekst_sadrzaj`, ne nad Pinecone-om) |
| 10 AI ANSWER | **WORKS WITH MITIGATION** |
| 11 AI PROVENANCE | **WORKS** — 124 reda, guard presreće i sirov klijent |
| 12 CONFLICT OF INTEREST | **DANGEROUS** — P0-1 |
| 13 DEADLINES | **DANGEROUS** — P1-1, tiho odbacivanje |
| 14 FEEDBACK | **BLOCKED** — P1-2 |
| 15 DOCUMENT DELETE | **BLOCKED** |
| 16 CASE DELETE | **BLOCKED** |
| 17 GDPR DELETION | **BLOCKED** |
| 18 AI COST / USAGE | **WORKS WITH MITIGATION** — izvodljivo iz `ai_forensics` |

```
WORKS 6 · WITH MITIGATION 5 · BLOCKED 4 · DANGEROUS 3
```

---

# 12. TESTOVI KOJI SE MORAJU OBRNUTI — **2**, ne 5

Od pet testova koji učvršćuju bagove, betu blokiraju **dva**:

| Test | Šta kodifikuje | Šta treba | Zašto mora |
|---|---|---|---|
| **`test_rokovi_lanac.py:214`** | da je izračunat rok „obrađen" i kad upis padne | upis mora uspeti ili se **javiti korisniku** | bez obrtanja, popravka P1-1 pada kao „regresija" |
| **`test_r004_uspesna_prijava_zaista_upisuje_sadrzaj`** | mokuje Supabase klijenta → dokazuje samo klijentsku polovinu ugovora | mora meriti **da je red stvarno upisan** | bez obrtanja, popravka P1-2 izgleda kao lom |

Ostala tri (`test_cross_doc.py:228`, `test_evidence_klasifikacija.py:93`,
`test_batch_ingest.py:248`) **ne blokiraju A/B nalaze** → posle bete.

---

# 13. TAČAN REDOSLED POPRAVKI — **10 stavki, konačno**

| # | Stavka | Zavisi od |
|---|---|---|
| 1 | **Obrnuti 2 testa** (§12) | — |
| 2 | **P0-1** sukob interesa: **fail-closed** | 1 |
| 3 | **P0-2** audit pri dešifrovanju PII | — |
| 4 | **P0-3** brisanje beleške briše i vektor | — |
| 5 | **P1-3** portal: `return_exceptions` + ukloniti `rokovi` upit | — |
| 6 | **P1-1** rokovi: uskladiti vrednosti sa CHECK-om | 1 |
| 7 | **P1-2** obe putanje prijave | 1 |
| 8 | **P1-4** 100 `select`-ova, počev od `billing_reports.py` | — |
| 9 | **P1-5** DELETE endpoint + povezati `vector_deletion.py` | — |
| 10 | **M-1, M-2, M-3** — isključiti portal upload, napisati dva ograničenja u ugovor | — |

**Lista je konačna i ograničena. Deset stavki. Nema nastavka.**

## Ugovor za P0-1 (§3 mandata) — tačna tražena implementacija

```
Provera je izvršena  →  prikaži rezultat (sukob / nema sukoba)
Provera NIJE izvršena →  prikaži "PROVERA NIJE IZVRŠENA"
                          NIKAD zeleno, nikad "nema sukoba"
```

Konkretno: odgovor mora nositi eksplicitno polje o **statusu provere**, ne samo
`conflict_detected`. `except` ne sme voditi u granu „nema sukoba" — mora vratiti
neuspeh. Frontend mora proveriti `r.ok` **i** taj status. Prazan izvor podataka
je **neuspeh provere**, ne odsustvo sukoba.

---

# 14. BETA GO / NO-GO

| Uslov | Stanje |
|---|---|
| Nijedan ekran ne prikazuje neizvršenu proveru kao pozitivnu | **NE** — P0-1 |
| Nijedan dokument nije dohvatljiv drugom advokatu | **DA** — dokazano |
| Svako obećanje u UI-ju je istinito | **NE** — P1-1, P1-2 |

## **NO-GO**

---

# 15. POSLE BETE

`api_costs` → `ai_forensics` · `ratio_decidendi` keš · `rokovi` refactor ·
92+12 migracija · re-ingest 43 dokumenta · `content_sha256` backfill · orphan
karantin · portal enkripcija · 26 FS-P2 + 7 FS-P3 · 3 preostala testa · 14
nereferenciranih tabela.

---

# FINALNI VERDIKT

## 🔴 RED

Postoji **aktivan blokator integriteta sa pravnom posledicom**, i tačno je
imenovan: **provera sukoba interesa prikazuje pozitivan rezultat provere koja
nije izvršena.**

Ali za razliku od prethodnih sprintova, ovaj **ne ostavlja backlog**. Skup za
zatvaranje je **konačan i prebrojiv: 10 stavki** — 3 P0, 5 P1, 2 obrtanja
testova, uz 3 mitigacije koje su odluke, ne kod.

Poverljivost — jedina stvar koja se advokatu ne sme obećati olako — je
**dokazana** na svakoj kontroli koja se mogla izmeriti. Ono što blokira betu
nije curenje podataka nego **tvrdnje koje sistem daje a ne može da podupre.**
