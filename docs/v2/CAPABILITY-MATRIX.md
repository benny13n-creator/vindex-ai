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
| `DEFERRED` | svesno odloženo, sa razlogom |
| `BLOCKED` | dokazana protivrečnost ugovora/podataka |

**§14 uslovi za IMPLEMENTED:** dohvatljivo V2 putovanje · stvaran backend
ugovor · ispravno ponašanje dozvola · izolacija tenanta · stanje učitavanja ·
prazno stanje · ponašanje pri grešci · mutacija gde je primenljivo ·
upotrebljiva responzivna površina · dokaz testom.

---

## A. OTVARANJE PREDMETA (P0)

| # | Sposobnost | V2 odredište | Stanje |
|---|---|---|---|
| A1 | Nov predmet — osnovni podaci | `/predmeti/nov` | IMPLEMENTED |
| A2 | Stranke uz predmet (tužilac/tuženi) | `/predmeti/nov` → PATCH | IMPLEMENTED |
| A3 | **Provera sukoba interesa pri otvaranju** | `/predmeti/nov` kapija | IMPLEMENTED |
| A4 | Validacija pri otvaranju | `/predmeti/nov` | IMPLEMENTED |
| A5 | Otvaranje u Dosije posle kreiranja | → `/predmet/<id>` | IMPLEMENTED |
| A6 | Povezivanje POSTOJEĆEG klijenta | — | **P0 otvoreno** |
| A7 | Smart Intake / AI intake iz dokumenta | — | P1 otvoreno |

## B. RAD NAD PREDMETOM

| # | Sposobnost | V2 odredište | Stanje |
|---|---|---|---|
| B1 | Registar predmeta (pretraga, straničenje) | `/predmeti` | IMPLEMENTED |
| B2 | Identitet i stanje predmeta | Dosije · Stanje | IMPLEMENTED |
| B3 | Hronologija | Dosije · Hronologija | IMPLEMENTED |
| B4 | Analiza predmeta (spremnost) | Dosije · Analiza | PARTIAL |
| B5 | Spisi predmeta | Dosije · Spisi | IMPLEMENTED |
| B6 | Rokovi i zadaci | Dosije · Rokovi | PARTIAL |
| B7 | Odluka o predloženom roku | Dosije + Danas | IMPLEMENTED |
| B8 | Izmena polja predmeta | — | **P0 otvoreno** |
| B9 | Beleške | — | **P0 otvoreno** |
| B10 | Zadaci | — | **P0 otvoreno** |
| B11 | Ročišta | — | **P0 otvoreno** |
| B12 | Brisanje predmeta | — | P1 otvoreno |
| B13 | Komentari | — | P1 otvoreno |
| B14 | Workflow / kanban faza | — | P2 |
| B15 | Strategija | — | P2 |
| B16 | Naplata po predmetu | — | P1 otvoreno |
| B17 | Komunikacija sa klijentom | — | P2 |
| B18 | Saradnja | — | P2 |
| B19 | Mapa veza (evidence graph) | — | P2 |
| B20 | Profitabilnost predmeta | — | P2 |
| B21 | Case DNA / Genome | — | P2 |
| B22 | Case Commander | — | P2 |
| B23 | Court Predictor | — | P2 |
| B24 | Digital Twin (simulacija) | — | P2 |
| B25 | Decision Replay | — | P2 |
| B26 | Zastarelost Guardian | — | P1 otvoreno |
| B27 | Priprema za ročište | — | P2 |
| B28 | AI preporuka za predmet | — | P2 |
| B29 | Multi-agent tim savetnika | — | P2 |
| B30 | Pravna procena predmeta | — | P2 |

## C. RAD SA SPISIMA

