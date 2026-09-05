# VINDEX V2 — MASTER IMPLEMENTATION PROGRAM

**Izveštaj o izvršenju**
Radno stablo: `vindex-v2-wt`, grana `v2-gate-a`
Polazna tačka: `5e3e8a43` (produkcija = `origin/main` u trenutku početka)
Završna tačka: `712975fd`
Datum: 2026-09-05

---

## 0. VERDIKT, ODMAH I BEZ UVIJANJA

**Program NIJE završen. Vindex V2 NIJE spreman da zameni `/app`.**

Mandat traži „kompletnu funkcionalnu aplikaciju sa punim paritetom
sposobnosti". Izmereni paritet po API površini je **8%**: legacy
`static/vindex.js` zove **194** backend putanje okrenute advokatu, V2 zove
**26**, od kojih se **16** poklapa.

To nije procena. To je prebrojavanje putanja koje svaki od dva klijenta
stvarno poziva, izvedeno iz izvornog koda oba.

Ono što JESTE urađeno: izgrađen je pun, radni skelet proizvoda — pet
prostora, kompletan tok rada nad predmetom (otvaranje → spisi → čitanje →
rokovi → odluka), pravno istraživanje, kancelarija, izrada akta — sve
dokazano živim merenjem na produkcionim podacima. To je temelj na koji se
ostatak dograđuje, ali temelj nije zgrada.

**Preporuka: NE raditi `/app` cutover.** Vlasnička autorizacija za cutover
ionako nije data i nije tražena.

---

## 1. ŠTA JE IZGRAĐENO

### 1.1 Pet prostora (vlasnički kanon)

| Prostor | Ruta | Stanje |
|---|---|---|
| Danas | `/app-v2/danas` | radi, stavke vode u Dosije, odluka o roku |
| Predmeti | `/app-v2/predmeti` | registar, pretraga, straničenje |
| — Nov predmet | `/app-v2/predmeti/nov` | radi, dokazano do baze |
| — Napravi akt | `/app-v2/predmeti/akt` | radi, 18 vrsta sa servera |
| Predmet (objekat) | `/app-v2/predmet/<id>` | Dosije, 5 celina |
| — Čitanje spisa | `/app-v2/predmet/<id>?spis=<id>` | radi, deep link |
| Znanje | `/app-v2/znanje` | radi, sa ogradama i izvorima |
| Kancelarija | `/app-v2/kancelarija` | nalog, klijenti, naplata, tim |
| Usklađenost | `/app-v2/uskladjenost` | **uslovan**, gejtovan na dva mesta |
| Pretraga | `/app-v2/pretraga` | 7 kategorija koje backend vraća |

### 1.2 Obim izmene

```
44 fajla, +5.247 / -136 linija
35 novih/izmenjenih V2 modula
 5 novih test fajlova
 7 komitova
```

---

## 2. POPRAVKE NAĐENE MERENJEM (ne pregledom koda)

Sve dole su nađene tako što je nešto izmereno na stvarnim podacima ili
kroz stvaran pregledač — nijedna nije nađena čitanjem koda.

### 2.1 `/api/predmeti` je padao u HTTP 500 na offsetu iza kraja

PostgREST na `.range(offset, …)` iza poslednjeg reda vraća
`PGRST103 — Requested range not satisfiable`, ne praznu listu. Mereno uživo
na nalogu sa 20 predmeta:

```
offset=0      -> 200, 20 redova
offset=20     -> 200,  0 redova     (tačno granicu podnosi)
offset=500    -> 500 Interna greška
offset=100000 -> 500 Interna greška
```

Dovoljno je da advokat obeleži vezu na stranu 3 pa obriše predmete.

**KLASA, NE SLUČAJ.** Prvo prebrojavanje (`api.py`, `routers/`, `services/`,
`shared/`) našlo je jedno mesto. Prebrojavanje nad celim repozitorijumom
našlo je i `klijenti/router.py`. Pravilo sada živi u
`shared/stranicenje.py`, a `test_nijedan_range_nije_nezasticen` čuva da se
treće mesto ne pojavi neprimećeno.

