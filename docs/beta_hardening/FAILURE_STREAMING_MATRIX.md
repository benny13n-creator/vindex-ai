# FAILURE / STREAMING FORENSICS — matrica putanja neuspeha

**Program:** BETA-HARDENING-001, Agent 3
**Baseline commit:** `6fb4a99f`
**Datum merenja:** 2026-08-13
**Metod:** izvršni eksperimenti, ne čitanje koda. 7 skripti, 44 merena scenarija.
Nijedan poziv nije otišao ka OpenAI/Pinecone/Supabase — SDK klase su stubovane
ispod kanonske kapije, `_orig_create` je zamenjen, WSS upstream je lažan.
Nijedan produkcijski fajl nije izmenjen.

---

## 0. ISPRAVKA PREMISE ZADATKA

Zadatak tvrdi: *„u produkcijskom kodu ima tačno 2 pojave `stream=True`. Nađi ih."*

**Ta tvrdnja je netačna i to je izmereno.** U celom repozitorijumu postoji
**jedna** pojava `stream=True`:

```
scripts/ingest_ofac_sdn.py:75
    r = requests.get(SOURCE_URL, ..., timeout=300, stream=True)
```

To je `requests` HTTP preuzimanje OFAC SDN liste — nema veze sa AI-jem, nema
veze sa korisnikom, nije chat completion. **Nijedan AI poziv u ovom
repozitorijumu ne koristi `stream=True`.** Isto stanje su nezavisno zabeležili i
`docs/beta_war/GOVERNANCE_TRUTH_WAVE_3.md:96` i
`docs/beta_hardening/AI_CALLSITE_MATRIX.md:442`.

Posledica za ostatak ovog dokumenta: **„streaming" u Vindex-u ne znači
token-level streaming iz modela.** Postoje dve streaming putanje i nijedna nije
`stream=True`. Da sam tražio `stream=True` i stao, prijavio bih „nema streaminga,
scenariji nisu primenljivi" — što bi bilo lažno umirenje. Zato su putanje
identifikovane po transportu ka korisniku, ne po SDK parametru.

---

## 1. GDE SU TAČNO DVE STREAMING PUTANJE

### Putanja A — SSE, `POST /api/pitanje/stream` (`api.py:3364-3549`)

Lažni strim. `ask_agent()` se izvrši **do kraja** (retrieval + guard +
anti-halucinacija + LLM), pa se gotov string veštački seče na komade od 80
karaktera i šalje kao `data: <komad>\n\n`, zatim `data: [DONE]`, zatim
`data: [CREDITS:N]`. Generator je `_event_generator` u telu rute.

Izmereno: za AI poziv koji traje 1.5 s, prvi bajt stiže korisniku posle
**1.509 s** — dakle nula bajtova dok ceo odgovor nije gotov. Nema heartbeat-a.

Endpoint **nema nijednog pozivaoca u frontendu** (`grep 'pitanje/stream'` po
`static/*.js` → 0 pogodaka), ali je javan i autentifikovan korisnik ga može
pozvati skriptom. To je bitno za ocenu ozbiljnosti FS-001 niže.

### Putanja B — sirov WebSocket, `WS /api/voice/realtime/ws`
(`routers/voice_realtime.py:139` → `services/voice_orchestrator.py:259`)

Pravi token/audio streaming. `relay_upstream_to_client()` iterira preko WSS
konekcije ka OpenAI Realtime API-ju i prosleđuje `response.audio.delta` događaje
browseru. **Ne prolazi kroz SDK**, pa ga monkey-patch iz `shared/ai_client.py`
fizički ne vidi — ni ulazni prompt guard, ni response firewall, ni per-poziv
provenance. `security/response_firewall.py:29` to i priznaje kao deo ugovora.

### Šta se dešava kad prekinu na sredini — kratak odgovor

| | Putanja A (SSE) | Putanja B (voice WSS) |
|---|---|---|
| Prekid na 60% | kredit se **refundira**, nijedan zapis ne kaže da je isporuka bila delimična | jedan `ai_provenance` red, **`status="success"`**, upisan na startu sesije |
| Trag u bazi | `audit_log(akcija='pitanje_stream')` — **nema `status` polja**, identičan kao kod uspeha | identičan redu iz sesije koja je prošla uredno |
| Može li se razlikovati od uspeha | **NE** | **NE** |

