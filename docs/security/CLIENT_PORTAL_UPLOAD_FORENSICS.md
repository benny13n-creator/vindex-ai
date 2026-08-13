# CLIENT PORTAL UPLOAD — FORENZIKA

**Datum:** 2026-08-13
**Obim:** `routers/client_portal.py` upload put + uporedna analiza SVIH Supabase Storage upload puteva
**Status izmena:** NIJEDAN produkcijski fajl nije menjan. Ovo je isključivo nalaz i dokaz.
**Metod:** čitanje koda (fajl:linija) + izvršni dokaz (privremene skripte u scratchpad-u, nisu commit-ovane)

---

## 0. Rezime u jednoj rečenici

`portal-uploads` je **jedini** od tri bucket-a koji prima **nešifrovane** bajtove, i to je jedini
bucket u koji piše **neautentifikovana spoljna strana** (klijent bez logina), sa **PII-jem u samom
imenu objekta**, a jedini način da se fajl pročita je **signed URL koji potpuno zaobilazi
aplikaciju**. Izmereno, ne pretpostavljeno.

---

## 1. Tačne linije (verifikovane, ne preuzete iz ranijeg sprinta)

| Šta | Fajl:linija |
|---|---|
| Ruta `POST /api/client-portal/dokument` | `routers/client_portal.py:514-521` |
| Čitanje bajtova | `routers/client_portal.py:563` (`sadrzaj = await fajl.read()`) |
| Konstrukcija imena objekta | `routers/client_portal.py:586-588` |
| **Upload u storage** | `routers/client_portal.py:591-599` (`bucket.upload(...)` na `:594`) |
| DB insert metapodataka | `routers/client_portal.py:609-621` |
| Log sa imenom fajla | `routers/client_portal.py:643` |
| Email advokatu sa imenom fajla | `routers/client_portal.py:646` → `:160-181` |
| **Signed URL** | `routers/client_portal.py:701-705` (`create_signed_url(_p, 3600)` na `:703`) |
| Brisanje iz storage-a | `routers/client_portal.py:779` |

Zadatak je pominjao „oko linije 591 (upload) i oko 701 (signed URL)" — **potvrđeno tačno**:
`bucket = supa.storage.from_("portal-uploads")` je na `:591`, sam `upload(` poziv na `:594`;
`create_signed_url` na `:703`.

---

## 2. Odgovori na 9 pitanja

### 2.1 Šta se tačno uploaduje — original ili transformisan?

**ORIGINALNI, NETAKNUTI BAJTOVI.** Između `await fajl.read()` (`:563`) i `bucket.upload(file=sadrzaj)`
(`:594-596`) ne postoji nijedna transformacija — samo provere veličine (`:564`), praznine (`:569`)
i magic-bytes (`:580-583`). Nijedna od njih ne menja `sadrzaj`.

**IZVRŠNI DOKAZ** (pokrenut pravi handler sa mockovanim Supabase klijentom, uhvaćen `file=` kwarg):

```
PLAINTEXT sha256 = bc3bd6c6deb4f455fee48d6f9af0b0f3565c244183fb34d4fef7e9dc03320c5d
PLAINTEXT len    = 61

--- PORTAL  routers/client_portal.py:594
    bucket        : portal-uploads
    path          : advokat-1/predmet-1/220363e0102f4c72a5ac40bd624008dd_Ugovor Petar Petrovic JMBG 0101990710123.pdf
    file_options  : {'content-type': 'application/pdf'}
    len(bytes)    : 61
    sha256(bytes) : bc3bd6c6deb4f455fee48d6f9af0b0f3565c244183fb34d4fef7e9dc03320c5d
    == plaintext? : True
    first 60 bytes: b'%PDF-1.7\nTAJNI UGOVOR JMBG 0101990710123 -- poverljivo\n%%EOF'
```

Sha256 uploadovanih bajtova je **identičan** sha256 ulaznog fajla. Prvih 60 bajtova su čitljiv tekst.

Za kontrast, isti fajl kroz Smart Intake u istom izvršavanju:

```
--- SMART INTAKE  routers/smart_intake.py:187
    bucket        : intake-dokumenti
    path          : advokat-1/95839ea223ba4521af333e101b1cebaf
    file_options  : {'content-type': 'application/octet-stream', 'upsert': 'false'}
    len(bytes)    : 120
    sha256(bytes) : 8e3f2260b6e263450a9f656ffe895ea6aaf386752271e8c7bd026c2d86a40990
    == plaintext? : False
    first 60 bytes: b'E97v310hWvn2pvecHHNHHX6EwJ-qRdUtpD86c-5SXWVtMJprRQeUX9uCuL_6'
```

### 2.2 U koji bucket i pod kojim imenom?

