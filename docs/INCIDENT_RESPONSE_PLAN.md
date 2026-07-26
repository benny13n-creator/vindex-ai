# Vindex AI — Incident Response Plan (IRP)

**Datum:** 2026-07-26
**Autor konteksta:** formalizacija operativne bezbednosti, nadovezuje se na
postojeću DevSecOps/DR infrastrukturu (v. §0).

---

## 0. Obim i odnos prema postojećim dokumentima

Vindex AI već ima 3 relevantna bezbednosna dokumenta — ovaj plan ih **ne
duplira**, već popunjava prazninu između njih:

| Dokument | Pokriva | Ovaj IRP se razlikuje po |
|---|---|---|
| `docs/security/DISASTER_RECOVERY_PLAN.md` | Infrastrukturni total outage (Render/Supabase nedostupni) i DB restore procedure, sa RTO/RPO ciljevima | IRP je ŠIRI: pokriva bezbednosne incidente (curenje podataka, RLS bypass), AI/kvalitet incidente (Quality Gate, LRE, Pinecone retrieval), i opštu P0-P3 klasifikaciju — ne samo infra outage |
| `docs/security/SECURITY_GAP_REGISTER.md` | Otvoreni bezbednosni nalazi (SEC-XXX numerisani) | IRP je proces ZA REAGOVANJE kad se nešto od ovoga (ili nešto novo) manifestuje kao stvaran incident |
| `docs/security/STRIDE_THREAT_MODEL.md` | Pretnje po kategoriji (Spoofing/Tampering/Repudiation/...) | IRP je operativni odgovor KADA se pretnja materijalizuje |

**Za scenario "totalni outage Render-a/Supabase-a" ili "DB restore", ovaj
dokument upućuje na `DISASTER_RECOVERY_PLAN.md` §4.1/§4.2 umesto da
ponavlja te korake** — ta dva scenarija su tamo već detaljno razrađena
(RTO ≤ 2h, konkretne komande, poznata ograničenja).

**Iskrena napomena o timu (ista kao u DRP-u, ne ponavlja se drugačije
ovde jer bi bilo neiskreno predstaviti drugačiju sliku):** Vindex AI ima
**jednog operatora** (founder) — nema sekundarni on-call, nema
bezbednosni tim za eskalaciju. Svaka referenca na "tim/inženjera" u
sekcijama ispod znači "founder, sam" — formulisano generički radi
budućeg rasta (kad se doda drugi operator, ažurirati samo §2/§5 uloge,
ne ceo dokument).

**Napomena o hosting platformi:** DRP (§9) već dokumentuje otvorenu
nejasnoću Render vs. Railway (postoji `railway.toml`, ali produkcioni
URL-ovi ukazuju na Render) — ovaj dokument pretpostavlja Render, isto
kao DRP, iz istog razloga.

---

## 1. Severity Klasifikacija Incidenata (P0–P3)

| Nivo | Definicija (opšta) | Konkretni primeri u Vindex AI kodu | SLA odziva | SLA rešavanja |
|---|---|---|---|---|
| **P0 — CRITICAL** | Prekid rada core sistema, curenje klijentskih podataka, RLS bypass, neovlašćen pristup tuđem namespace-u | • Render/Supabase totalni outage (→ DRP §4.1)<br>• RLS politika na `predmeti`/`klijenti`/`staging_memory` propušta cross-user pristup (migracije 018/078/088)<br>• Korisnik A vidi vektore iz `kancelarija_{B}`/`user_{B}` Pinecone namespace-a (`shared/kancelarija_utils.py::rag_owner_namespace`) — namespace izolacija probijena<br>• `security_events`/`audit_immutable` pokazuju masovan neautorizovan pristup | < 15 min | < 2h |
| **P1 — HIGH** | Pad ključnih AI servisa, masovne otkazane LLM pozive bez failover-a | • `services/legal_reasoning_engine.py` (LRE) ne uspeva ni za jedan poziv<br>• Pinecone `_get_index()` (`app/services/retrieve.py`) baca grešku na SVAKI upit, ne samo povremeno<br>• `services/quality_gate.py`/`_stage_draft_for_review` (`routers/drafting.py`) blokira SVE korisnike (napomena: dizajn je već fail-soft — v. §2 korak 3, ovo bi bio regresija u tom fail-soft ponašanju, ne očekivano stanje)<br>• OpenAI API nedostupan bez ijednog uspešnog poziva kroz `shared/ai_client.py` | < 1h | < 6h |
| **P2 — MEDIUM** | Parcijalni pad ne-kritičnih modula, usporavanje pretrage | • Greška u renderovanju jedne `.strat-feature-card` funkcije (npr. `pred_openStrat` za jedan modul)<br>• Cross-case Pinecone pretraga (`kancelarija_namespace` parametar) sporija ali funkcionalna<br>• Jedan `scripts/scrape_*.py` ingest posao otkazuje, ostatak korpusa nije pogođen | < 4h | < 24h |
| **P3 — LOW** | Kozmetičke UI greške, sporedni bagovi u logovanju | • Vizuelni glitch u `.vx-phase-tab` na određenoj rezoluciji<br>• Deprecation warning u logovima (`on_event`, `httpx` — već poznati, v. postojeći pytest izlaz) | < 24h | Sledeći sprint |