---

## 2. GLAVNA MATRICA — svih 12 traženih scenarija

Legenda verdikta: **OK** = ponaša se kako treba · **DEBT** = radi, ali ostavlja
netačan ili nedovoljan trag · **NALAZ** = merljiv kvar sa posledicom po korisnika.

| Scenario | Očekivano | Stvarno (izmereno) | Audit | Provenance | Korelacija | Korisnik vidi | Verdikt |
|---|---|---|---|---|---|---|---|
| **timeout** (`APITimeoutError`) | 3 pokušaja, pa uredna greška, kredit vraćen | 3 pokušaja do provajdera; endpoint refundira | `audit_log` 1 red, bez statusa | 3 reda `status="error"` | isti `correlation_id` u sva 3 | SSE: „Došlo je do greške. Pokušajte ponovo." + `[DONE]` bez `[CREDITS]`. Non-stream: HTTP 500 | DEBT (FS-005, FS-008) |
| **HTTP 429** | retry pa greška; korisnik zna da je provajder pretrpan | identično timeout-u; **429 se korisniku prikazuje kao HTTP 500** | isto | 3 × `error` | isti cid | generička serverska greška | DEBT (FS-009) |
| **HTTP 500** | retry pa greška, kredit vraćen | identično | isto | 3 × `error` | isti cid | generička greška | OK / DEBT |
| **mrežni izuzetak** (`APIConnectionError`) | retry pa greška | identično | isto | 3 × `error` | isti cid | generička greška | OK / DEBT |
| **malformed odgovor** (tražen JSON, vraćen ne-JSON) | poziv se obara, forenzika kaže „neuspeh" | firewall diže `ResponseBlocked` — **ali provenance red je već upisan sa `status="success"` i popunjenim `output_hash`** | firewall `BLOCK` u append-only ledger | 1 red **`success`** ← netačno | isti cid u oba zapisa | greška | **NALAZ FS-004** |
| **prazan odgovor** — SDK sloj (`content=""` ili `None`) | blokada + trag „prazno" | firewall `BLOCK` („sadržaj je prazan string" / „nema ni sadržaj ni poziv alata") | `BLOCK` u ledger | 1 red **`success`** | isti cid | greška | **NALAZ FS-004** |
| **prazan odgovor** — sloj agenta (`rezultat["data"]==""`) | korisnik obavešten, kredit vraćen | SSE: **0 komada teksta, pa `[DONE]` i `[CREDITS:9]`, bez refunda**. Non-stream: tekst „Sistem nije vratio odgovor" + bez refunda | 1 red, bez statusa | (LLM je uspeo) `success` | jedinstven | **SSE: prazan ekran koji izgleda kao uredno završen odgovor. Kredit naplaćen.** | **NALAZ FS-003** |
| **odbijanje provajdera** (refusal: `content=None`, `refusal` postavljen) | razlog odbijanja se beleži | firewall `BLOCK` sa razlogom „odgovor nema ni sadržaj ni poziv alata" — **`refusal` tekst se nigde ne čita ni ne beleži** | `BLOCK` | 1 red `success` | isti cid | generička greška, bez razloga | **NALAZ FS-004 + FS-013** |
| **odbijanje response firewall-a** | poziv pada, **ne ponavlja se** (novac je već potrošen) | `ResponseBlocked` **nije** u `retry_if_exception_type` → izmereno **1 pokušaj do provajdera**, bez ponavljanja | `BLOCK` u ledger (best-effort; neuspeh upisa se guta) | `success` (v. FS-004) | isti cid | greška | **OK** (dizajn drži) |
| **prekid strima** (SSE, 60%) | ništa ne sme reći „uredan uspeh"; delimična isporuka se beleži | kredit refundiran; **nijedan zapis ne postoji o delimičnoj isporuci** (jedina log linija je `PitanjeStream [uid=...]` sa početka zahteva) | 1 red, bez statusa — identičan uspehu | `success` (LLM jeste uspeo) | jedinstven | pola rečenice, presečeno na 66% teksta, bez `[DONE]` | **NALAZ FS-005** |
| **prekid strima** (voice WSS, 60% i 0%) | finalni status sesije | **jedan red `status="success"`, upisan pre prve delte**; nema drugog upisa ni na uredan kraj ni na pad | — (nema `audit_log`) | **`success` čak i kad je isporučeno 0 od 11 delti** | cid iz request konteksta | prekinut zvuk | **NALAZ FS-002 (KRITIČNO)** |
| **prekid veze klijenta** (SSE, posle poslednjeg komada) | naplata ostaje — odgovor je isporučen | **korisnik primi 363/363 karaktera (ceo odgovor, bajt-identičan), pa se pokrene refund → neto cena 0 kredita** | 1 red, bez statusa | `success` | jedinstven | ceo odgovor | **NALAZ FS-001 (KRITIČNO)** |
| **retry** (2×429 pa uspeh) | 1 poslovni događaj, N tehničkih | 3 poziva provajderu, **3 provenance reda** (`error`,`error`,`success`), **1** `audit_log`, **1** `consume` | 1 red | 3 reda, isti cid | isti cid u sva 3 — spojivo | ceo odgovor, kao da nije bilo greške | OK / DEBT (FS-010) |
| **retry korisnika** (2 identična zahteva) | idempotencija ili bar oznaka ponavljanja | **2 `consume`, 2 `audit_log` reda sa istim `q_hash`**, bez ključa idempotencije | 2 reda | 2 poziva | različiti cid | 2 odgovora, 2 kredita | DEBT (FS-011) |
| **iscrpljen retry** | jasno „nismo uspeli", kredit vraćen | 3 × `error` provenance; `ask_agent` pretvara u `{"status":"error"}`; endpoint refundira i vraća balans | 1 red, bez statusa | 3 × `error`, isti cid | isti cid | **non-stream: HTTP 200** sa tekstom „Sistem je trenutno zauzet"; **SSE: uredan `[DONE]` + `[CREDITS:10]`** | **NALAZ FS-009** |
| *(kontrola)* prompt-guard blokada na ulazu | bez naplate, bez AI poziva, trag ostaje | `consume=0`, `refund=0`, HTTP 400, `injection_attempt_blocked` u append-only ledger sa `user_id` | ledger | 0 redova (poziv nije ni krenuo) | — | „Zahtev je odbijen iz bezbednosnih razloga." | **OK** |
| *(kontrola)* guard nedostupan | fail-closed, poziv ne kreće | `GovernanceUnavailable`, **0 pokušaja do provajdera**, **nije retry-ovan** | — | 0 redova | — | greška | **OK** |

