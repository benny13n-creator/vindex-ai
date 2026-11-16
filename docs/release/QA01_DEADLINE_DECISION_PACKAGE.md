# QA-01 — paket odluka o semantici rokova

**Status: PRODUCT HOLD.** Ovaj dokument je samo analiza. Kod nije menjan, istorijski zapisi nisu dirani i nijedan zadatak nije automatski kreiran.
**Baza analize:** `main` = `ed0662be` (produkcija, potvrđeno preko `GET /api/version`).
**Oznake:** PROVEN = pročitano u kodu, sa navedenom linijom. INFERRED = obrazloženo, ali nije izvršeno nad stvarnim podacima. UNKNOWN = nedostaje dokaz.

## 1. Ko upisuje kandidat za rok (`predmet_hronologija`, `vrsta='rok'`)

| Pisac | Izvor datuma | `izvor` | `vaznost` | Naziv (`dogadjaj`) | Dedup | Filter datuma |
|---|---|---|---|---|---|---|
| Genome, `routers/case_dna.py::_sync_rokovi_to_hronologija` (~l. 912–950) | model (`rokovi_kriticni`, `status=="aktivan"`) | `AI_AUTONOMOUS` | **uvek `kritičan`**, upisano u kodu | `"{naziv}: {opis}"` — oba polja piše **model** | tačno (`dogadjaj`, `datum_iso`) | **nema**: prošao datum se upisuje |
| Smart Intake, `routers/smart_intake.py` (~l. 790–895) | polje `deadline` iz ekstrakcije | `AI_AUTONOMOUS` | `važan` | `"Rok iz dokumenta ({tip})"` | isti predmet + datum + naziv + izvorni fajl | samo prag pouzdanosti ili ljudska ispravka |
| Pipeline, `services/case_pipeline.py::_step` rokovi (~l. 300–395) | model iz **opisa predmeta** (ne iz dokumenta) | `AI_AUTONOMOUS` | koju predloži model (normalizovano) | opis koji piše **model** | jednom po predmetu (`[Pipeline:rokovi]` u istoriji); nema dedupa po redu | samo „ne stariji od 1 godine“ |
| Copilot / `dodaj_rok` / prvi rok na prijemu / lanac rokova | ljudski unos ili radnja | `HUMAN_DIRECT` / `AI_ASSISTED` | po radnji | po radnji | — | — |

Posebno: auto-analiza dokumenta (`api.py` ~l. 5655–5680, `_HRONOLOGIJA_SYSTEM_PROMPT`) upisuje **događaje**. Model sam bira `vaznost`, a „kritičan“ obuhvata i „ugovor potpisan“.

## 2. Kontrola i posledice

- **Izvršiva posledica** (email, SMS, Viber, kalendar): samo potvrđen rok, preko `shared/rokovi.py::sme_pokrenuti_obavezu`, bez izuzetka po `izvor`/`vaznost`. **PROVEN**, fail-closed.
- **Odbijanje**: čuva se u audit lancu (`shared/rok_potvrda.py`), a red ostaje. `je_razresen` ga uklanja iz aktivnog Danas. **PROVEN**.
- **Neuspeh čitanja**: `shared/rokovi.py::Stanje` razlikuje `NEUSPEH` i `PRAZNO`; „nema rokova“ sme da se kaže samo za `PRAZNO`. **PROVEN** za kanonskog čitaoca. Legacy čitaoci izvan tog modula nisu revidirani (UNKNOWN).
- **Case Action za nepotvrđen AI rok** (`services/case_evolution.py`, Rule 6, ~l. 1061–1100): tekst je pošten („čeka vašu potvrdu … prošao pre N dana“), ali `prioritet = _priority_by_days(dani)` daje **`critical` za svaki datum ≤ 3 dana, uključujući prošle datume**. **PROVEN** (l. 889–894).

## 3. Odgovori na adversarial pitanja

