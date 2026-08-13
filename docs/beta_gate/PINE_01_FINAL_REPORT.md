# BETA-DATA-PINE-01 — FORENSIC QUARANTINE + DETERMINISTIC VECTOR DELETION

# VERDICT

## 🟡 YELLOW

Kanonsko brisanje je implementirano, autorizovano, verifikovano i dokazano
mutacijama. Karantin je definisan i primenjen na svih 30 orphan vektora, a
dokazano je da **nijedan od njih nije dohvatljiv kroz autorizovani RAG** — nema
CRITICAL nalaza.

Nije GREEN iz jednog razloga koji se ne da zaobići i koji ne ublažavam:

> **Servis je danas primenljiv na 0 od 43 dokumenta.** Svih 43 reda
> `predmet_dokumenti` ima **prazan `content_sha256`**, pa bi funkcija za svaki
> vratila `REFUSED`. Uz to nema nijednog pozivaoca — **DELETE endpoint za
> dokument ni za predmet ne postoji** (potvrđeno: tri postojeće `delete` rute
> brišu belešku, dokaz i saradnika).

```
BASELINE:              dcbf3fd9
TEST COUNT:            5378 → 5400   (+22)
MIGRATIONS:            0
PRODUCTION MUTATIONS:  0   — nijedan Pinecone delete/upsert, nijedan DB upis
```

---

# A–M — ODGOVORI

| | Pitanje | Odgovor |
|---|---|---|
| **A** | Koliko novih vektora ima dokaziv deterministički ID? | **0.** Kanonski ugovor nema nijednu živu instancu — 0/3.000 uzorka u `sudska_praksa`, 0/3.000 u `zakoni_rs`, 0 u sva 4 potpuno izlistana namespace-a |
| **B** | Koliko legacy vektora nema dokaziv ID? | **434.217** ih je legacy; od toga **104 su `uuid4`** (74 `misljenja` + 30 klijentskih) i nemaju dokaziv identitet |
| **C** | Koliko orphan vektora postoji? | **30** klijentskih (6 × `pred_*` × 5). Obrnuto: **43/43** redova baze pokazuje na namespace koji ne postoji |
| **D** | Je li ijedan orphan dohvatljiv kroz autorizovani RAG? | **NE.** Dokazano na svih 5 read putanja — v. §Karantin |
| **E** | Može li jedan tenant obrisati drugi? | **NE** — `REFUSED`, `delete` se uopšte ne poziva |
| **F** | Može li jedan predmet obrisati drugi? | **NE** — dokument mora pripadati baš tom predmetu |
| **G** | Obuhvata li delete tačno sve chunk-ove? | **DA** — dokazano na 1, 10 i 137 chunk-ova, uz proveru da brat-dokument i tuđa firma ostaju netaknuti |
| **H** | Je li delete idempotentan? | **DA** — drugi poziv vraća `ALREADY_ABSENT` i **ne širi obim** |
| **I** | Može li se delimičan delete prijaviti kao uspeh? | **NE** — `PARTIAL_FAILURE`; HTTP 200 nije dokaz |
| **J** | Može li se delete izvršiti bez autorizacije? | **NE** — kapija je prva, pre svega ostalog |
| **K** | Šta danas može biti fizički obrisano iz Pinecone-a? | **Ništa preko ovog servisa** — v. verdikt |
| **L** | Šta još ne može? | 30 orphan vektora (identitet nerekonstruktibilan), i svih 43 dokumenta (prazan `content_sha256`) |
| **M** | Tačan sledeći blokator? | **PINE-02: popuniti `content_sha256` za 43 postojeća dokumenta** — v. §Sledeći blokator |

---

# PHASE 0 — MATRICA IDENTITETA: 19 PISAČA

Nezavisan AST sweep (svaki `Call` sa `upsert*`/`delete*`, ceo repo, 0 parse
grešaka): 55 `upsert*` poziva → 34 Supabase, 2 u testu, **19 fizičkih Pinecone**.
Oba ranije promašena pisača su sada u listi; `interni_stavovi.py:89` je grep
promašio zbog aliasiranog uvoza (`ingest_stav as _ingest_stav`), a AST ga hvata
na mestu upserta gde alias ne igra ulogu.