---

## 3. STREAMING — poseban nalog, 12 tačaka × 2 putanje

Nijedan red ispod nije dokazan preko non-streaming ekvivalenta.

| Tačka | Putanja A — SSE `/api/pitanje/stream` | Putanja B — voice WSS |
|---|---|---|
| **governance PRE strima** | ✓ `prompt_guard.analyze` se izvršava pre naplate i pre retrievala (`api.py:3416`); blokada vraća 400 **pre** otvaranja SSE toka | ✓ `proveri_voice_dozvolu` pre konekcije (`voice_orchestrator.py:203`) — nijedan bajt ne odlazi ako padne. ✗ **prompt guard i response firewall ne postoje na ovoj putanji uopšte** |
| **audit start** | ✓ `asyncio.create_task(_audit(...))` na `api.py:3436` — **pre `consume`, pre `pokreni`, pre svakog AI rada** | ✓ jedan `ai_provenance` red na `start()` — ali sa `status="success"` (v. FS-002) |
| **kontinuitet korelacije** | ✗ `audit_log` red **ne nosi `correlation_id`** (kolone: `user_id`, `akcija`, `q_hash`, `ts`) → SSE audit se ne može spojiti sa `ai_provenance` redom istog zahteva | ✓ cid se nasleđuje iz request konteksta i upisuje |
| **izvršenje kod provajdera** | ✓ ceo AI posao gotov pre prvog bajta | ✓ streaming uživo |
| **obrada delova** | seče se gotov string na 80 karaktera; `\n` → `\\n`; **nema provere granice reči** → prekid preseca rečenicu na pola | prosleđuje se `response.audio.delta` neizmenjeno |
| **firewall nad delovima** | firewall je već video **ceo** odgovor (SDK sloj), delovi se ne proveravaju — semantički ispravno | **firewall ne postoji**; `inspect_chat_response` ima granu `ESCALATE „odgovor nije pregledan (stream ili nepoznat oblik)"` za objekat bez `.choices` — izmerena i radi, ali je **mrtva u produkciji** jer nema `stream=True` |
| **uredan završetak** | ✓ `[DONE]` + `[CREDITS:N]` | `relay_upstream_to_client` završi kad iterator stane; **nema završnog zapisa** |
| **prekid na sredini** | refund se izvrši; **zapisa o delimičnoj isporuci nema** | `ConnectionResetError` se loguje; **provenance red i dalje kaže `success`** |
| **prekid veze klijenta** | `except BaseException` hvata `GeneratorExit`/`CancelledError`, refundira, pa re-raise-uje — mehanizam radi, **ali uslov `not _delivered` je pogrešno pozicioniran** (FS-001) | `WebSocketDisconnect` se hvata u ruti, `session.close()` u `finally`, brojač sesija se dekrementira ✓ |
| **timeout** | `VINDEX_LLM_TIMEOUT_S=60` po pozivu; `llm_retry` do 3 pokušaja → **do ~180 s tišine bez ijednog bajta i bez heartbeat-a** | retry samo na konekciji (`OSError`/`ConnectionError`/`TimeoutError`, 3 pokušaja); **za trajanje sesije nema timeout-a** |
| **delimičan izlaz** | isporučeno 3/5 komada = 66% teksta, poslednja rečenica presečena — korisniku izgleda kao da je AI stao usred misli | isporučeno 6/11 delti; zvuk se prekine |
| **finalni audit status** | **ne postoji** — `audit_log` nema `status` kolonu | **ne postoji** — jedini red je upisan na startu sa `success` |

