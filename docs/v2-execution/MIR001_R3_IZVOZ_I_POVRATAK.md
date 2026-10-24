# MIR001 FINAL RELEASE R3 — granice izvoza i bezbedan povratak

## 1. Izvozne putanje (trenutna grana)

| Putanja | Šta izvozi | Ko je pozivalac | Tvrdi li „odobreno"? |
|---|---|---|---|
| `POST /api/staging/{id}/docx`, tip `dokument_za_sud` | **predmetni izvoz odobrene verzije**: samo `approved`, tekst tačno odobrenog sha256, bez internih oznaka (`DOK-nn`), bez naslova i podnožja sistema | V2 „Preuzmi odobren dokument (.docx)" | jedini izvoz koji predstavlja odobren predmetni dokument |
| `POST /api/staging/{id}/docx`, tip `nacrt_iz_spisa` | **AI radni predlog** — ne izvozi se (409) | — | — |
| `POST /api/staging/{id}/docx`, drugi tipovi (`/api/podnesak` šabloni, raniji nacrti) | sačuvan tekst nacrta, sa naslovom i podnožjem „Generisano … \| Vindex AI"; tekst sa granicom internih napomena samo deo pre granice | V2 „Preuzmi kao Word" za nacrt sa overe | ne — naslov je vrsta nacrta, podnožje kaže da ga je generisao alat |
| `POST /api/nacrti/export/docx` | **generički izvoz proizvoljnog teksta** iz pregledača; odbija tip `nacrt_iz_spisa`/`dokument_za_sud` i tekst sa granicom internih napomena (409) | V2 nacrt iz šablona (bez reda na overi), legacy `/app-legacy` | ne — isti naslov/podnožje alata, nikakva oznaka odobrenja |
| `POST /export/docx` (`routers/export.py`) | generički izvoz teksta (legacy); odbija granicu internih napomena | legacy | ne |

Nijedan opšti izvoz ne sadrži reči „odobren", „pregledan" ni „overen" (proveren kod `_nacrt_to_docx` i
`routers/export._tekst_u_docx`).

**Granica koju Vindex može da garantuje:** zaštićeni predmetni tok (AI predlog → usvajanje → odobrenje → DOCX) ne
dozvoljava neodobrenu promociju ni automatsko predstavljanje dokumenta kao pravno pregledanog: AI predlog se ne
odobrava, ne menja i ne izvozi; dokument za sud se izvozi samo kao tačno odobrena verzija; odobrenje zahteva tačan tekst,
reviziju i 8 odluka advokata (C3b TASK-01..03, R1); Data API ne može da zaobiđe rute (R2, migracija 141).

**Šta Vindex NE može da zabrani:** korisnik može ručno da kopira AI tekst u drugi editor ili u generički izvoz (bez
granice internih napomena, sa nezaštićenim `tip`-om). Takav fajl nosi podnožje alata i nije predstavljen kao odobren
predmetni dokument. Ne tvrdi se apsolutna zabrana svakog izvoza AI teksta.

## 2. Povratak na `f33dcce8` — analiza

Read-only inventar produkcije (`MIR001_R3_PROD_INVENTAR.py`, samo GET/HEAD, agregatno; 2026-10-24; izlaz skripta čuva se
lokalno, van javnog repoa): `staging_memory` = **0 redova** (`staging_count_exact` = 0;
`kontrola_upit_radi` = true — nepostojeća kolona daje 400, dakle upiti zaista rade); nacrta iz promocije = 0; obim
(`predmeti`, `predmet_dokumenti`, otvorene `case_actions`) izmeren; `ns007_autonomy_work_items_http` = 404 (tabela NE postoji —
migracija 136 nije primenjena; NS007 nema gde da upiše rad).

**Danas nijedan zapis nije pogođen.** Opasnost nastaje tek kada nova verzija napravi redove novog toka (`nacrt_iz_spisa`,
`dokument_za_sud`) — tada stari kod (`f33dcce8`) nad njima:

