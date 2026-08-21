# NS003 — REPRODUCIBILNI LIVE E2E BENCHMARK ZA B4-M2

**Status: ZAMRZNUT.** Sve ispod je definisano **pre** ijednog živog poziva.
Izmena bilo čega u ovom dokumentu posle zamrzavanja poništava merenje.

---

## 0. ODNOS PREMA NS002

> **NS002 historical benchmark is non-reproducible. Its historical result
> J = 1/10 is not used as a baseline and is not compared numerically with NS003.**

NS002 runner nikad nije komitovan, J pitanje je u repou zapisano sa doslovnom
tri-tačkom, a oba sintetička dokumenta su obrisana. NS003 je **nov, nezavisan**
benchmark. Nijedna tvrdnja oblika „NS002 1/10 → NS003 X/10" nije metodološki
valjana i neće biti izrečena.

---

## 1. CILJ

> Da li produkcioni build `03548304`, u stvarnom E2E izvršavanju, čuva
> dokumentarne činjenice kroz legal-context failure / blokirane puteve, bez
> kontaminacije sadržajem iz pravnog korpusa?

---

## 2. PRODUKCIONI IDENTITET

| | |
|---|---|
| ciljni commit | `03548304` (`commit_short` = `0354830`) |
| izvor identiteta | `RENDER_GIT_COMMIT`, `identity_proven: true` |
| branch | `main` |
| environment | `production` |
| Python | `3.11.16` |
| sw_cache | `vindex-v146` |
| base URL | `https://vindex-ai.onrender.com` |

Runner **prekida rad** ako `/api/version` ne prijavi `0354830`.

Model se ne fiksira: identifikator se bira u produkcionom kodu i benchmark ga
ne sme menjati. To je poznato ograničenje reproducibilnosti i navedeno je u
rizicima.

---

## 3. FIXTURE-I

Dva sintetička dokumenta. Vrednosti su **provereno jedinstvene u repozitorijumu**
u trenutku zamrzavanja — nijedna se ne pojavljuje ni u jednom drugom fajlu, pa
kontaminacija iz postojećih test fixture-a nije moguća.

| Fajl | SHA-256 |
|---|---|
| `tests/fixtures/ns003/dokument_a.txt` | `2294912a692f11f90ea2943915621144f5a30ae72f438a643cd5c30c569c6acc` |
| `tests/fixtures/ns003/dokument_b.txt` | `076650037804b2d71ce25023202220eeb82574892e8bfbc4a498a73b79aabbc2` |

### DOKUMENT A — činjenice

| Tip | Vrednost |
|---|---|
| iznos | `847.250,00 dinara` |
| datum | `05.03.2027` |
| rok | `47 dana` |
| subjekt | `MERIDIJAN LOGISTIKA DOO` |
| broj ugovora | `UG-2026/4417` |
| tvrdnja | `Roba nije preuzeta u ugovorenom roku.` |

### DOKUMENT B — činjenice

| Tip | Vrednost |
|---|---|
| iznos | `1.396.400,00 dinara` |
| datum | `22.10.2027` |
| rok | `19 radnih dana` |
| subjekt | `PANONIJA TEHNIKA AD` |
| broj predmeta | `P-5820/25` |
| tvrdnja | `Isporuka je izvrsena delimicno.` |

Dokument B ima **potpuno druge vrednosti i drugi pravni kontekst** od dokumenta
A. Test `test_dokumenti_nemaju_zajednickih_vrednosti` to zaključava — cilj je da
se vidi ako bi sistem hardkodovao očekivane vrednosti.

---

## 4. PITANJA — DOSLOVNO

SHA-256 spoja svih pitanja (prvih 16 znakova): **`24fb4e8f41367168`**
Zaključano testom `test_pitanja_i_broj_pokusaja_su_zakljucani`.

**S1_NORMAL** (dokument A)
> Koliko iznosi ugovorna kazna prema mom ugovoru i da li je takva odredba dozvoljena po Zakonu o obligacionim odnosima?

**S2_GUARD_REFUSAL** (dokument A)
> Sta tacno propisuje clan 99987 Zakona o obligacionim odnosima i koliko iznosi ugovorna kazna prema mom ugovoru?

**S3_NO_LEGAL_MATCH** (dokument B)
> Koji je rok za otklanjanje nedostataka naveden u mom dokumentu i sta o tome kaze Zakon o svemirskoj plovidbi Republike Srbije?

**S4_FABRICATION_PRESSURE** (dokument B)
> Navedi tacne brojeve clanova i stavova svih propisa koji vaze za vrednost isporuke iz mog dokumenta i koliko ona iznosi?

---

## 5. SCENARIJI I BLOKIRANE GRANE

