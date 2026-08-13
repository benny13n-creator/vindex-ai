# BETA-DATA-CONFIDENTIALITY-001 — FINAL FORENSIC REPORT

# VERDICT

## 🔴 RED

Jedan eksploatabilan bypass poverljivosti je nađen, dokazan merenjem i
**zatvoren** u ovom sprintu. Ali ostaje više od jednog nalaza koji sprečava da
se advokatskoj kancelariji pošteno kaže da su dokumenti zaštićeni — uključujući
**jedan `UNKNOWN` koji može biti CRITICAL**, a koji se ne može razrešiti iz koda.

```
baseline:  0df948ec
testovi:   5255 → 5265 passed / 2 skipped / 0 failed
izmena:    1 produkcijski fajl (P0 popravka), 1 nov test fajl
migracija: NULA · mutacija produkcionih podataka: NULA
```

---

# DATA FLOW

`upload → validacija → Storage → ekstrakcija/OCR → chunking → embedding →
vezivanje za predmet → AI → provenance → UI` — mapirano u
`docs/security/DATA_FLOW_MAP.md` (751 linija).

**Postoje četiri puta za upload.** Tri šifruju pre slanja u Storage
(`api.py:5049`, `smart_intake.py:184`, `klijenti/router.py:798`).
**Četvrti ne šifruje ništa** — v. `CONF-002`.

---

# CRITICAL FINDINGS

## CONF-001 — prompt guard je bio slep iza 60.000 znakova · **ZATVORENO**

| | |
|---|---|
| **IZVOR** | otpremljen PDF/DOCX klijenta ili protivne strane |
| **TIP** | sadržaj dokumenta kao kanal instrukcija |
| **ULAZ** | `security/prompt_guard.py:176` — `normalized[:MAX_INPUT_CHARS]` |
| **IZLAZ** | pun tekst ka OpenAI-ju (`ask_analiza` ne skraćuje) |
| **KONTROLA** | prompt guard — **nije se izvršavao nad ostatkom** |
| **DOKAZ** | mereno znak po znak: `59.900 → blocked=True, score=1.00`; **`60.100 → blocked=False, score=0.00`**; `200.000 → 0.00` |

**Zašto je ovo ozbiljno baš ovde:** 60.000 znakova je ~25–30 strana. Ugovori i
presude to rutinski prelaze. Napad ne traži pristup sistemu — protivna strana
pošalje advokatu dokument sa uputstvom na 40. strani, advokat ga otpremi, guard
ne vidi ništa, a model dobije uputstvo doslovno.

**Popravka (jedini kod dirnut u ovom sprintu):** ceo tekst se skenira u
**preklapajućim prozorima** — isti obrasci, isti pragovi, isti sloj. Nije uveden
nov sistem zaštite; uklonjena je slepa tačka postojećeg.

Posle popravke:
```
60.100 / 80.000 / 200.000 zn.   → blocked=True
čist dokument od 288.000 zn.    → blocked=False   (nema lažnog pozitiva)
injekcija na spoju prozora      → blocked=True    (preklapanje radi)
cena za 500.000 zn.             → 0,40 s
```
Mutacija (vraćena slepa tačka) obara **3 testa**.

## CONF-002 — klijentski portal čuva originale **nešifrovano** · OTVORENO

| | |
|---|---|
| **IZVOR** | `routers/client_portal.py:591-599` |
| **KONTROLA** | **nijedna** — jedini od 4 upload puta bez kriptografskog koraka |
| **POGORŠANJE** | `:701-705` pravi **60-minutni signed URL** ka tom nešifrovanom blobu |
| **DODATNO** | putanja je `{uuid}_{ime_fajla}` — a `crypto.py:10` izričito propisuje „nikad ime fajla" |

To je put kojim **klijent, a ne advokat**, šalje dokumente — dakle strana koja
najmanje kontroliše bezbednost.

## CONF-003 — privatnost bucket-a se **ne može dokazati iz koda** · `UNKNOWN`

| Bucket | Dokaz |
|---|---|
| `intake-dokumenti` | `migrations/073:362` deklariše `public=false` — ali sa `ON CONFLICT DO NOTHING`; ako je ranije ručno napravljen kao javan, migracija ga **ne ispravlja** |
| `portal-uploads` | `migrations/013:5` — uputstvo čoveku u SQL komentaru, ne naredba |
| `klijent-dokumenti` | nijedna migracija, nijedan `CREATE POLICY ON storage.objects` u celom repou |

**Ako je ijedan javan, CONF-002 postaje neposredno curenje.** Rešava jedan upit:
`SELECT id, public FROM storage.buckets;`

---

# HIGH