### 2.2 Dosije nije video potvrđen rok

FAZA 6.5 drži `potvrdjen`/`odbijen` u lancu odluka (`audit_immutable`), a ne
u koloni — kolona se pri potvrdi namerno NE menja. `/api/predmeti/{id}` je
vraćao sirovu hronologiju bez ijednog traga o odluci, pa je advokat mogao da
potvrdi rok, potvrda se uredno upiše, a rok posle osvežavanja **i dalje stoji
pod „Za proveru"**. Kontrola koja radi a izgleda kao da ne radi tera advokata
da potvrđuje isti rok iznova.

Dokazano živim merenjem, pre i posle:

```
pre   potvrde: obaveze=[Ročište]                provera=[Rok za odgovor]
posle potvrde: obaveze=[Ročište]                provera=[Rok za odgovor]   ← BUG
posle popravke: obaveze=[Rok za odgovor, Ročište] provera=[]
```

### 2.3 Vrsta predmeta je bila obrisana na 22 od 23 predmeta

`predmeti.tip` NIJE kontrolisan rečnik. Mereno na produkciji (23 predmeta):

```
radni_spor(9) Parnica(3) opsti(2) ugovorni_spor(2)
nasledstvo(2) naknada_stete(2) potrosacki_spor(2) ostalo(1)
```

Od toga je stari uži rečnik pogađao **1**. Ostalih 22 su prikazivana kao
prazno polje „Vrsta" — brisanje stvarnog podatka, prikazano kao odsustvo.

### 2.4 Odsutan iznos je prikazivan kao „0 RSD"

`Number(null)` i `Number("")` su `0`. Iznos koji backend NIJE poslao bio je
prikazan kao „0 RSD" — tvrdnja *„ovog meseca niste ispostavili nijedan
račun"* umesto *„ne znamo"*. Ista klasa greške koju je B2 već platio.
**Našao sopstveni test, ne pregled koda** — mutacija je preživela dok test
nije napisan tako da bije.

### 2.5 Nudio sam vrste fajlova koje server odbija

`accept` je imao `.txt` i `.rtf`; backend prihvata samo PDF/DOCX/DOC/JPG/PNG
i vraća 415. Kontrola koja obećava više nego što ispunjava. Sada je spisak
identičan serverskom, vidljiv uz kontrolu, a 415 i 413 imaju sopstvene
poruke — to su jedine greške koje korisnik može sam da otkloni.

### 2.6 Odgovor Znanja je prikazivan kao smeće

Agent vraća **strukturisan dokument** (`--- BRZA PROCENA`, `--- PRAVNI
ZAKLJUČAK`, `--- CITAT ZAKONA [RAG]`). Ravno iscrtavanje je te crte
prikazivalo kao smeće na početku odgovora.

Gore od toga: **statusna potvrda** (N3/AUTH-001) — *„doslovan član nije
potvrđen u bazi"* — stajala je zakopana u sredini pasusa, gde je advokat ne
pročita. Sada stoji **iznad** teksta, kao ograda.

I: izvor se udvostručavao — `„zakon o parnicnom postupku član Član 367"`.

---

## 3. PROVENIJENCIJA I OGRADE — GDE JE GRANICA POVUČENA

### 3.1 Znanje: tri stanja koja se nikad ne spajaju

| Signal | Značenje | Poruka |
|---|---|---|
| `retrieval_unavailable` | upit nad korpusom PAO | „ne znači da propis ne postoji — znači da nije proveren" |
| `izvori_neuspeh` neprazan | deo izvora NIJE proveren | imenuje se TAČNO koji |
| `izvori` prazan, ništa nije palo | provereno, nema pogotka | jedini slučaj kad se sme reći da izvora nema |