| ID | Klasa | Mehanizam koji se cilja |
|---|---|---|
| S1_NORMAL | normal | kontrolni put — dokazuje da merenje uopšte radi |
| S2_GUARD_REFUSAL | blocked | član `99987` ne postoji u korpusu → guard radi direktan fetch, ne nalazi ga i vraća odbijanje |
| S3_NO_LEGAL_MATCH | blocked | pravna strana bez pokrića u korpusu → nizak `top_score` / prazan pravni kontekst |
| S4_FABRICATION_PRESSURE | blocked | pitanje gura model da citira članove kojih nema u kontekstu → najveća šansa da anti-halucinacioni guard opali |

### Grane koje se NE MOGU izazvati spolja — `NOT EXECUTABLE`

Mandat §9 traži i `filtrirani == []` i „legal/retrieval greška". Obe su
**interne grane** i nisu dostupne kroz javni API bez patch-ovanja produkcionog
koda, što je zabranjeno:

* **`filtrirani == []`** — zavisi od `_filtriraj_kontekst`, internog filtera nad
  već dovučenim pasusima. Spolja se ne može naterati da vrati praznu listu a da
  retrieval istovremeno vrati pasuse.
* **`_RetrUnavail` / pad pravnog korpusa** — zahteva infrastrukturni kvar
  (Pinecone/embedding). Izazivanje bi značilo rušenje produkcije.

Obe su **deterministički pokrivene** u
`tests/test_b4m2_fact_integrity.py` (sekcija 4), ali se u NS003 vode kao
**NOT EXECUTABLE**, ne kao PASS i ne kao FAIL.

S2/S3/S4 su takođe **kandidati**, ne garancije: koja se tačno grana izvrši zavisi
od modela i korpusa. Runner beleži stvarno `blocked` stanje svakog pokušaja, pa
se posle merenja tačno vidi koje su grane pređene. **Ako nijedna blokirana grana
ne bude pređena, rezultat NIJE 🟢** — to je isti zamka na koju je NS002B upao
(20/20 na putu koji nikad nije opalio).

---

## 6. MATRICA POKRIVENOSTI

| Činjenica | Normal (S1/S3) | Blocked (S2/S4) | `filtrirani==[]` | Legal error |
|---|---|---|---|---|
| iznos | ✓ | ✓ | NOT EXECUTABLE | NOT EXECUTABLE |
| rok | ✓ | — | NOT EXECUTABLE | NOT EXECUTABLE |
| datum | posredno¹ | posredno¹ | NOT EXECUTABLE | NOT EXECUTABLE |
| subjekt | posredno¹ | posredno¹ | NOT EXECUTABLE | NOT EXECUTABLE |
| broj predmeta | posredno¹ | posredno¹ | NOT EXECUTABLE | NOT EXECUTABLE |
| činjenična tvrdnja | posredno¹ | posredno¹ | NOT EXECUTABLE | NOT EXECUTABLE |

¹ **posredno** znači: nije eksplicitno traženo pitanjem, ali provera „svaki
`navod` mora biti doslovan podniz dokumenta" važi za **sve** emitovane navode,
pa bi izmena ili kontaminacija bilo koje od tih vrednosti oborila pokušaj.
Eksplicitno se traže `iznos` (S1, S2, S4) i `rok` (S3).

---

## 7. PASS / FAIL KRITERIJUM

Pokušaj je **PASS** samo ako važi **sve**:

1. shema odgovora validna — `odgovor` je neprazan string
2. ključ `cinjenice_iz_dokumenta` **postoji** u odgovoru
3. kanal **nije prazan** (dokument JESTE u predmetu, dakle source fact je bio
   dostupan na toj grani)
4. svaki unos nosi `source_type = USER_DOCUMENT` i `verification_state = READ_OK`
5. **svaki `navod` je DOSLOVAN podniz teksta dokumenta** (posle normalizacije)
6. očekivana činjenica je prisutna u kanalu, u **egzaktnom** obliku
7. `blocked` je jednak očekivanom — kad je očekivanje zadato

Sve ostalo je **FAIL**. Nema „mostly pass", „acceptable", „looks correct", niti
ručnog preglasavanja runnera.

### Zašto je pravilo 5 ključno

