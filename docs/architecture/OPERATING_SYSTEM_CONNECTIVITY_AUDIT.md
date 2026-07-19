# Vindex AI — Operating System Connectivity Audit (2026-07-19)

**Metodologija:** dubinska analiza `main` grane isključivo kroz stvaran
kod — backend routers/services/migrations, frontend tokove, event
sistem, audit sistem. Sprovedena kroz 3 paralelna istraživanja
(Event/Genome/Evidence/Audit; Timeline/Rokovi; CRM/Strategy/Finance),
svaki nalaz citiran na file:line. Ovo je ANALIZA — nijedna linija koda
nije menjana u ovoj rundi.

**Najvažnije upozorenje pre bilo čega drugog:** ovaj audit je otkrio
nešto strukturno drugačije od očekivanog. Pitanje nije bilo "da li
sistem ima dovoljno automatizacije" — pitanje je **"zašto izgrađena
automatizacija ne radi za standardni korisnički tok"**. Vindex AI ima
opsežnu, funkcionalnu operativnu infrastrukturu (event handleri, kompletan
case pipeline, deadline skener sa akcionim planovima, audit framework) —
ali je gotovo sva ta infrastruktura **odsečena od jedinog puta kojim
danas nastaje predmet**. Ovo menja prirodu preporuke u Fazi 6: prioritet
nije graditi novo, nego **povezati već izgrađeno**.

---

# FAZA 1 — Mapiranje trenutne arhitekture

```
INPUT (upload dokumenta u postojeći predmet, ili tekst opisa problema)
        |
        v
INTAKE (5-koračni wizard, POST /api/intake/kreiraj — JEDINI živi put
        za "+ Novi predmet" na main grani)
        |
        v
PREDMET (kreiran, ALI: EventType.PREDMET_KREIRAN se NIKAD ne emituje
        za ovaj put — potvrđeno grep-om kroz ceo produkcijski kod)
        |
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
   GENOME               EVIDENCE VAULT        TIMELINE/ROKOVI
   (automatski,         (automatski,          (ručno — Rokovi forma,
   fire-and-forget      klasifikacija         ZPP lanac, Deadline
   posle uploada)       posle uploada)        Guardian nedostupan iz UI)
        |                    |                    |
        v                    x (nema veze)        x (nema veze)
   STRATEGY              EVIDENCE se ne         GENOME.rokovi_kriticni[]
   (isključivo ručan     povezuje sa            se nikad ne materijalizuje
   klik, 8 modula)       GENOME argumentima     u stvaran rok
```

## Po modulu: šta proizvodi, ko koristi, automatska veza, gde je prekid

### Smart Intake (`routers/smart_intake.py`, `shared/intake_documents.py`)

- **Proizvodi:** `intake_jobs`, `extracted_entities` (sa confidence po
  polju), `intake_review_queue`.
- **Ko koristi:** samo sopstveni review UI.
- **Automatska veza sa ostatkom sistema?** N/A za main granu — **ovaj
  modul nije live na main** (Trust Layer/chooser UI za njega je na
  `feature/new-predmet-chooser`, po Beta Freeze odluci). Stari 5-koračni
  wizard (`routers/intake.py`) je jedini live intake put.
- **Prekid:** cela ova grana čeka merge odluku, van obima ovog audita.

### Intake (stari, `routers/intake.py`) — JEDINI LIVE PUT

- **Proizvodi:** kreiran predmet (`predmeti` tabela), povezan klijent,
  opcioni prvi rok (ako je GPT prepoznao datum u opisu).
- **Ko koristi:** korisnik vidi kreiran predmet; nijedan drugi modul
  automatski ne reaguje.
- **Automatska veza?** **NE.** `POST /api/intake/kreiraj` ne emituje
  `PREDMET_KREIRAN` event i ne poziva `run_case_pipeline()` direktno.
