# STORAGE BUCKET FORENSICS — Supabase Storage privatnost i signed URL lanac

**Datum:** 2026-08-13
**Opseg:** PRIORITET #1 — Storage bucket privacy (CONF-003)
**Metod:** statička forenzika repozitorijuma + **žive READ-ONLY sonde** protiv produkcionog Supabase projekta
**Mutacije izvršene:** nijedna (0 INSERT / UPDATE / DELETE / DDL, 0 izmena produkcijskih fajlova)
**Kredencijali:** nijedan nije ispisan; `SUPABASE_URL` maskiran u svim izlazima

---

## 0. EXECUTIVE SUMMARY

| Pitanje | Odgovor | Status dokaza |
|---|---|---|
| Da li je ijedan bucket dokazano PUBLIC? | **NE.** Oba postojeća bucket-a su izmereno `public=false`. | **IZMERENO** (živa sonda) |
| Da li ijedan signed URL može nastati bez ownership provere? | **NE.** Postoji tačno **jedan** `create_signed_url` u produkcijskom kodu i on je iza dvostruke ownership provere. | **DOKAZANO** (fajl:linija) |
| Da li aplikacija ikada koristi public URL? | **NE.** Nula `get_public_url` / `/object/public/` poziva u našem kodu. | **DOKAZANO** (grep) |
| Da li postoje RLS politike na `storage.objects`? | **Nijedna nije u repou.** Produkciono stanje = **UNKNOWN** (vidi §3). | UNKNOWN sa razlogom |
| **NOVO / KRITIČNO ZA PROIZVOD** | Bucket **`klijent-dokumenti` NE POSTOJI** u produkciji. Ceo „Trezor" upload/download put je mrtav. | **IZMERENO** |

**CONF-003 je time ZATVOREN u delu „da li su bucket-i javni": nisu.**
Ostaje otvoren rezidualni deo: RLS na `storage.objects` (§3) i nepostojeći `klijent-dokumenti` (§7).

---

## 1. BUCKET INVENTORY

### 1.1 Šta kod referencira (statički)

Repo-wide grep `\.storage\.from_\(` — svi produkcijski pogoci:

| Bucket (string u kodu) | Kod koji ga koristi (fajl:linija) | Operacija | Migracija koja ga kreira |
|---|---|---|---|
| `intake-dokumenti` | `routers/smart_intake.py:59` (`_STORAGE_BUCKET`), `:185` | `upload` | `migrations/073_intake_foundations.sql:362-364` |
| `intake-dokumenti` | `shared/intake_worker.py:480-481` | `download` | isto |
| `intake-dokumenti` | `api.py:5047-5055` (import `_STORAGE_BUCKET as _si_bucket`) | `upload` | isto |
| `intake-dokumenti` | `api.py:5254` (`_si_bucket_cleanup`) | `remove` (kompenzujuće) | isto |
| `portal-uploads` | `routers/client_portal.py:591-599` | `upload` | **nijedna** — `migrations/013_client_portal_uploads.sql:4-5` je samo SQL **komentar-uputstvo** („Dashboard → Storage → New bucket → Ime: `portal-uploads` → Private") |
| `portal-uploads` | `routers/client_portal.py:702-703` | `create_signed_url` | isto |
| `portal-uploads` | `routers/client_portal.py:779`, `:635` | `remove` | isto |
| `klijent-dokumenti` | `klijenti/router.py:809-816` | `upload` | **nijedna** |
| `klijent-dokumenti` | `klijenti/router.py:841` | `remove` (orphan cleanup) | **nijedna** |
| `klijent-dokumenti` | `klijenti/router.py:962-965` | `download` | **nijedna** |

Nema nijednog `create_bucket` / `update_bucket` / `list_buckets` poziva u repou
(grep → 0 pogodaka van vendored `static/supabase.min.js`). Bucket-i se prave **ručno u Dashboard-u**,
osim jednog `INSERT` iz migracije 073.

### 1.2 Šta stvarno postoji u produkciji (izmereno)

Sonda: `GET /storage/v1/bucket` sa service-role ključem + `supabase-py` `storage.list_buckets()`
(oba read-only; identičan rezultat).

```
=== PROBE A: supabase-py list_buckets() ===
RESULT: OK, 2 bucket(s)
  id=portal-uploads     name=portal-uploads     public=False  created=2026-06-17 21:40:33.025+00
  id=intake-dokumenti   name=intake-dokumenti   public=False  created=2026-07-15 18:45:01.378+00

=== PROBE B: raw GET /storage/v1/bucket ===
HTTP 200
  id=portal-uploads     public=False  created=2026-06-17T21:40:33.025Z
  id=intake-dokumenti   public=False  created=2026-07-15T18:45:01.378Z

=== PROBE E: GET /storage/v1/bucket/<id> ===
  klijent-dokumenti  HTTP 400 -> {"statusCode":"404","error":"Bucket not found",
                                  "message":"Bucket not found","code":"NoSuchBucket"}
  portal-uploads     HTTP 200 -> {"id":"portal-uploads",   ... "public":false, ...}
  intake-dokumenti   HTTP 200 -> {"id":"intake-dokumenti", ... "public":false, ...}
```

**Konsolidovani inventar:**

| Bucket | Postoji u produkciji | `public` | Kreiran | Sadrži klijentske dokumente |
|---|---|---|---|---|
| `intake-dokumenti` | **DA** | **false** (izmereno) | 2026-07-15 | **DA** — Smart Intake upload + originali dokumenata predmeta (`api.py:5048`) |
| `portal-uploads` | **DA** | **false** (izmereno) | 2026-06-17 | **DA** — dokumenti koje klijent šalje advokatu kroz portal |
| `klijent-dokumenti` | **NE** (`NoSuchBucket`) | n/a | nikad | trebalo bi (Trezor), ali ne postoji — vidi §7 |

> **Napomena o metodu:** `supa.storage.from_("klijent-dokumenti").list()` vraća **prazan niz, ne grešku**
> (PROBE I). To znači da `list()` **nije** pouzdan test postojanja bucket-a. Autoritativan test je
> `GET /storage/v1/bucket/<id>` (PROBE E). Ranije revizije koje su se oslanjale na `list()` mogle su
> pogrešno zaključiti da bucket postoji i da je prazan.

### 1.3 Sadržaj bucket-a (read-only listing, identifikatori maskirani)

```
portal-uploads     : 0 objekata          | client_portal_uploads count=0
intake-dokumenti   : 2 prefiksa / 7 blobova | intake_jobs count=4
klijent-dokumenti  : n/a (ne postoji)    | klijent_dokumenti count=0
```

**Sporedni nalaz (FIN-STG-004, LOW):** jedan od dva prefiksa u produkcionom `intake-dokumenti`
je dužine **37 znakova i počinje sa `00000000-`**, i **nije validan UUID** (rep sadrži slova van
hex opsega — obrazac `…-t?s?…`). To je sintetički **test-korisnik**, tj. test run je pisao
enkriptovane blobove u **produkcioni** bucket. Konzistentno sa već zabeleženim nalazom da su
testovi udarali produkcioni Pinecone.

---

## 2. PUBLIC / PRIVATE DOKAZ

### 2.1 Zašto migracija 073 NIJE dokaz

`migrations/073_intake_foundations.sql:357-364`:

```sql
-- Isti obrazac kao klijent-dokumenti (Trezor) — enkriptovano pre upload-a
-- (routers/smart_intake.py), bucket sam po sebi NIJE public. Ako je bucket
-- već ručno kreiran u Supabase Dashboard-u, ovaj insert je no-op.

INSERT INTO storage.buckets (id, name, public)
VALUES ('intake-dokumenti', 'intake-dokumenti', false)
ON CONFLICT (id) DO NOTHING;
```

`ON CONFLICT (id) DO NOTHING` znači: **ako je bucket ranije ručno napravljen kao PUBLIC, ova
migracija ga NE ispravlja.** Migracija to i sama priznaje u komentaru na `:360`. Dakle deklaracija
`public=false` u SQL-u je **nula dokaza** o produkcionom stanju. Ovo je bilo tačno kao sumnja.

Dodatno: `created_at` bucket-a je **2026-07-15**, a migracija 073 je iz iste ere — ne može se iz
timestampa zaključiti da li je `INSERT` odradio posao ili je bio no-op nad ručno kreiranim bucket-om.
**Zato je jedini dokaz merenje, i merenje je urađeno.**

### 2.2 Zašto migracija 013 NIJE dokaz

`migrations/013_client_portal_uploads.sql:4-5` je **samo komentar**:

```sql
-- NAPOMENA: Pre pokretanja kreirajte Supabase Storage bucket:
--   Dashboard → Storage → New bucket → Ime: "portal-uploads" → Private
```

Nema `INSERT INTO storage.buckets`. Privatnost `portal-uploads`-a je do ovog izveštaja počivala
isključivo na tome da li je čovek pročitao i poslušao komentar. **Sada je izmereno: `public=false`.**

### 2.3 Diferencijalni anonimni test (potvrda)

```
=== PROBE F: anonimni GET /storage/v1/object/public/<bucket>/<nepostojeci> ===
  public/portal-uploads     HTTP 400 -> NoSuchBucket
  public/intake-dokumenti   HTTP 400 -> NoSuchBucket
  public/klijent-dokumenti  HTTP 400 -> NoSuchBucket

=== PROBE G: anonimni GET /storage/v1/object/<bucket>/<nepostojeci> ===
  object/portal-uploads     HTTP 400 -> NoSuchBucket
  object/intake-dokumenti   HTTP 400 -> NoSuchBucket

=== PROBE D: anonimni GET /storage/v1/bucket (bez ključa) ===
  HTTP 400 -> "headers must have required property 'authorization'"
```

`/object/public/` ruta **ne servira** ništa iz ova dva bucket-a bez autentifikacije — Storage
gateway odgovara `NoSuchBucket` jer bucket nije javan. To je nezavisna potvrda §1.2.

> Metodološko ograničenje: `NoSuchBucket` je isti odgovor i za nepostojeći bucket, pa PROBE F
> sama po sebi **nije** konkluzivna — konkluzivne su PROBE A/B/E sa service ključem koje vraćaju
> eksplicitno `"public": false` polje.

### 2.4 Zaključak §2

**Nijedan bucket nije PUBLIC. Izmereno, ne pretpostavljeno.**

---

## 3. RLS POLITIKE NA `storage.objects`

### 3.1 Statički nalaz

Repo-wide grep `CREATE POLICY` + `storage.objects` → **nula politika nad `storage` šemom
u celom repozitorijumu.** Jedini pogoci su tekstualni, u ranijim izveštajima
(`docs/lambda/RLS_CERTIFICATION.md:96`, `docs/security/ACCESS_CONTROL_AUDIT.md:378-381`).
Sve `CREATE POLICY` naredbe u `migrations/`, `supabase_setup.sql`, `supabase_migration*.sql`
odnose se isključivo na `public.*` tabele.

**Nalaz: nijedna RLS politika na `storage.objects` ne postoji u izvornom kodu.**

### 3.2 Zašto to ovde NIJE kritično (ali jeste rizik)

Supabase Storage gateway proverava **prvo** `bucket.public`. Za privatan bucket, anonimni pristup
je odbijen pre nego što se uopšte stigne do RLS-a — to je i izmereno u §2.3. RLS na `storage.objects`
bi bio odbrana drugog reda za **ulogovane** korisnike koji bi zvali Storage API **direktno** iz
pretraživača, zaobilazeći naš backend.

**Bitno:** naš frontend **ne** zove Storage API direktno ni na jednom mestu (grep za
`getPublicUrl` / `createSignedUrl` u `static/*.js` → jedini pogodak je vendored `static/supabase.min.js`,
tj. sama biblioteka, bez pozivaoca u `static/vindex.js`). Sav pristup blobovima ide kroz FastAPI
backend sa service-role ključem. Rizik je time sveden na „šta ako neko ulogovan uzme svoj JWT i
udari Storage API ručno".

### 3.3 Pokušaj živog merenja RLS-a — NIJE USPEO

Pokušano je kovanje kratkotrajnog `role=authenticated` JWT-a potpisanog sa `SUPABASE_JWT_SECRET`
iz `.env`, da bi se izmerilo da li običan ulogovan korisnik može da lista tuđe blobove:

```
=== PROBE J: authenticated JWT -> POST /storage/v1/object/list/<bucket> ===
  portal-uploads    HTTP 400 -> {"statusCode":"403","error":"Unauthorized",
                                 "message":"signature verification failed","code":"AccessDenied"}
  intake-dokumenti  HTTP 400 -> isto
=== PROBE M: anon JWT -> isto ===  signature verification failed
```

Razlog neuspeha je utvrđen, ne nagađan: projekat koristi **asimetrično ES256 potpisivanje**
(`GET /auth/v1/.well-known/jwks.json` → `HTTP 200`, `{"keys":[{"alg":"ES256","kty":"EC",...}]}`),
a `SUPABASE_JWT_SECRET` u `.env` je 32-znakovni HS256 string koji Supabase gateway ne prihvata.
Nije moguće iskovati validan korisnički token bez privatnog ES256 ključa (koji Supabase ne izdaje).

→ **RLS na `storage.objects` ostaje UNKNOWN.** Vidi §8 za READ-ONLY SQL koji to zatvara.

### 3.4 Sporedni nalaz o `SUPABASE_JWT_SECRET` (van opsega, prijavljen radi potpunosti)

`SUPABASE_JWT_SECRET` iz `.env` **nije** legacy JWT secret ovog Supabase projekta — dokaz:
Storage gateway i PostgREST oba odbijaju tokene potpisane njime
(`{"message":"Invalid API key"}` na `/rest/v1/`). Aplikacija to preživljava jer
`shared/deps.py:209-224` i `api.py` imaju ES256/JWKS granu koja radi pravu verifikaciju.
HS256 grana (`shared/deps.py:196-206`, `api.py:236-239`) je time **mrtva grana** za realne
Supabase tokene. Nije bezbednosna rupa sama po sebi (verifikacija se i dalje vrši), ali je
zavaravajuća konfiguracija.

Provereno i: `.env` **jeste** u `.gitignore:4` i **nije** praćen (`git ls-files` → nema pogotka).
U istoriji je postojao u `dc29b764`, ali je tada sadržao **samo `OPENAI_API_KEY=`** — nikad
`SUPABASE_SERVICE_KEY` niti `SUPABASE_JWT_SECRET` (provereno preko imena promenljivih;
vrednosti nisu ispisivane). Dakle **service-role ključ nikad nije iscureo u git**.

---

## 4. PUBLIC URL UPOTREBA

| Obrazac | Pogodaka u našem kodu | Status |
|---|---|---|
| `get_public_url` (python) | **0** | ne postoji |
| `getPublicUrl` (JS) | 1 — `static/supabase.min.js:7` | **MRTAV** — vendored Supabase biblioteka; nula pozivalaca u `static/vindex.js` ili bilo kom `.html` (grep `getPublicUrl` po `*.js,*.html` → jedini pogodak je sama minifikovana biblioteka) |
| `/storage/v1/object/public/` (literal) | 1 — `static/supabase.min.js:7` | **MRTAV** — isto, deo biblioteke |

**Nijedan endpoint ne vraća public URL klijentu.** Jedini URL koji ide ka pretraživaču je
signed URL iz §5.

---

## 5. SIGNED URL MATRICA

Repo-wide grep `create_signed_url|createSignedUrl` → **tačno jedan produkcijski poziv.**

| # | Poziv (fajl:linija) | Bucket | TTL | Ownership provera PRE kreiranja? | Dokaz |
|---|---|---|---|---|---|
| 1 | `routers/client_portal.py:701-705`<br>`create_signed_url(_p, 3600)` | `portal-uploads` | **3600 s (60 min)** | **DA — dvostruka** | vidi §5.1 |

### 5.1 Trag unazad od poziva do autentifikacije

Endpoint: `GET /api/client-portal/uploads/{predmet_id}` — `routers/client_portal.py:658-724`

1. **Autentifikacija** — `user: dict = Depends(get_current_user)` (`:663`).
   Bez validnog Supabase JWT-a nema ulaska. `uid = user["user_id"]` (`:666`).
2. **Ownership provera #1 (predmet)** — `:670-678`:
   `supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid)`;
   ako nema reda → `404 "Predmet nije pronađen."`. Tuđi `predmet_id` ovde pada.
3. **Ownership provera #2 (upload red)** — `:682-689`:
   `supa.table("client_portal_uploads")...eq("predmet_id", predmet_id).eq("advokat_user_id", uid)`.
   **`storage_path` koji se kasnije potpisuje dolazi ISKLJUČIVO iz ovog reda** (`:699`, `:702`),
   nikad iz korisničkog ulaza.
4. **Tek tada** `create_signed_url(_p, 3600)` (`:701-705`).
5. Rezultat izlazi kao `"download_url"` (`:716`), a frontend ga koristi kao `<a href>`
   (`static/vindex.js:13619`, sa `rel="noopener"`).

**Zaključak: napadač NE MOŽE dobiti signed URL za tuđi dokument.**
Nema putanje kroz koju korisnički kontrolisan string stiže do `create_signed_url`. Nijedan
signed URL ne nastaje bez ownership provere.

### 5.2 Rizici koji ipak postoje na ovom jednom pozivu

| ID | Nalaz | Ozbiljnost | Dokaz |
|---|---|---|---|
| FIN-STG-001 | **60 min TTL je predugačak za bearer URL.** URL nosi svu autorizaciju u sebi, završava u istoriji pretraživača i u DOM-u, i deli se kopiranjem. Za jedan klik na „⬇ Preuzmi" dovoljno je 60-120 s. | MEDIUM | `client_portal.py:703` (`3600`), `static/vindex.js:13619` |
| FIN-STG-002 | **Signed URL preživljava opoziv pristupa.** Supabase signed URL je stateless potpisan token — ne postoji server-side lista opoziva. Deaktiviranje portal tokena (`is_active=false`, `client_portal.py:547`) ili brisanje reda **ne poništava** već izdat URL; on radi do isteka 60 min. | MEDIUM | `client_portal.py:547`, arhitektura Supabase signed URL-a |
| FIN-STG-003 | **Brisanje dokumenta je best-effort → signed URL može nadživeti „obrisan" dokument.** U `DELETE /api/client-portal/uploads/{upload_id}` (`:750-790`), `bucket.remove([storage_path])` je u `try/except` koji na grešku samo loguje `warning` (`:781-782`) i **nastavlja** da briše DB red. Ako `remove` padne, blob ostaje u bucket-u, DB red nestaje (pa ga niko više ne vidi u UI), a svaki ranije izdat signed URL i dalje vraća fajl do isteka TTL-a. Advokat vidi „obrisano", klijentov dokument je i dalje dohvatljiv. | MEDIUM | `routers/client_portal.py:776-790` |

Odgovor na pitanje 8 eksplicitno: **DA — signed URL nastavlja da radi nakon opoziva pristupa,
i može nastaviti da radi nakon „brisanja" dokumenta ako je storage `remove` tiho pao.**

### 5.3 Bucket-i BEZ signed URL-ova

- `intake-dokumenti` — **nema nijednog signed URL-a i nema nijednog read endpointa ka korisniku.**
  Blobovi se pišu (`smart_intake.py:185`, `api.py:5051`) i čita ih isključivo backend worker sa
  service ključem (`shared/intake_worker.py:480`). `predmet_dokumenti.storage_path` (`api.py:5203`)
  se nikad ne pretvara u URL — grep za čitanje te kolone iz endpointa → nema.
  Napadačka površina kroz URL: **nula**.
- `klijent-dokumenti` — download ide kroz backend proxy (`klijenti/router.py:913-999`):
  `_auth_from_request` → `can_perform(role,"download_document")` → `_verify_owns_klijent`
  (`klijenti/router.py:85-102`, `.eq("id",klijent_id).eq("user_id",user_id)`) → audit log →
  `bucket.download()` → AES-GCM dekripcija → `StreamingResponse` sa PDF watermark-om.
  Nema URL-a koji izlazi napolje. (Ali bucket ne postoji — §7.)

---

## 6. ENKRIPCIJA U MIROVANJU (kontekst za procenu uticaja)

| Bucket | Šta se upisuje | Dokaz |
|---|---|---|
| `intake-dokumenti` | **AES-GCM enkriptovano pre upload-a** (`smart_intake.py:184` `_encrypt(raw)`; `api.py:5049`), ključ iz `security.crypto._get_field_key()`; storage ključ je `{{user_id}}/{{uuid4hex}}` (`smart_intake.py:181`) | `smart_intake.py:183-192`, `intake_worker.py:472-487` |
| `klijent-dokumenti` | **AES-GCM enkriptovano** (`klijenti/router.py:797-802`), storage ključ randomizovan (`generate_storage_key()`, `:791`), naziv fajla takođe enkriptovan (`:822`) | `klijenti/router.py:793-816` |
| `portal-uploads` | **PLAINTEXT.** `bucket.upload(path=storage_path, file=sadrzaj, ...)` — `sadrzaj` je sirovi `await fajl.read()` (`:563`), bez enkripcije. Putanja: `{{advokat_uid}}/{{predmet_id}}/{{uuid4hex}}_{{bezbedan_naziv}}` (`:588`) | `routers/client_portal.py:563`, `:588`, `:591-599` |

**FIN-STG-005 (MEDIUM):** `portal-uploads` je **jedini bucket sa klijentskim dokumentima u
otvorenom tekstu**, i istovremeno **jedini bucket iz kog izlazi signed URL**. Da je taj bucket
bio javan, curenje bi bilo potpuno i nepovratno. Nije javan (§2), ali defense-in-depth ovde
zavisi od jedne jedine kontrole (`public=false`), bez druge linije (ni enkripcije, ni RLS-a).
Ostala dva bucket-a bi i pri javnom statusu izlagala samo AES-GCM ciphertext pod nasumičnim ključem.

---

## 7. `klijent-dokumenti` — BUCKET NE POSTOJI (novi nalaz)

**FIN-STG-006 (HIGH, funkcionalni + integritet podataka):**

Dokaz:
```
GET /storage/v1/bucket/klijent-dokumenti
  -> HTTP 400 {"statusCode":"404","error":"Bucket not found","code":"NoSuchBucket"}
supa.table("klijent_dokumenti").select(count="exact") -> count = 0
```

Nema migracije koja ga kreira (grep `storage.buckets` → jedini `INSERT` je za `intake-dokumenti`),
nema `create_bucket` poziva, nema ni komentara-uputstva kao za `portal-uploads`.

Posledica po kodu: `klijenti/router.py:809-819` (`bucket.upload`) uvek baca izuzetak na
`NoSuchBucket` i vraća `500 "Greška pri upload-u: ..."`. Cela „Faza 4 — Dokumentacioni trezor"
(upload `:755`, lista `:894`, download `:913`, watermark, audit) je **nedostižna funkcionalnost**:
0 redova u `klijent_dokumenti`, 0 blobova, nijedan korisnik nikad nije uspešno okačio dokument u Trezor.

Ovo **nije** bezbednosno curenje (ništa ne postoji da bi iscurelo), ali obara raniju tvrdnju iz
`docs/security/ACCESS_CONTROL_AUDIT.md:378` da je status tog bucket-a „UNKNOWN jer je napravljen
ručno u Dashboard-u". **Nije napravljen uopšte.**

Napomena o metodu koja je to prethodno sakrila: `supa.storage.from_("klijent-dokumenti").list()`
vraća prazan niz umesto greške, pa je bucket izgledao kao „postoji i prazan je".

---

## 8. READ-ONLY SQL VERIFIKACIONI ARTEFAKT (za rezidualni UNKNOWN)

Merenje `public` flag-a je uspelo i ne treba ga ponavljati. Sledeći SELECT-ovi zatvaraju **jedini
preostali UNKNOWN** (RLS na `storage.objects`) i moraju se pokrenuti u Supabase SQL editoru.
**Samo SELECT — ništa ne menja.**

```sql
-- ── VERIFY_STORAGE_RLS_READONLY.sql ──────────────────────────────────────────
-- Bez izmena. Samo čitanje. Pokrenuti u Supabase SQL editoru.

-- (1) Potvrda public flag-a nezavisno od Storage API-ja
SELECT id, name, public, created_at
FROM storage.buckets
ORDER BY id;
-- OČEKIVANO: 2 reda, oba public = false, klijent-dokumenti odsutan

-- (2) Da li je RLS uopšte uključen na storage.objects?
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN ('objects', 'buckets')
  AND relnamespace = 'storage'::regnamespace;
-- OČEKIVANO (bezbedno): relrowsecurity = true

-- (3) Koje politike postoje nad storage šemom?
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = 'storage'
ORDER BY tablename, policyname;
-- Ako je REZULTAT PRAZAN a (2) vraća relrowsecurity = true:
--   → nijedna uloga osim service_role ne može ništa nad storage.objects. BEZBEDNO.
-- Ako (3) vraća politiku sa `qual = true` ili `roles = {anon}`:
--   → NALAZ P0, prijaviti odmah.

-- (4) Kome su data prava na storage šemi
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'storage'
ORDER BY grantee, table_name, privilege_type;
-- Traži: grantee = 'anon' sa SELECT nad 'objects' → to bi bio nalaz.
```

---

## 9. UNKNOWN — sa razlozima

| # | Pitanje | Zašto je UNKNOWN | Kako se zatvara |
|---|---|---|---|
| U1 | Da li postoji RLS politika na `storage.objects` u produkciji? | `storage` šema nije izložena kroz PostgREST (`PGRST106: Only the following schemas are exposed: public, graphql_public`), a kovanje `authenticated` JWT-a nije moguće jer projekat koristi ES256/JWKS (`signature verification failed`). Bez `SUPABASE_DB_URL` nema direktnog `pg_policies` upita. | §8, upit (2) i (3) |
| U2 | Da li ulogovan korisnik može direktno kroz Storage API pročitati tuđi blob? | Zavisi isključivo od U1. Statički je utvrđeno da naš frontend to nikad ne radi, ali to ne sprečava ručni poziv. | §8, upit (2)/(3)/(4) |
| U3 | Da li je `intake-dokumenti` bio PUBLIC u nekom periodu pre 2026-08-13? | Supabase ne vodi istoriju promene `public` flag-a; `updated_at` je jednak `created_at`, što sugeriše da flag nikad nije menjan nakon kreiranja, ali to nije dokaz. | nema izvora podataka — trajno UNKNOWN |
| U4 | Da li je onih 7 blobova u `intake-dokumenti` dešifrovano ikad izloženo? | Nema access-log-a Storage objekata na trenutnom Supabase planu. | Storage access logs (plan upgrade) |

---

## 10. LISTA NALAZA

| ID | Nalaz | Ozbiljnost | Lokacija |
|---|---|---|---|
| FIN-STG-001 | Signed URL TTL 3600 s za jedan klik na preuzimanje | MEDIUM | `routers/client_portal.py:703` |
| FIN-STG-002 | Signed URL preživljava opoziv portal tokena / gašenje pristupa | MEDIUM | `routers/client_portal.py:547`, `:701-705` |
| FIN-STG-003 | Brisanje uploada: `storage.remove` je non-fatal → blob i signed URL nadžive „brisanje" | MEDIUM | `routers/client_portal.py:776-790` |
| FIN-STG-004 | Test-korisnički prefiks (`00000000-…`, nije UUID) sa blobovima u produkcionom bucket-u | LOW | produkcioni `intake-dokumenti` |
| FIN-STG-005 | `portal-uploads` čuva klijentske dokumente u PLAINTEXT-u; jedina odbrana je `public=false` | MEDIUM | `routers/client_portal.py:563`, `:591-599` |
| FIN-STG-006 | Bucket `klijent-dokumenti` ne postoji → cela Faza 4 „Trezor" je mrtva funkcionalnost | HIGH (funkcionalno) | `klijenti/router.py:809`, `:962`; nijedna migracija |
| FIN-STG-007 | Nijedna RLS politika na `storage.objects` u izvornom kodu — nema defense-in-depth ako `public` flag ikad odleti | MEDIUM | ceo repo (0 pogodaka) |
| FIN-STG-008 | `migrations/073:362` `ON CONFLICT DO NOTHING` — migracija ne može ispraviti ručno javan bucket; deklaracija nije kontrola | LOW (metodološki) | `migrations/073_intake_foundations.sql:362-364` |
| FIN-STG-009 | `portal-uploads` se ne kreira nijednom migracijom, samo SQL komentarom | LOW | `migrations/013_client_portal_uploads.sql:4-5` |
| FIN-STG-010 | `SUPABASE_JWT_SECRET` nije secret ovog projekta; HS256 grana verifikacije je mrtva | LOW (van opsega) | `shared/deps.py:196-206`, `api.py:236-239` |

---

## 11. METODOLOGIJA I INTEGRITET DOKAZA

- Sve sonde su bile **isključivo READ**: `GET /storage/v1/bucket`, `GET /storage/v1/bucket/{id}`,
  `GET /storage/v1/object[/public]/…`, `POST /storage/v1/object/list/…` (listing je čitanje),
  `select(..., count="exact").limit(0)`. **Nula** `upload` / `remove` / `create` / `update` poziva.
- Nijedan produkcijski fajl nije izmenjen. Skripte sondi žive samo u scratchpad-u sesije.
- Nijedan kredencijal nije ispisan. `SUPABASE_URL` maskiran. Vrednosti iz `.env` istorije
  proveravane su isključivo po **imenima promenljivih** (`grep -oE '^[A-Z_]+='`), nikad po vrednosti.
- Identifikatori korisnika iz bucket listinga maskirani su na prvih 6 znakova / opisani oblikom.

**Odgovor na dva ključna pitanja, bez ograda:**
1. **Nijedan bucket nije PUBLIC** — izmereno, `public=false` na oba postojeća.
2. **Nijedan signed URL ne može nastati bez ownership provere** — postoji tačno jedan
   `create_signed_url` u celom produkcijskom kodu i iza njega su dve nezavisne ownership provere.
