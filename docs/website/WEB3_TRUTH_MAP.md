# WEB3 TRUTH MAP — inventar sposobnosti za sajt

**Datum:** 2026-08-12
**Obim:** isključivo Web3/blockchain/digitalna imovina funkcionalnost Vindex AI platforme.
**Granica proizvoda (odluka vlasnika):** „Digital Asset Compliance & Due Diligence" — usklađenost
i provera porekla digitalne imovine. **Nema trading, nema DeFi, nema investicionog saveta.**
**Metod:** utvrđeno iz koda, testova, migracija i frontend fajlova. Ništa nije provereno protiv
žive produkcije — gde je produkciona provera bila nemoguća, to je izričito označeno.

---

## 0. Kako čitati statuse

| Status | Značenje u ovom dokumentu |
|---|---|
| `PRODUCTION` | Ruta postoji, registrovana je u `api.py`, frontend je zove, i ne zavisi od spoljnog ključa čije se prisustvo ne može dokazati. |
| `IMPLEMENTED_UNWIRED` | Backend radi, ali ga nijedan ekran ne zove. |
| `UNVERIFIED` | Kod je kompletan i ožičen, ali funkcija bez spoljne konfiguracije vraća grešku, a ta konfiguracija se iz repoa ne može dokazati. |
| `DEAD` | Kod postoji, ništa ga ne uvozi ni ne poziva. |

Sve `/web3/*` i `/csv-import/*` rute su registrovane u `api.py:590-594` (import) i
`api.py:687-691` (`include_router`). Svih 18 ruta je pokriveno frontendom u `static/vindex.js`.

---

## 1. TABELA SPOSOBNOSTI

### F11 — Regulatorna provera (ZDI / MiCA / CARF)

---

#### 1.1 Pretraga propisa o digitalnoj imovini (ZDI + MiCA)

- **SPOSOBNOST:** Pravnik postavi pitanje o srpskom Zakonu o digitalnoj imovini ili EU MiCA uredbi
  i dobija odgovor sa citiranim članovima — ali samo onim brojevima članova koji se doslovno
  nalaze u pronađenom tekstu zakona. Ako broj nije u izvoru, sistem piše opis odredbe bez broja.
- **LOKACIJA:** `routers/web3.py:60` → `POST /web3/pretraga`; logika `web3_compliance.py:286`
  (`web3_pretraga_sync`), Pinecone prostor `web3_zdi_mca` (`web3_compliance.py:26`).
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5001`, kartica „Regulatory Review"
  (`vindex.js:2137` `DIM_CARDS.regulatorna`), ekran `index.html:3207`.
- **TESTIRANO?** Bez direktnog testa endpointa. Postoji test da dobro formirani odgovori prolaze
  nepromenjeni: `tests/test_singular_intelligence_fixes.py::test_web3_well_formed_responses_pass_through_unchanged`.
- **NA PRODUKCIJI?** Traži `OPENAI_API_KEY` i Pinecone. Prostor `web3_zdi_mca` je izmeren na
  **479 vektora** (`data/pinecone_baseline_2026-07-13.json`), ZDI ima 146 članova → 664 vektora
  u glavnom korpusu zakona.
- **BEZBEDNA JAVNA FORMULACIJA:** „Pretraga teksta Zakona o digitalnoj imovini i EU MiCA uredbe.
  Sistem citira broj člana samo kada se taj broj doslovno nalazi u pronađenom tekstu propisa;
  u suprotnom navodi odredbu opisno, bez broja."

---

#### 1.2 Provera usklađenosti poslovnog modela

- **SPOSOBNOST:** Korisnik opiše šta radi ili planira da radi sa kripto imovinom; sistem odgovara
  da li ta aktivnost povlači dozvolu po ZDI (NBS / Komisija za HoV) ili CASP autorizaciju po MiCA.
- **LOKACIJA:** `routers/web3.py:85` → `POST /web3/compliance`; `web3_compliance.py:391`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5009`.
- **TESTIRANO?** Bez testa.
- **NA PRODUKCIJI?** `OPENAI_API_KEY` + Pinecone `web3_zdi_mca`.
- **BEZBEDNA JAVNA FORMULACIJA:** „Provera da li opisana aktivnost sa digitalnom imovinom povlači
  obavezu dozvole po Zakonu o digitalnoj imovini ili autorizacije po MiCA. Rezultat je pravna
  analiza kao polazna tačka, ne pravni savet."

---

#### 1.3 Analiza belog papira (whitepaper) / opisa projekta

- **SPOSOBNOST:** Sistem uporedi tekst belog papira ili opisa token projekta sa zahtevima ZDI
  čl. 12-19 i MiCA čl. 6, i navede šta postoji, šta nedostaje i šta treba dopuniti.
- **LOKACIJA:** `routers/web3.py:110` → `POST /web3/whitepaper`; `web3_compliance.py:437`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5017`, sekcija „Napredni AI alati"
  (`index.html:3260`).
- **TESTIRANO?** Bez testa.
- **NA PRODUKCIJI?** `OPENAI_API_KEY`.
- **BEZBEDNA JAVNA FORMULACIJA:** „Provera belog papira ili opisa token projekta prema zahtevima
  za sadržinu iz Zakona o digitalnoj imovini i MiCA uredbe — lista onoga što je pokriveno i onoga
  što nedostaje."

---

#### 1.4 MiCA ocena spremnosti (0-100)

- **SPOSOBNOST:** Numerička ocena spremnosti kripto projekta za MiCA po pet kategorija
  (usklađenost belog papira, CASP zahtevi, AML/KYC, rezerve, zabrana zloupotrebe tržišta).
- **LOKACIJA:** `routers/web3.py:135` → `POST /web3/mica-score`; `web3_compliance.py:535`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5025`.
- **TESTIRANO?** Da — `tests/test_singular_intelligence_fixes.py::test_mica_readiness_score_clamps_poisoned_response`
  (dokazuje da se ocena van opsega obara na 0-100, a neprepoznat nivo pada na najkonzervativniji).
- **NA PRODUKCIJI?** `OPENAI_API_KEY`.
- **BEZBEDNA JAVNA FORMULACIJA:** „Ocena spremnosti projekta za MiCA po pet kategorija, sa
  konkretnim nedostacima. Ocenu izračunava i ograničava backend — vrednost van dozvoljenog opsega
  se odbacuje, a neprepoznat nivo se tumači kao najniža spremnost, nikad kao 'spremno'."

---

#### 1.5 Provera potrebe za dozvolom po ZDI