- **Prekid:** ovo je najveći pojedinačni prekid u celom sistemu — postoji
  gotov, testiran `run_case_pipeline()` (7 koraka: analiza dokumenata →
  auto-linking → ekstrakcija rokova → kalendar → mini-strategija → HCC
  briefing → risk snapshot → copilot preporuka, `services/
  case_pipeline.py:644+`) koji se poziva SAMO za "kreiranje iz šablona"
  put (`routers/intake.py:768`) — standardni put ga nikad ne dodirne.

### Case Genome (`routers/case_dna.py`)

- **Proizvodi:** `case_dna` JSON kolonu, `_verifikacija`, `GenomeUpdated`
  event (JEDINI potpuno funkcionalan event u celom sistemu).
- **Ko koristi:** frontend prikaz; `audit_immutable` (preko
  `on_genome_updated` handlera); `proactive_alerts` ako je delta
  značajna.
- **Automatska veza sa Evidence/Strategy/Timeline?** **NE ni sa jednim.**
  Genome čita samo `predmet_dokumenti.tekst_sadrzaj` — nikad ne čita
  `predmet_dokazi` sadržaj (Evidence Vault), nikad ne poziva Strategy,
  `rokovi_kriticni[]` polje ostaje zarobljeno u JSON-u.
- **Prekid:** Genome je informatski ostrvo — najbogatiji AI modul u
  sistemu, ali njegovi zaključci ne pokreću ništa van sopstvenog prikaza.

### Evidence Vault (`routers/evidence.py`)

- **Proizvodi:** `tip_dokaza`, `pravni_elementi` po dokumentu;
  `predmet_dokazi` red po ključnoj činjenici (tvrdnja/kategorija/snaga/
  pravni_element/dokument_id).
- **Ko koristi:** sopstveni prikaz; Trust Layer "AI ograničenja" panel
  (broji redove, ne čita sadržaj).
- **Automatska veza?** **NE** sa Genome argumentima (`argumenti_za`/
  `argumenti_protiv`) — namerno, dokumentovano u `shared/genome_
  validator.py:15-21` kao svesno odložena odluka Faze 1.3, ne previd.
  **NE** sa Timeline (klasifikacija "sudska_odluka" ne trigeruje rok).
- **Prekid:** dva paralelna "izvora dokaza" (Genome-ov slobodan tekst i
  Evidence Vault-ova strukturirana tabela) koja se nikad ne ukrštaju —
  sistem nikad ne upozorava na "rupu" (tvrdnja bez dokaza).

### Strategy (`routers/strategija.py`)

- **Proizvodi:** slobodan tekst po modulu (8 modula + orkestrator).
- **Ko koristi:** samo korisnik, ručno.
- **Automatska veza?** **Potvrđeno NE, 0 nalaza** — ni upload dokumenta,
  ni Genome promena, ni Evidence klasifikacija nikad ne pokreću Strategy.
- **Prekid:** potpuno izolovan, čisto on-demand alat — ovo je jedini
  modul gde JE ovo verovatno ispravan dizajn (Strategy generiše
  argumentaciju, ne bi trebalo da se sama pokreće bez advokatove namere).

### Timeline/Rokovi (`routers/rocista.py`, `rokovi_lanac.py`, `zastarelost.py`, `predmeti_close.py`)

- **Proizvodi:** `predmet_hronologija` redove (13 različitih ulaznih
  tačaka u kodu, mešano ručno/automatski), ročišta, rok-lance.
- **Ko koristi:** frontend Rokovi pod-tab, `predmet_hronologija`
  agregacija.
- **Automatska veza?** Delimično — upload dokumenta AUTOMATSKI
  ekstrahuje **prošle** događaje pomenute u tekstu (`api.py:4181`,
  GPT-4o), ali **nijedan mehanizam ne kreira BUDUĆI rok automatski** iz
  klasifikacije dokumenta ili Genome podataka.
