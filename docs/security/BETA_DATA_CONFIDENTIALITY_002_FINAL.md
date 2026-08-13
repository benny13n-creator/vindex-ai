# BETA-DATA-CONFIDENTIALITY-002 — STORAGE & TENANT ISOLATION FORENSICS

# A. VERDICT

## 🔴 RED

Šest cross-tenant write rupa je zatvoreno sa mutation dokazom. Ali verdikt
ostaje crven, iz tri razloga koja se ne mogu zaobići:

1. **Klijentski portal i dalje čuva dokumente nešifrovano** (CONF-002).
2. **Ne postoji delete path za Pinecone** — GDPR čl. 17 je tehnički nesprovodiv.
3. **RAG unutar kancelarije zaobilazi ACL predmeta** (F-01) — putanja je živa.

Najveća vest sprinta je ipak dobra: **nijedan bucket nije javan**, i to je sada
izmereno, ne pretpostavljeno.

---

# B. BASELINE

```
baseline:   bb5cadbb   (radno stablo čisto, 0 izmena praćenih fajlova)
metod:      5 paralelnih forenzičkih timova + nezavisna re-verifikacija
            svakog kritičnog nalaza mojim merenjem
```

---

# C. TESTS

```
pre:    5265 passed / 2 skipped / 0 failed
posle:  5281 passed / 2 skipped / 0 failed      (+16)
seed:   no:randomly ✓   ·   randomly-seed=11 ✓
```

Nijedan postojeći test nije oslabljen ni prilagođen.

---

# D. DATA BOUNDARY MATRIX

| DATA | DESTINATION | ENCRYPTED | TENANT ISOLATED | RETENTION | DELETE | PROOF |
|---|---|---|---|---|---|---|
| Intake dokument | `intake-dokumenti` | **DA** AES-GCM | `user_id` putanja | trajno | ručno | sha256 pre/posle |
| **Portal dokument** | **`portal-uploads`** | **NE** | `user_id` putanja | trajno | delimično | sha256 = ulaz |
| Trezor dokument | `klijent-dokumenti` | n/p | n/p | n/p | n/p | **bucket ne postoji** |
| Tekst dokumenta | Pinecone | **NE** | namespace | **trajno** | **NE POSTOJI** | `describe_index_stats` |
| Tekst dokumenta | OpenAI | TLS | n/p | **politika provajdera** | ne | 0 pogodaka `store=False` |
| Polja klijenta | Supabase DB | 6 polja | `.eq(user_id)` | trajno | GDPR ruta | `crypto.py` |
| Audio razgovora | OpenAI WSS | TLS | n/p | politika provajdera | ne | `voice_orchestrator.py:531` |

---

# E. SECURITY FINDINGS

## CRITICAL

**CONF-008 — globalna promena role bez ijedne provere mete · ZATVORENO**

`klijenti/router.py:1195`. Jedina provera je bila `user["role"] < Role.PARTNER`
— pitanje o **pozivaocu**. `user_roles` je globalna tabela bez
`kancelarija_id`, pa je partner bilo koje kancelarije mogao da promeni rolu
korisniku bilo koje druge: da unapredi saučesnika u `partner`, ili da suparniku
spusti rolu na `sekretaricu` i time mu oduzme `access_confidential` i
`download_document` **nad njegovim sopstvenim klijentima**.

Četiri otežavajuće okolnosti koje ranije niko nije prijavio: nula audita
(akcija `user_role_change` deklarisana u `audit_immutable.py:89`, nula
pozivalaca); nema ograničenja stope; **proročište postojanja naloga** (strani
UUID → 200, nepostojeći → 500 kroz nepresretnuto kršenje stranog ključa);
i zaostala privilegija — uklanjanje iz firme nikad ne briše globalnu rolu.

## HIGH