- **SPOSOBNOST:** Klasifikuje digitalnu imovinu (virtuelna valuta / digitalni token), utvrđuje
  nadležni organ (NBS ili Komisija za hartije od vrednosti), procenjuje nivo rizika i nabraja
  mere koje aktivnost povlači.
- **LOKACIJA:** `routers/web3.py:165` → `POST /web3/license-check`; `web3_compliance.py:591`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5033`.
- **TESTIRANO?** Da — `tests/test_singular_intelligence_fixes.py::test_zdi_license_checker_fails_safe_to_visok_risk_on_poisoned_response`
  (neprepoznat nivo rizika obavezno pada na `VISOK`, nikad na nizak).
- **NA PRODUKCIJI?** `OPENAI_API_KEY`.
- **BEZBEDNA JAVNA FORMULACIJA:** „Klasifikacija digitalne imovine i utvrđivanje nadležnog organa
  (NBS ili Komisija za hartije od vrednosti) za opisanu aktivnost. Kada sistem ne može pouzdano da
  odredi nivo rizika, po pravilu ga prijavljuje kao visok — nikada ga ne spušta prećutno."

---

#### 1.6 Revizija AML/KYC politike

- **SPOSOBNOST:** Pregled teksta interne AML/KYC politike prema ZDI (čl. 81-97), ZSPNFT i FATF
  standardima, sa ocenom usklađenosti po osam kategorija.
- **LOKACIJA:** `routers/web3.py:195` → `POST /web3/aml-audit`; `web3_compliance.py:654`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5041`, „Napredni AI alati".
- **TESTIRANO?** Da — `tests/test_singular_intelligence_fixes.py::test_aml_kyc_auditor_clamps_poisoned_response`.
- **NA PRODUKCIJI?** `OPENAI_API_KEY`.
- **BEZBEDNA JAVNA FORMULACIJA:** „Revizija interne AML/KYC politike prema Zakonu o digitalnoj
  imovini, Zakonu o sprečavanju pranja novca i FATF standardima, sa ocenom po osam kategorija i
  listom nedostataka."

---

#### 1.7 Ocena spremnosti dokumentacije za due diligence

- **SPOSOBNOST:** Compliance oficir ili klijent opiše kakvu dokumentaciju ima o svojoj kripto
  imovini; sistem oceni koliko je ta dokumentacija spremna za pitanje banke, regulatora ili
  poreske uprave, po šest kategorija (KYC, istorija sa berzi, bankovni trag, evidencija novčanika,
  poreska rezidentnost, dokazi o sticanju), i imenuje **najveći pojedinačni rizik**.
- **LOKACIJA:** `routers/web3.py:225` → `POST /web3/health-score`;
  `web3_compliance.py:725` (`documentation_health_score_sync`).
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5059`, kartica „Due Diligence".
- **TESTIRANO?** Da — `tests/test_singular_intelligence_fixes.py::test_documentation_health_score_clamps_poisoned_response`.
- **NA PRODUKCIJI?** `OPENAI_API_KEY`. Nije RAG-grounded (izričito, `web3_compliance.py:678-681`).
- **BEZBEDNA JAVNA FORMULACIJA:** „Ocena spremnosti dokumentacije o digitalnoj imovini za upit
  banke, regulatora ili poreske uprave, po šest kategorija, sa imenovanjem najvećeg pojedinačnog
  rizika. Ovo je procena organizacione spremnosti dokumentacije, ne poresko ni pravno mišljenje."

---

#### 1.8 Simulator izveštavanja sa berzi (CARF/DAC8/CRS koncepti)

- **SPOSOBNOST:** Korisnik opiše scenario transakcija; sistem klasifikuje koje su kategorije
  transakcija prisutne i objasni zašto su tipično od interesa za međunarodne okvire izveštavanja.
- **LOKACIJA:** `routers/web3.py:255` → `POST /web3/reporting-simulator`;
  `web3_compliance.py:784`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5067`, „Napredni AI alati".
- **TESTIRANO?** Bez testa.
- **NA PRODUKCIJI?** `OPENAI_API_KEY`. **Namerno bez RAG-a i bez citiranja članova** — kod
  izričito zabranjuje modelu da citira konkretan član CARF/DAC8 teksta (`web3_compliance.py:752-757`,
  `:758`), jer bi citat bio izmišljen.
- **BEZBEDNA JAVNA FORMULACIJA:** „Edukativna simulacija: koje kategorije kripto transakcija
  međunarodni okviri izveštavanja tipično posmatraju. Sistem je programski sprečen da citira
  konkretan član CARF ili DAC8 teksta — to je opšta regulatorna edukacija, ne poreski savet."

---

#### 1.9 CARF/DAC8 spremnost (pretraga teksta)

- **SPOSOBNOST:** Konkretno pitanje o obavezama izveštavanja iz OECD CARF-a i EU direktive
  2023/2226 (DAC8), sa citiranjem samo onih sekcija koje su stvarno u bazi.
- **LOKACIJA:** `routers/web3.py:280` → `POST /web3/carf-readiness`; `web3_compliance.py:880`,
  Pinecone prostor `carf_dac8` (`web3_compliance.py:27`), punjenje `scripts/ingest_carf_dac8.py`.
- **STATUS:** `PRODUCTION`, **ali sa vrlo tankim korpusom**
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5075`.
- **TESTIRANO?** Bez testa.
- **NA PRODUKCIJI?** `OPENAI_API_KEY` + Pinecone. **Prostor `carf_dac8` je izmeren na 17 vektora**
  (`data/pinecone_baseline_2026-07-13.json`) — to je izvod iz CARF Part I, Section 2 i DAC8
  čl. 8ad / 25a / Aneks VI, ne pun tekst oba dokumenta.
- **BEZBEDNA JAVNA FORMULACIJA:** „Pitanja o obavezama izveštavanja iz OECD CARF okvira i EU
  direktive DAC8, uz citiranje isključivo onih odredaba koje su u bazi. Baza sadrži ključne
  sekcije oba dokumenta, ne njihov integralni tekst."

---

#### 1.10a Lista CARF jurisdikcija

- **SPOSOBNOST:** Zvanična OECD lista jurisdikcija koje su preuzele obavezu CARF razmene podataka
  o kripto imovini, po talasima primene, uz izričitu napomenu da Srbija nije ni na jednoj od tih
  lista.
- **LOKACIJA:** `routers/web3.py:305` → `GET /web3/jurisdikcije`;
  `web3_compliance.py:1028` (`carf_jurisdikcije_lista`), podaci `web3_compliance.py:~960-1020`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5309`, panel `index.html:3301`.
- **TESTIRANO?** Bez testa.
- **NA PRODUKCIJI?** Ne traži ništa spolja — čist statički podatak, bez AI poziva i bez troška
  kredita. **81 jurisdikcija** (46 + 29 + 1 + 5).