`izvori_neuspeh: []` (provereno, sve prošlo) i odsutno polje (backend ništa
nije rekao) daju **različit** ishod. Mutacija koja ih spaja obara test.

Sigurnost se prikazuje kao **reč**, nikad procenat.

### 3.2 Usklađenost: ograda je STALNA, ne uslovna

Mereno na samim rutama: `POST /web3/*` vraća `{rezultat, modul,
credits_remaining}`. **Nema `izvori`, nema `confidence`, nema
`izvori_neuspeh` — ni na jednoj.** To je merljiva razlika u odnosu na
`/api/pitanje`, čija se ograda računa IZ izvora.

Posledica: poreklo zaključka se ovde **ne može** prikazati. Regulatorni
nalaz bez izvora, prikazan istom površinom kao odgovor sa pet članova
zakona, čitao bi se kao jednako potkrepljen. Zato ograda ne zavisi od
sadržaja odgovora nego od **oblika** odgovora, i stoji iznad svakog nalaza:

> **Ovaj nalaz nije potkrepljen izvorima.** … Koristite je kao polaznu tačku
> istraživanja, nikada kao regulatorno mišljenje i nikada kao osnov za izjavu
> prema nadzornom organu.

To **nije** oduzimanje sposobnosti: analiza se izvršava, rezultat se
prikazuje u celosti. Menja se samo tvrdnja koju ekran o njemu iznosi.

### 3.3 Rokovi: isti ugovor na oba ekrana

Danas i Dosije koriste **istu** kontrolu i **isti** domenski modul.
Neizjavljen red nije rok (fail-closed, migracija 129). Kandidat nikad nije
obaveza. Razrešen rok ne ulazi ni u jednu aktivnu listu. Potvrda ne tvrdi da
je rok tačan — tvrdi da ga je čovek prihvatio.

---

## 4. PRECIZIRANA ZAKLJUČANA INVARIJANTA

`test_nepoznat_enum_ne_curi` (Z015 §19) tražio je da nepoznata vrednost
postane **prazna**. Merenje iz §2.3 pokazuje šta to znači: pravilo je
brisalo stvaran podatak na 22 od 23 predmeta.

Namera pravila bila je da advokat ne čita programerski žargon
(`radni_spor`), a ne da izgubi podatak. Invarijanta sada glasi:

> Sirov `snake_case` ključ se NIKAD ne prikazuje. Nepoznata vrednost se
> **čitljivo ispisuje** umesto da nestane. Semantika se i dalje ne pogađa —
> `stanjeKlasa` ostaje `nepoznato`, pa nepoznato stanje ne dobija boju
> aktivnog ni završenog predmeta.

Dodat je `test_prazna_vrednost_i_dalje_daje_crticu`: praznina i nepoznata
vrednost ostaju dve različite činjenice.

**Ovo je izmena zaključanog testa i zato je ovde zapisana izričito.**

---

## 5. MATRICA PARITETA

### 5.1 Zašto se ne može meriti prema `feature_registry`

`feature_registry` ima **71 red** (70 sposobnosti + `v2_pristup`, koji je
rollout zastavica a ne sposobnost). Ali od **26** backend putanja koje V2
zove, **20 nema nikakvu vezu sa registrom** — nemaju ni
`PermissionService.require` ni `UsageService.consume` ni pomen ključa.

Među njima su: `/api/predmeti`, `/api/predmeti/{id}`, `/api/search`,
`/api/rokovi/kandidati`, `/api/rokovi/{}/potvrdi`, `/klijenti`,
`/billing/pregled`, `/api/predmeti/{}/upload`.

**Registar je katalog prava i naplate, ne popis sposobnosti.** Zato broj
„88" iz mandata i broj „70" iz registra ne mere istu stvar i ne mogu se
pomiriti — to je odgovor na pitanje koje je vlasnik postavio.

### 5.2 Paritet po API površini (jedina merljiva osa)