---

## 4. KLJUČNI EKSPERIMENT — tvrdnja koja se merila

> „Ako strim prekine na 60%, sistem ne sme zabeležiti uspešan završetak kao da je
> dobio kompletan odgovor."

**Eksperiment** (`exp6_kljucni_dokaz.py`): pravi `StreamingResponse` iz
`api.pitanje_stream`, realan pravni odgovor od 363 karaktera (5 SSE komada),
stubovan `pokreni` i `UsageService` sa brojanjem stanja kredita. Iterator se troši
do zadatog komada, pa se poziva `body_iterator.aclose()` — tačno ono što Starlette
uradi kad klijent nestane. Kontrolna grupa: isti tok bez prekida.

**Rezultat — putanja A (SSE):** tvrdnja je **delimično oborena**.
Sistem ne upisuje eksplicitno „uspeh", ali **upisuje zapis koji se od uspeha ne
može razlikovati**: `audit_log(akcija='pitanje_stream')` bez `status` polja,
identičan u sva tri slučaja (uredan kraj, prekid na 60%, prekid na 10%), plus
`ai_provenance(status='success')` koji je tačan na nivou LLM poziva ali ne kaže
ništa o isporuci. **Nijedan zapis ne postoji da je isporuka bila delimična.**
Za reviziju, spor sa klijentom ili incident — 66% isporučen odgovor i 100%
isporučen odgovor su isti red u bazi.

**Rezultat — putanja B (voice WSS):** tvrdnja je **oborena bez ograde**.
Izmereno na 4 sesije:

| Sesija | Isporučeno klijentu | Provenance redova | Status |
|---|---|---|---|
| uredna do kraja | 11/11 delti | 1 | `success` |
| upstream pukao na 60% | 6/11 | 1 | `success` |
| klijent prekinuo na 30% | 3/11 | 1 | `success` |
| **upstream pukao odmah** | **0/11** | 1 | **`success`** |

Sesija u kojoj advokat nije čuo **nijedan** zvuk zabeležena je u forenzičkom
tragu kao uspešna. Uzrok je jedan poziv: `_uknjizi_voice_sesiju_provenance(self.user)`
(`voice_orchestrator.py:206`) sa podrazumevanim `status="success"` u potpisu
(`:143`), izvršen na kraju `start()` — dakle **posle rukovanja, pre prve delte**.
Postoji tačno **jedno** pozivno mesto; ni `close()` ni bilo koja `except` grana
ne upisuje finalni status.

---

