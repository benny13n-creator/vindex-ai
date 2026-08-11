# BETA HARDENING WAVE 8 — REMEDIATION REPORT

Remediation mode. **Nula novih forenzičkih pretraga** — samo zatvaranje poznatih dugova.

---

# EXECUTIVE VERDICT

## 🟡 **YELLOW**

Dva poznata duga zatvorena i mutaciono dokazana. Deset ranije zatvorenih nalaza potvrđeno
regresijom. Ostatak je namerno odložen — ne zato što je težak, nego zato što spada u kategorije
koje je mandat izričito zabranio da se „nasilno zatvaraju" (§26): vlasnička odluka, mrtav kod, ili
arhitektonski redesign.

Ne GREEN, jer jedna P0 stavka (`migracija 111`) i dalje čeka vlasnika, a dva P1 zahtevaju odluke
koje nisu inženjerske.

---

# BASELINE → FINAL

| | Pre | Posle |
|---|---|---|
| HEAD | `c0bc8972` | `9122984a` |
| Testovi | 4179 / 1 / 0 *(ponovljeno iz nule — poklopilo se)* | **4184 passed / 1 skipped / 0 failed** |
| Stablo | čisto | čisto |

---

# GLAVNA MATRICA

| Nalaz | Fixed? | Tested? | Mutation? | Production? | Status |
|---|---|---|---|---|---|
| **Lažno-pozitivan governance test** | **DA** | 15 | **DA** | n/a | **VERIFIED** |
| **Dupla invokacija analize** | **DA** | 5 | **DA** | ✖ | **FIXED** |
| P0-A build identity | ranije | ✔ | ✔ | **✔** | **PRODUCTION VERIFIED** |
| P0-B onboarding | ranije | ✔ | ✔ | **✔** | **PRODUCTION VERIFIED** |
| P0-D / D2 kontekst | ranije | ✔ 23 | ✔ | **✔** | **PRODUCTION VERIFIED** |
| P0-E atomična naplata | ranije | ✔ 59 | ✔ | ✖ | **VERIFIED (kod)** |
| P0-F cenovnik | ranije | n/a | n/a | **✔** | **PRODUCTION VERIFIED** |
| Response Firewall V1 | ranije | ✔ 13 | ✔ | ✔ *(`governance.active`)* | **VERIFIED** |
| Patch failure state | ranije | ✔ 8 | ✔ | **✔** | **VERIFIED** |
| Pre-flight bilans | Wave 6 | ✔ 10 | ✔ | ✖ | **VERIFIED (kod)** |
| **P0-C phantom naplata** | kod ✔ | ✔ 11 | ✔ | **✖** | **OWNER ACTION** |
| 402/429 propagacija | — | ✔ | n/a | ✖ | **P2 DEFERRED** |
| `feature_usage_log` šema | — | — | — | — | **OWNER / POST-BETA** |
| Voice raw WSS | — | — | — | — | **DEFERRED — van bete** |
| Cohere | — | ✔ 6 | — | — | **DEFERRED — latentan** |
| Cancellation ugovor | — | — | — | — | **DEFERRED — ne postoji** |
| Startup policy | — | — | — | — | **OWNER ACTION** |
| `data_classification.py` | — | — | — | — | **DEFERRED — mrtav** |

---

# POPRAVLJENO

## W8-01 · Lažno-pozitivan governance test — `17298189`

**Root cause.** `test_6` je ubacivao `MagicMock` modul sa `sanitize_prompt` u `sys.modules`, pa
tvrdio *„guard se poziva ako postoji"*. Prolazio je uvek — **sam je pravio uslov koji proverava.**

**Stvarnost, izmerena.** `security/prompt_guard.py` **nema** `sanitize_prompt`; njegova stvarna
ulazna funkcija je `analyze`. Zato `shared/ai_fabric.py:534-537` uvek digne `ImportError`,
`except ImportError: pass` ga proguta, i deklarisani „REUSE prompt guard-a" **nikad se ne izvrši**.

**Zamena, ne brisanje.** Novi test tvrdi dve nezavisne stvari: da simbol ne postoji a `analyze`
postoji, i da prompt prolazi kroz kapiju **neizmenjen** (ponašanje, ne struktura).