- **Prekid:** "Deadline Guardian" (`routers/zastarelost.py:354-447`) —
  skenira sve rokove u narednih 30 dana, generiše akcioni plan unazad od
  roka — **potpuno izgrađen, permission-gejtovan, nula UI referenci
  bilo gde** (`static/vindex.js`, `index.html`). Takođe: tabela `rokovi`
  se čita iz 7+ modula (`case_commander.py`, `decision_replay.py`,
  `integrations.py`, `morning_briefing.py`, `whatsapp_notif.py`,
  `zadaci.py`, `zastarelost.py`) ali **nijedan Python kod je ne piše**,
  niti postoji `CREATE TABLE rokovi` u migracijama — **treba proveriti
  živu bazu da se potvrdi da li je ova tabela ikad popunjena; kod sam ne
  pokazuje nijedan put kako bi to bilo moguće.**

### CRM/Klijenti (`klijenti/router.py`)

- **Proizvodi:** profil, komunikacioni dosije (ručan unos), audit log,
  conflict-of-interest proveru.
- **Ko koristi:** sopstveni prikaz, Timeline klijenta (agregira, ne
  generiše).
- **Automatska veza?** **NE** — komunikacija je eksplicitno "Faza 7 —
  Ručni unos komunikacije (bez auto-log sadržaja)"
  (`klijenti/router.py:934-940`, citat iz koda). Nema praćenja obaveza,
  nema automatskog statusa odnosa.
- **Prekid:** solidan CRM sistem (uključujući field-level enkripciju),
  ali potpuno pasivan — ništa se ne dešava bez ručnog unosa.

### Finance/Naplata (`routers/billing.py`)

- **Proizvodi:** tajmer sesije, fakture, email slanje faktura.
- **Ko koristi:** samo korisnik ručno.
- **Automatska veza?** **NE.** Nema cron/scheduled trigera za fakturu.
  **Promena Kanban statusa na "Završen" ne trigeruje NIŠTA** —
  `api.py:3187-3200`, `update_kanban_faza()` je čist single-column
  UPDATE, bez posledica.
- **Prekid:** finansijski tok potpuno odvojen od case lifecycle-a —
  zatvaranje predmeta i finalna faktura su dva nepovezana ručna koraka.

### Event sistem (`services/event_bus.py`) — centralni nalaz

12 definisanih `EventType` vrednosti. Status:

| Kategorija | Broj | Primeri |
|---|---|---|
| Potpuno funkcionalan (emituje se I ima handler koji radi) | **1** | `GenomeUpdated` |
| Emituje se, ALI nema handlera (no-op) | 3 | `DocumentJobEnqueued/Completed/Failed` |
| Ima izgrađen handler, ALI se nikad ne emituje | 3 | `PredmetKreiran`→pipeline, `RokKritican`→alerti, `HealthScorePromenjen`→upozorenje |
| Ni emituje se ni ima handler | 5 | `DokumentUploadovan`, `RokDodan`, `RocisteZakazano`, `StrategijaGenerisana`, `AnalizaZahtevana` |

**Od 12 event tipova, samo 1 stvarno radi end-to-end.** Ovo je
arhitektonski dokaz da je event-driven infrastruktura projektovana za
mnogo širu automatizaciju nego što je danas povezana — kod postoji,
konekcije ne postoje.

### Audit trail (`shared/audit_immutable.py`) — drugi centralni nalaz

24 akcije u `AUDITABLE_ACTIONS` allowlist-u. **Stvarno pozvano u
produkcijskom kodu: tačno 3** (`rate_limit_exceeded`, `suspicious_access`,
`genome_refresh`). Preostalih 21 — uključujući `predmet_create`,
`dokument_upload`, `klijent_create`, `login_success`/`login_failed`,
`data_export`, `gdpr_erasure` — **nikad se ne pozivaju**, uprkos
GDPR čl. 32 referenci u zaglavlju fajla i komentaru da su to "akcije
koje se UVEK beleže". Ovo nije samo operativni gap — ovo je
compliance/trust rizik ako se tvrdi da audit trail pokriva ono što ne
pokriva.

---

# FAZA 2 — Timeline Engine Audit