## 5. NALAZI

### FS-001 — KRITIČNO — pun odgovor + refund = besplatno korišćenje AI-ja
`api.py:3482` (`_delivered = True`) · **regresija NIGHT-005, koji je ovo tvrdio da zatvara**

Generator se suspenduje na `yield` **unutar** petlje (`api.py:3478`).
`_delivered = True` stoji **posle** petlje i izvršava se tek kad generator bude
nastavljen posle poslednjeg `yield`. Klijent koji primi poslednji komad teksta i
prestane da čita zatvara generator dok je `_delivered` još `False` → grana
`except BaseException` refundira.

**Izmereno, bajt za bajt:**

| | primljeno | jednako originalu | kredit pre | kredit posle | neto cena |
|---|---|---|---|---|---|
| prekid posle poslednjeg komada | 363/363 | **da** | 10 | **10** | **0** |
| kontrola: uredan završetak | 363/363 | da | 10 | 9 | 1 |

Ponovljivo do rate limita (10/min). `UsageService.refund` nema ni gornju granicu
ni vezu sa konkretnim zaduženjem, pa se stanje jednostavno vraća svaki put.
Trošak kod OpenAI-ja je pun i stvaran.

Postojeći testovi ovo ne mogu uhvatiti: `tests/test_beta_gate_credit_second_order.py:114`
proverava `assert "_delivered = True" in src`, tj. **prisustvo stringa u izvoru**,
ne poziciju izvršavanja. Svih 70 testova iz pet relevantnih fajlova je zeleno dok
je rupa otvorena.

Olakšavajuće: `/api/pitanje/stream` nema pozivaoca u frontendu, pa eksploataciju
mora da izvede autentifikovan korisnik skriptom. Ne umanjuje tačnost nalaza.

### FS-002 — KRITIČNO — voice provenance tvrdi uspeh pre nego što je išta isporučeno
`services/voice_orchestrator.py:143` (`status: str = "success"`) i `:206`

Jedini forenzički trag privilegovanog glasovnog razgovora upisuje se na otvaranju
sesije sa statusom „success" i nikad se ne revidira. Sesija koja pukne na 0%
neodvojiva je od sesije koja je prošla uredno. Ovo je istovremeno i „audit se piše
pre nego što se zna da je provajder uspeo" i „success događaj posle neuspelog
odgovora" — u istom redu.

### FS-003 — VISOKO — prazan odgovor na SSE putanji izgleda kao uspeh i naplaćuje se
`api.py:3467-3497`

Kad agent vrati `{"status":"success","data":""}` (ili rezultat bez ključa `data`):
0 komada teksta, zatim `[DONE]` i `[CREDITS:9]`, **bez refunda**. Advokat vidi
prazan ekran koji je protokolarno uredno završen i plaća ga.

