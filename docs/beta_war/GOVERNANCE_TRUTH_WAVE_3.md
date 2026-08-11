# GOVERNANCE TRUTH WAVE 3 — RESPONSE FIREWALL

Stanje: `HEAD` posle Wave 3. Baseline pre sprinta: `e06a99b4`, 4124 passed / 1 skipped / 0 failed.

---

## 1. EXECUTIVE VERDICT

## 🟡 **YELLOW**

Canonical Response Firewall je uveden i **dokazano se izvršava** kroz stvarne SDK pozive — ne kroz
postojanje helpera. Vezan je na monkey-patch nad SDK klasama, pa ga nijedno od 91 pozivnog mesta ne
može slučajno preskočiti; ni direktan `client.chat.completions.create(...)` iz proizvoljnog fajla.

**Ne GREEN**, iz tri merena razloga: dve produkcione putanje (raw WSS voice, Cohere SDK) ga
arhitektonski **mogu zaobići**; embeddings i audio odgovori nisu pokriveni jer nemaju chat oblik; a
V1 proverava integritet i format, **ne semantiku** — halucinacija koja je validan JSON prolazi.

---

## 2. BEFORE / AFTER

| Kontrola | Pre | Posle | Dokaz | Preostala rupa |
|---|---|---|---|---|
| Response guard — chat | **2 / 93** | **91 / 93** | `test_gov3_response_firewall.py` — stvarni SDK poziv, lažan provajder | voice WSS, Cohere |
| Response guard — embeddings | 0 | **0 (namerno)** | `test_e2_embeddings_i_audio_NISU_firewall_ovani` | nemaju chat oblik; zaseban ugovor |
| Fail-closed na grešci provere | n/a | **da** | `test_e_greska_u_samoj_proveri_ZATVARA` | domet: 91 putanja |
| Format contract (`response_format=json`) | 0 | **91** | `test_c_trazen_json_a_odgovor_nije_json_JE_BLOKIRAN` | — |
| Prazan/pokvaren odgovor | 0 | **91** | `test_b`, 3 parametra | — |
| Vidljivost degradacije identiteta | 0 | **ESCALATE** | `test_f_nedostatak_identiteta_je_ESCALATE` | ne upisuje se u audit |
| Semantička provera izlaza | 2 (`_proveri_halucinaciju`, RAG) | 2 | nepromenjeno | **91 putanja bez semantičke provere** |

---

## 3. FIREWALL CONTRACT

`security/response_firewall.py`

**Ulaz:** `response`, `kwargs` (radi `response_format`), `operation`, `provider`, `model`,
`correlation_id`, `user_id`.

**Izlaz — tri stanja, namerno ne više:**

| | Značenje | Posledica |
|---|---|---|
| `ALLOW` | odgovor je pregledan i ispravan | vraća se nepromenjen |
| `ESCALATE` | odgovor sme dalje, ali nosi degradaciju | vraća se, degradacija se loguje |
| `BLOCK` | odgovor ne sme dalje | `ResponseBlocked` |

**Fail ponašanje:**

```
provera uspela        → odgovor nastavlja
provera odbila        → ResponseBlocked, odgovor NE MOŽE tiho da nastavi
greška u proveri      → FAIL-CLOSED (ResponseBlocked)
identitet nedostaje   → ESCALATE (eksplicitno degradirano stanje), NE blokada
```

Nema nijednog `except Exception: pass` na putanji odluke.

**Zašto `ResponseBlocked` nije podklasa `openai.APIError`:** `shared/llm_retry.py` ponavlja samo
provajderske greške. Ponavljanje odbijenog odgovora bi potrošilo novac na isti ishod.

**Zašto je `ESCALATE` za identitet, a ne `BLOCK`:** postoje legitimne putanje bez korisnika (cron,
background agenti). Obaranje njih bi bila nova politika, ne popravka propusta.

### Domet fail-closed odluke — iskreno

Greška u samom firewall-u obara AI poziv na **svih 91 putanji**. Zato je površina provera
deterministička i minimalna: nema heuristike, nema modela koji ocenjuje model, nema mrežnog poziva.
Svaka provera je čitanje objekta koji je već u memoriji.

**Ako se ikad doda provera koja može pasti iz razloga nevezanog za sam odgovor, fail-closed postaje
neprihvatljiv i ugovor mora da se preispita — ne da se tiho pretvori u `except: pass`.**

---

## 4. EXECUTION COVERAGE

| Putanja | Provajder | Transport | Firewall | Audit | Provenance | Failure mode | Dokaz |
|---|---|---|---|---|---|---|---|
| 83 chat SDK putanje | openai | sdk | **DA** | da | da | fail-closed | stvarni SDK poziv |
| 8 LangChain embed putanja | openai | langchain | **NE** (nemaju chat oblik) | da | da | n/a | `test_e2` |
| `voice_orchestrator.py:242` | openai | **raw WSS** | **NE — MOŽE ZAOBIĆI** | **ne** | **ne** | nema | Wave 2 |
| `retrieve.py:1265` | cohere | sdk | **NE — MOŽE ZAOBIĆI** | ne | ne | nema | latentna |
| `/api/pitanje` RAG izlaz | openai | sdk | DA + `_proveri_halucinaciju` | da | da | fail-closed | jedina sa 2 sloja |
| `/api/pitanje/stream` | openai | sdk | DA (buffered) | da | da | fail-closed | v. §5 |

**Odgovor na pitanje „koje putanje mogu zaobići firewall": tačno dve** — `voice_orchestrator.py:242`
i `retrieve.py:1265`. Obe su van OpenAI SDK-a, pa ih monkey-patch fizički ne vidi.

### Streaming — izabrana opcija

