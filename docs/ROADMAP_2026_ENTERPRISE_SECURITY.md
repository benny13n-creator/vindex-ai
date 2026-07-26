# Vindex AI — Enterprise Security & Trust Roadmap (H2 2026)

**Datum:** 2026-07-26. **Baseline:** "Security Foundation" faza završena
(interna procena 88-92/100 — ovo je founder-ova/ranijih sesija sopstvena
ocena, ne nezavisno recertifikovana ovim dokumentom; v. §0.2 zašto je to
bitna razlika).

**Cilj ovog dokumenta:** definisati prelaz iz **interne verifikacije**
("mi tvrdimo da radi, testovi prolaze") u **eksterno dokazivu bezbednost**
("neko van firme je to potvrdio, ili je javno proverljivo").

---

## 0. Kontekst i odnos prema postojećim dokumentima

### 0.1 Šta ovaj dokument NIJE

- **Nije zamena za `docs/security/SECURITY_ROADMAP.md`** (2026-07-23) —
  taj dokument je P0-P3 lista OTVORENIH internih nalaza (gap-closing).
  Ovaj dokument je forward-looking: 3 programa za eksterno poverenje,
  ne lista bagova.
- **Nije zamena za `docs/SECURITY_MATURITY_DASHBOARD.md`** (2026-07-26) —
  taj dokument je SSOT za TRENUTNO stanje (✅/🟡/❌ po oblasti). Ovaj
  dokument je SLEDEĆIH 6 meseci.

### 0.2 Iskrena napomena o "88-92/100" oceni

Ta ocena potiče iz `docs/security/EXECUTIVE_SECURITY_SUMMARY.md` i
ranijih sesija — **samoprocena zasnovana na zatvorenim SEC-XXX
nalazima i pytest pokrivenosti, ne eksterni benchmark**. Ceo Program 1
ovog dokumenta postoji upravo zato što self-assessment ima plafon
verodostojnosti bez nezavisne potvrde — brojka se ne osporava ovde,
ali se eksplicitno NE tretira kao ekvivalent sertifikacije.

### 0.3 Vlasništvo zadataka — realnost jednog operatora

Isto kao `docs/security/DISASTER_RECOVERY_PLAN.md` §5 i
`docs/INCIDENT_RESPONSE_PLAN.md` §0: Vindex AI ima **jednog operatora**
(founder). "Owner" kolona ispod razlikuje:
- **Founder** — zahteva poslovnu odluku, novac, ili spoljni ugovor
  (pentest firma, Cloudflare nalog, Vault servis) — ništa od ovoga
  buduća inženjerska sesija ne može sama pokrenuti.
- **Engineering (buduća sesija)** — kod/infrastruktura koja se može
  implementirati kroz isti proces kao ova sesija, jednom kad founder
  donese odluku/obezbedi nalog gde je potreban.

---

## PROGRAM 1: Security Excellence (Infrastruktura & Eksterna Verifikacija)

### 1.1 Eksterni Penetration Test (Red Team)

| | |
|---|---|
| **Owner** | Founder (komercijalni ugovor sa pentest firmom) |
| **Rok** | Q4 2026 (target, po zahtevu) |
| **Definition of Done** | Potpisan izveštaj nezavisne firme, sa (a) CVSS ocenjenim nalazima, (b) remediation planom za svaki nalaz ≥ MEDIUM, (c) re-test potvrdom da su HIGH/CRITICAL nalazi zatvoreni pre javnog objavljivanja rezultata na Trust Center-u (§Program 3) |

**Opseg (predlog, ne konačan — pentest firma treba da ga sama potvrdi
posle uvida u arhitekturu):**
- Autentifikacija/autorizacija: Supabase JWT tok, `PermissionService`
  gate-ovi, `SEC-001`-klase ownership provere (v.
  `docs/SECURITY_MATURITY_DASHBOARD.md` red 1) — TAČNO ono što interni
  SAST alati (Semgrep/Bandit) **ne mogu** da uhvate (poslovna logika,
  ne poznati CVE obrazac).
- Multi-tenant izolacija: `kancelarija_{id}`/`user_{id}` Pinecone
  namespace (Institutional Memory V2) — pokušaj cross-tenant čitanja.
- AI-specifične pretnje: prompt injection zaobilaženje
  `security/prompt_guard.py`'s guard-a (`shared/ai_client.py`'s
  `_patch_prompt_guard()`), i pokušaj zaobilaska Quality Gate-a
  (`confidence_score >= 0.85` + `is_lawyer_approved` provera,
  `routers/drafting.py`) da se sirov AI tekst ipak ubaci u
  kancelarijsku bazu znanja.