Ne-streaming blizanac ovo **hvata** (`normalizuj_rezultat` + `if not resp.get("odgovor")`
na `api.py:3341` → tekst „Sistem nije vratio odgovor. Pokušajte ponovo.") —
ali ni on ne refundira. Streaming blizanac tu zaštitu **uopšte nema**.

### FS-004 — VISOKO — `ai_provenance.status="success"` za svaki odgovor koji je firewall odbio
`shared/ai_client.py:741` i `:772`

`_capture_chat_provenance(...)` se poziva **pre** `_enforce_response(...)`. Za
malformed JSON, prazan string, `content=None`, praznu listu izbora i refusal
provajdera — izmereno je `status="success"` u provenance redu, dok korisnik dobija
grešku. Kod malformed JSON-a upisan je i `output_hash` pokvarenog sadržaja pod
oznakom uspeha.

Zapisi jesu spojivi preko istog `correlation_id` (firewall `BLOCK` red postoji u
append-only ledger-u), pa istina je rekonstruktivna — ali samo za onoga ko zna da
mora da radi JOIN. Svaki izveštaj koji broji `ai_provenance WHERE status='success'`
prijaviće uspehe koji korisnika nikad nisu stigli.

### FS-005 — SREDNJE — `audit_log` nema status; jedan red za uspeh, prekid i grešku
`api.py:3117-3136`, `api.py:3436`

Tabela je `audit_log(user_id, akcija, q_hash, ts)`. Upis se pokreće
`asyncio.create_task` na početku zahteva, pre naplate i pre AI rada. U svih 16
merenih endpoint scenarija — uspeh, prazan odgovor, timeout, 429, 500, firewall
BLOCK, prekid na 10/60/100% — ostao je **tačno jedan identičan red**.

### FS-006 — SREDNJE — korelacija se lomi kad nema request konteksta
`shared/ai_client.py:452` vs `:692`

Izmereno na pozivu bez request konteksta (cron, pozadinski agent):
`_capture_chat_provenance` **generiše svež** `correlation_id`
(`... or _prov.new_correlation_id()`), dok `_enforce_response` prosleđuje
**`None`**. Dva zapisa istog AI poziva dobijaju različite identitete i ne mogu se
spojiti. Firewall to prijavljuje kao `ESCALATE „correlation_id nedostaje"` — što
je tačno za njegov zapis, a netačno za sliku sistema, jer provenance red taj id
ipak ima, samo izmišljen.

### FS-007 — SREDNJE — SSE bez heartbeat-a
Izmereno: 1.509 s do prvog bajta za AI poziv od 1.5 s. Sa `VINDEX_LLM_TIMEOUT_S=60`
i 3 pokušaja `llm_retry`, najgori slučaj je ~180 s otvorene konekcije bez ijednog
bajta. Klijent ne može da razlikuje „radi se" od „zaglavilo se".

### FS-008 — SREDNJE — greška šalje `[DONE]` bez `[CREDITS:]`
`api.py:3513-3514`. Na svih 6 merenih grešaka refund se izvrši, ali se novo stanje
kredita **ne šalje**. Prikazani broj kredita ostaje umanjen do sledećeg osvežavanja
— korisnik vidi da je plaćen odgovor koji nije dobio, iako je u bazi vraćen.

### FS-009 — SREDNJE — iscrpljen retry se po ugovoru API-ja predstavlja kao uspeh
Non-stream: **HTTP 200** sa telom `{"odgovor": "Sistem je trenutno zauzet.", "credits_remaining": 10}`.
SSE: uredan `data: ... [DONE] [CREDITS:10]`. Provajderski 429 se korisniku prikazuje
kao HTTP 500. Svaki integrator koji `200 OK` broji kao uspešan pravni odgovor
upisaće uspeh.

### FS-010 — NISKO — retry piše N provenance redova po jednom logičkom pozivu
3 pokušaja = 3 reda (`error`, `error`, `success`), svi sa **istim** `correlation_id`.
Grupisanje je moguće; svaki brojač poziva ili troška koji to ne radi biće naduvan.
Poslovni događaji (`audit_log`, `consume`) se **ne** dupliraju — izmereno.

### FS-011 — NISKO — korisnički retry duplira audit bez ključa idempotencije
2 identična zahteva → 2 `consume` + 2 `audit_log` reda sa istim `q_hash`. Naplata
je poštena (2 odgovora = 2 kredita), ali revizija ne može da razlikuje „pitao dva
puta" od „sistem je duplirao".

### FS-012 — NISKO — SSE blizanac nema šest stvari koje non-stream blizanac ima
Izmereno poređenjem izvora obe funkcije: `begin_cost_tracking`, `log_cost_to_db`,
`predmet_istorija` upis, `_session_sacuvaj`, `normalizuj_rezultat` (odatle FS-003) i
`_guard_truncate`. **Pitanje postavljeno preko strima ne ulazi u istoriju predmeta,
ne ulazi u konverzacionu memoriju i ne knjiži trošak AI-ja.** Nedostatak
`_guard_truncate` je bez merene posledice jer Pydantic ionako ograničava
`pitanje` na 2000 karaktera (`api.py:1199`).

### FS-013 — NISKO — razlog odbijanja provajdera se odbacuje
`security/response_firewall.py:104-112` čita samo `content` i `tool_calls`. OpenAI
`refusal` polje se ne čita, pa se odbijanje modela beleži kao „odgovor nema ni
sadržaj ni poziv alata" — tehnički tačno, informaciono prazno.

### FS-014 — METODOLOŠKI — testovi koji čuvaju ove putanje ne izvršavaju ih
`tests/test_beta_gate_credit_second_order.py`, `tests/test_commit4_p0.py`,
`tests/test_gov2_stream_guard_parity.py`, `tests/test_lambda008_certification.py`
proveravaju streaming ponašanje preko `inspect.getsource(...)` i `in src`. Nijedan
ne pokreće `_event_generator`. 70/70 zeleno na baseline-u `6fb4a99f`, sa FS-001
otvorenim.

---

## 6. ŠTA JE POTVRĐENO KAO ISPRAVNO

Ovo je mereno istim eksperimentima i drži:

- **Prompt-guard blokada ne naplaćuje.** `consume=0`, `refund=0`, HTTP 400 pre
  otvaranja SSE toka, `injection_attempt_blocked` sa `user_id` u append-only ledger.
- **Fail-closed AI granica radi.** Nedostupan analizator → `GovernanceUnavailable`,
  **0 poziva provajderu**, i `llm_retry` to **ne ponavlja** (nasleđuje `RuntimeError`).
- **`ResponseBlocked` se ne ponavlja.** Izmereno: 1 pokušaj do provajdera. Novac se
  ne troši dvaput na isti odbijeni ishod.
- **Refund je idempotentan.** `_refunded` sprečava dvostruki povraćaj kroz sve tri
  grane (uspeh, `Exception`, `BaseException`) — potvrđeno na 10 scenarija.
- **Klasifikacija prolaznih grešaka je tačna.** 429/500/timeout/connection → 3
  pokušaja; 400/401 se ne ponavljaju.
- **`except BaseException` u SSE generatoru re-raise-uje** — semantika otkazivanja
  je očuvana, ništa se ne guta.

---

## 7. GRANICE — šta NIJE izmereno (`UNKNOWN`)

- **Ponašanje na pravom mrežnom prekidu iza uvicorn/gunicorn.** Merio sam
  `body_iterator.aclose()`, što je ono što Starlette poziva na nestanak klijenta.
  Ponašanje iza proxy-ja sa buffering-om (`X-Accel-Buffering: no` je postavljen, ali
  nije verifikovan na živom deploy-u) nije mereno.
- **Da li `ai_provenance` i `audit_immutable` upisi zaista stižu u produkcionu bazu.**
  Svi upisi su stubovani. `_ledger_dozvoljen()` (`response_firewall.py:241`) vraća
  `False` pod `PYTEST_CURRENT_TEST`, pa **nijedan postojeći test nikad ne dokazuje
  da se BLOCK zapis stvarno upiše.** Van pytest-a upis se pokuša — izmereno je da
  `log_action_sync` padne na `getaddrinfo` i grešku proguta.
- **`services/voice_orchestrator.py` sa pravim `websockets` transportom.** Merio sam
  duck-typed lažni upstream; ponašanje `websockets` biblioteke na half-open konekciji
  nije mereno.
- **Konkurentno ponašanje refunda pod opterećenjem.** Merio sam jedan zahtev u jednom
  trenutku. Trka između `consume` i `refund` iz dva paralelna zahteva istog korisnika
  nije mereno.
- **Cohere putanja** (`app/services/retrieve.py::_cohere_rerank`) — paket nije u
  `requirements.txt`, nije merena.

---

## 8. REPRODUKCIJA

Eksperimenti su privremene skripte u scratch direktorijumu sesije, van repozitorijuma:

| Skripta | Šta meri |
|---|---|
| `exp1_sdk_failures.py` | 13 scenarija na SDK sloju: provenance status, firewall odluka, korelacija |
| `exp2_stream_endpoint.py` | 16 scenarija na `/api/pitanje/stream`: consume/refund/audit + šta klijent primi |
| `exp3_retry.py` | tenacity ponašanje: broj pokušaja, broj provenance redova, šta se ne ponavlja |
| `exp4_voice_stream.py` | 4 voice sesije sa lažnim WSS: prekid na 60%, 30%, 0% |
| `exp5_misc.py` | vreme do prvog bajta, duplo slanje, trag delimične isporuke |
| `exp6_kljucni_dokaz.py` | **ključni dokaz** — FS-001 i FS-005, bajt za bajt |
| `exp7_nonstream.py` | kontrolna grupa: `/api/pitanje` na istim greškama |

Nijedna ne dodiruje mrežu, nijedna ne piše u repozitorijum.