Od tri iskrene opcije izabrana je **(1) buffered final-response governance**, i to nije odluka ovog
sprinta nego zatečeno stanje: `api.py:3189-3196` dokumentuje da `ask_agent()` radi do kraja pa se
gotov string deli na SSE komade. Wave 2 je izmerio **nula `stream=True`** na svim produkcionim AI
putanjama.

Firewall zato vidi ceo odgovor pre prvog bajta. `test_h_stream_objekat_je_ESCALATE_ne_LAZNO_ALLOW`
pokriva slučaj pravog stream objekta (bez `choices`) — vraća `ESCALATE`, ne lažni `ALLOW`. To je
ugovor za budućnost, ne živa grana.

---

## 5. MUTATION RESULTS

| Mutacija | Očekivano | Stvarno | Test |
|---|---|---|---|
| M1 uklonjen poziv firewall-a (sync) | pad | **4 testa FAILED** | `test_b` ×2, `test_c`, `test_e` (wiring) |
| M2 firewall pozvan, rezultat ignorisan | pad | **1 test FAILED** | `test_e_izlazni_sloj_je_ozicen` |
| M3 `BLOCK` pretvoren u `ALLOW` | pad | **4 testa FAILED** | `test_b` ×3, `test_c` |
| M4 greška u proveri se guta | pad | **1 test FAILED** | `test_e_greska_u_samoj_proveri_ZATVARA` |

**M2 je poučna i vredi je razumeti.** Obara **samo strukturni** test, ne bihevioralne — jer `enforce`
na `BLOCK` i dalje diže izuzetak, pa ignorisanje povratne vrednosti bihevioralno gotovo ništa ne
menja. Da nije bilo `test_e` (wiring), ta mutacija bi prošla nezapaženo. **Zaključak: strukturni test
ovde JESTE ispravan dokaz, jer čuva invarijantu koju ponašanje ne izlaže.**

---

## 6. UNVERIFIED

| Šta | Zašto |
|---|---|
| Da li firewall menja latenciju u produkciji | nije mereno pod opterećenjem; provere su čitanja iz memorije, ali broj nije izmeren |
| Da li ijedna produkciona putanja legitimno vraća prazan sadržaj | ako postoji, firewall bi je sada oborio; 4138 testova to nije pokazalo, ali testovi nisu produkcija |
| Ponašanje pri `n>1` (više izbora u odgovoru) | firewall gleda `choices[0]`; nijedna produkciona putanja ne koristi `n>1`, ali to nije zaključano testom |
| Da li `ESCALATE` degradacije iko čita | trenutno se samo loguju; ne ulaze u `ai_forensics` ni u `audit_immutable` |

---

## 7. PREOSTALI P1 / P2

**P1**

- **Dve putanje mogu zaobići firewall** — raw WSS voice i Cohere SDK. Za voice je to isti kanal koji
  već nema nijedan `ai_forensics` red i nosi privilegovani razgovor.
- **Semantička provera izlaza pokriva 2 od 93.** Halucinacija koja je validan JSON prolazi firewall.
  V1 je namerno determinističan; semantika je zaseban ugovor.
- **`ESCALATE` se ne upisuje nigde trajno** — degradirano stanje postoji u logu, ne u auditu.
- `_guard_patched` se postavlja na `True` i pri neuspehu patch-a → fail-open je neosmotriv
  (nasleđeno iz Wave 2, nepopravljeno).
- Embeddings grana patch-a nema ni ulazni guard ni timeout (Wave 2).

**P2**

- `security/data_classification.py` je 100% mrtav — nula importera.
- `tests/test_ai_fabric_governance.py:91` je lažno-pozitivan test (mock-uje `sanitize_prompt` koji u
  produkciji ne postoji).
- `secrets.json` nije u `.gitignore` (fajl ne postoji — latentno).

---

## 8. ČETIRI PITANJA

**1. Gde response ulazi u governance?**
`shared/ai_client.py`, u `_guarded_create` i `_guarded_acreate`, odmah posle povratka provajdera i
posle `_capture_chat_provenance`. To je zamenjena metoda SDK klase, ne pozivno mesto.

**2. Koje produkcione AI putanje ga mogu zaobići?**
Tačno dve: `services/voice_orchestrator.py:242` (raw WebSocket) i
`app/services/retrieve.py:1265` (Cohere SDK). Plus embeddings/audio, koji nemaju chat oblik i za
koje V1 ugovor ne važi.

**3. Šta se dešava kada firewall pukne?**
`ResponseBlocked` — fail-closed. Nepregledan odgovor se ne sme predstaviti kao pregledan. Domet te
odluke je 91 putanja i zato je površina provera minimalna.

**4. Koji dokaz pokazuje da testovi mere stvarnu zaštitu?**
Četiri mutacije, sve izvršene i vraćene. Svaka obara tačno očekivane testove. Testovi ne čitaju
izvorni kod za tvrdnje o ponašanju — prave običan `openai.OpenAI(...)` klijent i zovu
`client.chat.completions.create(...)`, isto što radi bilo koji od 91 produkcionog pozivaoca, sa
`_orig_create` zamenjenim lažnim provajderom.

---

## 9. REGRESIJA

**4138 passed, 1 skipped, 0 failed** (baseline 4124 / 1 / 0). Razlika +14: 13 novih testova
firewall-a + 1 novi test granice pokrivenosti.

Nijedan postojeći test nije deaktiviran. Jedan (`test_e_izlazna_kontrola_ne_postoji_kao_sloj`) je
**zamenjen** testom pokrivenosti — tako kako je njegov sopstveni docstring nalagao kad je pisan u
Wave 2, jer je bio namerno pozitivna tvrdnja o odsustvu koje je ovaj sprint uklonio.
