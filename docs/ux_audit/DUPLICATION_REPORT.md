# DUPLICATION REPORT — Vindex AI

**Uloga:** Duplication Hunter (UX audit)
**Datum:** 2026-08-12
**Metod:** poređenje po pet osa — rukovalac / endpoint / stanje / rezultat za korisnika / kontekst.
**Ograničenje:** nijedan fajl nije menjan. Ovaj dokument je jedini novi fajl.
**Statička analiza** (čitanje koda), bez pokretanja aplikacije. Sve tvrdnje nose
`fajl:linija`. Gde dokaz nije bio dostupan, stoji `UNVERIFIED`.

---

## Legenda klasifikacije

| Oznaka | Značenje |
|---|---|
| `DUPLIKAT` | isti rukovalac / isti endpoint / isti ishod → kandidat za konsolidaciju |
| `PREČICA` | isti ishod, drugačiji kontekst ulaska → legitimno, ostaje |
| `RAZLIČITO` | deluje slično, radi drugu stvar → **ne dirati** |
| `SIROČE` | kontrola ili funkcija postoji u kodu, ali nema dostupan ulaz iz UI |
| `UNVERIFIED` | nije bilo moguće utvrditi statičkom analizom |

---

# A. GLASOVNA INTERAKCIJA

## A.0 — Inventar: NISU dva sistema, nego TRI

Zadatak je pretpostavljao dva glasovna ulaza. Kod ih ima tri, sa tri odvojena
mehanizma, tri odvojena modala i tri odvojena zahteva za dozvolu mikrofona.

| # | Sistem | Definicija | Ulazne tačke |
|---|---|---|---|
| 1 | **Diktiranje u polje** | `static/vindex.js:6566` `window.micToggle` | 5 × `.mic-btn` — `index.html:936, 1111, 1487, 2865, 3048` |
| 2 | **Glasovna komanda (Phase 2)** | `static/vindex.js:16664` `voice_start()` | `index.html:569` „Govori" (topbar, vidljivo) · `index.html:595` `#voice-cmd-btn` (`display:none`) · `Alt+V` (`vindex.js:18441`) · `vindex.js:16791` (auto-restart razgovornog moda) |
| 3 | **Vindex Live (Realtime)** | `static/vindex.js:17102` `vxLiveOpen()` | `index.html:4416` `#vx-voice-fab` |

