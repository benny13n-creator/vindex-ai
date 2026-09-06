# VINDEX V2 — MATRICA POSLOVNIH SPOSOBNOSTI

**Provenijencija ovog dokumenta — čitati pre brojeva.**

Vlasnik upućuje na Z011 kao kanonski inventar od 88 poslovnih sposobnosti.
**Z011 ne postoji u repozitorijumu.** Traženo je u radnom stablu, u
`legal-agent` folderu, kroz `git log --all` po svim granama, i po celom disku.
Jedini nađeni inventar je `diag_capability_inventory_2026-05-18.json` — 28
stavki, maj 2026, pre najvećeg dela aplikacije. To nije Z011.

Zato je ovaj inventar **rekonstruisan istom metodom koju je vlasnik opisao**:

```
user-triggerable frontend funkcije      120 (onclick + window.*)
legacy navigacione destinacije           13 (vx-sidebar)
legacy kartice unutar predmeta           12
backend rute okrenute advokatu          194
permission ključevi                      70 (feature_registry)
        ↓ destilacija u poslovno smislene sposobnosti
```

**Broj koji ovde stoji nije dokazano identičan Z011 broju 88.** Ako vlasnik
priloži Z011, ova matrica se mapira na njega; do tada je ovo najbliža
rekonstrukcija izvedena iz samog koda, a ne iz sećanja.

---

## KAKO SE ČITA STANJE

| Stanje | Značenje |
|---|---|
| `IMPLEMENTED` | ispunjava svih 10 uslova iz §14 mandata |
| `PARTIAL` | dostupno u V2, ali ne ispunjava sve uslove |
| `DEFERRED` | svesno odloženo, sa navedenim razlogom |
| `BLOCKED` | dokazana protivrečnost ugovora/podataka |

**§14 uslovi za IMPLEMENTED:** dohvatljivo V2 putovanje · stvaran backend
ugovor · ispravno ponašanje dozvola · izolacija tenanta · stanje učitavanja ·
prazno stanje · ponašanje pri grešci · mutacija gde je primenljivo ·
upotrebljiva responzivna površina · dokaz testom.

**Postojanje JS funkcije, endpointa ili navigacione veze NIJE dokaz.**

---

## A. OTVARANJE PREDMETA

| # | Sposobnost | V2 odredište | Prioritet | Stanje | Dokaz / preostali jaz |
|---|---|---|---|---|---|
| A1 | Nov predmet — osnovni podaci | `/predmeti/nov` | P0 | IMPLEMENTED | `mp_konflikt` uživo |
| A2 | Stranke uz predmet | `/predmeti/nov` → PATCH | P0 | IMPLEMENTED | uživo |
| A3 | **Provera sukoba pri otvaranju** | `/predmeti/nov` kapija | P0 | IMPLEMENTED | 19 testova, 12 mutacija, fail-closed dokazan |
| A4 | Validacija pri otvaranju | `/predmeti/nov` | P0 | IMPLEMENTED | uživo |
| A5 | Otvaranje Dosijea posle kreiranja | → `/predmet/<id>` | P0 | IMPLEMENTED | uživo |
| A6 | Povezivanje POSTOJEĆEG klijenta | `/predmeti/nov` + `confirm-links` | P0 | IMPLEMENTED | uživo |
| A7 | **Uvoz predmeta iz dokumenta** | `/predmeti/uvoz` | P1 | IMPLEMENTED | 22 testa, 19/19 mutacija; COI stanje se ne čita kao „nema sukoba" |

## B. RAD NAD PREDMETOM