| # | Sposobnost | V2 odredište | Stanje |
|---|---|---|---|
| C1 | Otpremanje spisa | Dosije · Spisi | IMPLEMENTED |
| C2 | Spisak spisa | Dosije · Spisi | IMPLEMENTED |
| C3 | Čitanje spisa | `?spis=<id>` | IMPLEMENTED |
| C4 | Preuzimanje originala | download ruta | IMPLEMENTED |
| C5 | Brisanje spisa | — | **P0 otvoreno** |
| C6 | Stanje analize spisa | Dosije · Spisi | PARTIAL |
| C7 | Poređenje dokumenata | — | P2 |
| C8 | Evidence Vault | — | P2 |
| C9 | Evidence Graph | — | P2 |

## D. PRAVNI RAD

| # | Sposobnost | V2 odredište | Stanje |
|---|---|---|---|
| D1 | Pravno pitanje (RAG + izvori) | `/znanje` | IMPLEMENTED |
| D2 | Prikaz izvora i ograda | `/znanje` | IMPLEMENTED |
| D3 | Izrada nacrta akta | `/predmeti/akt` | IMPLEMENTED |
| D4 | Šabloni dokumenata | — | P1 otvoreno |
| D5 | Podnesak | — | P1 otvoreno |
| D6 | Sudska praksa | — | **P0 otvoreno** |
| D7 | Istraživanje u kontekstu predmeta | — | P1 otvoreno |
| D8 | Knowledge Base | — | P2 |
| D9 | Interni pravni stavovi | — | P2 |
| D10 | Precedenti | — | P2 |
| D11 | Praćenje izmena zakona | — | P2 |
| D12 | Learning / lessons learned | — | P2 |
| D13 | Law Firm Brain (firm memory) | — | P2 |
| D14 | Knowledge Graph | — | P2 |
| D15 | Knowledge Transfer | — | P2 |
| D16 | Knowledge Hygiene | — | P2 |
| D17 | Memory Graph | — | P2 |
| D18 | Style Checker | — | P2 |
| D19 | Ispravke i učenje stila | — | P2 |
| D20 | Confidence Audit | — | P2 |

## E. RAD SA KLIJENTIMA

| # | Sposobnost | V2 odredište | Stanje |
|---|---|---|---|
| E1 | Spisak klijenata | Kancelarija · Klijenti | PARTIAL |
| E2 | Detalj klijenta | — | **P0 otvoreno** |
| E3 | Nov klijent | — | **P0 otvoreno** |
| E4 | Izmena klijenta | — | P1 otvoreno |
| E5 | Povezani predmeti klijenta | — | **P0 otvoreno** |
| E6 | Timeline klijenta | — | P2 |
| E7 | Dokumenti klijenta | — | P2 |
| E8 | Client Twin | — | P2 |
| E9 | Klijentski portal | — | P2 |
| E10 | Uvoz klijenata (CSV) | — | P2 |
| E11 | Brisanje / arhiviranje klijenta | — | P1 otvoreno |

## F. RAD KANCELARIJE

| # | Sposobnost | V2 odredište | Stanje |
|---|---|---|---|
| F1 | Pregled naplate (tekući mesec) | Kancelarija · Naplata | IMPLEMENTED |
| F2 | Nalog i krediti | Kancelarija · Nalog | IMPLEMENTED |
| F3 | Tim kancelarije | Kancelarija · Tim | PARTIAL |
| F4 | Unos rada / tajmer | — | **P0 otvoreno** |
| F5 | Fakture | — | **P0 otvoreno** |
| F6 | Dugovanja / naplata-status | — | P1 otvoreno |
| F7 | Izveštaji (mesečni, godišnji) | — | P1 otvoreno |
| F8 | Tarife (AKS) | — | P1 otvoreno |
| F9 | Portfolio kancelarije | — | P2 |
| F10 | Firm Health Index | — | P2 |
| F11 | Profitabilnost kancelarije | — | P2 |
| F12 | Matter / Outcome Intelligence | — | P2 |

## G. USLOVNE / SPECIJALIZOVANE