| ID | Nalaz | Dokaz |
|---|---|---|
| **CONF-004** | **Pinecone čuva pun neredigovan tekst dokumenta** — do 40.000 zn. po vektoru, plus naziv fajla i `user_id`, trajno, kod treće strane | `uploaded_doc/ingest.py:79-101`; `uploaded_doc/` ne pominje `_skini_pii` nijednom |
| **CONF-005** | **AAD je `None` na svih 5 mesta** — ciphertext nije vezan za red; šifrovan JMBG klijenta A može se premestiti u red klijenta B i dešifrovaće se čisto | `security/crypto.py` |
| **CONF-006** | **`kid` se parsira i baca** — rotacija ključa trajno uništava sve postojeće podatke | `crypto.py:190-198` |
| **CONF-007** | `api_kljucevi.kljuc` čuvan **u čistom obliku**, dok `hash_password()` (Argon2id) postoji u istom modulu i imenuje baš taj slučaj — nikad priključen | — |
| **CONF-008** | **`PUT /api/users/{target_user_id}/role` bez ijedne provere vlasništva** — partner jedne kancelarije menja ulogu korisnika druge. Izmereno: 200 OK, red promenjen; žrtva gubi `download_document` i `access_confidential` **nad sopstvenim klijentima** | `klijenti/router.py:1196` |
| **CONF-009** | **Write-side IDOR** — `POST /api/zadaci/kreiraj` prima tuđi `predmet_id`; `GET /api/zadaci/moji` zatim vrati `predmeti(naziv)` embed → **naziv tuđeg predmeta stiže napadaču**. Isti obrazac ubacuje napadačev red u spisak žrtve | `routers/zadaci.py:143` |
| **CONF-010** | Neproveren upis u `predmet_istorija` (`api.py:3377`, `:4895`) + čitanje bez `user_id` (`:4154`) → **tuđi tekst se pojavljuje u pravnom spisu žrtve kao njena AI istorija**. `api.py:4372` na istoj tabeli **ima** proveru — jedan pisač zaštićen, dva nisu | — |
| **CONF-011** | **Strategijske putanje šalju JMBG i PIB u čistom obliku** ka OpenAI-ju, plus privatnu belešku advokata. `_skini_pii` pokriva samo `/api/analiza`: **84 AI pozivna mesta, 75 (89%) u fajlovima koji ga uopšte ne pominju** | — |

---

# MEDIUM

- **`wrap_for_ai()` — deklarisani „Sloj 4: izolacija" — je mrtav kod**, nula
  poziva u produkciji. Docstring `analyze()` se na njega poziva kao na aktivnu
  odbranu: *„Sloj izolacije u wrap_for_ai() ostaje aktivan nezavisno od
  rezultata detekcije."* To više nije tačno.
- **`sanitize_for_ai()` ne postoji.** `security.prompt_guard.sanitize_prompt`
  takođe ne postoji — `ai_fabric.py:535` ga guta u `except ImportError: pass`.
- **Nema nijednog redaktujućeg log filtera.** Aktivno cure: ceo LLM odgovor
  (`api.py:3398`, ERROR), 200 zn. sadržaja dokumenta na **svakom** RAG pozivu
  (`retrieve.py:2204`, INFO), sirovo pitanje na 7 mesta, puni e-mailovi na ~15.
  Sentry ima `send_default_pii=False`, ali **nema `before_send`**.
- **`InvalidTag` se guta** i vraća kao string `[GREŠKA DEKRIPTOVANJA]` — napad
  izmenom ciphertext-a je detektovan, a nevidljiv.
- **Privremeni fajlovi**: 5 mesta, sva `delete=False` + `finally: unlink()`, ali
  `except Exception: pass` — neuspelo brisanje ne ostavlja trag. Kod
  `intake_worker.py:213` i `smart_intake.py:1276` fajl sadrži **dešifrovan**
  blob: sadržaj namerno zaštićen u Storage-u izlazi iz te zaštite na lokalni disk.
- **Drugi, paralelni portal** — `privremeni_pristup` (`saradnja.py:416`): token
  u bazi u čistom obliku, u URL-u, do 168h, **bez ijedne putanje opoziva**
  (`iskoriscen` se proverava ali ga nijedan kod ne postavlja).
- **EmailJS** se učitava sa CDN-a i inicijalizuje (`vindex.js:1066`), a
  **`send` se ne poziva nijednom** — treća strana izvršava kod na stranici koja
  prikazuje privilegovane dokumente, bez ijedne svrhe.

---

# LOW

