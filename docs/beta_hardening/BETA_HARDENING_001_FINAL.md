# BETA-HARDENING-001 — FINAL FORENSIC REPORT

# VERDICT

## 🟡 YELLOW

Četiri nalaza zatvorena po punoj matrici, uz mutacionu potvrdu. **Ali sprint se
NE proglašava zelenim**, jer stop-uslovi iz §18 masterprompta nisu svi ispunjeni:
ostaju dokazani bypass-i (glasovni WSS), audit gap-ovi i jedan `UNKNOWN` status
migracije od kog zavisi ceo provenance lanac.

Ono što je zatvoreno — zatvoreno je dokazano. Ono što nije — imenovano je.

---

# BASELINE

```
commit:  6fb4a99f
testovi: 5208 passed / 1 skipped / 0 failed
git:     clean (samo zatečeni untracked skriptovi i podaci)
```

# ZAVRŠNO STANJE

```
testovi: 5235 passed / 1 skipped / 0 failed   (+27)
redosled: no:randomly · seed=11 — oba zelena
migracije: NIJEDNA kreirana, nijedna izvršena
static/, index.html: NEDIRANO
```

---

# AI INVENTORY

Nezavisna inventura (Agent 1), AST-provereno:

```
produkcijskih fajlova sa AI tragom : 90     (moja početna procena 81 — OBORENA)
fajlova koji stvarno izvršavaju AI :  70
izvršnih call-site-ova             : 103
```

| Status | Broj |
|---|---|
| `VERIFIED` | 76 |
| `PARTIAL` | 15 |
| `BYPASS` | **12** |
| `UNKNOWN` | **0** |
| `DUPLICATE` | 0 |

## Ključna arhitektonska činjenica

Kanonska kapija **nije** na nivou gateway-a nego na **nivou SDK klasa**:
`shared/ai_client.py::_patch_prompt_guard()` (iz `api.py:28`) menja
`Completions.create`, `AsyncCompletions.create`, `Embeddings.create`,
`AsyncEmbeddings.create`, `Transcriptions.create`.

Runtime potvrda posle `import api`: sva četiri `_vindex_guarded = True`.

Zato pojedinačni `client.chat.completions.create(...)` **nije** bypass —
pokrivenost je stvar konstrukcije, ne discipline pozivaoca. Bypass je samo ono
što izbegne zakrpljenu metodu.

**LangChain ide KROZ zakrpu** — empirijski dokazano: `OpenAIEmbeddings` je
prošao kroz wrapper, što se vidi po `timeout: 60.0` koji LangChain nije poslao
nego ga je ubacio `_with_timeout()` iz zakrpe.

---

# ŠTA JE ZATVORENO — SA DOKAZOM

## FS-001 — BESPLATNO KORIŠĆENJE AI-JA (najozbiljniji nalaz sprinta)

`/api/pitanje/stream`: `_delivered = True` je stajalo **posle** petlje koja
emituje komade. Generator se suspenduje na `yield`; klijent koji primi poslednji
komad i prekine vezu nikad ne dopusti da se ta linija izvrši → `except
BaseException` refundira kredit.

**Izmereno pre popravke:** 363/363 znaka primljeno, bajt-identično, saldo
10 → 10, **neto cena 0**. Ponovljivo do granice od 10/min; `refund` nema gornju
granicu ni vezu sa zaduženjem.

**Ovo je regresija `NIGHT-005`**, koji je opisao tačno ovaj kvar i tvrdio da ga
zatvara. Njegov test proverava `assert "_delivered = True" in src` — **prisustvo
niske**, ne mesto izvršavanja. **70 testova je bilo zeleno dok je rupa stajala.**

### Prva popravka je bila nedovoljna — i protivnički pregled ju je oborio

Podigao sam zastavicu pred **poslednjim** komadom. To je granicu zloupotrebe
samo **pomerilo za 80 znakova**: prekid na pretposlednjem komadu i dalje je
refundirao. Izmereno: odgovor od 4.000 znakova, primljeno 3.920 (**98%**),
`refund = 1`.

Ubitačna okolnost: `DISCLAIMER` (265 znakova, `main.py:2336`) visi na kraju
**svakog** odgovora — poslednji komad je uvek rep pravne napomene. Napadač ga
žrtvuje i ne gubi nijedan znak pravnog sadržaja. **Cena zaobilaženja: nula.**

