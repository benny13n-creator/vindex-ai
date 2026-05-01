# VINDEX_REALITY.md — Dijagnoza sistema (2026-05-01)

Sve informacije prikupljene read-only analizom koda i živim upitima prema Pinecone/OpenAI.
Nijedan fajl nije izmenjen.

---

## 1. Deployment — stanje

| Parametar | Vrednost |
|---|---|
| Repozitorijum | `benny13n-creator/vindex-ai` (GitHub) |
| Stack | **FastAPI + Uvicorn** (nije Streamlit) |
| Deployment platforma | **Render** (auto-deploy iz `main` grane) |
| Frontend | Static HTML (`index.html`) serviran kroz FastAPI |
| Poslednji commit | `359c27c` — feat: remove TTS/voice feature completely |

**Konfigurisani servisi:**
- `POST /api/pitanje` — glavna RAG pretraga
- `POST /api/stream` — streaming verzija
- `POST /api/nacrt` / `POST /api/analiza` — dokumenti
- `POST /api/bot/ask` — Telegram bot endpoint (API key auth)
- Auth: Supabase JWT + kredit sistem

**Da li je live?** Na osnovu nedavnih push-ova i Render konfiguracije — da, servis je deployovan. Direktna HTTP provjera nije rađena (nije traženo).

---

## 2. Pinecone — stvarno stanje

### Statistike indeksa

| Parametar | Vrednost |
|---|---|
| Naziv indeksa | `vindex-ai` |
| Host | `vindex-ai-t8z679r.svc.aped-4627-b74a.pinecone.io` |
| **Ukupno vektora** | **9.724** |
| Dimenzija | 3.072 (text-embedding-3-large) |
| Metrika | cosine |
| Cloud/Region | AWS us-east-1 (serverless) |
| Namespace | `__default__` jedini, svi vektori unutar njega |

### Sample 3 vektora (zero-vector query, top 3)

**Vektor 1** — `001422e5`
```
law:     zakon o bezbednosti saobracaja na putevima
article: Član 14
text:    Vlada podnosi Narodnoj skupštini izveštaj o stanju bezbednosti saobraćaja...
parent_text: NEMA
```

**Vektor 2** — `001c60b4`
```
law:     zakon o arbitrazi
article: Član 42
text:    Ako se stranke nisu drukčije sporazumele i ako bez navođenja opravdanih razloga...
parent_text: NEMA
```

**Vektor 3** — `002483bb`
```
law:     zakon o bankama
article: Član 139
text:    Novčanom kaznom od 50.000 do 150.000 dinara kazniće se za prekršaj...
parent_text: NEMA
```

### Kritičan nalaz

> **Vektori NEMAJU `parent_text` polje.** Svaki vektor je jedan stav (paragraf) izvučen iz člana zakona — bez konteksta celog člana. Polje `text` sadrži samo taj jedan stav, najčešće 1–3 rečenice.

Metadata struktura: `{ law, article, source, text }` — bez `parent_text`.

Kod u `retrieve.py` traži `parent_text` i pada na `text` ako ga nema — ali to nije pravi problem (fallback radi). Problem je što je **semantičko podudaranje veoma loše** jer stav bez konteksta nema dovoljno informacija za precizno pronalaženje.

---

## 3. Retrieval pipeline — live test

### Upit: `"Koja je kazna za krađu prema Krivičnom zakoniku?"`

#### Korak 1 — Klasifikacija upita
```
DEFINICIJA (default)
```
**BUG**: Pitanje o kazni u KZ trebalo bi biti klasifikovano kao `PARNICA` ili posebna KZ kategorija, ne `DEFINICIJA`. Klasifikator ne prepoznaje krivičnopravna pitanja i pada na default koji koristi `gpt-4o-mini` (slabiji model, manji `max_tokens`).

#### Korak 2 — Query expansion (Multi-Query + HyDE)
- gpt-4o-mini razložio na 3 pod-pitanja ✓
- HyDE generisao hipotetički zakonski tekst ✓
- GPT-4o-mini generisao 4 search query-ja ✓

Ekspanzija radi ispravno. Problem nije ovde.

#### Korak 3 — Pinecone retrieval (top 5 za originalni query)

| # | Score | Zakon | Član | Tekst (preview) |
|---|---|---|---|---|
| 1 | 0.5874 | KZ | Član 348 | Ko neovlašćeno nosi predmete dela iz st. 1. i 2... |
| 2 | 0.5785 | KZ | Član 293 | Ako je usled dela iz stava 1. nastupila smrt... (piratstvo) |
| 3 | 0.5769 | KZ | Član 48 | Za krivična dela učinjena iz koristoljublja... |
| 4 | 0.5753 | KZ | Član 292 | Ko preti izvršenjem dela iz stava 1... |
| 5 | 0.5724 | KZ | Član 348 | Ko neovlašćeno nosi predmete... |

**Pinecone vraća rezultate ali POGREŠNE.** Nijedan od top-5 rezultata nije o krađi. `Član 203 KZ` (osnovna krađa) **ne postoji u indeksu**.

Proverom sa theft-specifičnim query-jem (`kradja imovinska korist protivpravno prisvajanje`), ni tada se ne vraća Član 203. KZ članci u indeksu su uglavnom: 10, 48, 288, 292, 293, 294, 348, 350 — oružje, piratstvo, opšta krivična pravila.