| ID | Nalaz | Status |
|---|---|---|
| **CONF-009** | `zadaci/kreiraj` — `predmet_id` **i `dodeljen_uid`** neprovereni. `workspace.py:129` čita zadatke samo po `dodeljen_uid`, pa je svako mogao ubaciti stavku proizvoljnog naslova i roka na **tuđu kanonsku dnevnu tablu**, uz notifikaciju. Prijavljeni lanac preko `predmeti(naziv)` embed-a zapravo **ne radi** — FK ne postoji, PostgREST bi vratio `PGRST200`. Stvarni exploit je drugi i gori. | **ZATVORENO** |
| **CONF-010** | `/api/pitanje` (`api.py:3378`) i `/api/procena` (`:4895`) upisivali napadačev tekst i pun GPT-4o nalaz u tuđi pravni spis. Asimetrija koja objašnjava propust: **čitanje konteksta na oba endpointa VEĆ filtrira po `user_id`** (`:3339`, `:4774`) — izolacija promišljena na čitanju, zaboravljena na upisu. | **ZATVORENO** |
| **CONF-011** | Isti obrazac na još 7 ruta. Najteže: `billing/recurring` (viseći cross-tenant FK propagira u stvarne `fakture` redove — u novac), `memory-graph/dodaj-vezu` i `firma-memorija/dodaj` (tuđi `predmet_id` u firm-shared graf → u LLM promptove kolega). | **4 ZATVORENE, 3 prihvaćene** |
| **F-01** | `retrieve.py:1847` pretražuje ceo `kancelarija_{id}` namespace za svakog ACTIVE člana, filter samo po `type` — bez `predmet_id`. Baza pristup predmetu ograničava na vlasnika + izričito pozvane saradnike; **RAG to zaobilazi i može vratiti doslovan tekst**. | **OTVORENO** |
| **CONF-002** | `client_portal.py:594` — jedini živi upload put bez enkripcije. To je put kojim **klijent**, ne advokat, šalje dokumente. | **OTVORENO** |
| **PINE-01** | **Ne postoji delete path za trajne vektore.** `cleanup_expired` briše samo `tmp_*`; `DELETE /api/gdpr/account` ne dodiruje Pinecone; nema `@router.delete` za predmet. | **OTVORENO** |

## MEDIUM

- **`klijent-dokumenti` bucket ne postoji** — cela „Dokumentacioni trezor"
  funkcionalnost (`klijenti/router.py:755-999`) puca na 500; tabela ima 0 redova.
  Raniji audit ga je vodio kao „UNKNOWN, ručno napravljen", jer `.list()` nad
  nepostojećim bucket-om vraća **prazan niz umesto greške**.
- **Signed URL je bearer capability bez audita** — 60 min, neopoziv, izdaje se
  unapred za do 50 fajlova, `/api/client-portal` nije u `_AUDIT_PATHS`. Trezor
  za iste dokumente radi obrnuto: audit pre bajtova, watermark, provera role.
- **Brisanje portal fajla je non-fatal** — `bucket.remove()` greška samo loguje
  `warning`, DB red se ipak briše. Advokat vidi „obrisano", blob ostaje.
- **Starlette rolluje upload >1 MB na disk** — plaintext kopija na fajlsistemu
  pre nego što enkripcija počne. Pogađa **sva četiri** puta, i „šifrovane".
- **3 pozadinska posla gube provenance** — `ai_forensics.user_id` je NOT NULL,
  `user_id` dolazi samo iz contextvar-a koji cron nikad ne postavlja. Podaci
  odlaze OpenAI-ju, red koji to dokazuje se ne upisuje.
- **Rotacija ključa uništava sve fajlove** — blobovi nemaju `kid` ni marker
  verzije; enkripcija duplirana 3×, dekripcija 2×, `crypto.py` nema funkciju za
  fajlove.
- **`integracije.py:409` nema SSRF validaciju** koju njen blizanac
  `integrations.py:165` ima. Slep (payload fiksan), ali živ.

## LOW

- `pred_*` ownership provera je logički pokvarena — poredi `predmeti.id` sa
  uuid4 session ID-jem, pa 404 za sve. Fail-closed, ali 30 vektora je zaključano
  i neobrisivo.
- Vector ID je `uuid4` → re-index pravi pune duplikate; upsert ide pre DB upisa
  bez rollback-a → orphan vektori.
- Sintetički test-korisnik (`00000000-…`, nevalidan UUID) ima blobove u
  **produkcionom** `intake-dokumenti`.
- CSP `connect-src` dozvoljava `api.openai.com` i `api.emailjs.com` — nijedan
  klijentski kod ih ne koristi.

## UNKNOWN

| Stavka | Zašto se ne može dokazati |
|---|---|
| **RLS na `storage.objects`** | `storage` šema nije izložena kroz PostgREST (`PGRST106`). Kovanje `authenticated` JWT-a nije uspelo: projekat potpisuje **ES256/JWKS**, a `SUPABASE_JWT_SECRET` u `.env` je HS256 string koji gateway odbija. Statički: **0 `CREATE POLICY` nad storage u celom repou.** READ-ONLY SQL artefakt je pripremljen. |
| **Sentry frame locals** | `send_default_pii=False` ali `before_send` ne postoji, a `include_local_variables` nije isključen uz `attach_stacktrace=True`. Mrtvo bez `SENTRY_DSN`. |
| **OpenAI retencija** | 0 pogodaka za `store=False`, ZDR endpoint, org/project zaglavlje. **Kod ne daje nijednu tehničku garanciju.** |