- **NAPOMENA O NESLAGANJU KODA I OPISA:** docstring na `routers/web3.py:307-308` tvrdi „Dostupno
  svim ulogovanim korisnicima (ne PRO-gated)", ali sama ruta ipak traži
  `PermissionService.require("da_regulatory_review")` — dakle **jeste** gejtovana addonom.
  Sajt mora da veruje kodu, ne docstring-u.
- **BEZBEDNA JAVNA FORMULACIJA:** „Pregled 81 jurisdikcije koje su preuzele obavezu CARF razmene
  podataka o kripto imovini, po talasima primene. Srbija se ne nalazi ni na jednoj od tih lista —
  trenutno formalno nema CARF obavezu izveštavanja."

---

#### 1.10b Pitanje o statusu jurisdikcije

- **SPOSOBNOST:** Objašnjenje šta status neke jurisdikcije praktično znači za korisnika, uz
  izričitu zabranu izmišljanja datuma i statusa koji nisu u strukturiranim podacima.
- **LOKACIJA:** `routers/web3.py:312` → `POST /web3/jurisdikcija-analiza`;
  `web3_compliance.py:1060`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5083`.
- **TESTIRANO?** Bez testa.
- **NA PRODUKCIJI?** `OPENAI_API_KEY`. Ne koristi RAG — radi nad strukturiranom listom.
- **BEZBEDNA JAVNA FORMULACIJA:** „Objašnjenje šta CARF status pojedine jurisdikcije praktično
  znači. Sistem odgovara isključivo na osnovu zvanične OECD liste ugrađene u proizvod i izričito
  kaže kada jurisdikcija nije na listi."

---

### F12 — Pravna analiza pametnog ugovora

#### 1.11 Pravna analiza Solidity pametnog ugovora

- **SPOSOBNOST:** Advokat ili compliance oficir koji ne poznaje Solidity nalepi izvorni kod
  pametnog ugovora i dobija strukturiran pravni prikaz: koje poslovne funkcije ugovor obavlja,
  ko ima privilegovana ovlašćenja i šta ta ovlašćenja pravno znače, nivo centralizacije,
  klasifikacija tokena, pravni rizici po ozbiljnosti, i koje odredbe propisa aktivira.
  Alat izričito **nije** bezbednosni audit koda.
- **LOKACIJA:** `routers/web3.py:552` → `POST /web3/analiziraj-ugovor`; sistemski prompt
  `routers/web3.py:339-472`; determinističke provere `routers/web3.py:505-540`;
  tabela `migrations/smart_contract_analyses.sql`.
- **STATUS:** `PRODUCTION` — **najbolje dokazana Web3 sposobnost u proizvodu**
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5049`, „Napredni AI alati" (`index.html:3262`).
- **TESTIRANO?** Da, najjače u celom modulu:
  - `tests/test_f12_postprocessing.py` — 21 test (`test_t1_detect_lock_without_exit_true`,
    `test_t7_lock_risk_appended_when_missing`, `test_tm1_detect_unrestricted_mint_true_for_onlyowner_mint`,
    `test_tm4_mint_risk_appended_when_missing`, `test_t5_aml_note_appended`, i dr.)
  - `tests/test_f12_prompt_hardening.py` — 5 testova nad sadržajem prompta
  - `tests/test_beta_gate_credit_race.py` — utrka pri odbijanju kredita za ovu funkciju
- **NA PRODUKCIJI?** `OPENAI_API_KEY` (gpt-4o). Košta **5 kredita** — najskuplji alat u modulu
  (`migrations/064_feature_registry.sql:153`).
- **VAŽNO — determinističke provere koje ne zavise od modela:** kod sam, regularnim izrazima,
  detektuje proxy/upgradeable obrazac, zaključavanje sredstava bez izlaza, i neograničeno
  mintovanje bez gornjeg limita ponude; ako model te rizike propusti, backend ih **dodaje sam**
  (`routers/web3.py:691-712`) i obara nivo pouzdanosti sa `HIGH` na `MEDIUM` kad je proxy
  detektovan (`routers/web3.py:673-675`).
- **BEZBEDNA JAVNA FORMULACIJA:** „Pravna analiza pametnog ugovora: prevodimo logiku Solidity koda
  u pravni jezik — ko ima kontrolu, šta ta kontrola pravno znači, koji rizici iz toga proizlaze i
  koje odredbe propisa aktiviraju. Tri rizika (proxy/nadogradivost, zaključana sredstva bez
  izlaza, neograničeno mintovanje) proverava sam kod, nezavisno od AI modela, i dodaje ih u
  izveštaj i kada ih model propusti. **Ovo nije bezbednosni audit koda.**"

---

### F13 — Uvoz transakcija sa berzi

#### 1.12 Uvoz i klasifikacija CSV izvoda sa Binance i Kraken

- **SPOSOBNOST:** Korisnik otpremi zvanični CSV izvod sa Binance-a (Transaction History) ili
  Kraken-a (Ledger History); sistem prepozna format po tačnim nazivima kolona, normalizuje redove
  i razvrsta transakcije u kategorije relevantne za CARF/DAC8 (kupovina/prodaja za fiat,
  crypto-to-crypto, uplata, isplata na sopstveni novčanik, staking prihod, airdrop, naknada).