**Konačna semantika:** refund samo kad je isporučeno **0 komada**.

## FS-003 — PRAZAN ODGOVOR SE NAPLAĆIVAO

`status="success"` sa praznim tekstom nije bio refundiran ni na jednoj od dve
putanje — prazan ekran, uredan `[DONE]`, naplaćen kredit.

Uslov je bio **doslovno isti** na obe putanje i obe su imale istu rupu. Uveden
je jedan kanonski predikat `api._treba_refundirati()` — **uklanjanje duplikata,
ne nov tok**.

## FS-004 — ODBIJEN ODGOVOR ZABELEŽEN KAO USPEH

`_capture_chat_provenance` se izvršavao **pre** `_enforce_response`. Kad
response firewall odbije odgovor, pozivalac dobija izuzetak — a jedini
forenzički trag kaže `status="success"`.

Popravljeno u **obe** grane (sync i async).

## FS-002 — GLASOVNA SESIJA BEZ ZVUKA ZABELEŽENA KAO USPEŠNA

`status="success"` se upisivao pri **otvaranju** sesije. Sesija u kojoj advokat
nije čuo ništa ostajala je zabeležena kao uspešna — a to je jedini forenzički
trag privilegovanog razgovora.

Sada: `"started"` na otvaranju, terminalni status u `close()` po **stvarnoj
isporuci**.

---

# NALAZI PROTIVNIČKOG PREGLEDA — SVI ZATVORENI

Recenzent je dobio zadatak da dokaže da sprint **nije** zatvoren. Uspeo je, i
dao verdikt **RED**. Sve što je našao je popravljeno:

| # | Nalaz | Ishod |
|---|---|---|
| **SE-001** | FS-001 popravka samo pomerila granicu za 80 znakova (98% besplatno) | zatvoreno — refund samo pri 0 isporučenih komada |
| **SE-004** | FS-002 brojao SAMO `audio.delta` → sesija sa transkriptom lažno `error` | zatvoreno — meri se ishod, ne jedan kanal |
| **SE-005** | odgovor od samih belina → prazan ekran + uredan `[DONE]` | zatvoreno |
| **SE-006** | `_treba_refundirati` bacao `AttributeError` na ne-`str` `data` (`ask_analiza_v2` vraća `dict`) | zatvoreno |
| **SE-007** | `not _delivered` postojalo SAMO u `except BaseException`; `except Exception` refundirao isporučen odgovor | zatvoreno |
| — | **dva moja testa prolazila iz pogrešnog razloga** (rekonstruisali granu / postavljali brojač ručno) | prepisani da voze produkcijske funkcije |

**Recenzentov nalaz da moji testovi prolaze uz pun revert produkcije bio je
tačan.** FS-004 test je rekonstruisao granu unutar sebe; FS-002 test je preko
`__new__` postavljao brojač i time merio aritmetiku, ne ožičenje.

---

# MUTATION PROOF

Svaka popravka je vraćena u kvar i mereno je da testovi padnu:

| Mutacija | Ishod |
|---|---|
| FS-001 vraćen (zastavica posle petlje) | **1 pao** |
| SE-001 vraćen (zastavica pred poslednjim komadom) | **3 pala** |
| FS-003 vraćen (prazan odgovor se naplaćuje) | **2 pala** |
| SE-007 vraćen (`except Exception` bez zaštite) | **1 pao** |
| FS-004 vraćen (provenance pre firewall-a) | **1 pao** |
| SE-004 vraćen (brojač samo na audio delte) | **2 pala** |
| refund potpuno bezuslovan | **2 pala** |
| tri zatečena testa, svaki sa svojim kvarom | **svaki pao** |

---

# TRI ZATEČENA TESTA — POJAČANA, NE OSLABLJENA

`test_commit4_p0.py`, `test_lambda008_certification.py`,
`test_gov2_runtime_interception.py` merili su **doslovne niske** starog oblika
uslova. Svojstva koja štite su očuvana; provere su prevedene na **izvršavanje**.

Recenzentova nezavisna ocena: prva dva **pojačana**, treći **neutralan**
(leksičan i pre i posle).