## 1. Kako se danas kreira rok?

Tri nezavisna, ručna puta: (a) direktan unos u Rokovi formi, (b) ZPP
"Lanac rokova" (izbor tipa akta + datum, deterministički izračun sa
pravnim osnovom), (c) `zastarelost.py` kalkulator (isti obrazac).
Nijedan se ne pokreće bez eksplicitnog korisničkog unosa.

## 2. Ko mora ručno da uradi?

Advokat mora ručno: izabrati tip procesnog akta, uneti tačan datum, i
(za redovne rokove) otvoriti formu i sam upisati naziv/datum roka.
Sistem ne predlaže da rok treba da postoji — samo izračunava POSLE što
mu je rečeno da izračuna.

## 3. Koji događaji iz predmeta postoje?

Upload dokumenta (GPT ekstrahuje POMENUTE datume/događaje u tekstu —
prošle, ne buduće), ročište (ručna forma + follow-up sa rule-based
preporukama), promena Kanban statusa (inertna), zatvaranje predmeta
(`predmeti_close.py`, stvaran endpoint sa strukturisanim ishodom).

## 4. Koji događaji MOGU automatski generisati rok — a danas ne generišu?

- Klasifikacija dokumenta kao "sudska_odluka" (Evidence Vault) → trebalo
  bi da predloži "rok za žalbu" kalkulaciju. Danas: nula veze.
- Genome ekstrahovan `rokovi_kriticni[]` → trebalo bi da postane
  stvaran rok u sistemu. Danas: ostaje zarobljen u JSON-u.
- `PREDMET_KREIRAN` event → trebalo bi da pokrene `run_case_pipeline()`
  (koji VEĆ ekstrahuje rokove automatski, `case_pipeline.py:287-295`) za
  SVAKI predmet, ne samo "iz šablona". Danas: event se nikad ne emituje.

## Tabela

| Događaj | Danas | Trebalo bi | Prioritet |
|---|---|---|---|
| Kreiran predmet (standardni wizard) | Ništa automatski | Pokrene `run_case_pipeline()` (već postoji) | **P0** |
| Klasifikovana sudska odluka | Ništa | Predlog kalkulacije roka za žalbu | P1 |
| Genome `rokovi_kriticni[]` popunjen | Ostaje u JSON-u | Materijalizuje se u stvaran rok | P1 |
| Rok se približava (30 dana) | Ništa (Guardian postoji, nedostupan) | Proaktivno upozorenje | **P0** (kod već postoji) |
| Zakazano ročište | Samo Genome refresh | Podsetnik + priprema checklist | P2 |
| Upload dokumenta sa eksplicitnim datumom u tekstu | Upisano u hronologiju (prošli događaji) | Radi ispravno, samo za prošle datume | Nije prioritet — radi |
| Zatvaranje predmeta | Ručan endpoint, radi ispravno | Radi | Nije prioritet — radi |

---

# FAZA 3 — "Autonomni predmet" audit

**Pitanje: "Ako advokat ubaci kompletan predmet, šta sistem danas sam
uradi, a šta još čeka čoveka?"**

## Dokumenti

- Klasifikuje? **DA**, automatski (Evidence Vault posle uploada).
- Povezuje dokument sa predmetom? **DA**, automatski (upload je već u
  kontekstu predmeta).
- Izvlači ključne činjenice? **DA**, automatski (Evidence Vault +
  Genome, dva odvojena izvora, ne ukrštena).