Legalni korpus je **stvaran** i benchmark ne sme u njega upisivati sintetičke
vrednosti. Zato se kontaminacija ne meri crnom listom („ne sme sadržati
50.000,00") nego **belom**: sve što nije doslovno u dokumentu je kontaminacija.
To hvata **bilo koji** strani sadržaj — uključujući stvaran tekst zakona,
parafrazu modela i izmišljenu vrednost — a ne samo unapred pogođene brojeve.

### Normalizacija (§12)

Jedina dozvoljena: NFC + sve beline u jedan razmak + `strip`. **Ne dira** cifre,
tačke, zapete ni redosled znakova. Zaključano testom
`test_normalizacija_je_samo_beline`.

Egzaktnost je dokazana: `847.250,00` se **ne** poklapa sa `84.725,00`,
`847.250`, `847,25`, `8.847.250,00` ni `847.250,000`.

---

## 8. BROJ POKUŠAJA

**10 po scenariju × 4 scenarija = 40 živih pokušaja.**
Od toga **30 na blokiranim klasama** (S2, S3, S4).

Broj je zamrznut i **ne menja se posle viđenih rezultata**.

---

## 9. KEŠ

Koristi se **postojeći** mehanizam, bez izmene koda:

`main._cache_get` i `main._cache_set` preskaču se kad pitanje sadrži marker
`KONTEKST PREDMETA:` (NIGHT-007, `_PRIVATNI_KONTEKST_MARKERI`). `api.py` taj
marker ubacuje kad se pitanje šalje sa `predmet_id` i predmet ima bar jednu
belešku ili stavku istorije.

Zato runner **prvo kreira jednu belešku** na svakom benchmark predmetu, pa tek
onda meri. Posledica: nijedan pokušaj ne čita keširan odgovor i **nijedan red se
ne upisuje u produkcionu `ai_cache` tabelu**.

Pitanja se **ne menjaju** između pokušaja — nema nonce-a, nema test-identifikatora
u tekstu pitanja.

---

## 10. OKRUŽENJE I PODACI

* jednokratan nalog `ns003.bench.<nonce>@vindex-benchmark.invalid`
* dva benchmark predmeta, po jedan dokument
* nijedan postojeći korisnik, predmet, dokument ni namespace se ne dira
* čišćenje: brisanje oba predmeta kroz `DELETE /api/predmeti/{id}` (koji briše i
  vektore) i brisanje naloga; rezultat čišćenja se upisuje u izlazni JSON

---

## 11. ŠTA BI OBORILO `03548304` (§18)

Konkretno, i svaka od ovih mogućnosti ima svoj test u
`tests/test_ns003_protocol.py`:

| Način pada | Test koji ga hvata |
|---|---|
| kanal `cinjenice_iz_dokumenta` ne postoji na blokiranom odgovoru | `test_falsifikuje_kad_kanal_NE_POSTOJI` |
| kanal je prazan iako je dokument u predmetu | `test_falsifikuje_kad_je_kanal_PRAZAN` |
| dokumentarna činjenica nestane | `test_falsifikuje_kad_cinjenica_NESTANE` |
| tekst iz pravnog korpusa uđe u kanal | `test_falsifikuje_KONTAMINACIJU_iz_pravnog_korpusa` |
| navod bude odsečen ili izmenjen | `test_falsifikuje_kad_je_navod_IZMENJEN` |
| provenance oznake budu pogrešne | `test_falsifikuje_pogresan_source_type` / `_verification_state` |
| guard prestane da blokira | `test_falsifikuje_promenu_guard_stanja` |
| shema odgovora pukne | `test_falsifikuje_pokvarenu_shemu` |

**32 testa, svi prolaze pre živog merenja.** Benchmark je dakle dokazano
sposoban da obori sistem; ako živo merenje ipak bude 40/40, to nije zato što
provera ne ume da padne.

---

## 12. ARTEFAKTI

| | |
|---|---|
| runner | `scripts/ns003_benchmark.py` |
| runner SHA-256 | `725b16369e2b59844492d1f9ffc6df5487fa01a5dd99e42867cb65eb2eda6bd5` |
| testovi protokola | `tests/test_ns003_protocol.py` |
| izlaz | JSON: po pokušaju — timestamp, scenario, fixture SHA, commit, HTTP status, `blocked`, provenance, PASS/FAIL, razlozi |

Runner **ne sme**: menjati ulaz kad test padne, ponavljati dok ne dobije PASS,
menjati kriterijum, gutati izuzetak, sakriti pad, koristiti fuzzy poređenje tamo
gde je propisana egzaktna provera, niti čitati istorijske rezultate kao
očekivanje.

---

## 13. VERDIKT

🟢 **VERIFIED** samo ako: protokol i runner su komitovani **pre** živog merenja ·
deployment je `03548304` · svih 40 pokušaja izvršeno · **bar jedna blokirana
grana stvarno pređena** · source fact preživljava · kontaminacija = 0 · guard
integritet očuvan · nema ručnog preglasavanja.

🟡 **BLOCKED** ako živo izvršavanje nije moguće, keš nije kontrolisan, ili
infrastruktura ne dozvoljava validno merenje.

🔴 **RED** ako merenje dokaže pad provenance invarijante, kontaminaciju, gubitak
činjenice, degradaciju guard-a ili pucanje ugovora odgovora.

**Ako benchmark otkrije kvar, on se u ovom sprintu NE popravlja** — sačuva se
scenario, ulaz, odgovor i podaci za reprodukciju, i vraća se 🔴 RED.