| # | Sposobnost | V2 odredište | Prioritet | Stanje | Dokaz / preostali jaz |
|---|---|---|---|---|---|
| B1 | Registar predmeta | `/predmeti` | P0 | IMPLEMENTED | offset-500 popravljen, 9 testova |
| B2 | Identitet i stanje predmeta | Dosije · Stanje | P0 | IMPLEMENTED | 34 testa |
| B3 | Hronologija | Dosije · Hronologija | P0 | IMPLEMENTED | 34 testa |
| B4 | Analiza predmeta (spremnost) | Dosije · Analiza | P0 | IMPLEMENTED | prikaz spremnosti + razlozi; procena rizika i preporuka radnje se vode kao B28/B30 |
| B5 | Spisi predmeta | Dosije · Spisi | P0 | IMPLEMENTED | uživo |
| B6 | Rokovi, zadaci i ročišta | Dosije · Rokovi | P0 | IMPLEMENTED | jaz zatvoren kroz B10/B11; migracija 129 ugovor |
| B7 | Odluka o predloženom roku | Dosije + Danas | P0 | IMPLEMENTED | potvrdi/odbij, 409 semantika |
| B8 | Izmena polja predmeta | Dosije · Stanje | P0 | IMPLEMENTED | `if_updated_at` → 409 |
| B9 | Beleške / napomene | Dosije · Stanje | P0 | IMPLEMENTED | jedan tok nad dve tabele, 21 test |
| B10 | Zadaci | Dosije · Rokovi | P0 | IMPLEMENTED | uživo |
| B11 | Ročišta | Dosije · Rokovi | P0 | IMPLEMENTED | uživo |
| B12 | Brisanje predmeta | Dosije · Stanje | P1 | IMPLEMENTED | 409 = predmet i dalje postoji |
| B13 | Komentari | Dosije · Beleške | P1 | IMPLEMENTED | GET je bio 500; spojeno u jedan tok, 9/9 mutacija |
| B14 | Workflow / kanban faza | — | P2 | DEFERRED | stanje predmeta se već vidi i menja u Dosijeu; kanban je drugi prikaz istog podatka, ne nova sposobnost |
| B15 | Strategija predmeta | — | P2 | DEFERRED | AI zaključak o ishodu; traži ugovor o provenijenciji po §5 mandata |
| B16 | Naplata po predmetu | Dosije · Naplata | P1 | IMPLEMENTED | 22 testa; zbir se krije kad nema unosa |
| B17 | Komunikacija sa klijentom | — | P2 | DEFERRED | nije u vlasnikovom redu izvršenja; napomene pokrivaju beleženje kontakta |
| B18 | Saradnja | — | P2 | DEFERRED | zavisi od postojanja kancelarije; vlasnikov nalog vraća `no_firma` |
| B19 | Mapa veza (evidence graph) | — | P2 | DEFERRED | AI izvedena veza bez provenijencije |
| B20 | Profitabilnost predmeta | — | P2 | DEFERRED | izvedeni pokazatelj nad naplatom koja je tek sada u V2; meri se posle upotrebe |
| B21 | Case Genome | — | P2 | DEFERRED | `project_case_genome_forensic_audit`: Genome je snimak, ne stanje; izvor istine je `predmet_dokazi` |
| B22 | Case Commander | — | P2 | DEFERRED | AI preporuka radnje bez provenijencije |
| B23 | Court Predictor | — | P2 | DEFERRED | predviđanje ishoda spora; najviši rizik lažne tvrdnje, traži vlasničku odluku |
| B24 | Digital Twin (simulacija) | — | P2 | DEFERRED | simulacija ishoda; isti razlog kao B23 |
| B25 | Decision Replay | — | P2 | DEFERRED | nema backend rute (0 rutera) |
| B26 | Zastarelost | `/znanje/rokovi` | P1 | IMPLEMENTED | 22 testa, 13/13 mutacija; svaki rezultat nosi ZOO/ZPP član |
| B27 | Priprema za ročište | — | P2 | DEFERRED | nije u redu izvršenja |
| B28 | AI preporuka za predmet | — | P2 | DEFERRED | AI zaključak bez provenijencije |
| B29 | Multi-agent tim savetnika | — | P2 | DEFERRED | isti razlog kao B28 |
| B30 | Pravna procena predmeta | — | P2 | DEFERRED | `project_single_brain_002`: verdikt je bio klampovan; traži vlasničku odluku |

## C. RAD SA SPISIMA