#### Korak 4 — CRAG ocena relevantnosti
```
CRAG: NIJE RELEVANTNO (iteracija 1)
```
CRAG **ispravno** detektuje da vraćeni dokumenti ne odgovaraju na pitanje. Aktivira HyDE fallback.

#### Korak 5 — HyDE fallback
HyDE donosi 10 novih dokumenata, ali i oni su iz istog skupa pogrešnih KZ članova (Član 348 ostaje top rezultat).

#### Korak 6 — LLM generisanje
```
kontekst_docs=10 | kontekst_chars=13.563 | model=gpt-4o-mini
```

Kontekst **jeste** poslat LLM-u — RAG nije "prazan" u tehničkom smislu. Ali sadržaj je pogrešan.

#### Korak 7 — LLM odgovor (stvarni)
```
[✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.

--- HIJERARHIJA IZVORA
Lex specialis: Krivični zakon ima prednost za ovu oblast.

--- PRAVNI ZAKLJUČAK
Kazna za krađu, u smislu neovlašćenog nošenja predmeta, može biti zatvor od šest
meseci do pet godina...

--- CITAT ZAKONA [RAG]
"Krivični zakon, član 348: (5) Ko neovlašćeno nosi predmete dela iz stava 1. ovog
člana za čije nabavljanje i držanje ima odobrenje nadležnog organa, kazniće se
zatvorom od šest meseci do pet godina."

--- PRAVNI OSNOV
Krivični zakon, član 348 → reguliše krivična dela vezana za neovlašćeno nošenje
vatrenog oružja, municije i eksplozivnih materija.
```

**LLM je citirao KZ Član 348 (nošenje oružja) kao odgovor na pitanje o krađi.** To je halucinacija na nivou relevantnosti — LLM je tehnički citirao tačan tekst koji postoji u kontekstu, ali taj tekst ne odgovara na postavljeno pitanje.

Anti-halucinacijska provera to **nije uhvatila** jer Član 348 jeste u kontekstu (`_proveri_halucinaciju` proverava da li su citirani članovi prisutni u kontekstu, i jesu — problem je što su to pogrešni članovi).

---

## 4. RAG field — rendering

Frontend **ispravno renderuje** sve `--- SEKCIJA` blokove uključujući `--- CITAT ZAKONA [RAG]`. CSS i JS parser rade kako treba.

Kada je odgovor `ODGOVOR_NIJE_PRONADJEN`, RAG polje prikazuje `[—]` što je ispravno.

**RAG field nije broken. Prikazuje ono što LLM vrati — problem je što LLM vrati pogrešan sadržaj.**

---

## 5. Verdict

### Odgovor: D) Nešto sasvim drugo

Nije problem A (rendering), nije B (Pinecone prazan), nije C (context dropovan).

### Stvarni uzroci (od najbitnijeg):

**Uzrok 1 — Nepotpun KZ indeks (kritično)**
Krivični zakonik je DELIMIČNO indeksiran. U 9.724 vektora, od KZ-a postoje uglavnom članovi o oružju (348, 350), piratstvu (292–294) i opštim odredbama (48, 10). **Clan 203 (osnovna krađa), Član 204 (teška krađa), Član 205 (prevara), Član 208 (utaja) i mnogi drugi imovinski delikti nisu indeksirani.**

**Uzrok 2 — Stav-level chunking bez parent_text**
Vektori su pojedinačni stavovi (1–3 rečenice) bez `parent_text`. Semantic similarity za pravne upite je ~0.57–0.59 — veoma nisko. Sistem ne može pouzdano da pronađe relevantan član jer su chunk-ovi premali za smisaono podudaranje.

**Uzrok 3 — Pogrešna klasifikacija KZ pitanja**
"Kazna za krađu" → klasifikovan kao `DEFINICIJA` umesto `PARNICA`. To znači: pogrešan system prompt, gpt-4o-mini umesto gpt-4o, i manji max_tokens. Krivično pravo nema sopstveni tip u klasifikatoru.

**Uzrok 4 — Anti-halucinacijska provera ne hvata ovo**
`_proveri_halucinaciju` proverava da li su citirani membri prisutni u kontekstu — jesu (Član 348 je tu). Ne proverava da li su relevantni za pitanje. False positive.

**Uzrok 5 — CRAG ispravno detektuje ali ne može popraviti**
CRAG ocenjuje kao "NIJE RELEVANTNO" i pokušava HyDE fallback — ali HyDE donosi iste KZ vektore jer su to jedini KZ vektori u indeksu.

### Šta treba da se uradi:

1. **Reingestovati kompletan Krivični zakonik** — svi imovinski delikti (Gl. 20: čl. 203–244), krivična dela protiv života (Gl. 16), itd.
2. **Dodati `parent_text` pri ingestu** — ceo član (sve stavove zajedno) čuvati kao `parent_text`, a svaki stav kao chunk za embedding. Ovo postoji u `reindex_agentic.py` ali nije primenjeno na sve zakone.
3. **Dodati KZ kao poseban tip klasifikacije** ili osigurati da KZ pitanja dobiju `gpt-4o` + odgovarajući prompt.
4. **Proširiti anti-halucinacijsku proveru** da detektuje relevantnost konteksta, ne samo prisutnost citiranog člana.

---

*Generisano: 2026-05-01 | Metod: statička analiza koda + live Pinecone/OpenAI upiti (read-only)*