- **LOKACIJA:** `routers/csv_import.py:183` → `POST /csv-import/analiziraj`;
  detekcija formata `:83`, Binance `:92`, Kraken `:114`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5574`, panel `index.html:3358`.
- **TESTIRANO?** **Bez testa.** Ovo je jedini deterministički parser u modulu bez ijednog testa.
- **NA PRODUKCIJI?** Ne traži ništa spolja — nema AI poziva, nema troška kredita. Limiti: 5 MB,
  50.000 redova, prikaz 500 transakcija.
- **KVALITET IMPLEMENTACIJE (dokaz iz koda):** Kraken svaki trade predstavlja kao dva reda
  povezana istim `refid`-om; parser ih **grupiše pre klasifikacije** (`csv_import.py:114-165`),
  jer bi izolovan pogled na crypto nogu para BTC/EUR pogrešno dao „crypto-to-crypto" umesto
  „kupovina za fiat". To je tačna, a ne približna klasifikacija.
- **BEZBEDNA JAVNA FORMULACIJA:** „Uvoz zvaničnog CSV izvoda sa Binance-a i Kraken-a i
  razvrstavanje transakcija u kategorije relevantne za CARF/DAC8 izveštavanje. Format se
  prepoznaje po tačnim nazivima kolona; Kraken trade-ovi se grupišu po identifikatoru para pre
  klasifikacije, da se kupovina za fiat ne bi pogrešno prikazala kao crypto-to-crypto zamena."

---

#### 1.13 Lista podržanih formata izvoda

- **LOKACIJA:** `routers/csv_import.py:271` → `GET /csv-import/podrzani-formati`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Ne direktno — panel `index.html:3358` sadrži uputstvo statički. Ruta je
  besplatna (`get_current_user`, bez addona) i vraća uputstvo korak-po-korak za oba izvoza.
- **TESTIRANO?** Bez testa.
- **BEZBEDNA JAVNA FORMULACIJA:** „Trenutno podržani izvozi: Binance (Transaction History) i
  Kraken (Ledger History). Coinbase i Bitget su na mapi puta."

---

### F14 — Sankciona provera (OFAC)

#### 1.14 Provera adresa protiv OFAC SDN liste

- **SPOSOBNOST:** Korisnik nalepi do 25 adresa digitalne imovine; sistem ih proverava protiv
  zvanične OFAC SDN liste i za svaku sankcionisanu adresu vraća entitet, imovinu, sankcione
  programe i OFAC identifikator.
- **LOKACIJA:** `routers/ofac_screening.py:67` → `POST /web3/ofac-screening`;
  podaci `data/ofac_crypto_addresses.json`, punjenje `scripts/ingest_ofac_sdn.py`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5359`, panel `index.html:3311`, kartica
  „Wallet Risk Assessment".
- **TESTIRANO?** **Bez testa.**
- **NA PRODUKCIJI?** Ne traži spoljni servis. Podaci su u repou i ulaze u Docker sliku
  (`Dockerfile`, `COPY . .`). Izmereno: **916 adresa**, izvor
  „OFAC SDN Advanced List (sanctionslistservice.ofac.treas.gov)", snapshot od **13.07.2026**.
  Ruta je besplatna i nije addon-gejtovana na backendu (`Depends(get_current_user)`), ali je
  ekran na kojem se nalazi gejtovan (vidi § 5).
- **OSVEŽAVANJE:** ručno pokretanje ingest skripte. Endpoint sam vraća datum poslednjeg
  osvežavanja baze u polju `coverage.poslednje_azuriranje_baze`.
- **BEZBEDNA JAVNA FORMULACIJA:** „Provera adresa digitalne imovine protiv zvanične OFAC SDN
  liste — trenutno 916 adresa iz zvaničnog OFAC izvora. Za svaku sankcionisanu adresu prikazujemo
  entitet i sankcione programe. Uz svaki rezultat prikazuje se i datum poslednjeg osvežavanja
  liste."

---

#### 1.15 Metapodaci o OFAC bazi

- **LOKACIJA:** `routers/ofac_screening.py:124` → `GET /web3/ofac-info`.
- **STATUS:** `PRODUCTION`
- **DOSTUPNO KORISNIKU?** Posredno — panel prikazuje izvor i datum iz odgovora screening rute.
- **TESTIRANO?** Bez testa.

---

### F15 — Poreklo novčanika

#### 1.16 Provera porekla Ethereum novčanika (Wallet Provenance)

- **SPOSOBNOST:** Za jednu Ethereum adresu sistem utvrđuje starost novčanika, obim aktivnosti,
  stanje, i — što je najvažnije — proverava **i sam novčanik i sve njegove direktne (1-hop)
  kontakte** protiv OFAC SDN liste. Nalazi su razdvojeni po nivou pouzdanosti: `VISOKA` (novčanik
  je sam na listi), `SREDNJA` (direktan kontakt sa adresom sa liste), `NISKA` (heuristička
  opservacija o obrascu ponašanja, izričito ne nalaz o sankcijama).
- **LOKACIJA:** `routers/wallet_provenance.py:311` → `POST /web3/wallet-provenance`;
  zajednička logika `:115` (`sakupi_wallet_provenance`); model pouzdanosti `:49-61`.