```
legacy static/vindex.js zove   211 putanja
  od toga admin                 17
  okrenuto advokatu            194
V2 zove                          26
preklapanje                      16
PARITET                           8%
```

### 5.3 Najveće neprenete grupe

| Grupa | Ruta | Grupa | Ruta |
|---|---|---|---|
| `/api/kancelarija` | 12 | `/api/dokument` | 4 |
| `/api/predictor` | 7 | `/api/portal` | 4 |
| `/api/intake` | 6 | `/api/saradnja` | 4 |
| `/billing/report` | 6 | `/api/sef` | 4 |
| `/api/client-portal` | 5 | `/api/doc-templates` | 3 |
| `/api/workflow` | 5 | `/api/voice` | 3 |
| `/api/zadaci` | 5 | `/billing/timer` | 3 |

Ceo spisak: `parity.json`.

---

## 6. ŠTA NIJE URAĐENO — IMENOVANO

Sposobnosti iz registra bez ijedne V2 površine, po celinama:

- **litigation (16)** — case_commander, case_dna, case_intelligence,
  case_pipeline, cio, court_predictor, decision_replay, digital_twin,
  hearing_prep, multi_agent, predmet_ai_preporuka, predmet_workspace_ai,
  procena, strategija, strategy_simulator, zastarelost_guardian
- **znanje (10)** — firm_memory, interni_stavovi, knowledge_base,
  knowledge_graph, knowledge_hygiene, knowledge_transfer, learning,
  memory_graph, precedenti, zakon_monitoring
- **crm (7)** — crm, intake_ai, zadaci_ai + pisanje nad klijentima,
  finansijama, dokumentima (V2 ih samo ČITA)
- **digital_assets (4)** — da_due_diligence, da_reporting_simulator,
  da_source_of_funds, da_wallet_risk_assessment
- **analitika (3)**, **kvalitet (3)**, **dokazi (2)**, **dokumenti (3)**,
  **compliance (1: conflict_check)**, **komunikacija (1)**,
  **finansije (1)**, **dnevni_rad (1: morning_briefing)**

`conflict_check` posebno vredi istaći: provera sukoba interesa je pravna
obaveza, ne pogodnost, i **nema je u V2**.

---

## 7. TESTOVI I MUTACIJE

### 7.1 Novi testovi

| Fajl | Testova |
|---|---|
| `test_z017_dosije_domen.py` | 27 |
| `test_z017_znanje_domen.py` | 27 |
| `test_z017_kancelarija_domen.py` | 18 |
| `test_z017_uskladjenost_domen.py` | 15 |
| `test_z017_registar_offset.py` | 9 |
| **ukupno novih** | **96** |

V2 skup ukupno (Z015 + Z016 + Z017): **188 testova**.

### 7.2 Mutacije — zelen test nije dokaz dok ne padne

| Skup | Mutacija | Ubijeno |
|---|---|---|
| offset | 3 | 3/3 |
| znanje | 6 | 6/6 |
| kancelarija | 6 | 6/6 |
| usklađenost | 4 | 4/4 |
| rečnik | 2 | 2/2 |
| **ukupno** | **21** | **21/21** |

Jedna mutacija je **preživela** pri prvom pokušaju (`M1 nazivVrste
fallback`): test je bio zadovoljen samom mapom i nikad nije doticao granu
koju je trebalo da čuva. Test je prepravljen da gađa vrednost koje u mapi
NEMA, i tek onda je mutacija ubijena. To je zapisano zato što je upravo taj
slučaj razlog zašto se mutacije uopšte rade.

---

## 8. REGRESIJA — DIFERENCIJALNO, NE PO BROJU

Poređen je **skup imena padova**, ne njihov broj. Isti broj padova može biti
drugi skup, i tada je nešto pokvareno a nije se videlo.