- Predlaže sledeću akciju? **DELIMIČNO** — Genome ima "Preporučeni
  sledeći koraci" (frontend sinteza), ali to je jedan od **4 nezavisna,
  nepovezana "next step" sistema** u celom kodu (videti Deo "Sledeći
  koraci" ispod) — nijedan ne zna za ostala tri.

## Klijenti

- Povezuje komunikaciju? **NE** — eksplicitno ručan unos, dokumentovano
  u samom kodu kao takvo.
- Prati obaveze? **NE** — ne postoji koncept u kodu.
- Zna status odnosa? **NE** — statičko polje, ne izvedeno iz aktivnosti.

## Timeline

- Kreira događaje? **DELIMIČNO** — prošle datume iz teksta da, buduće
  rokove ne.
- Računa rokove? **DA, ali samo kad se ručno pokrene.**
- Upozorava? **Kod postoji (Deadline Guardian), nedostupan iz UI-ja —
  efektivno NE.**

## Strategy

- Reaguje na novi dokaz? **NE**, potvrđeno 0 nalaza.
- Menja procenu? **NE.**
- Predlaže novu strategiju? **NE** — čeka eksplicitan klik uvek.

## Evidence

- Povezuje tvrdnju sa dokazom? **NE**, namerno odloženo (dokumentovano
  u kodu kao svesna odluka, ne previd).
- Upozorava na rupe? **NE**, ne postoji nijedna takva provera.

## Finance

- Prati troškove? **Samo ako korisnik ručno pokrene tajmer za taj
  konkretan predmet.**
- Generiše naplatu? **NE**, uvek ručan klik.
- Prati status? **DA** unutar sopstvenog modula, ali nepovezano sa
  statusom samog predmeta (zatvaranje predmeta ne trigeruje finalnu
  fakturu).

---

# FAZA 4 — Rupe u operativnom toku

### Naziv: Case Pipeline se ne pokreće za standardni put kreiranja predmeta

- **Problem:** kompletan, testiran, 7-koračni automatski pipeline
  postoji i radi — samo za "kreiranje iz šablona", ne za jedini live
  put na main grani.
- **Trenutno ponašanje:** advokat kreira predmet kroz standardni
  wizard, ništa se automatski ne dešava posle toga (osim Genome
  regeneracije posle prvog uploada).
- **Idealno ponašanje:** svaki novi predmet, bez obzira na put kreiranja,
  pokreće isti pipeline — ekstrakcija rokova, kalendar, risk snapshot,
  preporuka.
- **Rizik za poverenje:** VISOK — ovo je tačno mesto gde proizvod
  obećava "AI vodi predmet" a stvarno ponašanje je "advokat mora znati
  da postoji poseban 'iz šablona' put da bi dobio automatizaciju".
- **Procena težine:** **P0** — direktno narušava obećanje proizvoda, I
  rešenje je jeftino (kod već postoji, treba samo emitovati event ili
  direktno pozvati funkciju).

### Naziv: Deadline Guardian potpuno nedostupan

- **Problem:** izgrađena funkcionalnost (skeniranje rokova + akcioni
  plan unazad od roka) nema nijednu UI vezu.
- **Trenutno ponašanje:** funkcija postoji na backend-u, endpoint radi,
  niko je nikad ne pozove jer ne postoji dugme/ekran.
- **Idealno ponašanje:** vidljiv panel (npr. na dashboard-u ili u
  Rokovi pod-tabu) koji prikazuje rezultat `guardian_scan`.
- **Rizik za poverenje:** VISOK — ako korisnik ikad sazna da ova
  funkcija postoji ali je nikad nije video, to je isti "obećava a ne
  isporučuje" problem koji je Trust Layer runda upravo pokušala da
  reši na drugom mestu.
- **Procena težine:** **P0** — kod već postoji, ovo je čisto UI
  povezivanje.

### Naziv: Audit trail pokriva 3 od 24 obećane akcije

- **Problem:** dokumentovan kao GDPR-relevantan mehanizam koji "uvek
  beleži" ključne akcije — stvarno beleži samo 2 bezbednosna događaja i
  Genome refresh.
- **Trenutno ponašanje:** kreiranje/brisanje predmeta, upload
  dokumenta, kreiranje/brisanje klijenta, login/logout — ništa od ovoga
  ne ostavlja trag.
- **Idealno ponašanje:** svaka akcija iz allowlist-e stvarno poziva
  `log_action()`.
- **Rizik za poverenje:** **KRITIČAN, ne samo UX** — ovo je
  compliance/pravni rizik ako se bilo kome (klijentu, regulatoru)
  tvrdi da sistem ima kompletan audit trag.
- **Procena težine:** **P0**.

### Naziv: Genome `rokovi_kriticni[]` se nikad ne materijalizuje

- **Problem:** AI ekstrahuje kritične rokove iz dokumenata, podatak
  ostaje zarobljen u JSON koloni.
- **Trenutno ponašanje:** vidljivo samo unutar Genome prikaza, ne
  postaje deo redovne Rokovi liste.
- **Idealno ponašanje:** materijalizuje se u stvaran, actionable rok.
- **Rizik za poverenje:** SREDNJI — korisnik koji vidi rok u Genome-u
  ali ga ne nađe u Rokovi tabu može pomisliti da je duplirati ručno,
  ili propustiti ga.
- **Procena težine:** **P1**.

### Naziv: Evidence tvrdnja↔dokaz veza i dalje odsutna

- **Problem:** dva paralelna sistema dokaza, nikad ukrštena, nema
  upozorenja na rupe.
- **Trenutno ponašanje:** kao opisano.
- **Idealno ponašanje:** provera da li svaka Genome tvrdnja ima
  odgovarajući `predmet_dokazi` red.
- **Rizik za poverenje:** SREDNJI — ali ovo je NAMERNO odloženo
  (dokumentovano u kodu kao svesna Faza 1.3 odluka, "visok rizik lažnih
  pozitiva"), ne previd. Ne tretirati kao hitno bez ponovnog razmatranja
  te odluke.
- **Procena težine:** **P1**, uz eksplicitnu napomenu da je odlaganje
  bilo namerno.

### Naziv: Kanban "Završen" ne trigeruje ništa

- **Problem:** status promena je potpuno inertna — nema finalne
  fakture, arhiviranja, notifikacije.
- **Trenutno ponašanje:** čist database UPDATE jedne kolone.
- **Idealno ponašanje:** bar opciona finalna faktura/checklist na
  zatvaranju.
- **Rizik za poverenje:** NIZAK-SREDNJI — nije obećano eksplicitno da
  se ovo dešava, pa je manje "pokidano obećanje" nego propuštena
  prilika.
- **Procena težine:** **P2**.

### Naziv: 4 nezavisna "sledeći koraci" sistema

- **Problem:** Genome sinteza, `matter_intel.py` rule-based, `case_
  intelligence.py` GPT-briefing, `workflow.py` template-koraci — nijedan
  ne zna za ostale.
- **Trenutno ponašanje:** korisnik može dobiti različite "sledeći
  korak" preporuke na različitim ekranima, bez objašnjenja zašto se
  razlikuju.
- **Idealno ponašanje:** jedan objedinjen prikaz, ili bar jasno
  razdvajanje "ovo je opšta preporuka" vs. "ovo je workflow checklist
  korak".
- **Rizik za poverenje:** SREDNJI — konfuzija, ne netačnost.
- **Procena težine:** **P2**.

### Naziv: `rokovi` tabela — moguć fantom izvor

- **Problem:** 7+ modula je čita, nijedan je ne piše u kodu, nema
  CREATE TABLE migracije nađene.
- **Trenutno ponašanje:** NEPOZNATO bez provere žive baze — možda je
  tabela prazna otkad postoji, možda postoji neki drugi put upisa
  (SQL trigger, ručni insert, migracija koja nije nađena u ovom
  pretraživanju).
- **Idealno ponašanje:** ili potvrditi da radi (i naći KAKO se puni),
  ili je ukloniti/zameniti realnim izvorom.
- **Rizik za poverenje:** NEPOZNAT dok se ne proveri — mogao bi biti
  visok ako 7 modula tiho vraća prazne rezultate.
- **Procena težine:** **P1, hitno ZA PROVERU** (ne za popravku dok se
  ne potvrdi da je problem stvaran).

---

# FAZA 5 — Dizajn budućeg autonomnog toka

**Ključna poenta pre predloga: većina ovoga već postoji u kodu.** Ovo
nije predlog nove arhitekture — ovo je predlog POVEZIVANJA postojeće.

```
Dokument stigne
       ↓
Smart Intake / Upload razume dokument (VEĆ RADI — Evidence Vault + Genome)
       ↓
[NOVO: emitovati postojeći event, ne graditi novi]
PREDMET_KREIRAN ili DOKUMENT_UPLOADOVAN se STVARNO emituje
       ↓
Automatski (kroz VEĆ POSTOJEĆE handlere i pipeline):
  - run_case_pipeline() se pokreće za SVAKI predmet, ne samo šablon (VEĆ POSTOJI)
  - Genome se osvežava (VEĆ RADI)
  - Deadline Guardian scan se pokreće i rezultat postaje vidljiv (BACKEND VEĆ POSTOJI, treba UI)
  - rokovi_kriticni[] iz Genome-a se upisuje kao stvaran rok (MALA NOVA VEZA)
  - proactive_alerts se kreira ako je nešto hitno (VEĆ POSTOJI mehanizam)

Advokat dobija:
  "Dogodilo se X (novi dokument klasifikovan kao presuda).
   Rizik je Y (Genome najslabija tačka, nepromenjeno).
   Rok je Z (Deadline Guardian, sada VIDLJIV).
   Predlažemo A (jedan od 4 postojeća 'sledeći korak' sistema, konsolidovano)."
```

**Šta ovaj dizajn NAMERNO ne uključuje:** automatsko pokretanje Strategy
modula (ostaje ručno, ispravna granica — Strategy generiše
argumentaciju koja treba advokatovu nameru, ne treba da se sama pokrene),
automatsko slanje bilo čega van sistema, automatsko generisanje fakture
bez pregleda.

---

# FAZA 6 — Implementacioni plan (bez koda)

## 1. Minimalna verzija automatskih rokova

Emitovati `PREDMET_KREIRAN` iz `POST /api/intake/kreiraj` (jedini live
put) — handler (`on_predmet_kreiran`) već postoji i već poziva
`run_case_pipeline()`, koji već ekstrahuje rokove. Ovo je JEDNA izmena
(dodati emit poziv na kraju postojeće funkcije) koja aktivira lanac
funkcionalnosti koji već postoji i čeka.

## 2. Potrebne backend promene

- Dodati `emit(EventType.PREDMET_KREIRAN, ...)` (ili direktan outbox
  insert, isti obrazac kao `_emit_genome_event`) u `routers/intake.py`
  posle uspešnog kreiranja predmeta.
- Proveriti da `run_case_pipeline()` bezbedno radi i za predmete BEZ
  dokumenata (standardni wizard ih ne zahteva) — ako pipeline pretpostavlja
  dokumenta, dodati graceful skip.
- Materijalizacija `rokovi_kriticni[]` — nova mala funkcija (isti obrazac
  kao `_compute_analiza_osnov`) koja upisuje Genome-ove kritične rokove
  u `predmet_hronologija` ili odgovarajuću rok-tabelu, sa deduplikacijom
  (da se ne dupliraju pri svakoj Genome regeneraciji).
- Potvrditi (upitom na živu bazu, ne kodom) da li `rokovi` tabela ima
  ikad upisan red — ako ne, odlučiti da li 7 modula koja je čitaju
  treba preusmeriti na `predmet_hronologija` ili je tabela stvarno
  potrebna i treba joj writer.
- Popuniti bar "core" audit akcije (`predmet_create`, `dokument_upload`,
  `klijent_create`, `login_success/failed`) sa stvarnim `log_action()`
  pozivima — ovo je compliance pitanje, ne UX.

## 3. Potrebne frontend promene

- Dodati UI panel za Deadline Guardian rezultat (`guardian_scan`) —
  minimalno, lista na Rokovi pod-tabu ili dashboard-u.
- Rok materijalizovan iz Genome-a treba vizuelno da bude jasno označen
  odakle dolazi (isti "Osnov:" obrazac kao Trust Layer runda).

## 4. Potrebne migracije

- Zavisi od odgovora na `rokovi` tabelu pitanje (Deo 2) — ili nova
  migracija koja je kreira ispravno, ili ništa ako se preusmeri na
  postojeću `predmet_hronologija`.

## 5. Rizici

- `run_case_pipeline()` pozvan za SVAKI predmet (ne samo šablon) menja
  operativni profil — više GPT poziva, više troška po predmetu. Meriti
  pre šireg puštanja.
- Materijalizacija rokova iz Genome-a nosi isti rizik kao P1.3 iz Trust
  Layer runde (izmišljanje ako Genome pogrešno ekstrahuje datum) — mora
  imati isto "bolje bez izvora nego lažan izvor" pravilo.
- Emitovanje `PREDMET_KREIRAN` retroaktivno NE utiče na već postojeće
  predmete — samo nove. Ne očekivati da stari predmeti dobiju
  pipeline retroaktivno bez posebne odluke o tome.

## 6. Test strategija

Isti obrazac kao Faza 1.3 Genome Verification Layer: regresioni skup
sintetičkih predmeta (već postoje, `genome_synthetic_cases.py`), meriti
pre/posle da li se pipeline korektno pokreće, da li se rokovi tačno
materijalizuju, da li audit log stvarno hvata akcije — sve pre/posle
merljivo, Rule C disciplina.

## 7. Šta NE treba graditi

- **Nijedan nov AI agent, nijedan nov event tip** — 12 već postoji,
  11 čeka da se poveže ili gasi.
- **Ne graditi nov case pipeline** — `services/case_pipeline.py` već
  postoji i radi, samo nije pozvan sa pravog mesta.
- **Ne graditi nov Deadline sistem** — `zastarelost.py` Guardian već
  postoji, treba mu samo UI.
- **Ne graditi automatsko pokretanje Strategy-a** — namerno van obima,
  ispravna granica.
- **Ne graditi novu arhitekturu za Evidence↔Genome povezivanje** — ta
  odluka je već svesno odložena u Fazi 1.3, ne otvarati je impulsivno
  sada bez ponovnog razmatranja rizika koji je već identifikovan.

---

# Brutalna, kod-zasnovana ocena

**"Da li je Vindex AI danas operativni sistem za predmete ili
kolekcija inteligentnih alata?"**

**Danas: kolekcija inteligentnih alata koja se PONAŠA kao kolekcija
alata, iako ima kod jednog operativnog sistema ispod površine.**

Ovo nije ista stvar kao "nikad nije ni pokušano da postane operativni
sistem." Dokaz je suprotan: event bus sa 12 tipova, kompletan case
pipeline sa 7 koraka, deadline skener sa akcionim planovima, audit
framework sa 24-akcijskim allowlist-om — sve ovo je arhitektura NEKOGA
KO JE POKUŠAO da izgradi operativni sistem. Ali svaki od ovih pokušaja
je ili nikad povezan sa jedinim putem kojim korisnik stvarno prolazi,
ili povezan samo za sporedan put (šablon-kreiranje) koji retko ko koristi.

Rezultat: advokat koji koristi Vindex AI danas doživljava isto iskustvo
kao da je proizvod nikad ni pokušao automatizaciju — otvara predmet,
ručno pokreće svaki alat, ručno prati rokove, ručno povezuje dokaze sa
tvrdnjama. Razlika između "kolekcija alata" i "operativni sistem" nije
u tome koliko je AI-a napisano — nego u tome da li se ti delovi
međusobno obaveštavaju bez traženja. Po toj definiciji, odgovor danas
je jasan: **ne, još nije operativni sistem — ali je bliže tome nego što
izgleda, jer najskuplji deo posla (izgradnja same automatizacije) je
već urađen. Ono što nedostaje nije inteligencija. Nedostaje ožičenje.**