| # | Sposobnost | V2 odredište | Prioritet | Stanje | Dokaz / preostali jaz |
|---|---|---|---|---|---|
| C1 | Otpremanje spisa | Dosije · Spisi | P0 | IMPLEMENTED | `accept` usklađen sa serverom (415 popravljen) |
| C2 | Spisak spisa | Dosije · Spisi | P0 | IMPLEMENTED | uživo |
| C3 | Čitanje spisa | `?spis=<id>` | P0 | IMPLEMENTED | uživo |
| C4 | Preuzimanje originala | download ruta | P0 | IMPLEMENTED | uživo |
| C5 | Brisanje spisa | Dosije · Spisi | P0 | IMPLEMENTED | imenovana potvrda u dva koraka |
| C6 | Stanje analize spisa | Dosije · Spisi | P0 | IMPLEMENTED | „analiziran / nije analiziran" po spisu |
| C7 | Poređenje dokumenata | — | P2 | DEFERRED | nije u redu izvršenja |
| C8 | Evidence Vault | — | P2 | DEFERRED | nije u redu izvršenja |
| C9 | Evidence Graph | — | P2 | DEFERRED | isto kao B19 |

## D. PRAVNI RAD

| # | Sposobnost | V2 odredište | Prioritet | Stanje | Dokaz / preostali jaz |
|---|---|---|---|---|---|
| D1 | Pravno pitanje (RAG + izvori) | `/znanje` | P0 | IMPLEMENTED | 31 test |
| D2 | Prikaz izvora i ograda | `/znanje` | P0 | IMPLEMENTED | ograda IZNAD odgovora |
| D3 | Izrada nacrta akta | `/predmeti/akt` | P0 | IMPLEMENTED | ograda iznad teksta |
| D4 | Šabloni dokumenata | `/predmeti/sabloni` | P1 | IMPLEMENTED | 23 testa, 15/15 mutacija; čuvanje je bilo 500 — popravljeno |
| D5 | Podnesak sudu | `/predmeti/podnesak` | P1 | IMPLEMENTED | 15 testova, 9/9 mutacija; dodat `/api/podnesak/types` |
| D6 | Sudska praksa | `/znanje/praksa` | P0 | IMPLEMENTED | 15 testova; citat `", od ."` popravljen |
| D7 | Istraživanje u kontekstu predmeta | `/znanje?predmet=` | P1 | IMPLEMENTED | `kontekst_predmeta` dodat u backend; 3 živa poziva |
| D8 | Knowledge Base | — | P2 | DEFERRED | Znanje pokriva pitanje nad korpusom; KB je drugi ulaz u isti korpus |
| D9 | Interni pravni stavovi | — | P2 | DEFERRED | nije u redu izvršenja |
| D10 | Precedenti | — | P2 | DEFERRED | tvrdnja o presedanu traži provenijenciju (§5) |
| D11 | Praćenje izmena zakona | — | P2 | DEFERRED | tvrdnja o važenju propisa traži provenijenciju (§5) |
| D12 | Learning / lessons learned | — | P2 | DEFERRED | nije u redu izvršenja |
| D13 | Law Firm Brain | — | P2 | DEFERRED | AI izvedeno znanje bez provenijencije |
| D14 | Knowledge Graph | — | P2 | DEFERRED | isto kao D13 |
| D15 | Knowledge Transfer | — | P2 | DEFERRED | nije u redu izvršenja |
| D16 | Knowledge Hygiene | — | P2 | DEFERRED | administrativna funkcija, ne advokatska |
| D17 | Memory Graph | — | P2 | DEFERRED | isto kao D13 |
| D18 | Style Checker | — | P2 | DEFERRED | nije u redu izvršenja |
| D19 | Ispravke i učenje stila | — | P2 | DEFERRED | nije u redu izvršenja |
| D20 | Confidence Audit | — | P2 | DEFERRED | meri model, ne pravni posao |

## E. RAD SA KLIJENTIMA

| # | Sposobnost | V2 odredište | Prioritet | Stanje | Dokaz / preostali jaz |
|---|---|---|---|---|---|
| E1 | Spisak klijenata | Kancelarija · Klijenti | P0 | IMPLEMENTED | veza ka detalju i ka novom klijentu |
| E2 | Detalj klijenta | `/klijent/<id>` | P0 | IMPLEMENTED | 24 testa; poverljiva polja se NE prikazuju |
| E3 | Nov klijent | `/klijent/nov` | P0 | IMPLEMENTED | uživo |
| E4 | Izmena klijenta | `/klijent/<id>` | P1 | IMPLEMENTED | poverljiva polja se ne nude ni za izmenu |
| E5 | Povezani predmeti klijenta | `/klijent/<id>` | P0 | IMPLEMENTED | ugnežden oblik `predmeti` razrešen |
| E6 | Timeline klijenta | — | P2 | DEFERRED | nije u redu izvršenja |
| E7 | Dokumenti klijenta | — | P2 | DEFERRED | dokumenti žive uz predmet; klijentski pogled je drugi prikaz istog |
| E8 | Client Twin | — | P2 | DEFERRED | AI izveden profil bez provenijencije |
| E9 | Klijentski portal | — | P2 | DEFERRED | `project_schema_reconstruction`: portal je dokazano mrtav na backendu |
| E10 | Uvoz klijenata (CSV) | — | P2 | DEFERRED | nije u redu izvršenja |
| E11 | Arhiviranje klijenta | `/klijent/<id>` | P1 | IMPLEMENTED | imenovano kao arhiviranje, NE brisanje (soft delete) |