| putanja u `f33dcce8` | šta bi uradila sa redom novog toka |
|---|---|
| `POST /api/staging/{id}/approve` | odobrila AI predlog na čekanju i — ako je ocena ≥ 0,85 (predlog dobija ocenu pri izradi) — **upisala AI tekst u bazu znanja** (Pinecone + `predmet_dokumenti`) |
| `POST /api/staging/{id}/ponovi-upis` + `_ponovni_upis_moguc` | ponudila i izvršila upis **odobrenog dokumenta za sud** u bazu znanja (ocena dobijena pri izmeni teksta) |
| `PATCH /api/staging/{id}/tekst` | prepisala `quality_detail` i time **izbrisala zapis usvajanja i revizije** dokumenta na čekanju |
| `services/law_brain.artifact_item` | prikazala odobren dokument za sud kao `LAWYER_VERIFIED_ARTIFACT` (overeno znanje kancelarije), sa internim napomenama u izvodu — **stari status `approved` kao dokaz novog odobrenja** |
| `POST /api/nacrti/export/docx`, `/export/docx` | izvezla tekst AI predloga **zajedno sa internim napomenama** (stari kod nema blokadu granice) |
| `POST /api/staging/{id}/reject` | odbila **odobren dokument za sud** (opšti `reject` menja status po samom `id`) — zapis odluke advokata izgubljen |
| NS007 | `f33dcce8` već IMA NS007 infrastrukturu (`POST /api/cron/autonomy`, `run_autonomy_cycle`, `law_brain_promocija`) — nema samo `case_change_brief`. Nijedna NS007 putanja ne dira redove novog toka (`law_brain_promocija` piše samo tip `pripremljen_rad`). U produkciji tabela `autonomy_work_items` ne postoji (404) i nema Cron-a — NS007 je neaktivan pre i posle povratka |
| `case_actions` (van `staging_memory`) | MIR001 (C1) upisuje `dokaz.zadrzano` (nedokaziva veza → radnja ostaje otvorena); stari kod to polje ignoriše i takve radnje pri brisanju izvora zatvara po starom pravilu. Nije promocija nacrta, ali je semantika C1 koja se gubi povratkom (zaštita je ne vraća — to je stari ugovor) |

**Zaključak: prost povratak na goli `f33dcce8` je ZABRANJEN čim je MIR001 bar jednom pušten u produkciju** — ne može
da garantuje da opasna promocija neće biti izvršena. Inventar je trenutni snimak: dok nova verzija služi korisnike (pa i
dok se povratak deploy-uje), novi red `nacrt_iz_spisa` može nastati posle očitanog „0" (GATE-R3 B1).

## 3. Najmanja bezbedna alternativa: cilj povratka = `f33dcce8` + zaštita

Lokalna grana **`rollback/mir001-f33dcce8-guard`** (worktree `C:/vindex-mir001-rollback`, NIJE push): jedan commit
**`7e764891`** nad `f33dcce8` (3 fajla koda, +37/−3, i test):
- `approve`, `PATCH /tekst`, `ponovi-upis` za tip `nacrt_iz_spisa`/`dokument_za_sud` → 409 (ništa se ne menja, ne
  promoviše); `_ponovni_upis_moguc` → false za te tipove; `reject` odobrenog dokumenta za sud → 409; čitanje i
  odbijanje ostalog rade;
- `/api/nacrti/export/docx` i `/export/docx` odbijaju tekst sa granicom internih napomena i tip novog toka;
- `law_brain.artifact_item`: ta dva tipa su `AI_WORK_PRODUCT` (nikad overeno znanje), izvod bez internih napomena.
Test `tests/test_mir001_r3_rollback_guard.py`: 5/5 sa zaštitom; na golom `f33dcce8` 4/5 pada (opasnost dokazana);
širi skup (70 fajlova iz `fc_siri.txt` koji postoje na `f33dcce8`): 863 passed / 0 failed i sa zaštitom i bez nje.

Sa zaštitom ostaju (napomene, bez opasne promocije): `POST /api/nacrt` na `f33dcce8` prima `vrsta` kao slobodan
string i može da napravi red tipa `nacrt_iz_spisa` (sa zaštitom bezopasno — ne odobrava se, ne upisuje u znanje);
`law_brain.artifact_item` računa `pravna_aktuelnost` nad celim tekstom (stavka nije pouzdana — nizak uticaj).

**Pravilo povratka (za osnivača):**
1. **Pre prvog puštanja MIR001** osnivač pushuje (bez spajanja u main) granu `rollback/mir001-f33dcce8-guard`
   (`7e764891`), da u trenutku povratka postoji šta da se pusti. Agent ne pushuje.
2. **Čim je MIR001 bar jednom pušten, jedini dozvoljeni cilj povratka je `rollback/mir001-f33dcce8-guard`.** Goli
   `f33dcce8` je zabranjen bez obzira na inventar (inventar zastareva tokom samog povratka).
3. **Ne koristiti Render „Rollback" na prethodni deploy** (to je goli `f33dcce8`); povratak = ručni deploy grane sa
   zaštitom.
4. Migracija 141 se pri povratku aplikacije NE vraća (stari kod koristi `service_role`); njen povratak je zaseban,
   samo uz dokazanog potrošača sa korisničkim JWT-om.
5. Ne menjati produkcione zapise; read-only inventar (`MIR001_R3_PROD_INVENTAR.py`) pre i posle povratka — samo za
   uvid (koliko redova novog toka zaštita čuva), ne kao uslov za goli povratak.