---

# F. FIXES

| # | Nalaz | Root cause | Fix |
|---|---|---|---|
| 1 | CONF-008 | provera o pozivaocu umesto o meti; `user_roles` bez `kancelarija_id` | `_verify_moze_menjati_rolu` — meta mora biti ACTIVE član firme kojom pozivalac administrira; 404 svuda; samopromena 400; **osnivač bez zaobilaznice, izričito**; + audit + rate limit |
| 2 | CONF-009 | dva neproverena strana ključa | kapija za `predmet_id` po obrascu iz istog fajla (`:443`) + kapija za `dodeljen_uid` (ACTIVE član iste firme ili sam pozivalac) |
| 3 | CONF-010 | izolacija na čitanju, zaboravljena na upisu | `api._poseduje_predmet`, fail-closed, na oba mesta upisa |
| 4 | CONF-011 ×4 | isti obrazac, 10 ruta | **`shared/ownership.py`** — jedan vlasnik provere umesto deset kopija; primenjen na `recurring` (klijent+predmet), `memory_graph`, `firm_memory` |

Fix #4 je root-cause, ne simptomatski: `AUTHORIZATION_PATTERN_RECOMMENDATION.md`
je 2026-07-23 predložio tačno ovu konsolidaciju i nije primenjen — ovih deset
ruta su predviđena posledica.

## Svesno NISU popravljene

`style_checker` (zagađenje analitike, nema čitanja nazad), `knowledge_base`
(kozmetički pogrešna oznaka sopstvene beleške), `portal_monitoring`
(self-scoped). Nijedna ne prelazi granicu poverljivosti. Imenovane, ne tihe.

---

# G. UNRESOLVED

1. **CONF-002** — rewire portala na kanonsku enkripciju. Nije jedna linija:
   traži novi autentifikovani download endpoint (danas ga **nema uopšte** —
   signed URL ide pravo u `<a href>`), izmenu frontenda, i **diskriminator za
   postojeće plaintext fajlove** (`enc_version` kolona ili trial-decrypt;
   `is_encrypted()` se **ne sme** koristiti — vraća `False` za oba slučaja).
   Redosled bez prekida: prvo download koji podržava oba formata, pa frontend,
   pa upload.
2. **F-01** — traži da se lista dostupnih `predmet_id` doprovuče do
   najprometnije AI putanje. Nisam žurio izmenu tamo sa izmerenom izloženošću
   od 0 vektora.
3. **PINE-01** — delete path.
4. **RLS na storage** — čeka jedno pokretanje READ-ONLY SQL-a.

---

# H. ATTACK RESULTS

| # | Napad | Rezultat |
|---|---|---|
| 1 | Tenant A → dokument Tenant B | **ODBIJEN** — 0 cross-tenant read curenja na 297 ruta |
| 2 | Tenant A → signed URL Tenant B | **ODBIJEN** — jedini `create_signed_url` ima dve nezavisne provere pre poziva |
| 3 | Tenant A → Pinecone Tenant B | **ODBIJEN** između kancelarija (namespace iz autentifikovanog `user.id`); **PROLAZI unutar kancelarije** (F-01) |
| 4 | Tenant A → promena role Tenant B | **PROLAZIO → sada ODBIJEN** |
| 5 | Portal → plaintext storage | **PROLAZI** (CONF-002) |
| 6 | Obrisan dokument → i dalje dostupan | **PROLAZI** — signed URL preživi brisanje do isteka |
| 7 | Obrisan subjekt → vektori ostaju | **PROLAZI** (PINE-01) |
| 8 | Re-index → duplikati/orphan | **PROLAZI** — `uuid4` ID |
| 9 | Neovlašćen poziv provajderu | **ODBIJEN** — 3 stvarna bypass-a, od kojih 1 živ (voice WSS, ima entitlement + provenance) |
| 10 | Pozadinski posao zaobilazi governance | **DELIMIČNO** — guard radi, provenance se gubi (3 posla) |
| 11 | Direktan storage pristup mimo aplikacije | **ODBIJEN** — oba bucket-a `public=false`, anonimni pristup 400 |
| 12 | Zlonamerno ime fajla / metadata cure PII | **PROLAZI** — PII na 7 mesta, uključujući SMTP e-mail advokatu |