| # | Sposobnost | V2 odredište | Stanje |
|---|---|---|---|
| G1 | Regulatorna provera (ZDI/MiCA) | `/uskladjenost` | PARTIAL |
| G2 | Pretraga propisa o dig. imovini | `/uskladjenost` | PARTIAL |
| G3 | Analiza whitepaper-a | `/uskladjenost` | PARTIAL |
| G4 | AML/KYC revizija | `/uskladjenost` | PARTIAL |
| G5 | Pravna analiza pametnog ugovora | `/uskladjenost` | PARTIAL |
| G6 | Due Diligence | — | P2 |
| G7 | Wallet Risk Assessment | — | P2 |
| G8 | Source of Funds | — | P2 |
| G9 | Exchange Reporting Simulator | — | P2 |
| G10 | Uslovno prikazivanje prostora | boot + ruter | IMPLEMENTED |

**G1–G5 su PARTIAL, ne IMPLEMENTED:** rute ne vraćaju izvore, pa uslov §14.2
(stvaran backend ugovor dovoljan da UI pošteno predstavi tvrdnju) nije
ispunjen. Ograda je privremeni fail-closed mehanizam, ne konačna arhitektura
(vlasnička odluka Z017.1 §5).

## H. POPREČNE SPOSOBNOSTI

| # | Sposobnost | V2 odredište | Stanje |
|---|---|---|---|
| H1 | Globalna pretraga | `/pretraga` + Ctrl+K | IMPLEMENTED |
| H2 | Danas (šta traži pažnju) | `/danas` | IMPLEMENTED |
| H3 | Semantika grešaka (401/403/413/415/429/5xx) | platform | IMPLEMENTED |
| H4 | Odjava | Kancelarija | IMPLEMENTED |
| H5 | Jutarnji brifing | — | P1 otvoreno |
| H6 | Kalendar | — | P1 otvoreno |
| H7 | Notifikacije | — | P1 otvoreno |
| H8 | Export / GDPR | — | P2 |
| H9 | Podešavanja | — | P1 otvoreno |
| H10 | Glasovne komande | — | P2 |
| H11 | Copilot | — | P2 |
| H12 | Ambient Copilot (Word/Browser) | — | P2 |

---

## ZBIR

| Grupa | Ukupno | IMPLEMENTED | PARTIAL | Otvoreno |
|---|---|---|---|---|
| A · otvaranje predmeta | 7 | 5 | 0 | 2 |
| B · rad nad predmetom | 30 | 5 | 2 | 23 |
| C · spisi | 9 | 4 | 1 | 4 |
| D · pravni rad | 20 | 3 | 0 | 17 |
| E · klijenti | 11 | 0 | 1 | 10 |
| F · kancelarija | 12 | 3 | 1 | 8 |
| G · uslovne | 10 | 1 | 5 | 4 |
| H · poprečne | 12 | 4 | 0 | 8 |
| **UKUPNO** | **111** | **25** | **10** | **76** |

Rekonstruisani inventar ima **111** stavki, ne 88. Razlika je metodološka:
vlasnikov Z011 je verovatno spajao srodne stavke (npr. C1–C4 kao jedna
sposobnost „Spisi"). Ako se primeni to spajanje, broj se približava 88.
**Ne prikazujem 111 kao ispravku vlasnikovog broja** — prikazujem ga kao
rekonstrukciju čija granularnost čeka poređenje sa Z011.

## OTVORENI P0 (sledeći na redu)

```
A6   povezivanje postojećeg klijenta sa predmetom
B8   izmena polja predmeta
B9   beleške
B10  zadaci
B11  ročišta
C5   brisanje spisa
D6   sudska praksa
E2   detalj klijenta
E3   nov klijent
E5   povezani predmeti klijenta
F4   unos rada / tajmer
F5   fakture
```

---

## POKRIVENOST RUTA (odvojena metrika, §13 mandata)

```
legacy backend putanje okrenute advokatu   194
V2 backend putanje                          27
preklapanje                                 16
```

**Ovo NIJE paritet sposobnosti** i ne sme se tako predstaviti. Jedna
sposobnost koristi više ruta („Spisi" = list + upload + reader + download +
delete + analiza), a jedna generička ruta ne znači da je svih pet
korisničkih sposobnosti preneto. Broj se vodi kao tehnički pokazatelj.