Alias koji ih spaja: `static/vindex.js:18445` — `window.voiceStart = voice_start;`
(dugme „Govori" zove `voiceStart`, koji je samo drugo ime za `voice_start`).

---

## A.1 — `vxLiveOpen()` vs `micToggle()`

| Osa | `micToggle(targetId)` | `vxLiveOpen()` |
|---|---|---|
| **Rukovalac** | `vindex.js:6566`; interno `_start()` → `new SpeechRecognition()` (`vindex.js:6449`) | `vindex.js:17102`; interno `_vxLiveConnect()` → `getUserMedia` + `WebSocket` |
| **Endpoint** | **nijedan** — Web Speech API radi u browseru, nema mrežnog poziva ka Vindexu | `WS /api/voice/realtime/ws?token=…` (`vindex.js`, konektovanje) → `routers/voice_realtime.py:37` → `services/voice_orchestrator.py` → OpenAI Realtime |
| **Stanje** | menja `.value` jednog `<input>`/`<textarea>` čiji je `id` prosleđen kao argument; modul-lokalni `_activeId`, `_rec` | otvara `#vx-voice-modal-overlay`, `document.body.style.overflow='hidden'`, globalni objekat `_vxLive` (ws, dva AudioContext-a, stream, processor), `_vxLive.pendingConfirm` |
| **Rezultat za korisnika** | izgovoreni tekst se pojavi **kao tekst u polju**; korisnik ga zatim sam pošalje. Sistem ništa ne izvršava. | otvara se modal sa orbom, sistem **odgovara glasom** i **izvršava alate na serveru** uz HITL potvrdu („Da, potvrdi" / „Otkaži", `index.html:4441-4442`) |
| **Kontekst** | uz konkretno polje (beleška, cross-doc pitanje, copilot, glavni upit, opis podneska) | globalno, plutajuće dugme, nezavisno od predmeta |

**Klasifikacija: `RAZLIČITO`.**

**Obrazloženje.** Ne dele nijednu osu. `micToggle` je **metod unosa teksta** —
zamena za tastaturu. `vxLiveOpen` je **sagovornik** — zamena za klikanje kroz
aplikaciju. Dokaz da je razlika stvarna, a ne kozmetička: `micToggle` nema
nijedan `fetch` niti `WebSocket`; ceo život transkripta je `t.value = …`
(`vindex.js:6538`). `vxLiveOpen` nikada ne piše ni u jedno polje forme.

**Posledica: brisanje bilo kog od njih uklanja funkciju koju drugi ne pokriva.**
Ako se ukloni `micToggle`, advokat gubi diktiranje beleške i opisa podneska.
Ako se ukloni `vxLiveOpen`, gubi se glasovni razgovor sa sistemom.

> Napomena o alatima: `vxLive` ne može da popuni polje. Skup njegovih alata je
> `shared/voice_tools.py:37,56,79` — `pretraga_prakse_i_zakona`, `dodaj_belesku`,
> `kreiraj_nacrt`. `dodaj_belesku` upisuje belešku **u bazu**, dok `micToggle`
> nad `#pred-beleska-input` puni **polje** koje korisnik još može da izmeni pre
> slanja. To su različiti ishodi, ne isti ishod dvema rutama.

---

## A.2 — `voice_start()` vs `micToggle()`

| Osa | `micToggle(targetId)` | `voice_start()` |
|---|---|---|
| **Rukovalac** | `vindex.js:6566` | `vindex.js:16664` |
| **API u browseru** | `SpeechRecognition` (`vindex.js:6449`) | `SpeechRecognition` (`vindex.js:16683`) — **isti browser API** |
| **Endpoint** | nijedan | `POST /api/voice/command` (`vindex.js:16759`) → `routers/voice.py:197` |
| **Stanje** | `.value` ciljanog polja | `#voice-modal` `display:flex`, `_voiceActive`, `_voiceConvMode`, `_voiceConvTurns` |
| **Rezultat za korisnika** | tekst u polju | LLM tumači izgovoreno i **aplikacija sama izvrši radnju** (otvori predmet, prebaci tab, pokrene tajmer…), plus TTS odgovor |
| **Kontekst** | vezano za polje | globalno |

**Klasifikacija: `RAZLIČITO`.**

**Obrazloženje.** Dele isti browser API (`SpeechRecognition`) — i to je jedina
zajednička osa. Deljeni API nije deljena funkcija. `micToggle` transkript
**pokazuje**; `voice_start` transkript **šalje na tumačenje i izvršava**.

> Realan rizik pri koegzistenciji (nije duplikat, ali jeste defekt):
> oba drže sopstvenu `SpeechRecognition` instancu (`_rec` vs `_voiceRec`) i
> međusobno se ne prekidaju. `micToggle` čisti samo svoju (`vindex.js:6577`),
> `voice_start` samo svoju (`vindex.js:16674`). `window.micStopAll` postoji
> (`vindex.js:6588`) ali ga `voice_start` ne zove. Dva istovremena `recognition`
> objekta nad jednim mikrofonom su neodređeno ponašanje po specifikaciji.
> **Nije predmet ovog izveštaja — prosleđeno kao zaseban nalaz.**

---

## A.3 — `voice_start()` vs `vxLiveOpen()` ← PRAVI KANDIDAT

Ovo je par koji zadatak nije predvideo, a jedini je u grupi A sa stvarnim
preklapanjem.

| Osa | `voice_start()` (Phase 2) | `vxLiveOpen()` (Vindex Live) |
|---|---|---|
| **Rukovalac** | `vindex.js:16664` | `vindex.js:17102` |
| **Endpoint** | `POST /api/voice/command` → `routers/voice.py:197` | `WS /api/voice/realtime/ws` → `routers/voice_realtime.py:37` |
| **Prepoznavanje govora** | browser (`SpeechRecognition`) — **ne radi na iOS Safari** (`vindex.js:17077` to izričito konstatuje) | server (OpenAI Realtime preko `getUserMedia` + PCM16 24 kHz) — radi svuda |
| **Gde se radnja izvršava** | **u browseru** — `voice_doAction()` (`vindex.js:16904`) klikće kroz UI | **na serveru** — `execute_tool()` (`shared/voice_tools.py`) |
| **Skup mogućnosti** | ~17 akcija: `navigate_predmet`, `analyze_predmet`, `procena_rizika`, `ask_question`, `generate_document`, `show_tab`, `start_timer`, `stop_timer`, `show_dashboard`, `show_klijenti`, `open_digitalna_imovina`, `search`, `red_team`, `hearing_prep`, `export_pdf`, `load_doc_by_number`, `compare_docs`, `refresh_case_dna`, `stop_voice` | **3 alata**: `pretraga_prakse_i_zakona`, `dodaj_belesku`, `kreiraj_nacrt` (`shared/voice_tools.py:37,56,79`) |
| **Potvrda pre izmene podataka** | **ne postoji** — akcije se izvršavaju odmah | **postoji** — `requires_confirmation()` (`shared/voice_tools.py:199`) traži potvrdu za svaki alat koji menja podatke |
| **Modal** | `#voice-modal` (`index.html:4528`) | `#vx-voice-modal-overlay` (`index.html:4425`) |
| **Rezultat za korisnika** | „reci šta hoćeš, aplikacija to uradi" | „pričaj sa Vindexom, on odgovori i uz potvrdu uradi" |
| **Kontekst** | globalno, dugme u gornjoj traci | globalno, plutajuće dugme dole desno |

**Klasifikacija: `DUPLIKAT` — na nivou korisničkog koncepta.
Na nivou implementacije: `RAZLIČITO`.**

**Obrazloženje.** Za korisnika je posao identičan: *„govorim Vindexu, Vindex
uradi."* Aplikacija za taj jedan posao nudi **dva vidljiva dugmeta, dva različita
modala i dva odvojena traženja dozvole za mikrofon** — što je definicija
duplikata iz ugla UX-a. Ali skupovi mogućnosti se **ne poklapaju ni u jednom
smeru**:

- `vxLive` **ne ume** ništa od navigacije (`show_tab`, `navigate_predmet`,
  `start_timer`, `export_pdf`…) — to su čisto klijentske radnje.
- `voice_start` **nema** HITL potvrdu pred izmenu podataka i **ne radi na iOS-u**.

**Preporuka (bez izvršenja):**

- **Canonical: `vxLiveOpen()`.** Razlozi: radi na iOS Safari-ju (`voice_start`
  ne radi — `vindex.js:17077`); ima potvrdu pred izmenu podataka; prepoznavanje
  je serversko pa ne zavisi od browsera.
- **`voice_start` se NE sme obrisati kao „duplikat".** Njegovih ~17 akcija bi
  nestalo bez zamene. Konsolidacija znači **prenošenje tih akcija u
  `shared/voice_tools.py` kao alate**, pa tek onda gašenje drugog ulaza.
- Do tada je ispravan potez **ukloniti drugo *dugme*, ne drugu *funkciju***:
  ostaviti `Alt+V` kao prečicu, a topbar „Govori" (`index.html:569`) sakriti —
  čime korisnik vidi jedan glasovni ulaz, a funkcionalnost ostaje.

---

## A.4 — Sudar plutajućih dugmadi (nalaz uz grupu A)

Nije duplikat funkcije, ali direktno pogađa vidljivost glasovnog ulaza.

| Element | Pozicija | z-index | Izvor |
|---|---|---|---|
| `#vx-voice-fab` | `bottom:1.5rem; right:1.5rem;` **56×56 px** | `9990` | `static/vindex.css:3630-3642` |
| `#feedback-fab` | `bottom:18px; right:18px;` **42×42 px** | `7000` | `index.html:214` (inline stil) |

Voice FAB zauzima 24–80 px od desne i donje ivice; feedback FAB zauzima 18–60 px.
**Potpuno preklapanje**, a voice FAB ima viši `z-index` → **feedback dugme je na
desktopu prekriveno.**

Komentar u CSS-u (`static/vindex.css:3625-3628`) tvrdi: *„donji desni je slobodan
(nijedan drugi `position: fixed` element ne stoji tamo; provereno u ovom
fajlu)."* Provera je bila tačna **za taj fajl** — `#feedback-fab` je pozicioniran
inline u `index.html`, pa je promakao.

Na mobilnom nema sudara: `static/vindex.css:3761` pomera voice FAB na
`left:18px; bottom:76px`.

**Klasifikacija: `RAZLIČITO` (dve različite funkcije), ali sa potvrđenim
vizuelnim sudarom na desktopu.**

---

# B. POMOĆ / PODRŠKA / POVRATNA INFORMACIJA / KONTAKT

## B.0 — Inventar

| # | Kontrola | Rukovalac | Endpoint |
|---|---|---|---|
| 1 | `#feedback-fab` 💬 (`index.html:214`) | `feedbackSubmit()` `vindex.js:4277` | `POST /api/support/poruka` |
| 2 | „Pošalji poruku" u tabu Pomoć (`index.html:3813`) | `pomocPosalji()` `vindex.js:22673` | `POST /api/support/poruka` |
| 3 | „Prijavi netačan odgovor" ispod AI odgovora | `sendFeedback()` `vindex.js:7990` | Supabase `reported_errors` + `POST /api/feedback` |
| 4 | Dugmad na cenovniku | `pricing_kontakt()` `vindex.js:8240` | `POST /api/feedback` + `mailto:kontakt@vindex.ai` |
| 5 | Poziv na pretplatu | inline `vindex.js:1056` | `mailto:info@vindex.rs` |

## B.1 — `feedbackSubmit()` vs `pomocPosalji()`

| Osa | `feedbackSubmit()` | `pomocPosalji()` |
|---|---|---|
| **Rukovalac** | `vindex.js:4277` | `vindex.js:22673` — druga funkcija, isti posao |
| **Endpoint** | `POST /api/support/poruka` (`vindex.js:4292`) | `POST /api/support/poruka` (`vindex.js:22692`) — **identično** |
| **Stanje** | zatvara `#feedback-modal`, `piTrack('feedback','submitted')` | prazni `#pomoc-poruka`, ispisuje status u `#pomoc-msg` |
| **Rezultat za korisnika** | email osnivačima + tiket u Supabase (`routers/support.py:210,213`) | **isto** — email osnivačima + tiket |
| **Kontekst** | plutajuće dugme, dostupno sa svakog ekrana | stranica Pomoć, ispod FAQ-a |

**Razlike u payload-u** (jedini stvarni delta):

| Polje | `feedbackSubmit` | `pomocPosalji` |
|---|---|---|
| `kategorija` | tvrdo `'feedback'` | iz `<select>` `#pomoc-kategorija` |
| `rating` | ★1–5 (`_feedbackRating`) | — |
| `screenshot_base64` | da (`feedbackCaptureScreenshot`) | — |
| `kontekst` | `activeTab` | — |

**Klasifikacija: `DUPLIKAT`.**

**Obrazloženje.** Isti endpoint, ista tabela, isti email, isti ishod za
korisnika. Dva ulaza su legitimna (globalni i stranica Pomoć), ali su **dve
nezavisne implementacije jedne radnje** — i one su se već razišle: preko FAB-a
tiket nosi ocenu, snimak ekrana i kontekst; preko Pomoći ne nosi ništa od toga,
ali nosi kategoriju koju FAB ne ume da postavi. Nijedan ulaz ne šalje kompletan
tiket.

**Preporuka (bez izvršenja):** canonical **`feedbackSubmit()`** — jer je nadskup
(rating + screenshot + kontekst) i jer je dostupan sa svakog ekrana.
`pomocPosalji()` bi trebalo da postane tanak omotač koji zove istu funkciju sa
`kategorija` iz `<select>`-a. **Nijedno dugme se ne uklanja** — oba ulaza imaju
smisla, duplirana je samo implementacija.

## B.2 — `feedbackSubmit()` vs `sendFeedback()`

| Osa | `feedbackSubmit()` | `sendFeedback()` |
|---|---|---|
| **Rukovalac** | `vindex.js:4277` | `vindex.js:7990` |
| **Endpoint** | `/api/support/poruka` | Supabase `reported_errors` **direktno iz browsera** + `/api/feedback` (`routers/drafting.py:796`) |
| **Stanje** | zatvara modal | menja tekst dugmeta u „✓ Prijavljeno", `disabled` |
| **Rezultat za korisnika** | tiket podrške, odgovor u 24h | prijava **konkretnog netačnog AI odgovora** — ide u sasvim drugu tabelu, ne otvara tiket |
| **Kontekst** | globalno („kako vam radi aplikacija") | uz jedan konkretan AI odgovor (pitanje + odgovor se šalju kao sadržaj) |

**Klasifikacija: `RAZLIČITO`.**

**Obrazloženje.** Različit endpoint, različita tabela (`reported_errors` vs
`support_tickets`), različita svrha: jedan je kanal podrške, drugi je merenje
kvaliteta modela. **Brisanje `sendFeedback` bi ugasilo jedini kanal kojim
korisnik prijavljuje netačan pravni odgovor** — što je za pravnu aplikaciju
najvredniji signal koji postoji.

## B.3 — `pricing_kontakt()` vs ostali

**Klasifikacija: `RAZLIČITO`.** Prodajni lead, ne podrška: upisuje
`PRICING_INTEREST: <plan>` u `/api/feedback` i otvara `mailto`
(`vindex.js:8255-8262`).

## B.4 — Nekonzistentne kontakt adrese (nalaz uz grupu B)

Tri različite adrese za „javi nam se":

| Adresa | Mesto |
|---|---|
| `info@vindex.rs` | `static/vindex.js:1056` |
| `kontakt@vindex.ai` | `static/vindex.js:8262` |
| `support@vindex.ai` | `routers/data_export.py:34` |

Nije duplikat kontrole, ali jeste tri različite istine o tome gde korisnik piše.
**Nije predmet ovog izveštaja — prosleđeno kao zaseban nalaz.**

---

# C. PRETRAGA

## C.0 — Inventar

| # | Kontrola | Rukovalac | Endpoint | Domen |
|---|---|---|---|---|
| 1 | Globalna pretraga / ⌘K (`index.html:544`, `4241`) | `cmdkOpen` `vindex.js:13292` → `_cmdkFetch` `13326` | `GET /api/search` (`routers/search.py:232`) | vlastiti podaci: predmeti, klijenti, dokumenti, naplata, hronologija, beleške, zadaci |
| 2 | Sudska praksa (`index.html:1887`) | `praksa_search` `vindex.js:8459` | `POST /api/praksa/search` | eksterni korpus odluka |
| 3 | Interni stavovi (`index.html:2887`) | `pretraziInterneStavove` `vindex.js:4421` | `POST /interni-stavovi/pretraga` | interna baza znanja kancelarije |
| 4 | Glavni AI upit (`index.html:2865` `#qi`) | `execQuery` `vindex.js:7560` | `/api/nacrt` \| `/api/podnesak` \| `/api/pitanje` | AI nad zakonima |
| 5 | CRM pretraga klijenata (`index.html:1951`) | `crm_pretrazi` `vindex.js:4567` → `ucitajKlijente` `4536` | `GET /klijenti?pretraga=` | klijenti |
| 6 | Izbor klijenta u Intake wizard-u (`index.html:2158`) | `intakeKlijentSearch` `vindex.js:21016` | `GET /klijenti?pretraga=` | klijenti |
| 7 | Izbor klijenta u brzom unosu (`index.html:2363`) | `qiKlijentSearch` `vindex.js:22069` | `GET /klijenti?pretraga=&limit=5` | klijenti |
| 8 | Filter šablona (`index.html:2552`) | `docTplFilter` | — (lokalni filter) | šabloni |
| 9 | Filter u admin registru (`index.html:3937`) | `adminFeatureRegistryRender` | — (lokalni filter) | admin |

## C.1 — ⌘K vs pretraga sudske prakse vs interni stavovi

| Osa | ⌘K globalna | Sudska praksa | Interni stavovi |
|---|---|---|---|
| **Rukovalac** | `_cmdkFetch` | `praksa_search` | `pretraziInterneStavove` |
| **Endpoint** | `GET /api/search` | `POST /api/praksa/search` | `POST /interni-stavovi/pretraga` |
| **Stanje** | otvara overlay `#cmdk-overlay` | popunjava `#praksa-list`, `praksa_offset` | popunjava `#interni-rezultati` |
| **Rezultat** | skok na vlastiti objekat (predmet, klijent, dokument…) | lista sudskih odluka sa paginacijom i filtrima (sud, oblast, godine) | interni stavovi kancelarije |
| **Kontekst** | globalno, iz cele aplikacije | tab sudske prakse | tab baze znanja |

**Klasifikacija: `RAZLIČITO` (sva tri para).**

**Obrazloženje.** Tri odvojena korpusa, tri endpointa, tri različita oblika
rezultata. Zajednička im je samo reč „Pretraga" u placeholder-u. ⌘K pretražuje
**samo ono što korisnik poseduje** (`routers/search.py:38-195` — svaka
pod-pretraga filtrira po `uid`); ostala dva pretražuju **znanje**.

## C.2 — `intakeKlijentSearch()` vs `qiKlijentSearch()` vs `crm_pretrazi()`

| Osa | `intakeKlijentSearch` | `qiKlijentSearch` | `crm_pretrazi` |
|---|---|---|---|
| **Rukovalac** | `vindex.js:21016` | `vindex.js:22069` | `vindex.js:4567` |
| **Endpoint** | `GET /klijenti?pretraga=` | `GET /klijenti?pretraga=&limit=5` | `GET /klijenti?pretraga=` |
| **Debounce** | 300 ms | 280 ms | nema (na `Enter`) |
| **Ograničenje** | `.slice(0,8)` na klijentu | `limit=5` na serveru | bez ograničenja |
| **CSS klasa reda** | `.intake-klijent-result` | `.intake-klijent-result` — **ista klasa** | `.vx-grid-row` |
| **Stanje** | postavlja `_iKlijentId` (izbor za wizard) | postavlja `_qiKlijentId` (izbor za brzi unos) | menja tabelu `#crm-lista` |
| **Rezultat** | padajući izbornik → **bira klijenta za predmet** | padajući izbornik → **bira klijenta za predmet** | **filtrira listu klijenata** za pregled |
| **Escaping** | `replace(/'/g,"&#39;")` — parcijalno | `escHtml()` — potpuno | `_htmlEsc()` |

**Klasifikacija:**

- `intakeKlijentSearch` **vs** `qiKlijentSearch` → **`DUPLIKAT`**
- oba **vs** `crm_pretrazi` → **`RAZLIČITO`**

**Obrazloženje.** Prva dva su isti widget napisan dvaput: isti endpoint, isti
padajući izbornik, ista CSS klasa reda, isti ishod (izbor klijenta koji se veže
za novi predmet). Razlike (300 vs 280 ms, `slice(0,8)` vs `limit=5`, `escHtml`
vs ručni `replace`) nisu namera nego posledica dvostrukog pisanja — a razlika u
escaping-u znači i da **jedna kopija ima slabiju zaštitu izlaza od druge**.

`crm_pretrazi` je nešto treće: ne bira klijenta ni za šta, već filtrira pregled.

**Preporuka (bez izvršenja):** canonical **`qiKlijentSearch`** — koristi
`escHtml()` i ograničava na serveru, ne na klijentu. Konsolidacija je izdvajanje
u `klijentPicker(prefix, onSelect)` koji obe forme pozivaju. **Nijedno polje se
ne uklanja** — oba wizarda moraju da biraju klijenta.

## C.3 — Glasovna akcija `search` (nije zaseban ulaz)

`vindex.js:17008-17016`: akcija `search` iz glasovne komande otvara **⌘K paletu**
i popunjava je upitom. **Klasifikacija: `PREČICA`** ka C.1 #1. Ovo je ispravan
obrazac — glas ne pravi treću pretragu, nego ulazi u postojeću.

---

# D. NOV PREDMET

## D.0 — Inventar: pet putanja, tri endpointa

| # | Kontrola | Rukovalac | Endpoint | Dostupnost |
|---|---|---|---|---|
| 1 | „+ Novi predmet" (`index.html:592`) · „Otvori novi predmet" (`636`) · mobilni FAB (`4408`) · Quick Actions (`194`) · Kontrolni centar (`vindex.js:1624`) · prazno stanje (`10024`, `20709`) · ⌘K (`13271`) · `vindex.js:15848` | `intakeOtvori()` `vindex.js:20661` → `intakeKreiraj` | `POST /api/intake/kreiraj` (`vindex.js:21283` → `routers/intake.py:180`) | **vidljivo, 8 ulaza** |
| 2 | „+ Iz dokumenta" (`index.html:593`) · „Otpremi dokumenta" (`638`) | `siOtvori()` `vindex.js:21424` → `siFinalize()` `21800` | `POST /api/smart-intake/jobs/{id}/finalize` (`routers/smart_intake.py:765`) | **vidljivo, 2 ulaza** |
| 3 | `#btn-hitan-hidden` (`index.html:596`) | `qiOtvori()` `vindex.js:22048` → `qiKreiraj()` `22105` | `POST /api/intake/kreiraj` (`vindex.js:22110`) | **`display:none`** |
| 4 | `#btn-csv-hidden` (`index.html:597`) | `bulkOtvori()` → `bulkParseFile` | `POST /api/intake/bulk-import` (`vindex.js:22238`) | **`display:none`** |
| 5 | `#pred-new-modal` (`index.html:379-410`) | `pred_openNewModal()` `vindex.js:12537` → `pred_kreiraj()` `12545` | `POST /api/predmeti` (`api.py:3651`) | **SIROČE — nema pozivaoca** |

## D.1 — `intakeOtvori()`: osam ulaza, jedan ishod

**Klasifikacija: `PREČICA`.** Svih osam ulaza zovu istu funkciju i završavaju na
istom endpointu. Ovo je ispravan, namerni obrazac — ne dirati.

## D.2 — `intakeOtvori()` vs `siOtvori()`

| Osa | Intake Wizard | Iz dokumenta (Smart Intake) |
|---|---|---|
| **Rukovalac** | `intakeOtvori` `vindex.js:20661` | `siOtvori` `vindex.js:21424` |
| **Endpoint** | `POST /api/intake/kreiraj` | `POST /api/smart-intake/jobs/{id}/finalize` |
| **Stanje** | `#intake-overlay`, 5 koraka, `_iKlijentId`, `_iFiles` | `#si-overlay`, 3 koraka, `_siFiles`, `_siKlijentStrana` |
| **Rezultat** | predmet iz **ručno unetih** podataka | predmet iz podataka koje je **AI izvukao iz dokumenta** (uz ekran za ispravku, `_siRenderReview`) |
| **Kontekst** | „znam podatke, unosim ih" | „imam tužbu/presudu, neka Vindex pročita" |

**Klasifikacija: `RAZLIČITO`.**

**Obrazloženje.** Različit endpoint, različit broj koraka, i — presudno —
različit **izvor istine**. Smart Intake ima ekran za pregled i ispravku
izvučenih entiteta (`routers/smart_intake.py:356,453,514`) koji u wizard-u ne
postoji, jer u wizard-u nema šta da se ispravlja. Naslovi u UI-ju to i priznaju:
„Novi predmet — Intake Wizard" (`index.html:2139`) vs „Novi predmet — iz
dokumenta" (`index.html:2313`).

## D.3 — `intakeOtvori()` vs `qiOtvori()` ← DUPLIKAT, ali sakriven

| Osa | `intakeOtvori` | `qiOtvori` |
|---|---|---|
| **Rukovalac** | `vindex.js:20661` → `intakeKreiraj` | `vindex.js:22048` → `qiKreiraj` `22105` |
| **Endpoint** | `POST /api/intake/kreiraj` (`21283`) | `POST /api/intake/kreiraj` (`22110`) — **identično** |
| **Stanje** | `_iKlijentId`, 5 koraka | `_qiKlijentId`, jedan panel |
| **Rezultat** | predmet + veza sa klijentom + rok | predmet + veza sa klijentom |
| **Kontekst** | glavni tok | „brzo kreiranje" |

**Klasifikacija: `DUPLIKAT` — ali je drugi ulaz već ugašen.**

`#btn-hitan-hidden` ima `style="display:none"` (`index.html:596`) i nijedno drugo
mesto ne zove `qiOtvori()` (provereno preko celog repozitorijuma). Korisnik do
ovog toka **ne može da dođe**. Kod (panel `#qi-*`, `qiKlijentSearch`,
`qiKreiraj`) i dalje živi i održava se.

**Preporuka (bez izvršenja):** canonical je već `intakeOtvori`. Odluka koja
ostaje osnivaču: da li se `qi` tok vraća kao „brzi unos" ili se povlači. Do te
odluke ostaje kao **mrtav kod, ne kao konkurentski ulaz.** Napomena: `qi` panel
je izvor jedne od dve kopije iz **C.2** — ako panel ode, ide i ta kopija.

## D.4 — `pred_kreiraj()` ← SIROČE sa drugim endpointom

Najozbiljniji nalaz u grupi D.

| Osa | `intakeOtvori` (canonical) | `pred_kreiraj` (siroče) |
|---|---|---|
| **Rukovalac** | `intakeKreiraj` | `pred_kreiraj` `vindex.js:12545` |
| **Otvara ga** | 8 kontrola | **nijedna** — `pred_openNewModal()` (`vindex.js:12537`) nema nijednog pozivaoca u repozitorijumu |
| **Endpoint** | `POST /api/intake/kreiraj` | `POST /api/predmeti` (`api.py:3651`) |
| **Šta radi dodatno** | veza sa klijentom (`predmet_klijenti`, `routers/intake.py:267`), rok u hronologiju (`282`), vezivanje dokumenata (`318`), billing unos (`371`), tajmer (`381`), pokretanje pipeline-a (`429-436`) | samo `predmeti.insert` (`api.py:3684`) + emit `PredmetKreiran` u outbox |
| **Rezultat** | kompletan predmet | predmet **bez klijenta, bez roka, bez dokumenata** |
| **Kontekst** | glavni tok | modal `#pred-new-modal` postoji u DOM-u, ali ga ništa ne otvara |

**Klasifikacija: `SIROČE`.**

**Obrazloženje i zašto je važno.** Ovo **nije** duplikat koji treba obrisati bez
razmišljanja — ali nije ni živ ulaz. Modal u potpunosti postoji u
`index.html:379-410`, sa dugmetom „Kreiraj predmet" koje zove `pred_kreiraj()`.
Sve što nedostaje je jedan poziv `pred_openNewModal()`.

Dodatno: komentar u `api.py:3695` opisuje `POST /api/predmeti` kao *„standardni
'+ Novi predmet' tok"*. To više nije tačno — dugme „+ Novi predmet"
(`index.html:592`) zove `intakeOtvori()`, koji ide na `/api/intake/kreiraj`.
Backend komentar zaostaje za frontendom.

**Preporuka (bez izvršenja):** ne dodavati ulaz ka `pred_openNewModal` dok se ne
odluči da li je „predmet bez klijenta i bez roka" validno stanje. Ako jeste,
tok treba da ide preko `/api/intake/kreiraj` sa praznim opcionim poljima, da bi
pipeline i veze radili. Ako nije — modal i `pred_kreiraj` su mrtav kod.
`POST /api/predmeti` **ostaje** jer ga koristi backend/API, ali više nema
frontend pozivaoca.

---

# E. OTPREMANJE DOKUMENTA

## E.0 — Inventar

| # | Kontrola | Rukovalac | Endpoint | Rezultat |
|---|---|---|---|---|
| 1 | `#pred-upload-input` (`index.html:1085`) | `pred_upload_doc` `vindex.js:20040` | `POST /api/predmeti/{id}/upload` | dokument **priložen predmetu** + Genome regeneracija |
| 2 | `#doc-upload-input` (`index.html:2932`) | `doc_upload_file` `vindex.js:8910` | `POST /api/dokument/upload` | privremena sesija za **pitanja nad dokumentom** |
| 3 | `#intake-file-input` (`index.html:2192`) | `intakeUploadFile` `vindex.js:21059` | `POST /api/dokument/upload` | `session_id` u `_iFiles`, za **ekstrakciju u wizard-u** |
| 4 | `#si-file-input` (`index.html:2331`) | `siFilesSelected` → `siUploadAndProceed` `vindex.js:21559` | `POST /api/smart-intake/documents` | AI posao klasifikacije + ekstrakcije |
| 5 | `#playbook-file-input` (`index.html:3070`) | `playbookUploadFajlove` `vindex.js:4338` | `POST /api/playbook/upload` | indeksiranje u vektore kancelarije |
| 6 | `#portal-file-input` (`index.html:4099`) | `portal_uploadFajl` `vindex.js:13718` | `/api/client-portal/uploads/…` | **klijent** šalje dokument advokatu |
| 7 | `#law-pdf-input` (`index.html:3864`) | `lawUploadRun` `vindex.js:15156` | `POST /api/admin/law/upload` | admin unos zakona |
| 8 | `#crm-csv-file` (`2125`), `#bulk-file-input` (`2402`), `#web3-csv-fajl` (`3362`) | CSV rukovaoci | CSV import rute | uvoz podataka, ne dokumenata |

## E.1 — `doc_upload_file()` vs `intakeUploadFile()` ← isti endpoint

| Osa | `doc_upload_file` | `intakeUploadFile` |
|---|---|---|
| **Rukovalac** | `vindex.js:8910` | `vindex.js:21059` |
| **Endpoint** | `POST /api/dokument/upload` | `POST /api/dokument/upload` — **identično** |
| **Validacija pre slanja** | provera ekstenzije (`.pdf/.docx/.doc`) i veličine (25 MB) | **nema nijednu** |
| **Obrada grešaka** | zasebno 422 (nečitljiv dokument), 413 (prevelik), ostalo | jedna generička poruka |
| **Stanje** | `_docSessionId`, `_docUploadName`, `_docUploadSize`, upozorenje o OCR-u | `_iFiles.push({name, sessionId, chunks})`, `_iDirty = true` |
| **Rezultat** | otvara sesiju za **pitanja nad dokumentom** (`doc_ask_question`) | prilaže fajl **wizard-u**, da bi AI izvukao podatke o predmetu |
| **Kontekst** | tab dokumenata, samostalan rad | korak 3 Intake wizard-a |

**Klasifikacija: `RAZLIČITO` — uz `DUPLIKAT` na sloju transporta.**

**Obrazloženje.** Isti endpoint i isti tehnički artefakt (`session_id`), ali
**različit ishod za korisnika**: jedan otvara razgovor sa dokumentom, drugi
prilaže fajl kreiranju predmeta. Nijedan ne zamenjuje drugi.

Duplirano je samo *slanje*. I ta duplikacija ima cenu: `intakeUploadFile` nema
proveru tipa ni veličine, pa u wizard-u korisnik prevelik ili nepodržan fajl
saznaje tek kao „Greška: …" sa servera, dok mu isti fajl u tabu dokumenata
odmah kaže šta nije u redu.

**Preporuka (bez izvršenja):** zajednička `_uploadDokument(file)` koja radi
validaciju i mapiranje grešaka i vraća `{session_id, chunk_count, ocr_used}`;
oba pozivaoca ostaju i dalje rade svoje sa rezultatom. **Nijedan ulaz se ne
uklanja.**

## E.2 — Ostali parovi

| Par | Klasifikacija | Dokaz |
|---|---|---|
| `pred_upload_doc` vs `doc_upload_file` | `RAZLIČITO` | različit endpoint; prvi trajno vezuje za predmet i pokreće Genome (`vindex.js:19985` komentar), drugi pravi privremenu sesiju |
| `siFilesSelected` vs `intakeUploadFile` | `RAZLIČITO` | `/api/smart-intake/documents` (asinhroni posao, 202) vs `/api/dokument/upload` (sinhrono); prvi klasifikuje tip dokumenta i izvlači entitete uz pregled |
| `playbookUploadFajlove` | `RAZLIČITO` | vektorsko indeksiranje znanja kancelarije, ne dokument predmeta |
| `portal_uploadFajl` | `RAZLIČITO` | drugi akter — otprema **klijent**, ne advokat |
| `lawUploadRun` | `RAZLIČITO` | admin ruta, unos zakona u korpus |

**Zaključak za E:** nema nijednog para koji bi se smeo objediniti u jednu
kontrolu. „Otpremi dokument" je sedam različitih poslova koji dele reč.

---

# F. POKRETANJE ANALIZE

## F.1 — `pred_launchKompletnaAnaliza()` — pet ulaza, potvrđeno

| # | Kontrola | Mesto |
|---|---|---|
| 1 | dugme „Analiziraj" (Copilot traka) | `index.html:782` |
| 2 | klikabilan `<div>` — `.vx-insight-hero` | `index.html:1138` |
| 3 | `#agent-launch-all-btn` „Pokreni kompletnu analizu" | `index.html:1596` |
| 4 | ⌘K akcija „Pokreni analizu" | `vindex.js:13275` |
| 5 | `#strat-ork-btn` — direktno na `stratOrkestratorPokreni()` | `vindex.css`/`vindex.js:3591` (referencirano u komentaru `vindex.js:3704`) |

Sve konvergiraju na `stratOrkestratorPokreni()` (`vindex.js:3719`).

| Osa | vrednost (identična za svih pet) |
|---|---|
| **Rukovalac** | `pred_launchKompletnaAnaliza` `vindex.js:10608` → `stratOrkestratorPokreni` `3719` (ulaz #5 ide direktno) |
| **Endpoint** | orkestrator 6 modula strateške analize |
| **Stanje** | `openAITool('t')` → tab `aiws`, mod `strategija`; `_predAutoFill('strat-tekst')`; guard `_stratOrkUToku` |
| **Rezultat** | ista kompletna strateška analiza |
| **Kontekst** | Copilot traka / hero kartica / tab agenata / ⌘K / sam alat |

**Klasifikacija: `PREČICA` — potvrđeno, i to ispravno izvedeno.**

**Obrazloženje.** Guard `_stratOrkUToku` (`vindex.js:3717`) živi **u funkciji**,
ne na dugmetu. Komentar iznad njega (`vindex.js:3702-3710`) tačno navodi zašto:
`#strat-ork-btn` se štiti sa `disabled`, ali preostala četiri ulaza taj atribut
ne diraju, pa su dva paralelna naplativa posla bila moguća. Isti obrazac je
primenjen i na `stratPokreni` (`_stratModulUToku`, `vindex.js:3120`) —
preventivno, iako ta funkcija danas ima samo jedan ulaz.

**Ovo je referentni primer kako prečice treba da izgledaju: N ulaza, jedan
rukovalac, jedan guard u rukovaocu.** Ne dirati.

## F.2 — Sudar naziva: „Pokreni analizu" znači dve različite stvari

| Kontrola | Mesto | Poziva | Vodi na |
|---|---|---|---|
| Quick Actions → **„Pokreni analizu"** | `index.html:203-206` | `openAITool('q')` | AIWS mod **`zakon`** — pitanje o zakonu (`_AIWS_MODES`, `vindex.js:2244`) |
| ⌘K → **„Pokreni analizu"** | `vindex.js:13275` | `pred_launchKompletnaAnaliza()` | AIWS mod **`strategija`** — kompletna analiza predmeta |
| ⌘K → **„Pitaj AI"** | `vindex.js:13273` | `openAITool('q')` | AIWS mod **`zakon`** — **isto što i prvi red** |

**Klasifikacija:**

- Quick Actions „Pokreni analizu" **vs** ⌘K „Pokreni analizu" → **`RAZLIČITO`**
- Quick Actions „Pokreni analizu" **vs** ⌘K „Pitaj AI" → **`PREČICA`** (isti
  rukovalac `openAITool('q')`, isti ishod)

**Obrazloženje — i zašto je ovo najvažniji nalaz u izveštaju.** Ovde je pravilo
„naziv nije dokaz" potvrđeno u oba smera, na jednom mestu:

- **Isti naziv, različit posao.** Korisnik koji u Quick Actions klikne „Pokreni
  analizu" dobija prazno polje za pitanje o zakonu. Isti naziv u ⌘K pokreće
  šestomodulnu stratešku analizu otvorenog predmeta, koja troši kredite.
- **Različit naziv, isti posao.** „Pitaj AI" i „Pokreni analizu" iz Quick
  Actions su ista funkcija sa istim argumentom.

**Preporuka (bez izvršenja):** ne brisati nijednu kontrolu — problem je
isključivo u nazivima. Quick Actions stavku preimenovati u „Pitaj AI" (da se
poklopi sa ⌘K), a ⌘K stavku u „Kompletna analiza predmeta". Nula promena u
ponašanju.

## F.3 — Glasovne akcije `analyze_predmet` / `procena_rizika`

`vindex.js:16912-16913` i `17019`: obe vode na `pred_subtabSwitch('agenti')` +
`agent_run()` — **ne** na `stratOrkestratorPokreni`.

**Klasifikacija: `RAZLIČITO`** u odnosu na F.1. Glas pokreće **agenta nad
predmetom**, ne šestomodulnu stratešku analizu — uprkos tome što se u glasu
komanda zove „analiziraj predmet". Još jedan slučaj gde naziv ne prati funkciju.

> `UNVERIFIED`: nije utvrđeno da li `agent_run()` i `stratOrkestratorPokreni()`
> na kraju gađaju isti backend orkestrator. Ako gađaju, `agent_run` bi trebalo
> da deli `_stratOrkUToku` guard — inače je glasovna komanda peti neguardovan
> ulaz u naplativu operaciju. **Zahteva zaseban prolaz kroz `agent_run`.**

---

# NULA FUNKCIJA BEZ VLASNIKA

Za svaku funkcionalnu grupu: ko je danas canonical ulaz.

| Grupa | Canonical ulaz danas | Status |
|---|---|---|
| **Diktiranje u polje** | `micToggle(targetId)` — 5 `.mic-btn` uz polja | ✓ jasan vlasnik |
| **Glasovni razgovor sa sistemom** | **NEMA JEDNOG.** Dva ravnopravna: `voice_start()` (topbar „Govori" + `Alt+V`) i `vxLiveOpen()` (`#vx-voice-fab`) | ⚠ **bez vlasnika** — v. A.3 |
| **Slanje poruke podršci** | `feedbackSubmit()` (`#feedback-fab`) — nadskup polja | ⚠ vlasnik postoji, ali je na desktopu **vizuelno prekriven** voice FAB-om (A.4), a druga implementacija (`pomocPosalji`) šalje siromašniji tiket |
| **Prijava netačnog AI odgovora** | `sendFeedback()` — dugme ispod AI odgovora | ✓ jedini ulaz |
| **Kontakt za prodaju** | `pricing_kontakt()` | ⚠ tri različite email adrese u kodu (B.4) |
| **Globalna pretraga vlastitih podataka** | `cmdkOpen()` / ⌘K | ✓ jasan vlasnik; glasovna `search` akcija ispravno ulazi u njega |
| **Pretraga sudske prakse** | `praksa_search()` | ✓ jedini ulaz |
| **Pretraga internih stavova** | `pretraziInterneStavove()` | ✓ jedini ulaz |
| **Izbor klijenta pri kreiranju predmeta** | **NEMA JEDNOG.** `intakeKlijentSearch` i `qiKlijentSearch` — dve kopije (C.2) | ⚠ **bez vlasnika**, iako je jedna kopija trenutno nedostupna (D.3) |
| **Pregled/filtriranje klijenata** | `crm_pretrazi()` | ✓ jedini ulaz |
| **Kreiranje predmeta — ručno** | `intakeOtvori()` → `/api/intake/kreiraj`, 8 ulaznih tačaka | ✓ jasan vlasnik |
| **Kreiranje predmeta — iz dokumenta** | `siOtvori()` → smart-intake finalize | ✓ jasan vlasnik |
| **Kreiranje predmeta — brzo / CSV** | `qiOtvori()`, `bulkOtvori()` — **oba `display:none`** | ⚠ **funkcija bez ulaza** (D.3) |
| **Kreiranje predmeta — minimalno** | `pred_openNewModal()` — **nema nijednog pozivaoca** | ⚠ **SIROČE** (D.4) |
| **Prilaganje dokumenta predmetu** | `pred_upload_doc()` | ✓ jasan vlasnik |
| **Pitanja nad dokumentom** | `doc_upload_file()` | ✓ jasan vlasnik |
| **Transport uploada (`/api/dokument/upload`)** | **NEMA JEDNOG** — `doc_upload_file` i `intakeUploadFile` (E.1) | ⚠ duplirano, sa različitom validacijom |
| **Otprema od strane klijenta** | `portal_uploadFajl()` | ✓ jedini ulaz |
| **Indeksiranje znanja kancelarije** | `playbookUploadFajlove()` | ✓ jedini ulaz |
| **Kompletna strateška analiza** | `stratOrkestratorPokreni()` — 5 prečica, guard `_stratOrkUToku` | ✓ **referentni primer** |
| **Pojedinačni modul strategije** | `stratPokreni()` — guard `_stratModulUToku` | ✓ jasan vlasnik |
| **Agent nad predmetom** | `agent_run()` | ⚠ `UNVERIFIED` — v. F.3 |

---

# SAŽETAK KLASIFIKACIJA

## `DUPLIKAT` — kandidati za konsolidaciju

| # | Par | Canonical (predlog) | Šta se briše |
|---|---|---|---|
| 1 | `feedbackSubmit` / `pomocPosalji` (B.1) | `feedbackSubmit` | **ništa** — samo se `pomocPosalji` svodi na omotač; oba dugmeta ostaju |
| 2 | `intakeKlijentSearch` / `qiKlijentSearch` (C.2) | `qiKlijentSearch` (bolji escaping, server-side limit) | **ništa** — izdvajanje u `klijentPicker()`; oba polja ostaju |
| 3 | `voice_start` / `vxLiveOpen` (A.3) — konceptualni | `vxLiveOpen` | **ništa dok se ~17 akcija ne prenese u `voice_tools`**; do tada se sakriva samo dugme, ne funkcija |
| 4 | `intakeOtvori` / `qiOtvori` (D.3) | `intakeOtvori` | **ništa** — `qiOtvori` je već nedostupan (`display:none`) |
| 5 | transport u `doc_upload_file` / `intakeUploadFile` (E.1) | `doc_upload_file` (ima validaciju) | **ništa** — izdvajanje `_uploadDokument()`; oba ulaza ostaju |

**Nijedan potvrđeni duplikat ne zahteva brisanje kontrole iz UI-ja.** Svih pet
su duplirane *implementacije*, ne suvišna dugmad.

## `RAZLIČITO` — ne dirati

`micToggle` ↔ `vxLiveOpen` · `micToggle` ↔ `voice_start` · `feedbackSubmit` ↔
`sendFeedback` · `pricing_kontakt` ↔ podrška · ⌘K ↔ praksa ↔ interni stavovi ·
picker klijenta ↔ `crm_pretrazi` · `intakeOtvori` ↔ `siOtvori` ·
`pred_upload_doc` ↔ `doc_upload_file` ↔ `siFilesSelected` ↔ `playbook` ↔
`portal` ↔ `admin law` · Quick Actions „Pokreni analizu" ↔ ⌘K „Pokreni analizu" ·
glasovni `analyze_predmet` ↔ `stratOrkestratorPokreni`

## `PREČICA` — legitimno, ostaje

`intakeOtvori` (8 ulaza) · `pred_launchKompletnaAnaliza` → `stratOrkestratorPokreni`
(5 ulaza) · glasovna akcija `search` → ⌘K · Quick Actions „Pokreni analizu" ↔
⌘K „Pitaj AI"

## `SIROČE`

`pred_openNewModal` / `pred_kreiraj` / `#pred-new-modal` (D.4) ·
`qiOtvori` (D.3) · `bulkOtvori` (D.0 #4)

## `UNVERIFIED`

| # | Pitanje | Zašto nije utvrđeno |
|---|---|---|
| 1 | Da li `agent_run()` i `stratOrkestratorPokreni()` gađaju isti backend orkestrator (F.3)? | zahteva praćenje `agent_run` kroz backend; ako da, glas je neguardovan ulaz u naplativu operaciju |
| 2 | Da li se `#feedback-fab` i `#vx-voice-fab` stvarno preklapaju u pregledaču (A.4)? | preklapanje je izračunato iz CSS/inline vrednosti; vizuelna potvrda zahteva pokretanje aplikacije |
| 3 | Da li `support_tickets` i `reported_errors` završavaju u istom pregledu za osnivača (B.2)? | zahteva uvid u Supabase šemu / admin panel |
| 4 | Da li je `voice_start` namerno zadržan kao rezerva za browsere bez WebSocket-a? | u kodu nema ni komentara ni feature flag-a koji bi to potvrdio |
| 5 | Da li `#btn-hitan-hidden` / `#btn-csv-hidden` neka putanja prikazuje u runtime-u (npr. po ulozi)? | pretraga nije našla nijedan `style.display` set nad tim ID-jevima, ali dinamički selektor nije isključen |