---

# I. MUTATION RESULTS

```
uklonjene sve tri kapije (CONF-008 / 009 / 010):
  → 12 od 16 testova PADA
  → vraćeno: 16/16 prolazi
```

Preostala 4 su fail-closed provere i **kontrola nad samim test alatom** — one
ne mere kapije, pa je ispravno što prolaze.

Zašto je mutacija ovde uopšte značila nešto: postojeći testovi u repou grade
lance `MagicMock`-ova koji vraćaju unapred zadatu vrednost i **prolaze i sa
uklonjenom kapijom**. `_FakeSupa` u novom testu stvarno primenjuje `.eq()` nad
podacima. Bez toga bi „mutation proof" bio ritual.

**Zašto su postojeći testovi promašili svih deset:**
`test_sec001_predmet_ownership.py:14` opisuje „pun sweep" koji je birao rute po
**`{predmet_id}` u PUTANJI** — a 9 od 10 nalaza uzima ID iz **TELA**. Gore:
`test_beta_lockdown_zadaci_predmet_idor.py:16` u prozi tvrdi da je zadaci-rupa
„izolovan propust, ne sistemski problem" — dok `kreiraj`, u istom fajlu, ima
isti bag i nije testiran.

---

# J. REGRESSION

```
novi security testovi:  16 passed
full suite:             5281 passed / 2 skipped / 0 failed
no:randomly:            ✓
seed=11:                ✓
produkcijski fajlovi:   6 izmenjena + 1 nov (shared/ownership.py)
migracije:              0
mutacije prod. podataka: 0
secrets:                0 ispisanih
```

---

# K. BETA IMPACT

| Putanja | Ocena |
|---|---|
| Upload dokumenta kroz aplikaciju (intake) | **SAFE FOR BETA** — AES-GCM, privatan bucket, dokazano |
| Čitanje tuđih dokumenata kroz API | **SAFE FOR BETA** — 15/15 + 297 ruta bez read curenja |
| Promena role / zadaci / istorija predmeta | **SAFE FOR BETA** — zatvoreno u ovom sprintu |
| Direktan pristup storage-u mimo aplikacije | **SAFE FOR BETA** — bucket-i privatni, izmereno |
| **Klijentski portal** | **NOT SAFE FOR BETA** — plaintext + neopoziv signed URL bez audita |
| **Brisanje podataka / GDPR čl. 17** | **NOT SAFE FOR BETA** — Pinecone kopija se ne briše |
| **RAG unutar kancelarije** | **NOT SAFE FOR BETA** — F-01 |
| Dokumentacioni trezor | **NOT SAFE** — ne radi uopšte (bucket ne postoji) |
| RLS na storage | **UNKNOWN** |

---

# L. NEXT PRIORITY

Rangirano po severity × exploitability × data exposure × blast radius × beta
relevance:

1. **CONF-002 — enkripcija klijentskog portala.** Najviši proizvod svih pet
   kriterijuma: poverljivi dokumenti, plaintext, put kojim ulazi **klijent**,
   i jedini put iz kog izlazi neopoziv bearer URL bez audita.
2. **PINE-01 — delete path za Pinecone.** Blast radius je svaki dokument ikad
   otpremljen; pravna izloženost je GDPR čl. 17, ne samo tehnički dug.
3. **F-01 — filter po predmetu u firm RAG-u.** Izloženost danas 0, ali putanja
   je živa od sledećeg upload-a.
4. **RLS na `storage.objects`** — jedno pokretanje READ-ONLY SQL-a zatvara
   poslednji UNKNOWN u lancu storage-a.
5. **Provenance za pozadinske poslove** — audit, ne poverljivost.

---

# ZAVRŠNA REČ

Sprint je pomerio granicu na mestu gde je bila najtanja: **cross-tenant write je
bio otvoren na deset ruta i niko to nije znao**, jer su svi raniji auditi tražili
ID u putanji umesto u telu. Šest je zatvoreno sa mutation dokazom, uz jedan
vlasnik provere umesto deset budućih kopija.

Ali advokatskoj kancelariji se i dalje ne može reći „vaši dokumenti su
zaštićeni" — jer dokument koji **klijent** pošalje kroz portal stoji nešifrovan,
a nijedan dokument se ne može stvarno obrisati iz Pinecone-a.