- Infrastruktura: rate limiter fail-open granica (SEC-005, namerno
  ponašanje — pentest treba da POTVRDI da je to dizajn, ne propust).

**Zašto Q4 2026, ne ranije:** migracija 088 (`staging_memory`, Quality
Gate) je **potvrđeno neprimenjena u produkciji** (v. Maturity
Dashboard) — pentest AI Quality Gate opsega pre te migracije bi testirao
kod koji ne postoji uživo. Preduslov: pokrenuti migraciju 088 PRE
zakazivanja pentesta.

### 1.2 Secrets Management & Rotation

| | |
|---|---|
| **Owner** | Founder (izbor/nabavka alata) + Engineering (implementacija) |
| **Rok** | Q3 2026 — dizajn i `FIELD_ENCRYPTION_KEY` rotacija; Q4 2026 — puna automatizacija ako founder odluči za Vault-klase alat |
| **Definition of Done** | (a) `FIELD_ENCRYPTION_KEY` KEY_VERSION šema implementirana i testirana (v. postojeći plan); (b) dokumentovan, ponovljiv postupak ručne rotacije za `SUPABASE_SERVICE_KEY`/`OPENAI_API_KEY`/`PINECONE_API_KEY` (redeploy bez downtime-a); (c) ako founder odluči za automatizovan alat — taj alat u produkciji, ne samo evaluiran |

