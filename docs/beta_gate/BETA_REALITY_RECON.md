# BETA REALITY RECON — FINAL FORENSIC REPORT

**Datum:** 2026-08-21 · **Tip:** RECONNAISSANCE (bez remedijacije) · **Produkcija:** `27cb670`

---

## 1. VERDICT

🔴 **RED — BETA NO-GO**

Jedan dokazan blocker: **neuspelo brisanje predmeta uništava sadržaj dokumenta,
a korisniku poruka tvrdi da ništa nije promenjeno.**

---

## 2. PRODUCTION IDENTITY

`commit_short 27cb670` · `identity_proven: true` · `branch main` ·
`environment production` · Python 3.11.16 · `sw_cache v146`.
Lokalni HEAD identičan, worktree čist.

---

## 3. BETA USER JOURNEY

Izvedeno uživo, dva jednokratna tenanta, pravi ingest / Pinecone / model.

| Korak | Rezultat |
|---|---|
| auth, kreiranje predmeta | ✅ |
| upload DOCX + ingest | ✅ HTTP 200 |
| činjenično pitanje | ✅ činjenica vraćena |
| blokirano pravno pitanje | ✅ činjenica preživela |
| rok iz dokumenta | ✅ upisan, tačan datum |
| finansijski izveštaji | ✅ 4/4 HTTP 200 |
| glasovni put | ⚠️ NOT VERIFIED (greška harnessa) |
| **brisanje predmeta** | 🔴 **BLOCKER** |
| tenant izolacija | ✅ drži |

---

## 4. B1 STATUS — ✅ **RESOLVED**

Lanac dokazan uživo: `dodaj_rok` → `success=true` **i `rok_dodat=true`** →
`GET /hronologija` → rok pronađen → **datum tačan** (`2027-03-05`).