| Grupa | Broj | Sadržaj |
|---|---|---|
| **A) kanonski** | **1** | `uploaded_doc/ingest.py:186` — **jedini pisač u repou koji uvozi `shared/vector_identity`** |
| **B) legacy, predvidiv ID** | **15** | `auto_discovery`, `batch_ingest`, `knowledge_base`, `law_upload`, + 11 CLI skripti |
| **C) nepredvidiv (`uuid4`)** | **3** | `interni_stavovi.py:89`, `drafting/playbook.py:94`, `ingest_misljenja.py:160` |

**18 od 19 proizvodi ID van kanonskog ugovora.** Podtipovi vredni imenovanja:

- **3 su `uuid4`** — identitet nepovratno izgubljen u trenutku upisa.
- **6 je deterministično ali SLEPO NA SADRŽAJ** — MD5 nad `v2|{zakon}|{clan}|{stav}`.
  Tekst zakona može da se promeni **u celosti**, a ID ostaje isti. To nije
  identitet sadržaja nego identitet mesta.
- **14 nema tenant binding.** Samo 1 ima `chunk_schema`.

---

# PHASE 1 — KARANTIN: 30 ORPHAN VEKTORA

## Dohvatljivost — NE, i to je dokazano na svih 5 putanja

**Presudni mehanizam** (`routers/dokument.py:194`): poredi se `uuid4().hex` —
32 heks znaka **bez crtica** (`uploaded_doc/session.py:7`) — sa `predmeti.id`,
UUID-om **sa crticama** od 36 znakova. **Dva disjunktna prostora ID-eva.**
Izmereno: **0 poklapanja od 19 predmeta**, i direktno i sa uklonjenim crticama →
bezuslovni 404 na `:197`, **pre** `validate_session` i **pre** `ask_agent`.

| Putanja | Zašto ne dohvata |
|---|---|
| `/pitanje`, `/klasifikuj-sesija` | gornji mehanizam |
| `/analiza`, `/rokovi` | hardkodovan `"tmp_"` prefiks |
| `kancelarija_namespace` (RAG) | strukturno uvek `kancelarija_*`/`user_*` |
| `cleanup_expired` | filtrira isključivo `tmp_` |
| glasovna putanja | ne postoji |

## Šesta putanja, koju nijedan raniji sprint nije naveo

`api.py:5985-5990` (`GET /api/predmeti/{id}/dokumenti/{dok_id}`) zove
`_fetch_session_tekst(session_id, "pred_")` **bez**
`_verify_pred_namespace_ownership`.

Autorizacija je ipak ispravna — namespace dolazi iz reda koji je već prošao
`.eq("user_id", uid)`, ne iz zahteva. Uz to je zatvaraju dve **merene** barijere:
**0/43** redova pokazuje na ijedan od 6 orphan namespace-ova, i **0/43** ima
prazan `tekst_sadrzaj` koji bi granu uopšte pokrenuo.

Prijavljujem je jer je oslonjena na disciplinu pozivaoca, ne na svojstvo funkcije.

## Zašto se ID ne može rekonstruisati — tri nezavisna razloga

1. **`scope` je nepoznat i neizvodiv** — nema veze ka predmetu.
2. **`verzija` je nerekonstruktibilna** — SHA-256 celog izvučenog teksta, a
   chunk-ovi se preklapaju (`OVERLAP_TOKENS=100`, mereno 31.600 → 36.428
   znakova) i `text` je skraćen na 40k. Original ne postoji.
3. **`chunk_schema` nije zabeležen.**

Nijedna od četiri kandidat-veze ka bazi ne postoji (sve izmerene, sve prazne):
`session_id`↔`predmeti.id` **0/19**; `pred_<sid>`↔`pinecone_namespace` **0/43**;
`content_sha256` — obe strane prazne; `source_filename`↔`naziv_fajla` **0/43**
(a i da ih ima, bilo bi nagađanje: 43 reda ima svega 19 različitih naziva).