| Pitanje | Odgovor | Dokaz |
|---|---|---|
| Može li datum već izvršene radnje postati obaveza? | **DA, kao kandidat.** Genome nema filter datuma, a Pipeline prima datume do godinu dana unazad. Na Radnoj listi postaje „kritična“ stavka pregleda. Izvršiva obaveza ne postaje bez potvrde. | case_dna l. 912–920; case_evolution l. 889, 1093 |
| Može li AI opis posledice postati naziv roka? | **DA.** `dogadjaj = "{naziv}: {opis}"` iz modela (Genome), odnosno `opis` iz modela (Pipeline). | case_dna l. 922; case_pipeline l. 368 |
| Može li nepotvrđen predlog dobiti „kritičan“ bez kriterijuma? | **DA, na dva mesta:** Genome upisuje `kritičan` u kodu za svaki rok, a Rule 6 daje `critical` po broju dana. Legacy `/api/predmeti/dashboard` i `/workspace` (l. 4927, 7522) računaju „urgentne rokove“ samo po `vaznost=="kritičan"`, bez `vrsta` i bez potvrde. | navedene linije |
| Može li odbijen rok ponovo nastati drugim putem? | **DA (INFERRED).** Dedup je po tačnom tekstu. Ako model drugim rečima opiše isti rok, nastaje nov kandidat, bez veze sa odbijenim. Smart Intake i Pipeline ne proveravaju odbijene. | dedup ključevi u tabeli 1 |
| Mogu li dva izvora imati isti datum, a različite obaveze? | **DA, i sistem ih (ispravno) ne spaja.** Smart Intake namerno ne spaja različite izvorne fajlove (N03-FD2). | smart_intake l. 828–840 |
| Može li neuspeh baze biti prikazan kao „nema rokova“? | **NE** za kanonskog čitaoca (`NEUSPEH` ≠ `PRAZNO`). Za legacy čitaoce: UNKNOWN. | rokovi.py `Stanje` |

## 4. Predlog četiri kategorije (za odluku osnivača, nije implementirano)

| Kategorija | Primer iz bete | Predloženi prikaz | Poreklo | Ljudska kontrola | Rizik ako se pomeša |
|---|---|---|---|---|---|
| **1. Datum događaja** (činjenica u prošlosti) | 01.09.2026 (relevantno za navode); 24.08.2026 (dodatna isporuka **već izvršena**) | Hronologija, bez odbrojavanja i bez „kritično“ | dokument (citat + DOK oznaka) | nije potrebna potvrda; ispravka po želji | izvršena radnja prikazana kao obaveza → lažna hitnost |
| **2. Ugovorna vremenska obaveza** | 15.08.2026 (ugovorena isporuka) | „Ugovorni rok“ uz stranu koja ga duguje; status ispunjenja odvojeno od blagovremenosti | ugovor (DOK + klauzula) | advokat potvrđuje da je obaveza i čija je | pomeša se sa procesnim rokom; „ispunjeno“ ≠ „blagovremeno“ |
| **3. Procesni rok** | rok za izjašnjenje iz zapisnika | „Procesni rok“ sa odbrojavanjem; jedini koji sme biti „kritičan“, i to tek posle potvrde | zapisnik/rešenje suda | **obavezna** potvrda pre podsetnika (već važi) | propušten rok, ili lažna sigurnost ako je AI pogrešio datum |
| **4. Interna radnja advokata** | 22.10.2026 (interna priprema pregleda) | Predlog zadatka, **ne** rok; ne kreira se automatski | interna beleška | advokat sam kreira zadatak (postojeći ručni tok) | interna beleška postaje „obaveza prema sudu“ |

## 5. Odluke koje traže osnivača (nijedna nije doneta)

1. Da li uvesti kategoriju roka (1–4)? To traži migraciju (nova kolona ili proširenje CHECK za `vrsta`), dakle posebno odobrenje.
2. Ko sme da označi „kritičan“? Predlog: samo potvrđen procesni rok. Do tada Genome ne bi upisivao `kritičan` u kodu. To je izmena ponašanja, koja čeka odobrenje.
3. Da li prošli datum sme da postane kandidat za rok, ili ide samo u hronologiju kao događaj?
4. Kako se odbijen rok štiti od ponovnog nastanka (identitet izvora + datum, ne tekst)? Traži produktno pravilo.
5. Legacy `/api/predmeti/dashboard` i `/workspace`: da li ih uskladiti sa `vrsta` i potvrdom, ili ih ugasiti posle prelaska na V2?

**Bez blokera:** nijedan nalaz nije nova regresija autorizacije niti bezbednosti rokova. Sve opisano je postojeće ponašanje. Izvršive posledice ostaju zaključane potvrdom.