Stari nalaz („UI tvrdi da jeste, a nije sačuvano") **više ne važi**. API sada
razdvaja `success` od `rok_dodat`, a frontend proverava `rok_dodat` nezavisno.

## 5. B2 STATUS — 🟡 **NO BLOCKER EVIDENCE / NOT FULLY VERIFIED**

`/billing/report/{godisnji,po-klijentu,mesecni,po-tipu}` — **4/4 HTTP 200**,
koherentne nule za prazan tenant, `nepotpuno: []`. Nijedan 5xx, nijedna lažna
tvrdnja. **Nije mereno sa stvarnim finansijskim podacima** — schema drift nije
ponovo dokazan, ali ni isključen.

## 6. B3 STATUS — ⚠️ **NOT VERIFIED**

`POST /api/voice/command` vratio **422**: moj harness je slao `tekst`, a polje se
zove `text`. **Greška harnessa, ne proizvoda.** Glasovni put ostaje neizmeren.

## 7. B4 STATUS — ✅ **CLOSED, bez regresije**

Smoke uživo: činjenično pitanje i blokirano pitanje — oba `HTTP 200`, kanal
prisutan, `847.250,00` prisutan. B4-M2 ostaje zatvoren.

## 8. B5 STATUS — 🟡 **RISK**

Nije rađena destruktivna reprodukcija u produkciji.

Nađeno čitanjem šeme: **`events(id)` referenciraju tri tabele bez
`ON DELETE CASCADE`** — `case_evolution_consequences` (096),
`case_intelligence_summaries` (098), `case_actions` (099). To je korenski uzrok
blockera iz §12. Migration tracking i dalje ne postoji kao mehanizam.

---

## 9. SECURITY STATUS — ✅ **IZOLACIJA DRŽI**

Tenant B napao predmet tenanta A, četiri sonde, sa proverom baze pre i posle:

| Sonda | HTTP | Pročitao tuđe | Upisao |
|---|---|---|---|
| GET hronologija | 500 | **NE** | — |
| GET predmet | 404 | **NE** | — |
| POST beleska | 500 | **NE** | **+0 redova** |
| POST confirm-links | 500 | **NE** | **+0 redova** |

Tajna beleška i rok tenanta A ostali netaknuti. **Nema cross-tenant curenja.**

**BETA-SEC-001 (LOW):** vlasnička provera koristi `.single()`, koji **baca** kad
nema reda, pa tuđi zahtev dobija **HTTP 500 umesto 404/403**. Linija
`if not pred_row.data: 404` je time mrtva. Fail-closed — bezbednosno ispravno,
ali pogrešan status i šum u Sentry-ju.

---

## 10. DATA LIFECYCLE STATUS — 🔴 **BLOCKER**

`CREATE / READ / UPDATE` ✅. **`DELETE` pada za svaki predmet sa dokumentom.**

---

## 11. AI FAILURE MODE STATUS — ✅

Slab/nepostojeći pravni pogodak → sistem priznaje neizvesnost
(„nije pronađen u indeksu"), ne izmišlja izvor, razdvaja dokumentarnu od pravne
činjenice, i odbija kad treba. Dokazano u B4-M2 živom merenju (10/10).

---

## 12. DISCOVERED BLOCKERS

| ID | Severity | Finding | Evidence | Reproducible | Beta impact |
|---|---|---|---|---|---|
| **BETA-DEL-001** | 🔴 RED | Neuspelo brisanje predmeta **uništi vektore dokumenta** a predmet ostavi; korisniku piše da ništa nije promenjeno | pre: činjenica DA → `DELETE 409`, `vektori: OBRISANI`, `neuspele_tabele: ['events']` → posle: činjenica **NE**, predmet vidljiv `200`, dokument u bazi | **3/3** | Advokat izgubi sadržaj predmeta i ne zna |
| BETA-SEC-001 | 🟢 LOW | Cross-tenant zahtev vraća 500 umesto 404/403 (`.single()` baca) | 3 sonde, `+0` upisa, 0 pročitanih tuđih podataka | 2/2 | Kozmetika + Sentry šum |
| BETA-COST-001 | 🟢 LOW | `api_costs` tabela ne postoji; `shared/cost.py:97` INSERT pada, hvata se | probe šeme | 1/1 | Nema; trošak se ne evidentira |
| BETA-RATIO-001 | 🟢 LOW | `ratio_decidendi` ne postoji; keš uvek promašuje | probe šeme | 1/1 | Viši trošak, bez lažne tvrdnje |

### BETA-DEL-001 — ROOT CAUSE

Dva sloja, oba pročitana iz koda:

1. `shared/predmet_deletion.py:30` — **vektori se brišu PRE redova**, namerno
   („zaostao vektor uz obrisan red je curenje").
2. `shared/predmet_deletion.py:65` — **`events` je uvršten u `TABELE_BEZ_FK`**.
   To je **netačno**: `events(id)` referenciraju tri tabele bez
   `ON DELETE CASCADE`, pa brisanje pada na FK RESTRICT.

Redosled je time fatalan: vektori nestanu → `events` padne → `PARTIAL_FAILURE` →
predmet ostane. **Ponavljanje ne može uspeti** — FK će pasti opet.

Poruka koju korisnik dobija:

> „Predmet NIJE obrisan i operacija se moze ponoviti. Predmet je i dalje u vašoj
> listi; pokušajte ponovo."

Ta poruka je **neistinita**: vektori jesu obrisani, nepovratno.

---

## 13. FALSE POSITIVES / STARI NALAZI KOJI VIŠE NE VAŽE

| Stari nalaz | Zašto više ne važi |
|---|---|
| `rokovi` tabela ne postoji a kod je gađa | **Kod je NE gađa** — 0 pojava u produkcionom kodu. Rokovi žive u `predmet_hronologija` (52 reda) |
| `stavke_fakture` ne postoji | Kod je ne gađa |
| B1 — rok se ne čuva, UI laže | Dokazano uživo: čuva se, datum tačan, API priznaje `rok_dodat` |
| B2 — schema drift ruši izveštaje | 4/4 endpointa HTTP 200, koherentno |
| „3 cross-tenant RED nalaza" iz prvog prolaza | **Moja greška klasifikacije**: HTTP 500 sam tretirao kao propuštanje. Provera baze pokazuje `+0` upisa i 0 pročitanih tuđih podataka |

---

## 14. OPEN RISKS

* **BLOCKER:** BETA-DEL-001
* **RISK:** FK bez `ON DELETE CASCADE` na `events` (096/098/099); migration
  tracking ne postoji
* **BACKLOG:** BETA-SEC-001, BETA-COST-001, BETA-RATIO-001
* **NOT VERIFIED:** B3 glasovni put (greška harnessa); B2 sa stvarnim
  finansijskim podacima; Pinecone vektori posle `PARTIAL_FAILURE` (koliko ih
  tačno ostane)

---

## 15. BETA GO / NO-GO MATRIX

| | |
|---|---|
| 🔴 RED | BETA-DEL-001 — beta ne sme dalje |
| 🟡 YELLOW | B2 i B3 nisu potpuno izmereni |
| 🟢 GREEN | B1, B4-M2, tenant izolacija, AI failure modes |

---

## 16. SINGLE HIGHEST PRIORITY

**BETA-DEL-001.** Jedini blocker. Spada u kategoriju #1 (DATA LOSS) i #8 (SILENT
FAILURE) istovremeno — gubitak je tih i poruka ga aktivno poriče.

---

## 17. RECOMMENDED NEXT FORENSIC SPRINT

Remediation sprint za **BETA-DEL-001**. Otvorena pitanja koja sprint mora rešiti
pre koda: da li se `events` briše kaskadno, arhivira, ili se brisanje vektora
pomera **posle** uspešnog brisanja redova (uz karantin da vektor ne ostane
orphan). To je arhitektonska odluka o redosledu, ne jednolinijska popravka.

---

## 18. WHAT MUST NOT BE TOUCHED

* **B4-M2** — 🟢 VERIFIED uživo (10/10 blocked, NEG 5/5, UI 5/5). Ne otvarati
  bez dokaza o regresiji.
* **Anti-halucinacioni guard** — dokazano netaknut i funkcionalan.
* **Zamrznuti NS003 protokol** — heševi zaključani.
* **Tenant izolacija** — dokazano drži; ne „popravljati" 500 tako što se dira
  ovlašćenje, nego samo mapiranje statusa.
* **B1 lanac roka** — dokazano radi.