## F. RAD KANCELARIJE

| # | Sposobnost | V2 odredište | Prioritet | Stanje | Dokaz / preostali jaz |
|---|---|---|---|---|---|
| F1 | Pregled naplate (tekući mesec) | Kancelarija · Naplata | P0 | IMPLEMENTED | 22 testa |
| F2 | Nalog i krediti | Kancelarija · Nalog | P0 | IMPLEMENTED | uživo |
| F3 | Tim kancelarije | Kancelarija · Tim | P0 | PARTIAL | **prikaz je potpun** (firma, članovi, uloge, stanje bez firme); **jaz: upravljanje timom** (`pozovi`/`suspenduj`/`reaktiviraj`/`ukloni`/`napusti`/`naziv`/`mesta`/`istorija`, 8 ruta) nije u V2. DEFERRED: vlasnikov nalog vraća `no_firma`, pa ulazni uslov nije ispunjen |
| F4 | Unos rada / tajmer | Kancelarija + Dosije | P0 | IMPLEMENTED | jedan tajmer po advokatu, 409 kao pravilo |
| F5 | Fakture | Kancelarija · Naplata | P0 | IMPLEMENTED | uživo |
| F6 | Stanje naplate / nefakturisan rad | `/kancelarija/finansije` | P1 | IMPLEMENTED | 23 testa, 17/17 mutacija; tri iznosa razdvojena |
| F7 | Izveštaji (godišnji, po tipu) | `/kancelarija/finansije` | P1 | IMPLEMENTED | stopa naplate se ne prikazuje nad nulom |
| F8 | Tarife (AKS) | `/kancelarija/tarife` | P1 | IMPLEMENTED | AKS iznos se prikazuje UVEK, uz sopstvenu izmenu |
| F9 | Portfolio kancelarije | — | P2 | DEFERRED | izvedeni pokazatelj; meri se posle upotrebe |
| F10 | Firm Health Index | — | P2 | DEFERRED | nema backend rute (0 rutera) |
| F11 | Profitabilnost kancelarije | — | P2 | DEFERRED | isto kao B20 |
| F12 | Matter / Outcome Intelligence | — | P2 | DEFERRED | predviđanje ishoda; isto kao B23 |

## G. USLOVNE / SPECIJALIZOVANE

| # | Sposobnost | V2 odredište | Prioritet | Stanje | Dokaz / preostali jaz |
|---|---|---|---|---|---|
| G1 | Regulatorna provera (ZDI/MiCA) | `/uskladjenost` | P0 | **BLOCKED** | ruta ne vraća izvore; §14.2 nije ispunjen |
| G2 | Pretraga propisa o dig. imovini | `/uskladjenost` | P0 | **BLOCKED** | isto |
| G3 | Analiza whitepaper-a | `/uskladjenost` | P0 | **BLOCKED** | isto |
| G4 | AML/KYC revizija | `/uskladjenost` | P0 | **BLOCKED** | isto |
| G5 | Pravna analiza pametnog ugovora | `/uskladjenost` | P0 | **BLOCKED** | isto |
| G6 | Due Diligence | — | P2 | DEFERRED | isti blokator kao G1–G5 |
| G7 | Wallet Risk Assessment | — | P2 | DEFERRED | isti blokator |
| G8 | Source of Funds | — | P2 | DEFERRED | isti blokator |
| G9 | Exchange Reporting Simulator | — | P2 | DEFERRED | isti blokator |
| G10 | Uslovno prikazivanje prostora | boot + ruter | P0 | IMPLEMENTED | fail-closed: pravo koje nije dokazano se ne prikazuje |