**Bucket:** `portal-uploads` (`:591`, hardkodiran string).

**Putanja** (`:586-588`):
```python
bezbedan_naziv = re.sub(r"[^\w\-\. ]", "_", fajl.filename or "dokument")[:100]
storage_path = f"{advokat_uid}/{predmet_id}/{_uuid_mod.uuid4().hex}_{bezbedan_naziv}"
```

Dakle: `{advokat_user_id}/{predmet_id}/{uuid4hex}_{ORIGINALNO_IME_FAJLA}`.

Sanitizacija na `:586` je **zaštita od path traversal-a, ne od PII-ja** — regex `[^\w\-\. ]`
zadržava sva slova, cifre, `_`, `-`, `.` i razmak. `\w` je Unicode-aware u Python 3, pa i ćirilica
prolazi. Ime `Ugovor Petar Petrović JMBG 0101990710123.pdf` prolazi netaknuto.

`content-type` se postavlja na **pravi MIME** (`:597`), ne na `application/octet-stream` kao na
druga dva puta — što znači da signed URL servira fajl koji se **otvara direktno u pregledaču**.

### 2.3 Da li se sadržaj šifruje PRE slanja? — NE. Dokaz poređenjem.

| Put | Fajl:linija upload-a | Šifrovanje pre upload-a | Gde |
|---|---|---|---|
| Smart Intake | `routers/smart_intake.py:187` | **DA** | `:184` `encrypted = await asyncio.to_thread(_encrypt, raw)` |
| Predmet dokument (Pipeline A) | `api.py:5051` | **DA** | `:5049` `_encrypted = await asyncio.to_thread(_si_encrypt, raw)` |
| Klijenti Trezor | `klijenti/router.py:811` | **DA** | `:796-802` inline AESGCM |
| **Client Portal** | **`routers/client_portal.py:594`** | **NE** | **ne postoji** |

Između `:563` i `:594` u `client_portal.py` nema poziva ka `security.crypto`, ka `AESGCM`, niti ka
`_encrypt`. Repo-wide grep za `_encrypt|AESGCM|encrypt_field` ne daje **nijedan** pogodak unutar
`routers/client_portal.py`.

### 2.4 Koji ključ koriste ostali putevi i kako se dobija?

Sva tri šifrovana puta koriste **isti** ključ, dobijen na **isti** način:

```
security/crypto.py:122  def _get_field_key() -> bytes
    → os.environ["FIELD_ENCRYPTION_KEY"]        (crypto.py:46, :123)
    → base64.urlsafe_b64decode(raw + "==")      (crypto.py:132)
    → min 32 bajta, uzima prvih 32              (crypto.py:135-140)
```

Pozivna mesta: `routers/smart_intake.py:99`, `klijenti/router.py:795`, `shared/intake_worker.py:476`.
Ključ je fail-fast validiran na startu (`security/crypto.py:55-117`, pozvano iz `api.py:78`).

**VAŽNO ZA REWIRE:** `security/crypto.py` **NEMA funkciju za šifrovanje fajlova.** Ima samo
`encrypt_field(str) -> str` / `decrypt_field(str) -> str` za **string polja** (format `enc_v1:k1:<b64>`)
i `generate_storage_key()`. Šifrovanje blobova je **duplirano ručno na tri mesta**:

| Mesto | Implementacija |
|---|---|
| `routers/smart_intake.py:95-105` | `_encrypt(raw: bytes) -> bytes` — jedina imenovana funkcija |
| `klijenti/router.py:796-802` | inline, kopija istog koda |
| `api.py:5047` | `from routers.smart_intake import _encrypt as _si_encrypt` — pravi reuse |

Kanonski format bloba (identičan na sva tri mesta):
```
base64url( nonce[12B] || AESGCM(key).encrypt(nonce, raw, None) )
```
gde ciphertext već sadrži 16-bajtni GCM tag. Overhead izmeren: **59 bajtova / 1.967x na 61-bajtnom
ulazu**, asimptotski ~1.333x + 38 B.

**Dekripcija** (samo dva mesta):
```
klijenti/router.py:963-973     bucket.download → b64decode(+b"==") → nonce=[:12], ct=[12:] → AESGCM.decrypt
shared/intake_worker.py:472-487 _download_and_decrypt(storage_path) -> bytes  — jedina imenovana funkcija
```

**Nonce/kid se NE čuvaju odvojeno** — nonce je prvih 12 bajtova samog bloba. **Key ID (`kid`) se
uopšte NE zapisuje u fajl-blobove** (za razliku od `encrypt_field`, gde je `k1` u prefiksu). To
znači: rotacija `FIELD_ENCRYPTION_KEY` danas **nepovratno gubi sve fajlove u sva tri bucket-a**.
To je postojeći dug, ne nov nalaz ovog izveštaja, ali rewire portala ga proširuje na četvrti bucket.

