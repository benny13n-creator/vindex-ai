# Model Independence Report — Program Beta (Masterprompt 002), Phase 8

**Pitanje:** ako GPT (OpenAI) sutra prestane da postoji, da li platforma
ostaje ista, ili se poslovna logika mora menjati?

## Nalaz: poslovna logika je model-nezavisna. Infrastruktura nije (potpuno).

Ovo je namerno razdvojeno pitanje. Cela ova misija je, u suštini, dokaz da
je odgovor na prvi deo "da" tamo gde je princip primenjen, i imenovanje
konkretnih mesta gde još nije.

### Poslovna logika — potvrđeno model-nezavisna (3 nezavisna dokaza)

Svaki deterministički mehanizam katalogizovan u
`CONFIDENCE_MODEL_SPECIFICATION.md` radi identično bez obzira koji model je
proizveo ULAZNE činjenice:

- `compute_snaga_score()` — ne zna niti mari da li je `snaga_faktori` došao
  od gpt-4o, Claude, Gemini ili lokalnog modela. Radi nad JSON strukturom.
- `_calc_confidence_nivo()`/`_procenat_iz_score()` (Court Predictor) — isto.
- `validate_dok_reference()`, `_snaga_iz_lokacije()` (implementirano ovom
  misijom) — potpuno model-nezavisni po dizajnu, čist Python nad tekstom.
- `_lociraj_tvrdnju()`, `verify_genome()`, `quality_gate` — svi rade nad
  TEKSTU ili STRUKTURIRANOM IZLAZU, nikad nad modelom samim.

**Zaključak:** gde god je Program Beta-in princip ("LLM rezonuje, platforma
računa") već primenjen, promena modela zahteva ZERO promena poslovne
logike — samo promenu ko generiše ulazne JSON faktore.

### Infrastruktura — 3 konkretna, imenovana coupling tačke

1. **`shared/ai_client.py::_patch_openai_module()`** — kanonski wrapper
   (Mission Atlas) STRUKTURNO patch-uje `openai` Python modul (ne
   zahteva da svako pozivno mesto eksplicitno zove wrapper funkciju — zato
   ~130 poziva mesta širom repoa dobijaju provenance/audit "besplatno").
   Ovo je snažan dizajn ZA OpenAI-kompatibilan svet (već dokazano radi za
   Azure OpenAI deployment mapping — vidi modul docstring, "gpt-4o" →
   Azure deployment "gpt-4o", isti SDK/protokol) ali je SDK-specifičan:
   zamena za Claude/Gemini/lokalni model bi zahtevala PONOVNU implementaciju
   iste strukturne patch tehnike za taj SDK, ne samo promenu konfiguracije.
   **Infrastruktura-nivo trošak, ne poslovna logika.**
2. **`response_format={"type": "json_object"}`** — OpenAI-specifičan API
   parametar, korišćen na svakom mestu koji traži strukturiran JSON izlaz
   (case_dna.py, strategija.py, evidence.py, main.py, retrieve.py — desetine
   poziva). Zamena modela bi zahtevala ekvivalentan mehanizam za novi
   provider (npr. Claude tool-use forced JSON, ili čisto prompt-based JSON
   sa parsing fallback-om koji retrieve.py već ima kao obrazac —
   `json.loads` sa `except JSONDecodeError`).
3. **Model-ime stringovi hardkodovani po pozivnom mestu** (`"gpt-4o"`,
   `"gpt-4o-mini"`) — NIJE centralizovano kao jedna konfiguracija (za
   razliku od `EMBEDDING_MODEL` konstante koju je Program Alpha
   kanonizovao). Zamena modela = find-and-replace kroz 100+ poziva mesta,
   ne izmena jedne promenljive. Ovo je real, boring infrastrukturni dug —
   nazvan ovde, implementacija van scope-a Programa Beta (nije AI-rezonovanje
   defekt, to je konfiguracija-management defekt, isti tip posla koji je
   Program Alpha uradio za embedding model).
4. **Embedding model** (`text-embedding-3-large`) — odvojena zavisnost od
   chat/completion modela. RAG retrieval je već arhitektonski odvojen od
   generacije (retrieve pa reason), pa promena LLM-a NE zahteva promenu
   embedding modela — ali potpuni nestanak OpenAI-ja bi zahtevao i ovo,
   nazvano radi kompletnosti.

## Šta OVA misija NIJE otkrila (bitno negativno)

Nijedan poslovni princip, pravno rezonovanje, ili odluka-tok NIJE nađen
kako zavisi od specifičnog ponašanja GPT-4o modela (npr. specifičan prompt
trik koji radi samo za taj model, ili poslovno pravilo izraženo kao "GPT
uvek vraća X"). Svaka non-deterministička vrednost katalogizovana u ovoj
misiji (Strategy Engine 4 procenta, Genome heatmap) je problem ZATO ŠTO je
prepuštena LLM-u bez ikakvog deterministic check-a — ne zato što bi
specifično GPT ponašanje bilo ugrađeno u poslovnu logiku. Popravka za oba
tipa nalaza je ISTA (deterministic post-processing), što je samo po sebi
dokaz modela-nezavisnog dizajna principa.

## Zaključak

**Platforma NIJE danas 100% model-nezavisna — ali gap je isključivo
infrastrukturni (SDK interception, JSON-format parametar, hardkodovana
imena), nikad poslovno-logički.** Zamena modela sutra bi bio realan, ne
trivijalan inženjerski posao (procenjeno: reimplementacija `_patch_openai_
module()`-ekvivalenta za novi SDK, find-and-replace modela imena, JSON-
format fallback strategija) — ali ZERO promena bi bila potrebna u bilo kom
`compute_*()`/`validate_*()`/`verify_*()` deterministic mehanizmu, i ZERO
promena u pravnoj metodologiji ili odluka-toku. Ovo je tačno stanje koje
misija cilja: "ako se menja LLM, ne menja se poslovni princip" — potvrđeno
tačno tamo gde je princip primenjen, imenovano gde nije.