**G1–G5 su BLOCKED, ne PARTIAL.** Dokazana protivrečnost: ekran bi prikazao
regulatorni zaključak, a ruta ne vraća izvor kojim se on dokazuje
(`B-U-DA-REALITY-GATE`: 8/11 funkcija daje regulatorne zaključke bez ijednog
izvora). Ograda je **privremeni fail-closed mehanizam, ne konačna
arhitektura** (vlasnička odluka Z017.1 §5). Konačno pravilo: ako V2 prikazuje
pravnu/regulatornu tvrdnju, backend mora vratiti dovoljnu provenijenciju.
Ovo je jedini BLOCKED skup u matrici i traži izmenu backenda, ne frontenda.

## H. POPREČNE SPOSOBNOSTI

| # | Sposobnost | V2 odredište | Prioritet | Stanje | Dokaz / preostali jaz |
|---|---|---|---|---|---|
| H1 | Globalna pretraga | `/pretraga` + Ctrl+K | P0 | IMPLEMENTED | uživo |
| H2 | Danas (šta traži pažnju) | `/danas` | P0 | IMPLEMENTED | kandidati ≠ termini |
| H3 | Semantika grešaka | platform | P0 | IMPLEMENTED | 400/401/403/404/409/422/429/500/503 |
| H4 | Odjava | Kancelarija | P0 | IMPLEMENTED | uživo |
| H5 | Jutarnji brifing | `/danas/brifing` | P1 | IMPLEMENTED | 16 testova, 11/11 mutacija; „nije očitano" ≠ 0 |
| H6 | Kalendar | `/danas/kalendar` | P1 | IMPLEMENTED | 24 testa, 11/11 mutacija |
| H7 | Obaveštenja | `/danas/obavestenja` | P1 | IMPLEMENTED | 21 test, 12/12 mutacija; pala pretraga ≠ „nema obaveštenja" |
| H8 | Export / GDPR | — | P2 | DEFERRED | nije u redu izvršenja; pravna obaveza nije dokazana u ovom programu |
| H9 | Plan i potrošnja | Kancelarija · Nalog | P1 | IMPLEMENTED | iz boot podatka, bez novog poziva (granica 60/h) |
| H10 | Glasovne komande | — | P2 | DEFERRED | `project_beta_b3`: glas ne prolazi kroz B4-M2 guard |
| H11 | Copilot | — | P2 | DEFERRED | AI predlog bez provenijencije |
| H12 | Ambient Copilot (Word/Browser) | — | P2 | DEFERRED | zahteva instalaciju van veba |

---

## ZBIR

| Grupa | Ukupno | IMPLEMENTED | PARTIAL | BLOCKED | DEFERRED (P2) |
|---|---|---|---|---|---|
| A · otvaranje predmeta | 7 | 7 | 0 | 0 | 0 |
| B · rad nad predmetom | 30 | 15 | 0 | 0 | 15 |
| C · spisi | 9 | 6 | 0 | 0 | 3 |
| D · pravni rad | 20 | 7 | 0 | 0 | 13 |
| E · klijenti | 11 | 6 | 0 | 0 | 5 |
| F · kancelarija | 12 | 7 | 1 | 0 | 4 |
| G · uslovne | 10 | 1 | 0 | 5 | 4 |
| H · poprečne | 12 | 8 | 0 | 0 | 4 |
| **UKUPNO** | **111** | **57** | **1** | **5** | **48** |

### Po prioritetu

| Prioritet | Ukupno | IMPLEMENTED | PARTIAL | BLOCKED | DEFERRED |
|---|---|---|---|---|---|
| **P0** | 46 | 40 | 1 (F3) | 5 (G1–G5) | 0 |
| **P1** | 17 | **17** | 0 | 0 | 0 |
| **P2** | 48 | 0 | 0 | 0 | **48**, svaka sa razlogom |

**P1 je zatvoren u celosti: 17/17.**
**P0 je zatvoren osim 5 BLOCKED (G1–G5) i 1 PARTIAL (F3).**

Nijedna sposobnost nije nestala iz matrice.

---