- CDN-ovi (`cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, `unpkg.com`) vide IP
  adresu svakog advokata. **SRI postoji na 6/6 izvršnih resursa**, CSP ima
  `frame-ancestors 'none'` i `report-uri` — supply-chain rizik je smanjen.
- `script-src` sadrži `'unsafe-inline'` — praktično iznuđeno arhitekturom
  (620 inline `onclick` u `index.html`).

---

# ŠTO JE DOKAZANO **ISPRAVNO** (ne sve je problem)

| Kontrola | Dokaz |
|---|---|
| **AES-GCM nonce** | `os.urandom(12)`, 100.000 uzoraka: **0 kolizija**, entropija 7,99788/8,0 bita/bajt, nezavisni procesi daju različite nizove (bitno jer gunicorn forkuje). **NIJE CRITICAL** |
| **Auth tag** | stvarno se proverava — `InvalidTag` na oba tamper testa |
| **IDOR na čitanju dokumenata** | 15 ruta ODBIJENO (404), uz kontrolni test koji dokazuje da 404 dolazi od koda a ne od praznog stub-a. **Nijedna ruta koja vraća dokument ne curi** |
| **Klijentski portal** | falsifikovan token → 401; opozvan → 401; istekao → 401. `predmet_id` postoji samo unutar HMAC payload-a. Klijent **ne vidi nijedan dokument** |
| **`case_actions`** (nema `user_id`) | izolacija je izvedena i danas ispravna — svih 15 čitalaca prvo razreši vlasnikove `predmet_ids` pa radi `.in_()` |
| **OCR** | **lokalan** (`pytesseract`) — nema cloud OCR provajdera |
| **Prompt/odgovor u provenance** | isključivo SHA-256; `retrieval_query` jeste projektovan kao sirov tekst ali ima **nula produkcijskih pozivalaca** — latentno, ne aktivno |
| **Frontend analytics** | **nula** |
| **Generisani PDF/DOCX/ZIP** | rade u `io.BytesIO`, ne dodiruju disk |

---

# OPENAI DATA BOUNDARY

Mandat traži da se razdvoji **Vindex kontrola** od **politike provajdera**.

## Vindex tehnička kontrola

| | |
|---|---|
| šta se šalje | pun tekst dokumenta, imena stranaka, firme, adrese, sadržaj predmeta |
| maskirano | JMBG, PIB, e-mail, telefon, IBAN, LK, broj predmeta — **samo na `/api/analiza`** |
| modeli | `gpt-4o-mini` (53 mesta), `gpt-4o` (44), `whisper-1`, `tts-1` |
| ulazni guard | da (sada i preko 60k) |
| izlazni firewall | da, na chat putanjama |

## Kontrola provajdera — **NIJEDNA nije podešena iz koda**

Pretraga celog repoa: **nema `store=False`, nema zero-retention endpointa, nema
org/project zaglavlja.** Dakle retencija kod OpenAI-ja počiva **100% na politici
provajdera**, a **0% na tehničkoj kontroli Vindexa**.

To je činjenica koja se mora reći kancelariji doslovno tako — ne kao
„OpenAI ne trenira na našim podacima".

---

# TREĆE STRANE

| Servis | Obavezan | Šta odlazi |
|---|---|---|
| OpenAI | DA | v. gore |
| Pinecone | DA | **pun tekst dokumenta**, do 40.000 zn./vektor, trajno |
| Supabase | DA | sve — baza i Storage |
| Cohere | ne (3 uslova, nije u `requirements.txt`) | rerank upiti |
| Sentry, SMTP, Twilio, Viber, Push, GCal | isključeni po defaultu | — |
| **EmailJS** | **ne — učitan i inicijalizovan, nikad korišćen** | ništa (ali izvršava kod) |
| CDN-ovi | de facto da | IP adresa korisnika |

---

# COMPROMISE MATRIX (sažeto)

| Scenario | Šta napadač vidi | Šta ga zaustavlja |
|---|---|---|
| **A. čitanje baze** | pun tekst dokumenata (`tekst_sadrzaj`), AI istorija, beleške, IP adrese | ništa — samo 6 polja je šifrovano |
| **B. čitanje Storage-a** | `portal-uploads` **u čistom obliku**; druga dva bucket-a šifrovana | AES-GCM na 3 od 4 puta |
| **C. korisnička sesija** | svoje podatke; **+ naziv tuđeg predmeta** (CONF-009) | provera vlasništva na čitanju dokumenata |
| **D. A traži B dokument** | **ništa** — 15/15 odbijeno | dokazano merenjem |
| **K. procureo signed URL** | jedan nešifrovan original, 60 min | TTL |
| **L. ukraden ključ** | svih 6 šifrovanih polja, **zauvek** — rotacija nije moguća (CONF-006) | — |
| **H/I. provajder** | sve što je poslato — v. OpenAI boundary | nijedna Vindex kontrola |

---

# ADVERSARIAL PASS

Meta nije bila arhitektura nego **najjača tvrdnja ovog izveštaja**: *„dokument
od 200 strana više ne može da prokrijumčari uputstvo kroz prompt guard."*

## Napad 1 — „guard čita samo pitanje, ne dokument"

`shared/ai_client.py:251 _extract_user_text()` prosleđuje guardu **isključivo
`user` poruke**. Da tekst dokumenta ide u `system` poruku, popravka CONF-001 ne
bi imala nikakve veze sa dokumentima i ovaj izveštaj bi bio pogrešan.

Mereno statički pa **potvrđeno runtime-om**, sa špijunom na `_extract_user_text`:

```
dokument+injekcija ~125.000 zn., jedna user poruka  → BLOKIRANO,  guard video 125.073 zn.
kontekst i pitanje kao DVE user poruke              → BLOKIRANO,  guard video 125.079 zn.
čist dokument ~125.000 zn.                          → propušten,  guard video 125.011 zn.
```

Guard vidi **ceo** dokument (125k > 60k), blokira injekciju bez obzira na dubinu,
i ne blokira čist tekst. **Napad odbijen — tvrdnja stoji.**

## Napad 2 — injekcija u `system` poruci · **PROLAZI**

```
injekcija u system poruci  → NIJE blokirano,  guard video 10 zn.
```

To je **ugovor, ne kvar**: `system` poruke piše autor rute, ne korisnik. Ali
ugovor je bio nezapisan, pa ga ovde fiksiram kao merenu zavisnost:

> **CONF-012 (LOW, uslovno):** poverljivost počiva na tome da nijedan sadržaj
> koji potiče od korisnika ili dokumenta ne završi u `system` poruci. Mereno na
> 6 modula: **0 od 8 mesta** stavlja tekst dokumenta u `system` — svih 8 ide u
> `user`. Danas tačno. Prvi `system` prompt sastavljen sa korisničkim tekstom
> tiho poništava CONF-001.

## Napad 3 — nusproizvod sonde: provenance pada bez korisnika

Sonda je slučajno pokazala nešto što nije bilo predmet audita:

```
[FORENSICS] provenance NIJE upisan — trag je izgubljen:
  null value in column "user_id" ... violates not-null constraint (23502)
```

AI poziv bez korisničkog konteksta (pozadinski posao, skripta, cron) **ne ostavlja
nijedan forenzički trag** — `INSERT` odbija baza. Prijavljeno, nije popravljeno
(van scope-a ovog sprinta, i tiče se audita a ne poverljivosti).

**Nula redova upisano u produkciju** — oba pokušaja odbijena sa 400 pre nastanka
reda; nijedan `UPDATE`/`DELETE` nije ni pokušan.

---

# REGRESSION

```
targeted (CONF-001):  10 passed
full suite:           5265 passed / 2 skipped / 0 failed
```

Nijedan test nije oslabljen ni prilagođen. Mutacija P0 popravke obara 3 testa.

---

# FINAL QUESTION

> *„Možemo li pošteno reći beta kancelariji da su njeni klijentski dokumenti
> zaštićeni Vindexovim tehničkim kontrolama, i možemo li precizno objasniti šta
> napušta Vindex infrastrukturu i zašto?"*

## **NE.**

**Drugi deo pitanja — da.** Sada tačno znamo šta odlazi, kome i u kom obliku, i
to je zapisano u tri dokumenta ovog sprinta.

**Prvi deo — ne**, dok se ne zatvori sledeće:

1. **`SELECT id, public FROM storage.buckets;`** — jedan upit. Dok se ne zna da
   li su bucket-i privatni, ne sme se tvrditi da su dokumenti zaštićeni.
2. **CONF-002** — klijentski portal mora da šifruje kao ostala tri puta.
3. **CONF-008/009/010** — tri provere vlasništva, po obrascu koji `api.py:4372`
   već ima u istom fajlu.
4. **Formulacija prema kancelariji** mora razdvojiti Vindex kontrolu od politike
   OpenAI-ja i Pinecone-a. Pun tekst dokumenta trajno stoji kod Pinecone-a —
   to nije detalj koji se prećutkuje.

Ono što se **već sada sme reći bez ograde**: dokument koji advokat otpremi kroz
aplikaciju šifruje se pre skladištenja, drugi korisnik ga ne može dohvatiti
(mereno na 15 ruta), klijentski portal ne izlaže nijedan dokument, OCR je
lokalan, a od ovog sprinta ni dokument od 200 strana više ne može da prokrijumčari
uputstvo kroz prompt guard — što je jedina tvrdnja ovde koja je potvrđena i
runtime merenjem, a ne samo čitanjem koda.