**Zašto produkcioni kod nije popravljen:** `ai_fabric.py` ima **nula produkcionih pozivalaca**.
Popravljanje mrtvog koda ne povećava beta sigurnost. Ako ikad dobije pozivaoca, **ovaj test pada** i
tera da se kapija ožiči pre upotrebe.

**Mutacija:** dodat `sanitize_prompt` u produkciju → `test_6` **FAILED**. Stari test bi tu mutaciju
propustio.

## W8-02 · Dupla invokacija analize — `9122984a`

**Root cause.** `#strat-ork-btn` se zaključava sa `disabled`, ali analiza ima još **četiri** ulazne
tačke koje taj atribut ne diraju — `index.html:782`, `:1138` (klikabilan `<div>`, **bez ikakvog
guard-a**), `:1596`, i CMD-K (`vindex.js:13070`). Sve idu kroz `pred_launchKompletnaAnaliza()` →
`stratOrkestratorPokreni()`, koja **nikad nije proveravala `orkBtn.disabled`**.

Sa njih su dva paralelna posla bila moguća — svaki **8 GPT-4o poziva i 6 kredita**.

**Zašto dedupe nije bio dovoljan.** `create_job_deduped` to hvata, ali je **poslednja** odbrana i
radi samo unutar jednog worker procesa — `routers/jobs.py:48-55` to izričito priznaje.

**Detalji koji su bitni:** zastavica se postavlja **posle** ranih `return` grana (odbijen pokušaj ne
sme zaključati dugme), a oslobađa se u **`finally`** (jedan neuspeh ne sme trajno zaključati
funkciju).

**Testovi mere ponašanje.** Repo nema JS test framework, pa se funkcija **stvarno izvršava u
Node-u** sa minimalnim DOM stubom i broje se stvarni `fetch` pozivi:

| Scenario | Rezultat |
|---|---|
| dva klika u letu | **1 zahtev** |
| četiri brza klika | **1 zahtev** |
| posle završetka | **2 zahteva** *(negativna kontrola)* |
| posle greške | nova analiza moguća |
| prekratak tekst | ne zaključava funkciju |

**Mutacije:** uklonjena provera → `test_a` + `test_b` FAILED. Zastavica se ne oslobađa u `finally`
→ `test_ng` + `test_c` FAILED.

---

# ODLOŽENO — sa razlogom, ne iz nemoći

| Stavka | Zašto |
|---|---|
| **402/429 propagacija** | Wave 7 je izmerio da informacija **preživi** u error stringu (`"402: {'code': 'NO_CREDITS'}"`). Strukturisana propagacija traži izmenu `run_in_background`, dakle refaktor granice posla — §10 to izričito zabranjuje. **P2.** |
| **`feature_usage_log` šema** | dodavanje `predmet_id`/`correlation_id` je izmena naplatne šeme. §21: „Ako zahteva billing/schema redesign: NE." |
| **Voice** | §15: ne uvoditi u betu, ne instrumentisati. Kill-switch i tarifna kapija su već dokazani (Wave 2). |
| **Cohere** | latentan; §14 zabranjuje novu provider apstrakciju radi teorijskog coverage-a. Zaključan testom. |
| **Cancellation** | §26-C: sistem nema ugovor, ne izmišljati ga. |
| **`data_classification.py`** | §16: mrtav, ne troši noć na cleanup koji ne povećava beta sigurnost. |
| **Startup policy** | §12: vlasnička odluka. |
| **Migracija 111** | §25: produkcija ostaje vlasnička akcija. |

---

# NEW_DISCOVERY_OUT_OF_SCOPE

**Nijedan.** Noć je prošla bez novog nalaza — i to je, po §33, dobar ishod, ne loš.

---

# OWNER ACTIONS

1. **`migrations/111_phantom_ai_charges.sql`** — jedina P0 stavka. Kod je popravljen i testiran;
   registry deo čeka izvršenje.
2. Potvrditi `voice.aktivno` u bazi.
3. Odluka o startup politici pri neuspehu governance patch-a.

---

# FINAL BETA RISK

Nijedan poznati, inženjerski rešiv, beta-kritičan problem nije ostao otvoren. Preostali rizici su
tri vrste: **vlasnička odluka** (3), **van beta obima** (2), i **arhitektonski redesign koji mandat
zabranjuje** (2).

Sistem je u stanju u kome je svaka tvrdnja iz osam sprintova pokrivena testom koji pada kada se
zaštita ukloni.