## ŠTA JOŠ NIJE URAĐENO — TAČNO, BEZ „50+"

**BLOCKED (5):** G1, G2, G3, G4, G5 — regulatorna provera digitalne imovine.
Blokator je jedan i isti: backend ne vraća provenijenciju za regulatorni
zaključak. Traži izmenu backenda.

**PARTIAL (1):** F3 — upravljanje timom kancelarije (8 ruta). Prikaz radi;
upravljanje nije preneto. Ulazni uslov (postojanje kancelarije) nije ispunjen
kod vlasnika (`no_firma`).

**DEFERRED (48):** svih 48 P2 stavki, svaka sa razlogom u tabeli iznad.
Grupisano po razlogu (svaka stavka je u TAČNO jednom redu; zbir = 48):

| Razlog | Broj | Stavke |
|---|---|---|
| AI zaključak bez ugovora o provenijenciji | 14 | B15, B19, B21, B22, B23, B24, B28, B29, B30, D13, D14, D17, E8, H11 |
| Nije u vlasnikovom redu izvršenja | 15 | B17, B27, C7, C8, D9, D12, D15, D16, D18, D19, D20, E6, E10, H8, H12 |
| Isti blokator kao G1–G5 (digitalna imovina) | 4 | G6, G7, G8, G9 |
| Drugi prikaz već prenete sposobnosti | 4 | B14, C9, D8, E7 |
| Izvedeni pokazatelj — meri se posle upotrebe | 4 | B20, F9, F11, F12 |
| Ulazni uslov nije ispunjen / dokazano mrtvo | 3 | B18, E9, H10 |
| Tvrdnja o pravu traži provenijenciju | 2 | D10, D11 |
| Nema backend rute | 2 | B25, F10 |

**Nijedna P2 stavka nije implementirana u ovom programu.** To nije previd
nego posledica vlasnikovog reda izvršenja: §6 je definisao P0 i P1 kao red,
a P2 kao „klasifikuj i implementiraj/deferuj". Ovde je svih 48 klasifikovano
i odloženo sa razlogom.

---

## POKRIVENOST RUTA (ODVOJENA METRIKA, §13 mandata)

Mereno 2026-09-06 regexom nad `v2/**/*.js` i `static/vindex.js`, sa
normalizacijom `{id}` segmenata:

```
legacy putanje pozvane iz vindex.js        195
V2 backend putanje                          50   (bilo 27 na početku programa)
preklapanje                                 37   (bilo 16)
samo u V2 (nema ih u legacy pozivima)       13
```

Metod ima poznatu granicu: putanje sastavljene u više koraka (npr. download
spisa) regex ne vidi, pa je pravi broj V2 putanja ≥ 50. Broj se zato vodi kao
**donja granica**, ne kao tačan popis.

**Ovo NIJE paritet sposobnosti** i ne sme se tako predstaviti. Jedna
sposobnost koristi više ruta („Spisi" = list + upload + reader + download +
delete + analiza), a jedna generička ruta ne znači da je svih pet
korisničkih sposobnosti preneto. Broj se vodi kao tehnički pokazatelj i
**nikada kao konačna ocena.**

---

## IZMENE BACKENDA U OVOM PROGRAMU

Sve su minimalne, unazad kompatibilne i praćene testom:

| Izmena | Razlog | Dokaz |
|---|---|---|
| `shared/stranicenje.py` | `/api/predmeti` je 500-ovao na offset iza kraja (PGRST103) | 9 testova |
| `get_predmet` nosi `stanje_odluke` | Dosije nikad nije video potvrđene rokove | uživo |
| `komentari.order("kreirano")` | GET je bio **500 za svakog korisnika** | 9 testova, mutacija |
| `obrisi_belesku` zero-row guard | `{"ok": true}` za nepostojeću belešku | mutacija |
| `doc-templates/sacuvaj` kolone | upis je gađao `tekst`+`tip` — **nikad nije radilo** | 7 testova, 4 mutacije |
| `GET /api/podnesak/types` | katalog je živeo samo u validatoru | 15 testova |
| `/notifications` `procitano_uspesno` | pala pretraga = „nema obaveštenja" | 2 testa, mutacija |
| `/api/pitanje` `kontekst_predmeta` | kontekst se tiho preskakao | 3 živa poziva |