---

# ŠTA OSTAJE OTVORENO — I ZAŠTO SPRINT NIJE ZELEN

## BYPASS-7 — glasovni WSS (jedini bypass na običnom korisničkom zahtevu)

`services/voice_orchestrator.py:379` ← `routers/voice_realtime.py:139`:
sirov `websockets.connect(wss://api.openai.com/v1/realtime)`. **Nema prompt
guard, nema response firewall, nema per-poziv provenance, nema timeout.**
Zaobilazi zakrpu po konstrukciji jer ne dodiruje SDK.

Popravljen mu je **forenzički trag** (FS-002), ne i kapija.

## GT-001 — provenance zavisi od migracije `089`, status `UNKNOWN`

`log_provenance_from_wrapper` na „kolona ne postoji" **tiho** pada na legacy
skup od 10 kolona — bez `correlation_id`, `predmet_id`, `document_id`, `status`.
Degradacija je potpuno nema: uski fallback ne loguje ništa, totalan neuspeh je
`logger.debug`, nema health-checka za stanje šeme.

Ako `089` nije primenjena, provenance u produkciji piše redove **bez join
ključa** — i ništa u aplikaciji to ne prijavljuje.

**Nijedna migracija nije kreirana u ovom sprintu** — to bi bilo pogađanje bez
pristupa produkcionoj šemi (`SUPABASE_DB_URL` je i dalje u dugu).

## Ostali imenovani gap-ovi

| ID | Nalaz |
|---|---|
| BYPASS-1..6 | 6 samostalnih skripti (`main.py __main__`, ingest) bez `import api` — **nisu produkcijski runtime** (produkcija je `gunicorn api:app`), ali mogu da rade nad produkcionim podacima |
| BYPASS-8..10 | Cohere rerank + `ai_fabric` anthropic/gemini — **mrtav kod** (0 produkcijskih pozivalaca, `cohere` nije ni u `requirements.txt`) |
| — | `shared/ai_fabric.py:535` uvozi `security.prompt_guard.sanitize_prompt` — **funkcija ne postoji**, `except ImportError: pass` → jedini bezbednosni korak provider-neutralne kapije je **tihi no-op**. Modul je mrtav, pa nije popravljan u ovom sprintu. |
| — | korelacija se gubi kroz 2 gola `ThreadPoolExecutor` pool-a (`retrieve.py:1685`, `main.py:4080`) |
| — | `_enforce_response` ostavlja `correlation_id = None` dok `:452` kuje nov → različiti ID-evi za isti poziv na ne-HTTP putanjama |
| — | audit `AUDITABLE_ACTIONS`: failure path AI poziva uglavnom **nema** trag; 38% (78/205) pozivnih mesta guta izuzetak u `except Exception` |
| — | WebSocket ruta ne prolazi kroz HTTP middleware → 0/1 WS ruta postavlja korelacioni kontekst |
| SE-010 | non-stream putanja i dalje koristi `preostalo + 1` umesto `UsageService.balance()` (SOA-016 popravljen samo na jednoj putanji) |

---

# ODGOVORI NA OSAM ZAVRŠNIH PITANJA

**1. Postoji li ijedan poznat production AI path koji može zaobići governance?**
**DA.** Glasovni WSS (`BYPASS-7`) — jedini na običnom korisničkom zahtevu.
Ostalih 11 bypass-a su samostalne skripte ili mrtav kod.

**2. Postoji li kritični AI path bez audit/provenance traga?**
**DA.** Glasovni WSS nema per-poziv provenance (samo sesijski, sada sa tačnim
statusom). Failure path većine AI poziva nema audit.

**3. Postoji li failure path koji može proizvesti false success?**
**Ne više na četiri merena mesta** (FS-001…FS-004 + SE-001…SE-007). Nije
dokazano da ih nema drugde — `retry` i dalje pravi 3 provenance reda, a audit
tabela nema `status` kolonu.

**4. Ima li streaming iste garancije kao non-streaming?**
**Neprimenjivo za AI** — nijedan AI poziv ne koristi `stream=True`
(potvrđeno nezavisno tri puta). SSE putanja je „lažni strim" (ceo odgovor pa
sečenje), i sada ima ispravnu semantiku isporuke. Pravi streaming postoji samo
na glasovnom WSS-u, koji je bypass.