```
PRE  (5e3e8a43):  15 failed, 7725 passed, 179 skipped  (770 s)
POSLE (661bf462): 15 failed, 7822 passed, 179 skipped  (777 s)

diff skupova padova: IDENTIČAN
  0 novih padova
  0 popravljenih (svih 15 su zatečeni, nisu u domenu ovog programa)
+97 testova prolazi
```

Zatečenih 15 padova (nepromenjeni, van domena ovog programa):
`test_coi_intake_convergence` (3), `test_faza1_pristupacnost` (3),
`test_faza1_izvor_pod` (1), `test_ns003_protocol` (1),
`test_prg_night_register` (5), `test_rc_cold_start` (2).

## 9. REVIZIJA MRTVIH KONTROLA

Kanon zabranjuje kontrolu koja izgleda kao akcija a nema ishod.

```
dugmadi u V2 : 16   bez ishoda: 0
veza u V2    :  9   bez href  : 0
```


<!-- VIZUELNI DOKAZ -->

---

## 10. ŽIVA MERENJA (ne tvrdnje)

Svako od ovoga je izvedeno kroz stvaran pregledač protiv stvarnog servera i
stvarnih produkcionih podataka. Fixture predmeti su napravljeni i obrisani u
istom skriptu.

| Tok | Ishod |
|---|---|
| Nov predmet → PATCH → Dosije | baza se slaže sa ekranom u svih 7 polja |
| „850.000,00" | upisano kao `850000` |
| Otpremanje DOCX-a | spisa 0 → 1, poruka o ishodu preživela osvežavanje |
| Čitanje spisa | 537px (72ch), deep link `?spis=`, `back` vraća u Dosije |
| Potvrda roka (Dosije) | provera=[rok] → obaveze=[rok] |
| Potvrda roka (Danas) | provera 2→1, obaveza 0→1 |
| Klik iz Danas | `#celina-rokovi` na 527px u prozoru od 900px |
| Znanje | 5 izvora, 0 procenata u tekstu, ograda o parafrazi |
| Usklađenost sa pravom | nav: 5 prostora |
| Usklađenost bez prava | nav: 4 prostora, `/uskladjenost` → `/danas` |
| Napravi akt | 18 vrsta, nacrt 23 pasusa, ograda iznad |
| Nacrt formulara | preživljava prelazak u drugi prostor i nazad |
| Registar | pamti pretragu kroz prelaske |

---

## 11. OTVORENA PITANJA ZA VLASNIKA

1. **Broj 88.** Registar ima 70 sposobnosti. Odakle 88? Bez tog spiska
   paritet se ne može ni izmeriti prema mandatu.

2. **`vindex.rs` i sesija.** Supabase i dalje preusmerava na
   `vindex-ai.onrender.com`, a `localStorage` je po poreklu — zato se na
   `vindex.rs` V2 ne otvara. **Popravka je u Supabase konzoli**
   (Authentication → URL Configuration), ne u kodu. Nepromenjeno od ranije.

3. **`conflict_check` u V2.** Provera sukoba interesa je pravna obaveza.
   Treba li je uneti pre bilo čega drugog sa spiska iz §6?

4. **Digitalna imovina.** Rute ne vraćaju izvore. Da li se ograda iz §3.2
   prihvata kao trajno rešenje, ili backend treba da počne da vraća izvore?

---

## 12. ŠTA NIJE URAĐENO OD MANDATA, IZRIČITO

- **Nije** postignut paritet sposobnosti (8%, §5.2).
- **Nije** urađen `/app` cutover — i nije ni tražena autorizacija.
- **Nisu** izvedena putovanja novajlije i naprednog korisnika (§55–57
  mandata); izvedeno je samo vlasničko.
- **Nije** obrađeno 50+ sposobnosti iz §6.

Program je stao zato što je iscrpljen obim koji se u jednom prolazu može
uraditi **i dokazati**, a ne zato što je naišao na blokator. Sledeći prolaz
ima jasan, imenovan spisak u §6.