**Napomena o klasifikaciji AI/kvalitet incidenata (P1 kategorija je nova
u odnosu na DRP, koji pokriva samo infra):** ovi scenariji su specifični
za Institutional Memory V2 arhitekturu (2026-07-26) i Legal Reasoning
Engine — DRP ih ne pominje jer nisu infra-outage tipa.

---

## 2. First 30-Minutes Recovery Playbook (P0/P1)

### 0–5 min — Containment & Trijaža

1. Potvrdi obim: `https://status.render.com`, `https://status.supabase.com`,
   [OpenAI status](https://status.openai.com), [Pinecone status](https://status.pinecone.io).
   Ako je platforma-širok outage → DRP §4.1, ne debaguj aplikativni kod.
2. Ako je incident BEZBEDNOSNE prirode (kompromitovan ključ/sesija):
   - **Kompromitovan API ključ** (`SUPABASE_SERVICE_KEY`/`OPENAI_API_KEY`/
     `PINECONE_API_KEY`): rotiraj ključ kod provajdera, ažuriraj Render
     environment varijable, redeploy (isti mehanizam kao DRP §4.1 korak 3).
   - **Kompromitovana korisnička sesija**: Supabase Dashboard →
     Authentication → Users → pronađi korisnika → "Sign out" (invalidira
     sve aktivne JWT sesije tog korisnika odmah).
   - **Kompromitovan `BRIEFING_CRON_SECRET`/`CRON_SECRET`**: rotiraj u
     Render env varijablama (v. `docs/PRODUCTION_READINESS_REPORT_2026-07-25.md`
     za kontekst zašto je ova varijabla posebno osetljiva — fail-closed
     od 2026-07-26, ali i dalje deljena tajna).
3. Zapiši vreme početka (interni status log — pošto je operator sam,
   ovo može biti prost timestamp u ličnoj belešci/Slack-u-sebi, isto
   kao DRP §4.1 korak 2) — postaje referentna tačka za post-mortem §4.

### 5–15 min — Assess & Triage (uticaj na podatke)

1. Proveri `security_events` tabelu za neobične obrasce (masovni
   `login_failed`, neočekivan `permission_denied` iz istog IP-a/user-a):
   ```sql
   select * from security_events where created_at > now() - interval '1 hour' order by created_at desc;
   ```
2. Proveri `staging_memory` (Institutional Memory V2) za znake zagađenja
   — vektori sa `origin=AI_GENERATED` koji su NEKAKO dospeli u
   `kancelarija_{id}`/`user_{id}` Pinecone namespace bi bili tačno "AI-to-AI
   degeneracija" rizik koji je taj sistem dizajniran da spreči (v.
   `docs/INSTITUTIONAL_MEMORY_V2_IMPLEMENTATION.md` STUB 2 defense-in-depth):
   ```sql
   select id, status, is_lawyer_approved, confidence_score, pinecone_indexed
     from staging_memory where pinecone_indexed = true and is_lawyer_approved = false;
   ```
   (Ovaj upit ne bi smeo NIKAD da vrati redove — ako vrati, to je dokaz
   da je gate zaobiđen, ne samo da postoji sumnjiv sadržaj.)
3. Proveri audit hash-chain integritet (`shared/audit_immutable.py`):
   ```
   GET /api/admin/security/audit-verify
   ```
   ili `python scripts/dr_runbook.py --check chain`. Prekid NA MESTU
   restore-a je očekivan (DRP §4.3); prekid NEGDE DRUGO je signal
   neovlašćene izmene, ne restore artefakt.
4. Za Pinecone-specifičan incident: **iskreno ograničenje** — ne postoji
   automatizovan export/snapshot alat za same vektore u ovom repo-u
   (`pinecone_capacity_snapshots`, migracija 087, prati samo BROJ
   vektora radi kapaciteta, ne sadržaj). Ako je potrebna forenzička
   kopija namespace-a PRE bilo kakve izmene, koristi Pinecone Python
   klijent direktno (`from uploaded_doc.ingest import _get_pinecone_index`)
   da izvezeš ID-jeve i metadata pogođenog namespace-a u JSON PRE
   intervencije — v. §3.