**Klasifikacija: `ORPHAN_UNIDENTIFIABLE` za svih 30.** To je po dizajnu
**konačan ishod, ne međukorak ka brisanju** — vektor čiji identitet ne znamo se
ne briše nikad, jer bi to bilo pogađanje.

---

# PHASE 2 — KANONSKI DELETE

`shared/vector_deletion.py`. **Ulaz je `document_id`, nikad Pinecone vector ID
iz zahteva** — da funkcija prima ID spolja, autorizacija bi bila zaobiđena po
definiciji.

```
autorizovan pozivalac
  → kanonska kapija predmeta (vlasnik ILI aktivna delegacija)
  → red u bazi mora pripadati BAŠ tom predmetu
  → izvođenje identiteta (content_sha256 + prefiks_dokumenta)
  → listanje po prefiksu u izričitom namespace-u
  → provera da NIJEDAN vraćen ID nije van prefiksa
  → delete(ids=[...])
  → verifikacija ponovnim listanjem
```

`predmet_saradnici` **namerno nije uračunat** — kanonska kapija ga ne konsultuje,
pa bi ga uključiti značilo dati pravo **brisanja** koje pravo **čitanja** ne daje.

## Šest fail-closed tačaka, nijedna ne degradira u „obriši šta možeš"

| Uslov | Ishod |
|---|---|
| nema autorizacije | `REFUSED` |
| dokument nije u tom predmetu | `REFUSED` (404-semantika, bez proročišta) |
| `content_sha256` nije kanonskog oblika (legacy 64-znakovni heš) | `REFUSED` |
| listanje palo | `REFUSED` — „ne znam" nikad ne postaje „nema ničega" |
| ijedan ID van prefiksa | `REFUSED`, **bez ijednog brisanja** |
| verifikacija ne potvrdi | `PARTIAL_FAILURE` |

`delete_all` i `filter` se **nikad** ne koriste — test to izričito tvrdi.

---

# MUTATION RESULTS

| # | Mutacija | Ishod |
|---|---|---|
| A | ukloni tenant binding | **3 pada** |
| B | ukloni autorizaciju predmeta | **3 pada** |
| C | promeni namespace | **10 pada** |
| D | razbij izvođenje ID-a | **5 pada** |
| E | dozvoli proizvoljan dokument | **1 pada** |
| F | prazno umesto odbijanja pri padu listanja | **1 pada** |
| G | ukloni proveru prefiksa | **prvo 0 → test popravljen → 2 pada** |
| H | ukloni proveru praznog `content_sha256` | **0 — redundansa, v. dole** |
| I | ukloni proveru kanonskog oblika | **1 pada** |
| J | ukloni verifikaciju | **1 pada** |

## G je bila stvarna rupa u mojim testovima

Lažni indeks je uvek filtrirao ispravno, pa provera prefiksa nikad nije dolazila
na red. Ta provera postoji baš za slučaj da provajder vrati nešto van prefiksa.
Dodat je indeks koji se loše ponaša i podmeće ID iz **tuđeg namespace-a**; sada
mutacija obara 2 testa.

## H nije rupa nego redundansa — i to kažem kao nalaz, ne kao izgovor

Prazan `content_sha256` i dalje biva odbijen, samo drugom kapijom:
`proveri_kanonsku_verziju("")` diže izuzetak. Dve provere čuvaju isto svojstvo.
Svojstvo je zaštićeno; jedna linija je suvišna.

---

# PHASE 7 — READ-ONLY INVENTAR

```
ukupno:                   434.217 vektora, 11 namespace-ova
kanonski ID:              0
legacy ID:                434.217
uuid4 (bez identiteta):   104   (74 misljenja + 30 klijentskih)
orphan (klijentski):      30
```

Po uzorku metapodataka (721 vektor): **0 ima tenant binding, 0 ima `predmet_id`,
0 ima identitet dokumenta, 0 ima `chunk_schema`**; 417/721 nema ni `chunk_index`.

Ne postoji nijedan namespace koji kod aktivno piše: `kancelarija_*`, `user_*`,
`tmp_*`, `kb_*`, `interni_stavovi_*`, `playbook_*`, ni `__default__`.