**Trenutno stanje (provereno, ne pretpostavljeno):**
- **Nema Vault-a niti automatizovane rotacije bilo gde u kodu.** Svi
  ključevi su plain env varijable u Render dashboard-u, ručno rotirane
  (v. `docs/INCIDENT_RESPONSE_PLAN.md` §2, korak "kompromitovan API
  ključ" — postupak postoji, alat za automatizaciju ne).
- **`FIELD_ENCRYPTION_KEY` (AES-256-GCM za JMBG/pasoš/PIB u `klijenti`
  tabeli) VEĆ IMA napisan rotacioni dizajn** — `KEY_ROTATION_ANALYSIS.md`
  (2026-06-11): KEY_VERSION prefiks šema (`enc_v2:` uz stari `enc_v1:`),
  eksplicitno označen "Analiza — ne implementovati bez zasebnog
  planiranja". **Ovaj roadmap item NIJE "smisliti rotaciju" — VEĆ JE
  "implementirati već smišljen, dokumentovan plan."**
- API ključevi (OpenAI/Supabase/Pinecone) nemaju NIKAKAV rotacioni
  plan, dokumentovan ili implementiran — ovo je prava praznina, ne
  već-postojeći-ali-neizvršen posao.

**Predlog koraka:**
1. (Engineering) Implementirati `KEY_ROTATION_ANALYSIS.md`'s
   KEY_VERSION šemu za `FIELD_ENCRYPTION_KEY` — jasno definisan,
   ograničen posao.
2. (Founder) Odlučiti: da li puni Vault (HashiCorp Vault/1Password
   Secrets/Supabase Vault) opravdava operativni trošak za tim od jedne
   osobe, ili je dokumentovan ručni postupak (v. IRP §2) dovoljan za
   sada. **Ovo NIJE inženjerska odluka** — zavisi od budžeta i da li se
   tim uskoro proširuje.
3. Ako founder odluči za automatizaciju: Engineering implementira
   integraciju, sa istim standardom kao ostatak ove sesije (testovi,
   dry-run pre produkcije).

### 1.3 WAF & Hardened Headers

| | |
|---|---|
| **Owner** | Founder (Cloudflare nalog/plan) + Engineering (konfiguracija, CSP refaktor) |
| **Rok** | Q3 2026 — Cloudflare WAF (infrastrukturna promena, brza); Q1 2027 — CSP nonce (veliki frontend refaktor, v. napomena ispod, realno van H2 2026) |
| **Definition of Done** | (a) Cloudflare proxy aktivan ispred Render-a, WAF pravila aktivna (OWASP core ruleset minimum); (b) CSP više ne koristi `'unsafe-inline'` za `script-src` (nonce ili hash-based); (c) CSP report endpoint prima i loguje violation-e (već postoji, v. ispod) |

**Trenutno stanje (provereno):**
- **CSP REPORT ENDPOINT VEĆ POSTOJI** (`api.py:1928`, "CSP Violation
  Report Endpoint") — **ovo NIJE novi posao**, roadmap item ovde je
  samo osigurati da se stvarno koristi (`report-uri`/`report-to`
  direktiva u CSP header-u treba da pokazuje na njega — proveriti pri
  implementaciji, ne pretpostaviti da je već povezano).
- **CSP header postoji** (`api.py:1095-1100`) **ALI koristi
  `'unsafe-inline'`** za i `script-src` i `style-src` — što u praksi
  poništava veliki deo CSP-ove XSS zaštite (inline `onclick="..."`
  handleri, kojih `index.html` ima na hiljade mesta kroz celu
  aplikaciju, rade upravo zato što je `unsafe-inline` dozvoljen).
  **Iskreno o obimu:** prelazak na nonce/hash-based CSP zahteva
  refaktorisanje SVAKOG inline `onclick=`/`<script>` bloka u
  `index.html` (~5000+ linija) na `addEventListener` obrazac — ovo NIJE
  jednodnevni zadatak, realno je **veći frontend refaktor**, ne
  "uključi nonce zastavicu". Zato je rok za ovaj pod-deo pomeren u Q1
  2027 dok se WAF (infrastrukturni, brz) cilja za Q3 2026.
- **Cloudflare se danas koristi SAMO kao CDN** za font/script asset-e
  (`cdnjs.cloudflare.com` u CSP `script-src`/`style-src` dozvoljenoj
  listi, `security/compute_sri.py`'s SRI hash-evi za te asset-e) — **NE
  kao WAF/proxy ispred aplikacije.** Dodavanje pravog Cloudflare
  proxy-ja je genuinski nov infrastrukturni rad, ne postojeća stvar
  koja se samo "uključi".

### 1.4 Disaster Recovery Live Drill

| | |
|---|---|
| **Owner** | Founder (izvršava, jedini operator sa pristupom) |
| **Rok** | Prvi Chaos Drill: kraj Q3 2026; mesečni ritam počinje odmah posle |
| **Definition of Done** | (a) Prvi PUN restore-iz-backup-a drill izvršen na NE-produkcionom (novom test) Supabase projektu, ne samo `scripts/verify_backup_restore.py`'s read-only provera; (b) rezultat upisan u `docs/security/DISASTER_RECOVERY_PLAN.md` §8 (Verification Log); (c) mesečni ritam Chaos Drill-ova (v. `docs/SECURITY_MATURITY_DASHBOARD.md` §2.2) formalno počeo, ne samo definisan |

**Ovaj roadmap item NE definiše nov proces — proces već postoji i
detaljno je definisan** u:
- `docs/security/DISASTER_RECOVERY_PLAN.md` §4 (recovery procedure) i
  §6 (`scripts/dr_runbook.py`, `scripts/verify_backup_restore.py`).
- `docs/SECURITY_MATURITY_DASHBOARD.md` §2.2 (Chaos Drill kalendar,
  scenariji: Pinecone outage, LLM timeout, Supabase degradation).

**Ono što STVARNO nedostaje:** **NIJEDAN od ova dva ritma je ikad
STVARNO izvršen.** `verify_backup_restore.py` je pokrenut jednom
(2026-07-24, v. DRP §8 Verification Log) kao READ-ONLY provera protiv
LIVE produkcije — to dokazuje konekciju i strukturnu ispravnost, **ne**
da je pun restore-from-backup put stvarno proveren od nule (novi
Supabase projekat, restore, verifikacija, sve od nule). Taj pun drill
nikad nije urađen. Ovaj roadmap item = "izvrši ono što je već
dizajnirano, prvi put, stvarno."

### 1.5 Supply Chain Security (SBOM & potpisani release-ovi)

| | |
|---|---|
| **Owner** | Engineering (SBOM CI wiring — mali posao); Founder (odluka o code-signing pristupu) |
| **Rok** | SBOM u CI: Q3 2026 (mali posao, brzo); Potpisani release-ovi: Q4 2026 |
| **Definition of Done** | (a) `security/sbom_check.py --ci` pokreće se u `.github/workflows/security.yml` na svaki release/tag, JSON SBOM artifact se čuva (isti obrazac kao postojeći `bandit-full-report`/`semgrep-full-report`); (b) definisan i primenjen mehanizam potpisivanja release-ova (v. opcije ispod) |

**Trenutno stanje (provereno):**
- **`security/sbom_check.py` VEĆ POSTOJI** — `generate_sbom()`,
  `run_pip_audit()`, `check_pinned_versions()`, `check_critical_deps()`,
  već ima `--ci`/`--sbom-out` CLI flagove spremne za automatizaciju.
  **NIJE povezan ni sa jednim GitHub Actions workflow-om danas**
  (provereno — nema pomena u `.github/workflows/*.yml`). **Roadmap item
  ovde nije "uvesti SBOM" — već je "povezati već napisan alat u CI",
  bukvalno jedan novi job blok u `security.yml`, isti obrazac kao
  `semgrep-full` iz `docs/SECURITY_SPRINT_PHASE1.md`.**
- **Potpisani release-ovi ne postoje u bilo kom obliku.** Za tim od
  jedne osobe bez container-image pipeline-a (potvrđeno — nema
  Dockerfile-orijentisanog release procesa, Render gradi direktno iz
  git-a), najrealniji minimalni pristup je **git tag signing**
  (`git tag -s`, GPG ili SSH ključ) na svaki produkcioni release tag —
  ne puni Sigstore/cosign container-signing pipeline, koji bi
  pretpostavljao container-based deploy koji danas ne postoji. Founder
  treba da odluči da li i ovaj minimalni nivo vredi operativnog troška
  pre nego što se veći pristup razmatra.

---

## PROGRAM 2: AI Reliability & Drift Observability

### 2.1 Hallucination & Drift Dashboards

| | |
|---|---|
| **Owner** | Engineering |
| **Rok** | Q3 2026 |
| **Definition of Done** | Dashboard (interni, admin-only ruta) koji prikazuje: (a) % AI odgovora sa `confidence: LOW` iz `app/services/retrieve.py`'s `get_confidence_level()`, po nedelji; (b) broj/procenat `origin_label`-a po tipu u `match_breakdown` (v. `docs/INSTITUTIONAL_MEMORY_V2_IMPLEMENTATION.md` STUB 4) — koliko odgovora se oslanja na zakon/praksu naspram kancelarijskog iskustva; (c) trend, ne samo trenutna vrednost |

**Osnova već postoji, dashboard ne:** `retrieve_documents()` već računa
`confidence`/`confidence_detail`/`match_breakdown` PO SVAKOM pozivu
(STUB 4, ova sesija) — podaci se generišu, ali se NIGDE ne agregiraju
niti prikazuju kroz vreme. Ovaj item je izgradnja agregacije/prikaza
nad već-postojećim signalom, ne nov signal.

### 2.2 Quality Gate Reject Rate

| | |
|---|---|
| **Owner** | Engineering |
| **Rok** | Q3 2026 |
| **Definition of Done** | Metrika (query ili admin endpoint) koja izračunava: `% (status='rejected') / ukupno` i `% (confidence_score < 0.85 AND is_lawyer_approved=true)` iz `staging_memory` tabele, po nedelji/mesecu, sa alarmom ako reject rate pređe definisan prag (prag TBD posle prvih realnih podataka — ne izmišljati broj bez ijednog stvarnog nacrta u tabeli) |

**Zavisnost:** `staging_memory` (migracija 088) mora biti PRIMENJENA u
produkciji da bi ova metrika imala bilo kakve podatke da meri (v.
Maturity Dashboard — potvrđeno neprimenjena danas). **Ovaj item ne može
stvarno početi pre te migracije**, bez obzira na to kad je kod za
dashboard napisan.

### 2.3 Golden Dataset Continuous Benchmarking

| | |
|---|---|
| **Owner** | **Founder** (kuriranje stvarnih dokumenata — eksplicitno njegov zadatak, v. ispod) + Engineering (CI wiring) |
| **Rok** | Founder kuriranje: bez fiksnog roka (zavisi od pristupa realnim predmetima/kancelarijama); Engineering CI wiring: Q4 2026, ALI samo posle prvog kruga podataka |
| **Definition of Done** | (a) `evaluation/lec/` popunjen sa 50+ stvarnih (ne sintetičkih) pravnih dokumenata kroz 3 kategorije (a_clean_digital/b_typical_serbian/c_nightmare); (b) `evaluation/phase_0_5/run.py`+`compare.py`+`report.py` (ili LEC-ov ekvivalent) pokreće se automatski na svaki release/tag; (c) rezultat (tačnost LRE rezonovanja po profilu predmeta) upisan u dashboard iz §2.1 |

**Ovo NIJE greenfield posao — infrastruktura VEĆ POSTOJI, namerno
prazna:**
- `evaluation/lec/` (Legal Evaluation Corpus, ranije "golden_dataset",
  preimenovano 2026-07-15) — anotacioni format, verzionisanje
  (`VERSION`, `CHANGELOG.md`), 3-kategorijska struktura VEĆ definisani.
  **`evaluation/lec/README.md`'s sopstvene reči: "This directory ships
  empty on purpose... Populating this is the founder's own task, not
  something the assistant can do for him."** — kuriranje stvarnih
  dokumenata iz stvarnih kancelarija zahteva founder-ove stvarne
  poslovne odnose, nije nešto što inženjerska sesija može popuniti
  fabrikovanjem "realnih" predmeta.
- `evaluation/phase_0_5/` — srodan, uži framework (specifično: da li je
  LRE Reasoning Graph bolji od Genome-ovih postojećih polja), takođe
  **"Status: TEMPLATE — no data collected yet"**, ista founder-kurira-
  ručno-nikad-automatski disciplina.
- **Šta STVARNO nedostaje:** (1) founder-ovo kuriranje 50+ dokumenata
  (van dometa bilo koje inženjerske sesije po dizajnu), (2) povezivanje
  već napisanih `run.py`/`compare.py`/`report.py` skripti u CI/release
  gate (mali inženjerski posao, ALI besmislen pre koraka 1).

---

## PROGRAM 3: Vindex AI Trust Center Portal

### 3.1 Javna `/trust` stranica — specifikacija

| | |
|---|---|
| **Owner** | Engineering (implementacija) + Founder (finalna revizija sadržaja pre javnog objavljivanja) |
| **Rok** | Q3 2026 (sadržaj VEĆ postoji raspoređen na 4 stranice — v. ispod — posao je konsolidacija/navigacija, ne pisanje od nule) |
| **Definition of Done** | Jedna `/trust` ruta koja linkuje/agregira postojeće stranice + nove sekcije (Incident Response Summary, Security Changelog, Responsible Disclosure) na jedno mesto, sa jasnom navigacijom |

**Sadržaj VEĆ POSTOJI, samo NIJE konsolidovan na jedno mesto —
potvrđeno u repou:**

| Zahtevana sekcija | Postojeći izvor | Status |
|---|---|---|
| Security Architecture & Data Isolation (SEC-001/SEC-004) | `static/security.html` (335 linija, potvrđeno realan sadržaj), `static/bezbednosni-list.html` | Postoji, treba linkovati sa `/trust` + osvežiti SEC-004 arhitektonsku napomenu (v. Maturity Dashboard red 2) |
| GDPR & Data Retention Policy (SEC-002) | `static/dpa.html` (154 linije), `privacy.html` (168 linija) | Postoji — ALI treba ažurirati retention brojke da odražavaju `services/retention_service.py`'s stvarne konstante (`SECURITY_EVENTS_RETENTION_DAYS` itd.), ne generičku formulaciju |
| Incident Response Summary & SLA | **Ne postoji javno** — `docs/INCIDENT_RESPONSE_PLAN.md` je interni dokument | **Nov posao** — javna verzija SLA tabele (P0 < 2h itd.) BEZ internih operativnih detalja (playbook koraci ostaju interni) |
| Security Changelog | **Ne postoji ni u jednom obliku** | **Nov posao** — javna, kurirana lista bezbednosnih poboljšanja (npr. "2026-07-26: Semgrep SAST dodat u CI", "2026-07-26: AI nacrti sada zahtevaju eksplicitnu advokatsku potvrdu pre ulaska u bazu znanja") — BEZ otkrivanja specifičnih CVE/SEC-XXX detalja koji bi mogli pomoći napadaču dok su nalazi još otvoreni |
| Responsible Disclosure Policy | **Ne postoji — nema `security.txt`, nema `/trust` ni bilo koje ekvivalentne stranice** | **Nov posao** — `/.well-known/security.txt` (RFC 9116 standard) + kontakt kanal za odgovorno prijavljivanje ranjivosti |

---

## DODATAK: Odbranjivi Bezbednosni Narativ (javne poruke)

**Princip:** svaka rečenica ispod mora biti direktno potkrepljena
commit-om, testom, ili audit dokumentom naveden pored nje — ne
marketinška fraza koja "zvuči dobro". Ako se ne može potkrepiti,
**ne ide u javnu komunikaciju.**

| Poruka (za javnu upotrebu, npr. Trust Center/sales) | Dokaz |
|---|---|
| "Svaki AI-generisan nacrt prolazi kroz automatsku proveru kvaliteta i **zahteva eksplicitnu potvrdu advokata** pre nego što postane deo baze znanja kancelarije." | `routers/drafting.py::_stage_draft_for_review`/`_promote_staged_draft_to_pinecone`, `tests/test_institutional_memory_v2.py` (21 testova) |
| "Podaci jedne kancelarije su tehnički odvojeni od podataka drugih kancelarija u AI pretrazi." | `shared/kancelarija_utils.py::rag_owner_namespace`, cross-case test `test_returns_document_from_past_case_in_same_kancelarija` — **napomena za internu upotrebu, NE za javnu tvrdnju bez ograde**: ovo opisuje Pinecone namespace izolaciju, NE tvrdi da je RLS jedini/dovoljan mehanizam (SEC-004 arhitektonska činjenica — javna formulacija mora biti precizna, ne uopštena "imamo RLS" tvrdnja koja bi bila netačna) |
| "Naš bezbednosni pipeline automatski skenira svaki commit za otkrivene tajne, poznate ranjivosti u zavisnostima, i bezbednosne obrasce u kodu." | `.github/workflows/security.yml` (Gitleaks/Bandit/pip-audit/Semgrep, svih 6 job-ova, `docs/SECURITY_SPRINT_PHASE1.md`) |
| "Imamo dokumentovan, testiran plan za odgovor na bezbednosne incidente sa definisanim vremenima odziva." | `docs/INCIDENT_RESPONSE_PLAN.md` — **ograda za javnu verziju**: ne tvrditi da je plan "testiran u praksi" dok Chaos Drill (§Program 1.4) stvarno ne bude izvršen bar jednom — do tada, formulacija mora biti "definisan i dokumentovan", ne "dokazano funkcioniše pod pritiskom" |
| "Sprovodimo redovnu internu bezbednosnu reviziju." | Tačno, opsežna istorija u `docs/security/` (SEC-001 do SEC-036) |
| ~~"Nezavisno bezbednosno sertifikovani"~~ / ~~"Penetration tested"~~ | **NE KORISTITI dok Program 1.1 stvarno ne bude završen.** Ovo je tačno ono što ovaj roadmap postoji da promeni — koristiti ovu formulaciju danas bi bilo lažno predstavljanje, čak i ako je namera iskrena |
| ~~"SOC 2 / ISO 27001 usklađeni"~~ | **Ne pominjati** — nijedan dokument u ovom repou ne pominje bilo koji formalni compliance framework kao cilj; ako founder želi ovo kao budući cilj, to je zaseban, veći poduhvat (kontrole, dokumentacija, eksterni auditor) koji nije obuhvaćen ovim roadmap-om i ne treba ga implicirati dok se eksplicitno ne odluči |

---

## Verifikacija

Svi linkovi/putanje citirane iznad provereni da postoje u repozitorijumu
pre pisanja ovog dokumenta (ne pretpostavljeno):

`docs/security/SECURITY_ROADMAP.md`, `docs/SECURITY_MATURITY_DASHBOARD.md`,
`docs/security/EXECUTIVE_SECURITY_SUMMARY.md`, `docs/security/DISASTER_RECOVERY_PLAN.md`,
`docs/INCIDENT_RESPONSE_PLAN.md`, `KEY_ROTATION_ANALYSIS.md`,
`security/sbom_check.py`, `api.py` (CSP header + violation endpoint),
`security/compute_sri.py`, `shared/rate.py`, `evaluation/lec/README.md`,
`evaluation/lec/VERSION`, `evaluation/phase_0_5/README.md`,
`evaluation/phase_0_5/PHASE_0_5_DECISION.md`, `static/security.html`,
`static/dpa.html`, `static/bezbednosni-list.html`, `privacy.html`,
`routers/drafting.py`, `shared/kancelarija_utils.py`,
`docs/INSTITUTIONAL_MEMORY_V2_IMPLEMENTATION.md`,
`docs/SECURITY_SPRINT_PHASE1.md` — svih 20 potvrđeno postojećih.

### Pytest suite

Ovaj dokument je čista dokumentacija (nula izmena koda). Pun pytest
suite pokrenut posle pisanja radi potvrde da nema regresija:

```
python -m pytest -q
```