### 15–25 min — Rollback / Failover Execution

1. **Migracije/šema**: `python scripts/audit_deployment_consistency.py`
   — potvrđuje da li je šema usklađena sa kodom (v.
   `docs/SECURITY_SPRINT_PHASE1.md` §2 za puno objašnjenje alata i
   živo-testirane rezultate). Ako incident potiče iz migracije koja
   nije trebalo da bude primenjena, ovo je prvi dijagnostički korak.
2. **Loš deploy (git rollback)**: Render Dashboard → Vindex servis →
   "Manual Deploy" → izaberi prethodni poznato-dobar commit (isti
   mehanizam kao DRP §4.1 korak 3, primenjen na "loš kod" umesto
   "platform down" scenario). Ne koristiti `git revert` + push kao
   jedini korak ako je potrebna HITNA promena — direktan redeploy
   prethodnog commit-a je brži od čekanja CI-ja.
3. **LLM provajder failover**: `shared/ai_client.py`'s
   `_patch_openai_module()` bira Azure OpenAI **samo ako** su
   `AZURE_OPENAI_KEY`/`AZURE_OPENAI_ENDPOINT` postavljeni **pri
   pokretanju procesa** — ovo NIJE automatski runtime failover.
   Ako je OpenAI nedostupan: postaviti te 2 env varijable u Render
   dashboard-u + redeploy. Podaci ostaju u EU (Azure), deployment imena
   moraju se poklapati sa model imenima (`gpt-4o`, `gpt-4o-mini`).
4. **Rate limiter fail-open podsetnik**: `shared/rate.py` je već
   dizajniran da fail-open-uje na Redis grešku (SEC-005,
   `tests/test_sec005_failopen_limiter.py`) — ako je incident
   "previše zahteva prolazi", ovo JE očekivano ponašanje po dizajnu
   (svesna odluka posle prošlog Upstash ispada), ne bug za rollback.

### 25–30 min — Communication & Status

1. Upisati incident u interni registar (v. §4 template ispod — čak i
   ako je pun post-mortem tek za 48h, OTVORITI zapis SADA sa Incident ID
   i vremenom detekcije).
2. Ako incident uključuje gubitak/curenje podataka ili je prešao 1h
   trajanja: poslati GDPR čl. 33-34 / ZZPL čl. 52-53 obaveštenje —
   template već postoji u `scripts/dr_runbook.py`'s
   `INCIDENT_EMAIL_TEMPLATE` (isti mehanizam kao DRP §4.1 korak 8, ovde
   primenjen i na bezbednosne, ne samo infra incidente).
3. Pošto je operator sam, "interno obaveštenje" iz zahteva je u praksi
   ažuriranje istog log zapisa iz koraka 1 — nema drugog tima kome se
   šalje.

---

## 3. Evidence Preservation Procedure

**Princip:** NIŠTA se ne briše/restartuje dok se ne sačuva dokaz o
trenutnom stanju — čak i ako to znači da je sistem u degradiranom stanju
par minuta duže.

1. **Sentry** (ako je `SENTRY_DSN` konfigurisan u produkciji — proveriti
   `api.py:30`): Sentry sam zadržava evente po sopstvenoj retencionoj
   politici (plan-zavisno) — ništa dodatno ne treba raditi da bi se
   "sačuvalo", ALI treba zabeležiti direktan link ka relevantnom Sentry
   issue-u u incident zapisu (§2 korak 1) dok je još svež, pre nego što
   se error stream nastavi i zatrpa ga.
2. **Supabase — `security_events` i `audit_immutable` tabele**: PRE bilo
   kakvog restore-a ili brisanja, izvesti relevantan vremenski opseg:
   ```sql
   copy (select * from security_events where created_at > 'INCIDENT_START') to stdout with csv header;
   copy (select * from audit_immutable where created_at > 'INCIDENT_START') to stdout with csv header;
   ```
   (Pokrenuti preko Supabase SQL Editor-a "Download as CSV" opcije, ili
   `psql` direktne konekcije ako je dostupna — čuvati lokalno PRE
   restore koraka iz DRP §4.2.)
3. **Pinecone**: v. §2 korak 4 — nema ugrađenog snapshot alata u ovom
   repo-u (priznato ograničenje, ne prećutano). Ako je forenzička kopija
   namespace-a potrebna, izvesti ID-jeve+metadata (ne embeddinge, koji
   se mogu regenerisati iz `predmet_dokumenti.tekst_sadrzaj` ako
   zatreba) preko Pinecone `index.query`/`list` API-ja u JSON fajl PRE
   bilo kakve izmene namespace-a.