### 2.5 Da li postoji decrypt path za portal fajlove? — NE POSTOJI.

Repo-wide grep za `.download(` daje **tačno dva** pogotka:
```
klijenti/router.py:964
shared/intake_worker.py:481
```
Nijedan nije `portal-uploads`. `routers/client_portal.py` nikada ne poziva `bucket.download()`.

Jedini put do sadržaja portal fajla je **signed URL** (`:703`) koji pregledač otvara direktno.
Potvrđeno na frontendu — `static/vindex.js` u `portal_loadUploads()`:
```javascript
(u.download_url ? '<a href="'+u.download_url+'" target="_blank" rel="noopener" ...>⬇ Preuzmi</a>' : '')
```
Bajtovi **nikada ne prolaze kroz FastAPI aplikaciju** pri preuzimanju.

### 2.6 Ko sve može pristupiti originalu?

1. **Bilo ko sa signed URL-om**, 60 minuta, bez ikakve autentifikacije (§2.7).
2. **Nosilac `SUPABASE_SERVICE_KEY`** — `shared/deps.py:83-93` pravi jedan globalni klijent sa
   service-role ključem, koji zaobilazi RLS. Isto važi i za druga dva bucket-a, ali tamo bi
   napadač dobio ciphertext; ovde dobija dokument.