---

# PHASE 9 — GDPR GRANICA

Reč **„obrisano" se koristi samo za fizičko uklanjanje.** Sve ostalo je
imenovano tačno.

| Sloj | Stanje |
|---|---|
| **DATABASE** | brisanje postoji za neke entitete; za dokument i predmet **endpoint ne postoji** |
| **STORAGE** | preživljava GDPR brisanje naloga (nalaz iz -002) |
| **PINECONE** | **fizički obrisivo: ništa preko ovog servisa danas.** 30 orphana → **karantin**, ne brisanje. 43 dokumenta → `REFUSED` |
| **PROVENANCE/AUDIT** | namerno nepromenljiv; nije predmet čl. 17 na isti način |
| **BACKUPS/RETENTION** | **UNKNOWN** — nije mereno u ovom sprintu |
| **THIRD-PARTY** | OpenAI retencija = politika provajdera, 0 tehničkih kontrola (nalaz iz -001) |

**„Nedohvatljivo" ≠ „obrisano".** 30 orphan vektora je dokazano nedohvatljivo
kroz aplikaciju, ali **fizički postoji kod Pinecone-a**. To se kancelariji mora
reći tako.

---

# OPEN FINDINGS

| ID | Nalaz | Nivo |
|---|---|---|
| **PINE-A** | `content_sha256` prazan na **43/43** → kanonsko brisanje primenljivo na **0** dokumenata | **RED** |
| **PINE-B** | **DELETE endpoint za dokument i predmet ne postoji** — servis nema pozivaoca | **RED** |
| **PINE-C** | `scripts/ingest_case_law.py:347,542` rade **`delete_all` nad celim `sudska_praksa`** (407.795 vektora), bez filtera po izvoru — briše i bilten i sudskapraksa.sud.rs vektore kao kolateralu | **HIGH** |
| **PINE-D** | tri različita sanitizera ID-a pišu u isti `sudska_praksa` namespace — isti `chunk_id` sa razmakom ili ćirilicom daje **tri različita** vektor ID-a | **HIGH** |
| **PINE-E** | `api.py:5985` čita `pred_*` bez `_verify_pred_namespace_ownership`; danas bezbedno kroz dve merene barijere, ali oslonjeno na disciplinu pozivaoca | MEDIUM |
| **PINE-F** | 30 orphana nema **nikakav mehanizam isteka** (`expires_at` prazan, `cleanup_expired` ih ne gleda) | MEDIUM |
| **PINE-G** | 6 pisača ima identitet **slep na sadržaj** (MD5 nad `v2\|{zakon}\|{clan}\|{stav}`) | MEDIUM |

---

# SLEDEĆI BLOKATOR — PINE-02

**Popuniti `content_sha256` za 43 postojeća dokumenta.**

To je jedina stavka koja pretvara ovaj servis iz „ispravnog i neprimenljivog" u
„primenljiv". Sve je za to spremno i mereno u ID-02: svih 43 su **kategorija A**
— `tekst_sadrzaj` je popunjen 43/43, pa se `verzija_dokumenta(tekst)` može
izračunati bez originalnog fajla.

**Ali to je izmena produkcionih podataka** i po §20 ovog mandata traži izričitu
potvrdu. Nisam je izveo.

Redosled posle toga: **PINE-03** — izložiti servis kroz autorizovan DELETE
endpoint (danas ne postoji nijedan za dokument ni predmet).

---

# ZAVRŠNA REČ

Sprint je isporučio ono što je tražio: dokaziv, autorizovan, deterministički i
verifikovan delete, sa karantinom umesto pogađanja.

Ali brojka koja opisuje stvarno stanje nije broj testova nego ova: **servis je
danas primenljiv na 0 od 43 dokumenta**, jer nijedan nema identitet u bazi, i
nema ga ko pozvati jer endpoint ne postoji.

To ne umanjuje vrednost — bez ovog sloja bi svaki pokušaj GDPR brisanja bio
`delete_all` nad kancelarijom. Ali GREEN bi bio netačan.