- **STATUS:** **`UNVERIFIED`** — kod je kompletan i ožičen, ali **bez `ETHERSCAN_API_KEY`
  endpoint vraća HTTP 503** (`routers/wallet_provenance.py:118-126`), a prisustvo tog ključa u
  produkciji se iz repoa ne može dokazati.
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5417`, panel `index.html:3325`.
- **TESTIRANO?** Bez testa same logike. Postoji test naplate:
  `tests/test_phantom_ai_charges.py` (`da_wallet_risk_assessment` — vidi § 3).
- **NA PRODUKCIJI?** **Traži `ETHERSCAN_API_KEY`** (`.env.example:115`). Ključ postoji u lokalnom
  `.env`; produkciona konfiguracija nije proverljiva iz repoa. Izvor: Etherscan API **V2**
  (`api.etherscan.io/v2/api`, `chainid=1`) — stari V1 endpoint je ukinut 15.08.2025.
  Obim po pozivu: najviše 1.000 transakcija (Etherscan Free tier), a kad se limit dostigne,
  odgovor sadrži izričito upozorenje.
- **BEZBEDNA JAVNA FORMULACIJA:** „Provera Ethereum novčanika: starost, obim aktivnosti i
  unakrsna provera samog novčanika i njegovih direktnih kontakata protiv OFAC SDN liste. Nalazi
  su razvrstani po nivou pouzdanosti — od determinističkog pogotka na sankcionoj listi do
  heurističke opservacije koja izričito nije nalaz o sankcijama. **Analiza je ograničena na
  Ethereum mrežu i direktne (1-hop) kontakte i ne predstavlja potpunu blockchain forenzičku
  analizu.**" (Videti § 4 — ograda je obavezna.)

---

### F16 — Dosije o poreklu sredstava

#### 1.17 Source-of-Funds / Source-of-Wealth compliance dosije (PDF)

- **SPOSOBNOST:** Jedan PDF dokument za banku ili regulatora koji spaja tri stvari: ocenu
  spremnosti dokumentacije (§ 1.7), CARF/DAC8 kontekst (§ 1.9) i — opciono — proveru porekla
  novčanika (§ 1.16). Ograničenja analize se u PDF-u štampaju **pre** bilo kog nalaza, ne u
  fusnoti (`dossier_pdf.py:190-193`).
- **LOKACIJA:** `routers/source_of_funds.py:64` → `POST /web3/source-of-funds-dossier`;
  generisanje PDF-a `dossier_pdf.py:generisi_dossier_pdf`.
- **STATUS:** `PRODUCTION` (wallet sekcija je opciona i degradira gracioznо)
- **DOSTUPNO KORISNIKU?** Da — `static/vindex.js:5515`, panel `index.html:3339`, kartica
  „Source of Funds".
- **TESTIRANO?** Bez testa.
- **NA PRODUKCIJI?** `OPENAI_API_KEY` (dva paralelna poziva). Košta **2 kredita**
  (`migrations/064_feature_registry.sql:152`). Ako `ETHERSCAN_API_KEY` nedostaje, wallet sekcija
  se **preskače uz upozorenje u logu, a dosije se svejedno generiše**
  (`routers/source_of_funds.py:87-94`) — ovo je dokazano ponašanje, ne pretpostavka.
- **BEZBEDNA JAVNA FORMULACIJA:** „Jedan PDF dosije o poreklu sredstava za banku ili regulatora:
  ocena spremnosti dokumentacije, kontekst obaveza izveštavanja i, opciono, provera porekla
  novčanika. Ograničenja analize štampaju se na vrhu izveštaja, pre svakog nalaza."

---

### Mrtav kod — postoji, ali nije deo proizvoda

| Modul | Šta radi | Status | Dokaz |
|---|---|---|---|
| `vindex_web3/` | Kleros v2 pipeline za on-chain arbitražu: detekcija sporova iz blockchain događaja, mapiranje na ZOO/ZDI, generisanje Kleros dokaznog paketa | `DEAD` | Nijedan produkcioni fajl ga ne uvozi (provereno pretragom `from vindex_web3` / `import vindex_web3` po celom repou — nula pogodaka van samog direktorijuma). Sopstveni `README.md` kaže: „Extension modul — nije u produkcijskom API-ju". |
| `web3_integracija/` | Queue adapter koji blockchain događaje pretvara u pravne upite prema `/api/pitanje` | `DEAD` | Isto — nula uvoza spolja; sopstveni `README.md` to izričito priznaje. |

**Ovi moduli ne smeju na sajt ni u jednom obliku** — ni kao „u razvoju", ni kao „mapa puta",
jer bi svaka pomena Kleros arbitraže ili on-chain event obrade bila tvrdnja o sposobnosti koju
proizvod nema ožičenu.

---

## 2. ŠTA SME NA SAJT

**Sme:** 17 sposobnosti sa statusom `PRODUCTION`. Ispod su doslovne formulacije, spremne za
kopiranje. Svaka je izvedena iz koda i ne tvrdi ništa preko onoga što kod radi.

### Naslov sekcije/stranice
> **Digitalna imovina — usklađenost i provera porekla**
> Due diligence, regulatorna provera, sankciona provera novčanika i dokumentacija o poreklu
> sredstava — za advokatske kancelarije, banke i compliance timove.

*(Ova rečenica nije izmišljena — doslovno je preuzeta iz proizvoda, `index.html:3215`.)*

### Četiri stuba — tačno onako kako su ožičeni u proizvodu

Redosled i grupisanje ispod nisu marketinška konstrukcija: to je `DIM_CARDS`
(`static/vindex.js:2137`), stvarna struktura ekrana.

**1. Due Diligence**
> „Ocena spremnosti dokumentacije o digitalnoj imovini za upit banke, regulatora ili poreske
> uprave, po šest kategorija — KYC, istorija sa berzi, bankovni trag, evidencija novčanika,
> poreska rezidentnost i dokazi o sticanju — sa imenovanjem najvećeg pojedinačnog rizika.
> Ovo je procena organizacione spremnosti dokumentacije, ne poresko ni pravno mišljenje."

**2. Regulatorna provera**
> „Pretraga teksta Zakona o digitalnoj imovini i EU MiCA uredbe, provera da li opisana aktivnost
> povlači dozvolu NBS-a ili Komisije za hartije od vrednosti odnosno CASP autorizaciju, ocena
> spremnosti projekta za MiCA, provera belog papira, pitanja o CARF i DAC8 obavezama, pregled 81
> jurisdikcije koja je preuzela CARF obavezu, i uvoz izvoda transakcija sa Binance-a i Kraken-a.
> Broj člana propisa citiramo samo kada se taj broj doslovno nalazi u pronađenom tekstu."

**3. Sankciona provera novčanika**
> „Provera adresa digitalne imovine protiv zvanične OFAC SDN liste — trenutno 916 adresa iz
> zvaničnog OFAC izvora, sa prikazom entiteta, sankcionih programa i datuma poslednjeg
> osvežavanja liste."

**4. Poreklo sredstava**
> „Jedan PDF dosije za banku ili regulatora: ocena spremnosti dokumentacije, kontekst obaveza
> izveštavanja i, opciono, provera porekla novčanika. Ograničenja analize štampamo na vrhu
> izveštaja, pre svakog nalaza — ne u fusnoti."

### Najjača pojedinačna tvrdnja koju smemo da iznesemo

> **„Pravna analiza pametnog ugovora — bez čitanja koda."**
> „Nalepite Solidity izvorni kod i dobijate pravni prikaz, ne tehnički: ko ima kontrolu nad
> sistemom, šta ta kontrola pravno znači, koji rizici iz toga proizlaze i koje odredbe propisa
> aktiviraju. Tri rizika — nadogradivost ugovora, zaključana sredstva bez mehanizma izlaza, i
> neograničeno mintovanje bez gornjeg limita ponude — proverava sam kod, regularnim izrazima,
> nezavisno od AI modela, i dodaje ih u izveštaj i kada ih model propusti.
> Ovo nije bezbednosni audit koda."

Ovo je jedina Web3 sposobnost sa **26 testova** (`tests/test_f12_postprocessing.py`,
`tests/test_f12_prompt_hardening.py`) i može se braniti u razgovoru sa tehničkim kupcem.

### Tvrdnja o disciplini koja se sme izneti (i retka je)

> „Kada sistem ne može pouzdano da odredi nivo rizika, prijavljuje ga kao visok — nikada ga ne
> spušta prećutno."

Dokaz: `tests/test_singular_intelligence_fixes.py::test_zdi_license_checker_fails_safe_to_visok_risk_on_poisoned_response`,
plus tri prateća testa koja dokazuju da se ocene van opsega obaraju u konzervativnom smeru.

---

## 3. ŠTA NE SME NA SAJT — po stavci

| # | Tvrdnja koja NE sme | Zašto |
|---|---|---|
| 1 | Bilo šta o **Kleros arbitraži, on-chain rešavanju sporova, obradi blockchain događaja** | `vindex_web3/` i `web3_integracija/` su `DEAD` — nula uvoza iz produkcionog koda, sopstveni README to priznaje. |
| 2 | **„Blockchain forenzika"**, „praćenje toka sredstava", „tragovi kroz više transakcija" | Kod izričito tvrdi suprotno: `routers/wallet_provenance.py:70` — „Rezultat NE predstavlja potpunu blockchain forenzičku analizu." Prati se samo 1-hop. |
| 3 | **„Podrška za sve blockchain mreže"** ili pominjanje bilo koje mreže osim Ethereum-a | `routers/wallet_provenance.py:67` — „Analiza je trenutno ograničena na Ethereum mrežu (mainnet)." |
| 4 | **Wallet Provenance kao dostupna funkcija bez ograde** | Status `UNVERIFIED`: bez `ETHERSCAN_API_KEY` vraća 503 (`wallet_provenance.py:118-126`). Dok se prisustvo ključa u produkciji ne potvrdi, ovo se sme opisati samo uz uslov. |
| 5 | **„Pretraga kompletnog CARF i DAC8 teksta"** | Prostor `carf_dac8` ima **17 vektora** (`data/pinecone_baseline_2026-07-13.json`) — ključne sekcije, ne integralni tekst. Smemo reći „ključne sekcije", ne „kompletan tekst". |
| 6 | **Citiranje konkretnih članova CARF/DAC8** u marketinškim primerima | Simulator izveštavanja (§ 1.8) je programski sprečen da to radi (`web3_compliance.py:758`), jer dokumenti nisu ingestovani u toj granularnosti. Primer na sajtu koji prikazuje „CARF čl. X" bio bi lažan prikaz proizvoda. |
| 7 | **„Poreski savet"**, „poreska optimizacija", bilo kakav kalkulator poreske obaveze | `routers/csv_import.py:265`, `web3_compliance.py:777-781` — svi ti moduli sami sebe označavaju kao „NIJE poreski savet". |
| 8 | **Trading, DeFi prinosi, preporuka kupovine/prodaje, cene, portfolio vrednost** | Van obima proizvoda po odluci vlasnika. U kodu ovo ne postoji — nema nijedne rute koja radi bilo šta od toga. Provereno. |
| 9 | **„Kompletan sankcijski compliance program"** ili „AML program" | `routers/ofac_screening.py:119` — „Ovo nije pravni savet niti zamena za profesionalni sankcijski compliance program." |
| 10 | **„Adresa je čista / bez rizika"** kao ishod provere | `routers/wallet_provenance.py:302-305` — „Odsustvo poklapanja NE predstavlja potvrdu da su sredstva bez rizika". Sajt ne sme prikazati zeleni „čisto" ishod. |
| 11 | **Bilo koja tvrdnja o samouslužnoj kupovini modula** | Stripe nije integrisan (`migrations/060`, `:062` izričito). Aktivacija je ručna, na zahtev. Postojeći UI to i radi ispravno („Zatražite aktivaciju"). |
| 12 | **„Ažurirano u realnom vremenu"** za OFAC listu | Snapshot od 13.07.2026, ručno osvežavanje. Sam kod upozorava: „OFAC lista se ažurira u realnom vremenu i ovaj snapshot može biti neaktuelan." |
| 13 | **„Bezbednosni audit pametnog ugovora"** | `routers/web3.py:342` — „NISI alat za bezbednosni audit koda". Ovo je granica koju je pisao neko ko zna posledice njenog prelaska. |

---

## 4. OGRADE KOJE SU OBAVEZNE — doslovno iz koda

Ove rečenice su napisali ljudi koji su znali granice sistema. Sajt ih **mora ponoviti**, ne
parafrazirati blaže.

### 4.1 Wallet Provenance — četiri ograničenja, uvek na vrhu

`routers/wallet_provenance.py:66-73` (`OGRANICENJA_ANALIZE`), štampa se na vrhu i u UI-ju i u
PDF-u (`dossier_pdf.py:190-193`):

> 1. „Analiza je trenutno ograničena na Ethereum mrežu (mainnet)."
> 2. „Proveravaju se isključivo direktni (1-hop) kontakti novčanika — sredstva se ne prate kroz
>    više transakcija unazad (multi-hop)."
> 3. **„Rezultat NE predstavlja potpunu blockchain forenzičku analizu."**
> 4. „Ne vrši se identifikacija vlasnika novčanika niti atribucija entiteta, osim putem javno
>    dostupnih oznaka i zvaničnih sankcionih lista (OFAC SDN)."

### 4.2 Wallet Provenance — zaključna napomena

`routers/wallet_provenance.py:301-307`:

> „Provera pokriva samo Ethereum mainnet i DIREKTNE (1-hop) kontakte novčanika — ne prati sredstva
> kroz više transakcija unazad (multi-hop). **Odsustvo poklapanja NE predstavlja potvrdu da su
> sredstva bez rizika** — samo da nema poznatog poklapanja sa trenutno učitanom OFAC SDN listom.
> Ovo nije pravni savet niti zamena za profesionalni AML/sankcijski program."

### 4.3 OFAC screening

`routers/ofac_screening.py:115-120`:

> „Provera je izvršena protiv zvanične OFAC SDN liste digitalne imovine. **Odsustvo pogotka NE
> znači da adresa nema drugi pravni ili reputacioni rizik** — OFAC lista se ažurira u realnom
> vremenu i ovaj snapshot može biti neaktuelan. Ovo nije pravni savet niti zamena za profesionalni
> sankcijski compliance program."

### 4.4 Uvoz CSV izvoda

`routers/csv_import.py:263-267`:

> „Ovo je deterministička klasifikacija na osnovu naziva operacije/tipa iz CSV exporta — **NIJE
> poreski savet i ne zamenjuje pregled od strane poreskog savetnika.** Kategorije
> 'crypto_to_crypto' i 'nepoznato' posebno zahtevaju ručnu proveru."

### 4.5 Simulator izveštavanja (CARF/DAC8/CRS)

`web3_compliance.py:777-781` — model je obavezan da ovim tekstom završi **svaki** odgovor:

> „Ovo je opšta regulatorna edukacija zasnovana na javno poznatim obrascima međunarodnog
> izveštavanja o kripto imovini (CARF/DAC8/CRS koncepti), NE poreski ili pravni savet, i NE
> zvanično tumačenje CARF ili DAC8 teksta. Konkretna obaveza izveštavanja zavisi od jurisdikcije,
> statusa platforme i datuma primene lokalnih propisa — konsultujte poreskog savetnika ili
> advokata pre donošenja odluka."

### 4.6 CARF/DAC8 spremnost

`web3_compliance.py:875-877`:

> „Ovo je opšta regulatorna analiza zasnovana na CARF/DAC8 tekstu, NE poreski ili pravni savet.
> Implementacija se razlikuje po jurisdikciji i vremenskom okviru primene — konsultujte poreskog
> [savetnika ili advokata]."

### 4.7 ZDI/MiCA pretraga

`web3_compliance.py:194`:

> „Ovo nije pravni savet. Konsultujte advokata specijalizovanog za digitalnu imovinu."

Uz to, kad relevantnost pronađenih izvora padne ispod 55%, sistem sam dodaje upozorenje
(`web3_compliance.py:380-386`):

> „Napomena o pouzdanosti: Za ovo pitanje nisu pronađeni visoko relevantni izvodi iz baze
> zakona… Odgovor se delimično zasniva na pravnoj logici — preporučujemo konsultaciju sa
> advokatom pre donošenja odluke."

### 4.8 Documentation Health Score

`web3_compliance.py:720`:

> „Ovo je procena ORGANIZACIONE spremnosti dokumentacije, ne poresko ili pravno mišljenje."

### 4.9 Pametni ugovor — pravna analiza

`routers/web3.py:342`:

> „NISI alat za bezbednosni audit koda niti za tehničko objašnjavanje Solidity funkcija."

I napomena koju backend sam dodaje ako je model ne uključi (`routers/web3.py:480-484`):

> „AML obaveze se tipično procenjuju na nivou platforme ili operatera sistema (koji mora imati
> politiku AML/KYC), a ne na nivou samog pametnog ugovora koji nema mehanizam za identifikaciju
> korisnika."

### 4.10 Srbija i CARF

`web3_compliance.py:1034-1037`:

> „Srbija se ne pojavljuje ni na jednoj od gornjih lista (46+29+1+5=81 jurisdikcija) — trenutno
> formalno nema CARF obavezu izveštavanja."

---

## 5. USLOVI — bez čega ništa ne radi

### 5.1 Gejtovanje — modul NIJE dostupan podrazumevano

Ovo je najvažniji uslov i sajt ga ne sme prećutati.

**Backend gate.** Svih 14 „skupih" ruta traži `PermissionService.require(...)` sa jednim od osam
`da_*` ključeva. Svih osam ključeva u `migrations/064_feature_registry.sql:149-156` ima
`minimum_plan = NULL` i `addon = 'digital_assets'`. `NULL` minimum_plan znači, doslovno po
`migrations/111:113-114`: **„otključava se ISKLJUČIVO preko addon-a"** — nijedna tarifa ga ne
uključuje sama po sebi.

| Ključ | Rute koje štiti | Krediti |
|---|---|---|
| `da_regulatory_review` | `/web3/pretraga`, `/web3/compliance`, `/web3/mica-score`, `/web3/license-check`, `/web3/carf-readiness`, `/web3/jurisdikcije`, `/web3/jurisdikcija-analiza`, `/csv-import/analiziraj` | 1 |
| `da_due_diligence` | `/web3/health-score` | 1 |
| `da_whitepaper_analysis` | `/web3/whitepaper` | 1 |
| `da_aml_audit` | `/web3/aml-audit` | 1 |
| `da_reporting_simulator` | `/web3/reporting-simulator` | 1 |
| `da_smart_contract` | `/web3/analiziraj-ugovor` | **5** |
| `da_source_of_funds` | `/web3/source-of-funds-dossier` | **2** |
| `da_wallet_risk_assessment` | `/web3/wallet-provenance` | **0** (vidi § 5.3) |

Besplatne i negejtovane na backendu (`Depends(get_current_user)`): `/web3/ofac-screening`,
`/web3/ofac-info`, `/csv-import/podrzani-formati`.

**Frontend gate.** Pill „Vindex AI - Digitalna imovina & usklađenost" (`index.html:2846`) je
`display:none` dok `currentUserDigitalnaImovinaAktivirano` nije tačno
(`static/vindex.js:2093-2095`). Postoji i odbrambena provera protiv deep-link zaobilaska
(`static/vindex.js:2041-2054`). **Posledica koju sajt mora znati:** i besplatne rute (OFAC
screening, uvoz CSV formata) su korisniku nedostupne dok modul nije aktiviran, jer je jedini
ekran sa kojeg se zovu unutar gejtovanog režima.

**Tarifa.** Dva ulaza (`migrations/062`, `static/vindex.js:8208-8209`):
- **79 EUR/mes samostalno** — bez ostatka platforme (predviđeno za banke); ostatak UI-ja se
  sakriva (`_dimApplyStandaloneRestriction`, `vindex.js:2100-2128`)
- **39 EUR/mes kao dodatak** uz postojeći PRO nalog

**Stripe nije integrisan.** `migrations/060:8-11` i `062:14-16` izričito: aktivacija je ručna —
korisnik pošalje zahtev, osnivač postavi flagove u bazi. Sajt sme imati samo CTA tipa „Zatražite
aktivaciju", nikad „Kupite odmah".

### 5.2 Spoljni ključevi

| Ključ | Šta bez njega ne radi | Dokaz |
|---|---|---|
| **`ETHERSCAN_API_KEY`** | `/web3/wallet-provenance` vraća **HTTP 503** sa porukom „Wallet Risk Assessment servis nije konfigurisan". Dosije o poreklu sredstava se i dalje generiše, ali **bez wallet sekcije**. | `.env.example:115`; `routers/wallet_provenance.py:118-126`; `routers/source_of_funds.py:87-94` |
| `OPENAI_API_KEY` | 12 od 18 ruta (sve AI rute). | `routers/web3.py` (svaka ruta), `web3_compliance.py` |
| Pinecone (`PINECONE_API_KEY`, `PINECONE_HOST`) | `/web3/pretraga`, `/web3/compliance`, `/web3/carf-readiness` — jedine tri RAG rute. | `web3_compliance.py:26-27`, `app/services/retrieve.py` |

**Ne traže ništa spolja:** OFAC screening, OFAC info, lista jurisdikcija, uvoz CSV izvoda,
lista podržanih formata. To su čisti deterministički moduli — i to je, za compliance publiku,
prednost koju vredi reći naglas.

### 5.3 `da_wallet_risk_assessment` — šta se sa njim desilo

Ključ je bio jedan od tri u `migrations/111_phantom_ai_charges.sql` (grupa A — ključevi čija
**sva** naplatna mesta nemaju AI poziv). `routers/wallet_provenance.py` nema čak ni
`import openai` — provera novčanika je čist Etherscan poziv plus lokalni lookup po OFAC listi.
Migracija ga postavlja na `krediti = 0`, `chargeable = false`, `ai_model = NULL`
(`migrations/111:73-97`).

**Da li još naplaćuje?** Zavisi isključivo od toga da li je migracija 111 pokrenuta u produkciji.
Poslednji zapis u repou (`docs/beta_war/BETA_HARDENING_WAVE_9.md:127`) kaže:
**„IMPLEMENTED / TESTED / PRODUCTION VERIFIED: NO — OWNER ACTION"**. Isto stoji i u
`P0_CLOSURE_LEDGER.md:197`. Kod je popravljen i pokriven testovima
(`tests/test_phantom_ai_charges.py`, `tests/test_wave9_migration_111.py`), ali migracija čeka
vlasnika. **Dok se ne pokrene, provera novčanika i dalje troši 1 kredit iako nema nijedan AI
poziv.** Sajt ne sme reklamirati proveru novčanika kao „bez troška kredita" dok se to ne potvrdi.

Napomena: `UsageService.consume()` se namerno **ne** uklanja iz koda ni sa `krediti=0` — ostaju
cooldown, dnevni/mesečni limit i telemetrija (`migrations/111:63-67`).

### 5.4 Svežina podataka

| Podatak | Stanje | Osvežavanje |
|---|---|---|
| OFAC SDN adrese | 916 adresa, snapshot **13.07.2026** | ručno, `scripts/ingest_ofac_sdn.py` |
| `web3_zdi_mca` (ZDI + MiCA) | 479 vektora | ručno, `scripts/ingest_web3_addendum.py` |
| `carf_dac8` | **17 vektora** — ključne sekcije, ne pun tekst | ručno, `scripts/ingest_carf_dac8.py` |
| CARF jurisdikcije | 81 jurisdikcija, ugrađeno u kod | izmena koda |

---

## 6. PRESUDA — samostalna stranica `/web3` ili sekcija u `/vizija`?

### Odluka: **DA — samostalna stranica je opravdana.**

Ali ne stranica pod imenom `/web3`. Preporučena putanja: **`/digitalna-imovina`**, sa naslovom
„Digitalna imovina — usklađenost i provera porekla". Razlog je proizvodni, ne estetski: sam
proizvod je taj modul preimenovao iz „Web3 & Kripto" u „Digitalna imovina & Usklađenost"
(`migrations/060:6-7`), a publika koju ova stranica cilja — banke, compliance timovi, advokati —
reč „Web3" doživljava kao signal spekulativnog proizvoda, što je tačno ono što ovaj modul nije.

### Obrazloženje brojem

| Status | Broj sposobnosti |
|---|---|
| `PRODUCTION` | **17** |
| `UNVERIFIED` (Wallet Provenance — čeka `ETHERSCAN_API_KEY` u produkciji) | 1 |
| `IMPLEMENTED_UNWIRED` | 0 |
| `DEAD` (moduli, ne rute) | 2 |
| **Ukupno ruta** | **18** |

### Obrazloženje težinom — pet argumenata, svaki sa dokazom

**1. Ovo nije skup demoa nego kompletan proizvodni tok.** Postoji dvonivoski ekran sa četiri
kartice (`index.html:3207-3370`), 16 alata mapiranih na te kartice (`vindex.js:2137-2160`),
sopstveni PDF izlaz (`dossier_pdf.py`), i sopstvena tabela u bazi
(`migrations/smart_contract_analyses.sql`). Korisnik može ući, uraditi posao i izaći sa
dokumentom koji nosi banci. To je definicija završenog scenarija.

**2. Modul već ima sopstvenu cenu i sopstvenog kupca.** Dve tarife (79 EUR samostalno / 39 EUR
dodatak, `migrations/062`) i režim u kojem se **ostatak platforme sakriva**
(`_dimApplyStandaloneRestriction`) — dakle proizvod je već predviđen da se prodaje nekome ko
Vindex ne kupuje kao advokatski softver. Kupac koji dolazi po taj proizvod ne sme da ga traži
kao pasus unutar stranice o viziji. Sekcija u `/vizija` bi bila u direktnoj protivrečnosti sa
poslovnom odlukom koja je već implementirana u kodu.

**3. Ima sadržaja za punu stranicu, a ne za jedan pasus.** Četiri stuba, svaki sa 1-8 stvarnih
alata, plus jedan flagship alat (pravna analiza pametnog ugovora) koji sam po sebi nosi sekciju.
Sedamnaest dokazanih sposobnosti je više nego što neke cele stranice na sajtu imaju.

**4. Kvalitet dokaza je iznadprosečan za ovaj repo.** F12 ima 26 testova. Četiri ocene imaju
testove koji dokazuju da otrovan odgovor modela ne može da obori nivo rizika naniže. To je
materijal koji izdrži tehnički due diligence kupca — a to je tačno publika ove stranice.

**5. Ograde su napisane pre nego što je iko tražio da budu napisane.** Deset različitih ograda
u kodu, među njima i one koje se štampaju **pre** nalaza, a ne posle (`dossier_pdf.py:190`).
Za compliance publiku to nije mana koju treba sakriti — to je **glavni prodajni argument**.
Stranica koja doslovno citira „Rezultat NE predstavlja potpunu blockchain forenzičku analizu"
gradi više poverenja od stranice koja obećava forenziku.

### Šta presuda NE pokriva — uslovi bez kojih stranica ne sme da izađe

1. **Wallet Provenance mora dobiti potvrdu da `ETHERSCAN_API_KEY` postoji u produkciji.** Do
   tada se na stranici sme pominjati samo kao deo sankcione provere sa izričitim uslovom, ili
   nikako. Ovo je jedina stavka koja može da učini stranicu neistinitom prvog dana.
2. **Migracija 111 mora biti pokrenuta** pre nego što se bilo gde tvrdi da je provera novčanika
   besplatna.
3. **CTA mora biti „Zatražite aktivaciju"**, nikad „Kupite" — Stripe ne postoji.
4. **Stranica mora sadržati bar ograde iz § 4.1, § 4.3 i § 4.4** doslovno.
5. **Nijedna reč o Kleros-u, on-chain arbitraži, drugim mrežama osim Ethereum-a, tradingu ili
   DeFi-ju.**

### Alternativa koju sam razmotrio i odbacio

Sekcija unutar `/vizija` bi bila **pogrešna**, i to ne malo. Ona sadržaj koji je proizvodno
završen, testiran, ožičen i već ima cenu — svrstava među stvari koje tek dolaze. To bi bila
obrnuta greška od one koju ovaj dokument inače štiti: ne preterivanje, nego potcenjivanje
dokazanog. Jedina stavka koja stvarno pripada „viziji" je red koji proizvod već sam prikazuje
(`index.html:3268`): „Na mapi puta: Cross-border reporting · Enhanced provenance · Additional
blockchain support" — i to je jedina rečenica sa te stranice koja sme da govori o budućnosti.