3. **Bilo ko sa pristupom Supabase Dashboard-u** (Storage browser) — vidi i preuzima direktno.
4. **Bilo ko, ako je bucket javan.** Status `public` za `portal-uploads` je **NEDOKAZAN**:
   `migrations/013_client_portal_uploads.sql:5` sadrži samo *komentar* („Dashboard → New bucket →
   Private"), ne SQL naredbu. Za poređenje, `intake-dokumenti` bar ima
   `INSERT INTO storage.buckets (id, name, public) VALUES (..., false)` u
   `migrations/073_intake_foundations.sql:362-364`. Za `portal-uploads` i `klijent-dokumenti`
   ne postoji ništa. Takođe: **nigde u repou ne postoji `CREATE POLICY` nad `storage.objects`**
   (grep nad `migrations/` daje 0 pogodaka).
   → Otvoreno pitanje, jedan read-only upit: `SELECT id, public FROM storage.buckets ORDER BY id;`
   Ovo je isto pitanje koje `docs/security/ACCESS_CONTROL_AUDIT.md:377` već postavlja i koje je
   i dalje neodgovoreno.
5. **Niko drugi u aplikaciji** — `client_portal_uploads` se čita isključivo unutar
   `routers/client_portal.py` (grep potvrđen). Nijedan pipeline (Case Genome, RAG, intake worker)
   ne dodiruje portal blobove. To je ublažavajuća okolnost: površina je uska, ali potpuno nezaštićena.

### 2.7 Da li signed URL zaobilazi aplikacijsku autorizaciju? — DA, potpuno.

`create_signed_url(_p, 3600)` (`:703`) vraća URL sa HMAC tokenom u query stringu. Taj URL je
**bearer capability**: ko ga ima, ima fajl. Konkretno:

- **Nema autentifikacije** pri preuzimanju — ni JWT, ni portal token, ni cookie.
- **Važi 3600 s** i ne može se opozvati (opoziv portal tokena na `:751` ne poništava već izdate
  signed URL-ove; brisanje objekta na `:779` jeste, ali to je destruktivna radnja).
- **Curi kroz `Referer`, istoriju pregledača, korporativni proxy, DLP, chat/email prosleđivanje.**
- **Izdaje se proaktivno za svih do 50 uploada** pri svakom `GET /uploads/{predmet_id}`
  (`:687` `.limit(50)`, petlja `:697-707`), čak i za fajlove koje advokat neće otvoriti.
- **Izdavanje se ne beleži nigde.** `client_portal_lista_uploada` nema nijedan poziv ka
  `log_action`/`log_event`. `shared/audit.py:15` `_AUDIT_PATHS = {"/api/predmeti", "/api/klijenti",
  "/api/billing", "/api/firm"}` — `/api/client-portal` nije u listi, pa ni middleware ne loguje.

**Kontrast sa Trezorom:** `klijenti/router.py:913-999` **nikada ne izdaje signed URL.** Preuzimanje
ide kroz autentifikovani endpoint koji: proverava rolu (`:926`), proverava vlasništvo (`:933`),
**upisuje audit PRE vraćanja bajtova** (`:950-957`, sa eksplicitnim komentarom „AUDIT LOG MORA biti
pre vraćanja fajla"), dekriptuje u RAM-u (`:960-973`) i dodaje PDF watermark sa email-om korisnika
(`:983-991`). Portal put nema **nijednu** od tih pet kontrola.

### 2.8 Da li ime fajla ili metadata cure PII? — DA, na četiri mesta.

| Gde | Fajl:linija | Šta curi |
|---|---|---|
| Ime objekta u storage-u | `:588` | Puno originalno ime fajla + `predmet_id` |
| DB kolona `fajl_naziv` | `:614` | Plaintext ime fajla |
| DB kolona `storage_path` | `:617` | Plaintext, sadrži isto ime |
| DB kolona `napomena` | `:618` | Slobodan tekst klijenta, plaintext, do 500 znakova |
| Aplikativni log | `:643` | `naziv=%r` — ime fajla u logovima |
| Log pri cleanup-u | `:637` | `path=%s` — puna putanja, dakle i ime |
| **Email advokatu (SMTP)** | `:174` | `<p ...>{fajl_naziv}</p>` — ime fajla napušta sistem preko SMTP-a |

Dokaz iz izvršavanja (DB red koji handler stvarno upisuje):
```
{'predmet_id': 'predmet-1', 'advokat_user_id': 'advokat-1',
 'token_hash': '1a4fa614...', 'fajl_naziv': 'Ugovor Petar Petrovic JMBG 0101990710123.pdf',
 'fajl_velicina': 61, 'content_type': 'application/pdf',
 'storage_path': 'advokat-1/predmet-1/220363e0.../Ugovor Petar Petrovic JMBG 0101990710123.pdf',
 'napomena': 'test', 'pregledano': False}
```

**Kontrast:**
- `klijenti/router.py:791` koristi `generate_storage_key()` → `encrypted_blob_<uuid4>`
  (izmereno: `encrypted_blob_7451ddf1-5d85-41a0-be0f-2db0e2bcb319`) — **nula PII-ja u putanji** —
  a ime fajla ide u `naziv_fajla_encrypted` kroz `encrypt_field` (`:822`).
- `routers/smart_intake.py:181` → `{user_id}/{uuid4hex}` — nema imena fajla u putanji.
- `api.py:5048` → `{user.id}/{predmet_id}/{uuid4hex}{suffix}` — samo ekstenzija, ne ime.

Docstring `security/crypto.py:10` doslovno propisuje: *„Storage putanje → `generate_storage_key()` —
randomizovani UUID, **nikad ime fajla**"*. Portal put krši sopstveno pisano pravilo projekta.

### 2.9 Da li error logging može ispisati sadržaj dokumenta? — NE.

Provereno u instaliranoj biblioteci `storage3 2.28.3`:
- `_sync/file_api.py:80-89` — na HTTP grešci hvata `HTTPStatusError` i diže
  `StorageApiError(resp["message"], resp["error"], resp["statusCode"])`.
- `exceptions.py` — `StorageApiError.__str__` je samo `{'statusCode': .., 'error': .., 'message': ..}`.

Poruka potiče **isključivo** od Supabase servera; telo zahteva (fajl) nije deo poruke. Zato
`logger.error("[PORTAL_UPLOAD] Storage upload greška: %s", exc)` (`:601`) **ne može** ispisati
sadržaj dokumenta. Nijedan poziv ne koristi `exc_info=True`, a standardni Python traceback ionako
ne serijalizuje lokalne promenljive.

Takođe provereno: ne postoji middleware koji loguje telo zahteva (`shared/audit.py:22-51` loguje
samo metodu, putanju, uid, status, IP; `api.py:1028` i `api.py:1055` ne dodiruju telo).

**ALI:** curenje kroz logove **postoji** — samo ne sadržaja, nego **imena fajla**, eksplicitno i
namerno, na `:643` i `:637` (vidi §2.8).

---

## 3. UPOREDNA TABELA — SVI upload putevi u repou

Iscrpna pretraga: `\.upload\(`, `storage\.from_\(`, `create_signed_upload_url`,
`upload_to_signed_url`, `storage/v1/object`, `supabase.storage` (uključujući `static/`).
Pogoci van `tests/`, `docs/` i `.vindex_ai_team/`: **tačno četiri upload poziva u tri bucket-a.**

| # | Fajl:linija | Bucket | Šifrovano | Koja funkcija šifruje | Ime fajla sadrži PII |
|---|---|---|---|---|---|
| 1 | `api.py:5051` | `intake-dokumenti` | **DA** | `routers.smart_intake._encrypt` (import na `:5047`, poziv na `:5049`) | **NE** — `{user.id}/{predmet_id}/{uuid4hex}{suffix}` (`:5048`) |
| 2 | `routers/smart_intake.py:187` | `intake-dokumenti` | **DA** | `_encrypt` (`smart_intake.py:95-105`, poziv na `:184`) | **NE** — `{user_id}/{uuid4hex}` (`:181`) |
| 3 | `klijenti/router.py:811` | `klijent-dokumenti` | **DA** | inline AESGCM (`klijenti/router.py:796-802`) | **NE** — `generate_storage_key()` → `encrypted_blob_<uuid4>` (`:791`) |
| 4 | **`routers/client_portal.py:594`** | **`portal-uploads`** | **NE** | **nijedna** | **DA** — `{advokat_uid}/{predmet_id}/{uuid4hex}_{originalno_ime}` (`:588`) |

**Odgovor na kontrolno pitanje iz zadatka: prethodni sprint je TAČAN.**
Ima ih tačno 4, ne više. Tri šifruju, portal ne. Sve četiri linije verifikovane čitanjem, a tri od
četiri i izvršavanjem. (Sitna korekcija numeracije: prethodni izveštaj navodi
`smart_intake.py:184` i `klijenti/router.py:798` — to su linije *enkripcije*, ne linije *upload-a*;
`upload(` pozivi su na `:187` odnosno `:811`. Suština je nepromenjena.)

Dodatna verifikacija odsustva alternativnih puteva:
- **Nema** `create_signed_upload_url` / `upload_to_signed_url` nigde u repou.
- **Nema** direktnog upload-a iz pregledača — jedini pogodak na `supabase.storage` u `static/` je
  minifikovana biblioteka `static/supabase.min.js:7`; `static/vindex.js` je nikad ne koristi za
  storage. Svi upload-i idu kroz backend.
- **Nema** sirovih HTTP poziva ka `/storage/v1/object`.

---

## 4. Bonus nalaz koji nije bio u zadatku: plaintext kopija na disku VEĆ postoji

Ovo je direktno relevantno za pitanje „da li bi rewire napravio DRUGU plaintext kopiju".

Starlette 1.3.1, `formparsers.py:147`:
```python
spool_max_size = 1024 * 1024  # 1MB
```
i `:230`: `tempfile = SpooledTemporaryFile(max_size=self.spool_max_size)`.

**Izmereno:**
```
MultiPartParser.spool_max_size = 1048576
tempfile.gettempdir()          = C:\Users\Benny\AppData\Local\Temp

payload=524286 bajta
  _rolled (na disku?) : False
  putanja na disku    : None

payload=2097156 bajta
  _rolled (na disku?) : True
  putanja na disku    : C:\Users\Benny\AppData\Local\Temp\tmpqvlf6vvq
```

**Posledica:** svaki upload **preko 1 MB** Starlette upisuje u **plaintext-u na disk kontejnera**
pre nego što handler uopšte počne da se izvršava. Ovo važi za **sva četiri** puta jednako (svi
koriste `UploadFile` ili `await request.form()`), uključujući ona tri koja se smatraju „šifrovanim".
Fajl se briše kad se `SpooledTemporaryFile` zatvori na kraju zahteva, ali postoji na disku tokom
obrade i ostaje kao neobrisani blok podataka posle unlink-a.

Sekundarno, na portal putu: provera veličine (`:564`) se izvršava **POSLE** `await fajl.read()`
(`:563`), a Starlette nema globalni limit veličine tela (grep za `limit_request|max_request_size|
client_max_body|ContentSizeLimit` → 0 pogodaka u repou). `max_part_size` iz `formparsers.py:184`
se primenjuje **samo na ne-fajl polja** (`if self._current_part.file is None`). Dakle
neautentifikovana strana može naterati server da spool-uje proizvoljno veliku plaintext datoteku na
disk pre nego što dobije 413. Rate limit je 5/min po IP-u (`:515`).

---

## 5. PLAN REWIRE-a (opis, NE implementacija)

### 5.1 Šta se menja na upload strani

U `routers/client_portal.py`, između `:588` i `:591`:

1. **Import:** `from routers.smart_intake import _encrypt` — isti reuse obrazac koji `api.py:5047`
   već koristi. Ne pisati četvrtu kopiju AESGCM koda.
   *Bolja varijanta ako se sme dirati `security/crypto.py`:* preseliti `_encrypt` tamo kao
   `encrypt_blob(raw: bytes) -> bytes` i dodati par `decrypt_blob(blob: bytes) -> bytes`, pa da
   sva četiri puta zovu jedno mesto. Trenutno je logika duplirana 3x za enkripciju i 2x za
   dekripciju, bez ijedne zajedničke funkcije u `security/`.
2. **Enkripcija van event-loop-a:** `sifrovan = await asyncio.to_thread(_encrypt, sadrzaj)` —
   identično `smart_intake.py:184`. AESGCM je CPU-bound.
3. **Ime objekta:** zameniti `:588` sa `storage_path = f"{advokat_uid}/{predmet_id}/{uuid4().hex}"`
   — **bez** `_{bezbedan_naziv}`. Ovim se zatvara §2.8 i poštuje `security/crypto.py:10`.
   `bezbedan_naziv` i dalje treba računati (`:586`) jer ide u DB.
4. **`file_options`:** `{"content-type": "application/octet-stream", "upsert": "false"}` — kao na
   druga dva puta. Pravi MIME (`:597`) više nije istinit za ciphertext, a `upsert: false` sprečava
   tiho pregaženje.
5. **`upload(file=sifrovan)`** umesto `file=sadrzaj` na `:596`.
6. **`fajl_velicina`** na `:615` **ostaviti kao `len(sadrzaj)`** (veličina originala, ono što
   advokat vidi u UI), NE `len(sifrovan)`. Inače UI prikazuje 1.33x naduvane KB.
7. **Metapodaci u DB (`:610-620`):** dodati `"enc": True` / `"enc_version": 1` (vidi §6) i ozbiljno
   razmotriti `fajl_naziv` kroz `encrypt_field()` + `napomena` kroz `encrypt_field()`, po uzoru na
   `klijenti/router.py:822`. Ako se to uradi, `:643` log i `:174` email moraju se prilagoditi.

### 5.2 Šta se MORA promeniti na download strani — inače fajlovi postaju nečitljivi

**Ovo je obavezno, ne opciono.** Trenutno pregledač otvara signed URL direktno
(`static/vindex.js`, `portal_loadUploads`). Ako se sadržaj šifruje, pregledač dobija base64url
tekst umesto PDF-a. Signed URL **prestaje da bude upotrebljiv** i mora se ukloniti.

Potrebno je:

1. **Novi autentifikovani endpoint**, npr. `GET /api/client-portal/uploads/{upload_id}/download`,
   po ugledu na `klijenti/router.py:913-999`:
   - `Depends(get_current_user)`
   - vlasništvo: `.eq("id", upload_id).eq("advokat_user_id", uid)`
   - **audit PRE vraćanja bajtova** (`shared.audit_immutable.log_action`, isti obrazac kao
     `client_portal.py:811-813`) — čime se usput zatvara i rupa iz §2.7 (danas se izdavanje
     signed URL-a nigde ne beleži)
   - `bucket.download(storage_path)` → `b64decode(+b"==")` → `nonce=[:12], ct=[12:]` →
     `AESGCM(_get_field_key()).decrypt(...)`
   - `StreamingResponse(iter([file_bytes]), media_type=meta["content_type"],
     headers={"Content-Disposition": f'attachment; filename="{fajl_naziv}"'})`
2. **`client_portal_lista_uploada` (`:695-707`):** obrisati ceo `create_signed_url` blok; `download_url`
   postaje putanja ka novom endpointu. Ovim nestaje i N+1 mrežni poziv ka Supabase-u po prikazu liste.
3. **`static/vindex.js`, `portal_loadUploads`:** `<a href="'+u.download_url+'">` ne šalje
   `Authorization` header, pa prost `href` više neće raditi. Mora se prepisati u `fetch` sa
   `Authorization: Bearer` → `blob()` → `URL.createObjectURL` → programski klik. Uz to bump
   `CACHE_NAME` u `static/sw.js`.
4. **`storage_path` prestati slati klijentu** (`:683` `select`, danas se dohvata i koristi samo
   interno, ali je u istom `select`-u) — nije nužno, ali je besplatno.

### 5.3 KRITIČNO PITANJE: da li rewire pravi DRUGU plaintext kopiju?

**Odgovor: NE pravi nijednu NOVU, ali plaintext kopija na disku VEĆ POSTOJI i rewire je NE uklanja.**

Razloženo:

| Potencijalna kopija | Postoji danas? | Posle rewire-a? | Dokaz |
|---|---|---|---|
| `sadrzaj` u RAM-u procesa | DA | DA (nužno — mora se šifrovati) | `:563` |
| `sifrovan` u RAM-u | ne | DA (ciphertext, nije plaintext) | novo, `:590` |
| **Privremeni fajl na disku (>1 MB)** | **DA** | **DA, nepromenjeno** | §4, `formparsers.py:147,230`, izmereno |
| Plaintext blob u `portal-uploads` | DA | **NE za nove**, DA za stare | §6 |
| Plaintext u DB (`fajl_naziv`, `napomena`) | DA | DA, osim ako se doda `encrypt_field` (§5.1.7) | `:614,618` |
| Plaintext u logu | DA (`:643`, `:637`) | DA, osim ako se log promeni | §2.8 |
| Plaintext u email-u advokatu | DA (`:174`) | DA, osim ako se email promeni | §2.8 |

Ključno: **rewire šifruje samo jedan od sedam redova gornje tabele.** Portal put danas curi ime
fajla u DB, log i SMTP nezavisno od enkripcije bloba. Ako se rewire uradi samo na blobu, nalaz
„portal cure PII" ostaje otvoren — samo mu se smanjuje težina. Rewire treba planirati kao paket:
blob + putanja + `fajl_naziv`/`napomena` + log + email.

Dodatno, o originalu koji ostaje u storage-u: **ne ostaje.** Postojeći kod upisuje na
`storage_path` **jednom** i nikada drugi put (`:594`, jedini `upload` u fajlu). Ne postoji
„upload plaintext pa upload ciphertext" scenario. Ali za **stare** fajlove vidi §6.

---

## 6. MIGRACIJA POSTOJEĆIH PLAINTEXT FAJLOVA — dokazan odgovor

### 6.1 Šta se dešava sa fajlovima koji su već u storage-u

Ništa se ne dešava automatski. Bucket `portal-uploads` postaje **mešovit**: stari objekti su
plaintext, novi su ciphertext. Nijedna kolona u `client_portal_uploads` danas ne razlikuje ta dva —
šema iz `migrations/013_client_portal_uploads.sql:9-21` ima tačno 10 kolona
(`id, predmet_id, advokat_user_id, token_hash, fajl_naziv, fajl_velicina, content_type,
storage_path, napomena, pregledano, uploaded_at`) i **nijedna migracija posle 013 je ne menja**
(grep nad `migrations/` za `client_portal_uploads` daje pogotke samo u 013).

Bez diskriminatora, novi download endpoint bi pokušao da dekriptuje stari plaintext PDF, `AESGCM.decrypt`
bi digao `InvalidTag`, i advokat bi dobio HTTP 500 na **svaki dokument primljen pre rewire-a**.
To je tiha regresija koja pogađa 100% postojećih podataka.

### 6.2 Može li download path da razlikuje stare od novih? — DA, na dva načina. Oba dokazana.

**Način A — eksplicitna kolona (preporučeno).**
Migracija dodaje `ALTER TABLE client_portal_uploads ADD COLUMN IF NOT EXISTS enc_version SMALLINT
NOT NULL DEFAULT 0;` Postojeći redovi dobijaju `0` (plaintext), novi upisi postavljaju `1`. Download
endpoint grana na toj vrednosti. Ovo radi jer endpoint **ionako čita metapodatke iz DB pre nego što
dodirne storage** — nema dodatnog upita, nema dodatne latencije.
*(Migracioni SQL se ne prilaže ovde — po konvenciji projekta migracije piše i pokreće osnivač.)*

**Način B — trial-decrypt (za redove nastale pre nego što kolona postoji, i kao pojas-i-tregeri).**
Pokušaj dekripcije; ako GCM tag verifikuje → ciphertext, ako pukne → plaintext. Ovo je
**kriptografski čvrsto**: falsifikovanje validnog GCM taga bez ključa je ~2⁻¹²⁸.

**IZMERENO** (uključujući namerno zlonameran slučaj — plaintext `.txt` koji se sastoji isključivo
od base64url znakova, dakle najgori mogući lažni pozitiv za naivnu heuristiku po abecedi):

```
=== is_encrypted() na FILE blobovima ===
  is_encrypted=False  <- stari plaintext PDF
  is_encrypted=False  <- stari plaintext TXT
  is_encrypted=False  <- stari plaintext TXT koji IZGLEDA kao base64url
  is_encrypted=False  <- stari plaintext PNG
  is_encrypted=False  <- NOVI sifrovan blob (PDF)
  is_encrypted=False  <- NOVI sifrovan blob (TXT)

=== trial-decrypt diskriminator (AES-GCM tag kao dokaz) ===
  PLAINTEXT (ocekivano PLAINTEXT) OK   <- stari plaintext PDF
  PLAINTEXT (ocekivano PLAINTEXT) OK   <- stari plaintext TXT
  PLAINTEXT (ocekivano PLAINTEXT) OK   <- stari plaintext TXT koji IZGLEDA kao base64url
  PLAINTEXT (ocekivano PLAINTEXT) OK   <- stari plaintext PNG
  SIFROVAN  (ocekivano SIFROVAN ) OK   <- NOVI sifrovan blob (PDF)
  SIFROVAN  (ocekivano SIFROVAN ) OK   <- NOVI sifrovan blob (TXT)

  Diskriminator tacan na svim slucajevima: True
```

**Kritično upozorenje iz prvog bloka:** `security.crypto.is_encrypted()` **NE SME** da se koristi za
fajl-blobove. Vraća `False` i za plaintext i za ciphertext, jer proverava prefiks `enc_v1:` koji
postoji **samo** u `encrypt_field()` izlazu za string polja. Fajl-blobovi su goli
`base64url(nonce||ct)` bez ikakvog markera verzije ili formata. Ovo je zamka u koju je lako upasti
pri implementaciji rewire-a i vredi je zabeležiti kao naslovni rizik.

**Šta NE radi kao diskriminator:**
- provera abecede/dužine (`^[A-Za-z0-9_\-=]+$`, `len % 4 == 0`) — treći test slučaj je gore
  demantuje; `text/plain` je dozvoljen tip (`client_portal.py:508`)
- `content_type` kolona — postavlja se iz klijentovog `Content-Type`, ista je i pre i posle
- magic bytes — pokriva PDF/PNG/JPEG/WEBP/DOCX ali **ne** `text/plain`
- `is_encrypted()` — vidi gore

### 6.3 Preporučeni redosled rolloutа (bez prozora nedostupnosti)

1. **Prvo download strana, pa tek onda upload strana.** Deploy novog `/download` endpointa koji
   podržava OBA formata (kolona ako postoji, inače trial-decrypt), dok upload još piše plaintext.
   U ovoj fazi ništa nije nečitljivo — endpoint čita i stare i (buduće) nove.
2. **Zatim frontend** prebaciti sa `href=signed_url` na `fetch` + `Authorization`, uz bump
   `static/sw.js` `CACHE_NAME`.
3. **Tek onda upload strana** — enkripcija + čista putanja bez imena fajla.
4. **Backfill (opciono, zasebna odluka):** skripta koja za svaki red sa `enc_version=0` preuzme
   blob, šifruje ga, upiše pod **novim** ključem, postavi `enc_version=1` + novi `storage_path`, i
   **tek posle uspešnog upisa** obriše stari objekat. Redosled je bitan — brisanje pre upisa znači
   trajan gubitak dokumenta klijenta. Backfill se sme preskočiti; trial-decrypt/kolona ga čini
   nepotrebnim za funkcionisanje, ali stari plaintext blobovi ostaju u bucket-u dok se ne obrišu.
5. **Prvo odgovoriti na `SELECT id, public FROM storage.buckets;`** Ako je `portal-uploads` javan,
   to je hitnije od enkripcije — enkripcija štiti sadržaj, ali javni bucket i dalje otkriva
   postojanje, imena i količinu dokumenata po predmetu.

---

## 7. Sažetak nalaza

| ID | Nalaz | Fajl:linija | Težina |
|---|---|---|---|
| CPU-01 | Portal fajlovi se čuvaju u plaintext-u; jedini od 3 bucket-a | `client_portal.py:594` | **VISOKA** |
| CPU-02 | Puno ime fajla (PII) u imenu objekta u storage-u | `client_portal.py:588` | **VISOKA** |
| CPU-03 | Signed URL zaobilazi svu aplikacijsku autorizaciju, 60 min, neopoziv | `client_portal.py:703` | **VISOKA** |
| CPU-04 | Izdavanje signed URL-a se nigde ne beleži (ni ruta ni middleware) | `client_portal.py:695-707`, `shared/audit.py:15` | SREDNJA |
| CPU-05 | Ime fajla u logu i u SMTP email-u | `client_portal.py:643,637,174` | SREDNJA |
| CPU-06 | `napomena` klijenta plaintext u DB | `client_portal.py:618` | NISKA-SREDNJA |
| CPU-07 | Signed URL se izdaje za do 50 fajlova unapred, i za neotvorene | `client_portal.py:687,697` | NISKA |
| CPU-08 | Provera veličine posle `read()`; nema globalnog limita tela | `client_portal.py:563-568` | NISKA-SREDNJA |
| CPU-09 | Plaintext spool na disk >1 MB — pogađa SVA 4 puta | `starlette/formparsers.py:147,230` | SREDNJA |
| CPU-10 | Blob enkripcija duplirana 3x, dekripcija 2x; nema je u `security/crypto.py` | `smart_intake.py:95`, `klijenti/router.py:796`, `api.py:5047` | SREDNJA (dug) |
| CPU-11 | Fajl-blobovi nemaju marker verzije/`kid`; rotacija ključa gubi sve fajlove | sva tri puta | SREDNJA (dug) |
| CPU-12 | `public` status bucket-a `portal-uploads` i `klijent-dokumenti` nedokaziv iz koda | `migrations/013:5` | **OTVORENO PITANJE** |

**Sve tvrdnje u ovom dokumentu su ili `fajl:linija` ili izmereni izlaz. Nijedan produkcijski fajl
nije menjan.**