**5. Je li išta ostalo otvoreno samo zato što nismo dovoljno istražili?**
**Ne.** Sve otvoreno je imenovano sa razlogom: bypass koji traži arhitektonski
zahvat, ili migracija čiji status ne mogu da utvrdim bez produkcionog pristupa.

**6. Je li išta popravljeno tako da uvodi nov paralelni put?**
**Ne.** `_treba_refundirati` je **uklonio** duplikat uslova koji je već postojao
dva puta. Ostale tri popravke menjaju redosled/uslov unutar postojećih funkcija.

**7. Je li išta obrisano bez mutacionog dokaza?**
**Ništa nije obrisano.** Sprint je samo menjao redosled i uslove.

**8. Bi li sada pustio stvarnog advokata na ovaj AI tok?**

| Putanja | DA/NE | Zašto |
|---|---|---|
| `/api/pitanje` (non-stream) | **DA** | guard + firewall + provenance + ispravna naplata |
| `/api/pitanje/stream` (SSE) | **DA** | četiri rupe u naplati zatvorene i mutaciono potvrđene; nijedan prvostrani klijent ga i ne zove |
| Upload dokumenta / analiza | **DA** | kroz zakrpu, provenance sada tačan |
| Glasovni asistent (WSS) | **NE** | bez prompt guard-a, bez firewall-a, bez korelacionog konteksta. Trag je sada istinit, ali kapije nema |
| Provenance kao dokaz u sporu | **NE dok se ne potvrdi migracija 089** | fallback tiho gubi join ključ, i ništa to ne prijavljuje |

---

# IZMENJENI FAJLOVI

**Produkcija (3):**
```
api.py                          +100 / −11   (FS-001, FS-003, SE-001, SE-005, SE-006, SE-007)
shared/ai_client.py              +35 / −4    (FS-004, obe grane)
services/voice_orchestrator.py   +33 / −2    (FS-002, SE-004)
```

**Testovi (4):**
```
tests/test_beta_hardening_001.py         NOV, 27 testova
tests/test_commit4_p0.py                 +20  (leksički → izvršni)
tests/test_gov2_runtime_interception.py  +31  (leksički → redosled + izvršni)
tests/test_lambda008_certification.py    +15  (leksički → izvršni)
```

**Migracije:** nijedna kreirana, nijedna izvršena.
**Frontend:** `static/` i `index.html` nedirani.

---

# DEFERRED

| ID | Razlog | Uslov zatvaranja | Vlasnik |
|---|---|---|---|
| `BYPASS-7` | glasovni WSS ne dodiruje SDK; kapija traži proxy sloj ili preseljenje na SDK realtime klijent | prompt guard + firewall + korelacioni kontekst nad WSS porukama | founder — arhitektonska odluka |
| `GT-001` | status migracije `089` se ne može utvrditi bez `SUPABASE_DB_URL` | potvrda da su kolone prisutne + health-check koji glasno pada ako nisu | founder — pristup bazi |
| `F2-001` | **nedirnuto ovim sprintom**, kako je naloženo | zaseban dead-code prolaz | founder |
| 13 helpera | **nedirnuto**, kako je naloženo | zaseban closure | founder |

---

# ŠTA JE OVAJ SPRINT NAUČIO

**Dvanaesto pravilo:**

> **Popravka koja pomera granicu nije popravka.**

Prva verzija FS-001 popravke je zloupotrebu učinila skupljom za 80 znakova —
i to znakova pravne napomene, dakle besplatno za napadača. Test koji je merio
samo prekid na poslednjem komadu to nije video.

Zato tačka napada mora biti **parametar testa**, ne konstanta. Kad se brani
granica, treba je napasti sa obe strane i iznutra.

**Trinaesto pravilo:**

> **Protivnički pregled mora imati pravo da obori sprint — i mora se poslušati.**

Recenzent je dao **RED** na sprint koji je imao 5219 zelenih testova, i bio je u
pravu na svih pet tačaka. Dva testa koja sam napisao prolazila su uz pun revert
produkcije. Da je pregled bio formalnost, sprint bi bio proglašen zelenim sa
rupom koja košta naplatu.