4. **Git/kod stanje**: `git log -1 --format=%H` u trenutku detekcije
   (koji je commit bio live) — čuva se u incident zapisu, posebno bitno
   ako se rollback desi (§2 korak 15-25min) pre nego što je stanje
   dokumentovano.
5. **Nikad ne restartovati Render servis PRE koraka 1-4** ako je
   incident bezbednosne prirode — restart briše in-memory stanje
   (uključujući `shared/rate.py`'s in-memory fallback limiter brojače i
   `routers/voice_realtime.py`'s `_active_sessions` dict) koje može biti
   relevantno za rekonstrukciju šta se dogodilo.

---

## 4. Post-Mortem Template

**Popunjava se u roku od 48h od zatvaranja SVAKOG P0/P1 incidenta.**
(Napomena: ovo je formalniji/detaljniji template od postojećeg u DRP §7,
koji ostaje kao brz stub za čisto infra-outage scenarije; za bilo koji
incident koji uključuje bezbednost, podatke, ili AI-sistem, koristiti
OVAJ template.)

```markdown
## Incident ID & Title
INC-YYYY-MM-DD-NN — [kratak opisni naslov]

## Severity Level
P0 / P1 / P2 / P3 (v. §1 matricu)

## Timeline
| Vreme (UTC) | Događaj |
|---|---|
| | Detection — kako/ko je primetio |
| | Containment — prvi korak izolacije |
| | Mitigation — kada je uticaj prestao da raste |
| | Recovery declared — kada je sistem potvrđen zdravim |

## Root Cause Analysis (5 Whys)
1. Zašto se incident desio? →
2. Zašto [odgovor na 1]? →
3. Zašto [odgovor na 2]? →
4. Zašto [odgovor na 3]? →
5. Zašto [odgovor na 4]? → (koren uzroka)

## Impact Analysis
- Pogođeni korisnici (broj/segment, ne nužno imena — GDPR):
- Pogođeni podaci (koje tabele/namespace-ovi, da li je bilo curenja van sistema):
- Finansijski/reputacioni uticaj (ako primenjivo):
- Da li je RTO/RPO cilj iz DRP-a ispoštovan (za infra incidente)?

## Action Items
| Akcija | Vlasnik | Rok | Status |
|---|---|---|---|
| | | | |

## Deviations from this plan and why
(Ako je nešto iz §2 preskočeno ili urađeno drugačije — zašto, i da li
plan treba ažurirati.)
```

---

## 5. Verifikacija & Integracija

**Konkretne komande za pokretanje postojećih alata (ne hipotetičke):**

```bash
# Connectivity + config + audit chain check (brzo, posle svakog deploy-a)
python scripts/dr_runbook.py --quick

# Pun check: backup, chain, env, sve
python scripts/dr_runbook.py --check all

# Da li je šema (uključujući migracije 085-088) usklađena sa živom bazom
python scripts/audit_deployment_consistency.py

# Backup-restore drill verifikacija (mesečno, ili odmah posle P0 restore-a)
python scripts/verify_backup_restore.py

# Audit hash-chain integritet (HTTP) -- zahteva pravi founder Supabase JWT
# (Authorization: Bearer <access_token> iz normalne prijave), NE
# FOUNDER_TOKEN env var (taj je posebna, odvojena mera za X-Admin-Token
# na drugom endpointu, routers/dokument.py -- proveri _is_founder(email)
# guard u api.py pre nego što pretpostaviš da bilo koji token radi).
curl https://vindex-ai.onrender.com/api/admin/security/audit-verify \
  -H "Authorization: Bearer <supabase-access-token-za-founder-nalog>"
```

**DevSecOps skeneri** (`.github/workflows/security.yml`, v.
`docs/SECURITY_SPRINT_PHASE1.md` za pun kontekst) — pokreću se
automatski na svaki push/PR ka `main`, ali mogu se ručno okinuti:

```bash
gh workflow run security.yml           # svih 6 job-ova (secret-scan,
                                        # sast-core/full, dependency-scan,
                                        # semgrep-core/full)
```

Ako P0/P1 incident potiče od koda koji je prošao CI — to je samo po sebi
nalaz za post-mortem §4 Action Items ("zašto skener nije uhvatio ovo").

### Pytest verifikacija

Ovaj dokument je čista dokumentacija (nula izmena koda) — pytest suite
je pokrenut radi potvrde da dodavanje `.md` fajla nije uticalo ni na šta
(očekivano, ali provereno, ne pretpostavljeno):

```
python -m pytest -q
```
