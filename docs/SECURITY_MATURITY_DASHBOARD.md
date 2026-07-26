# Vindex AI — Security Maturity Dashboard (SSOT)

**Datum:** 2026-07-26. Ovo je **Single Source of Truth** za bezbednosnu
zrelost, compliance i operativnu spremnost — zamenjuje potrebu da se
status "sklapa" ručno iz 15+ pojedinačnih dokumenata u `docs/security/`.

**Metodologija statusa (✅/🟡/❌):** nije proizvoljna procena — mapirana
na `docs/security/FINDING_LIFECYCLE.md`'s 9-stage model (Observation →
Finding → Confirmed Risk → Remediation Candidate → Architecture Approved
→ Implementation → Verified Fix → **Production Verified** → **Closed**).
✅ = Stage 8/9 (produkciono potvrđeno ili formalno zatvoreno). 🟡 = Stage
4-7 (plan/implementacija/test postoji, produkciona potvrda ne). ❌ =
Stage 0-2 ili nije ni započeto.

**Odnos prema postojećim dokumentima:** `docs/security/
EXECUTIVE_SECURITY_SUMMARY.md` (poslednja izmena 2026-07-24) je narativni
istorijat audit putovanja — vredan konteksta, ali **NIJE ažuriran** sa
današnjim radom (Semgrep u CI, Institutional Memory V2, Incident Response
Plan). Ova tabla JESTE ažurna i preuzima ulogu brzog, tabelarnog pregleda;
narativni dokument ostaje za "kako smo stigli dovde".

**Svaka tvrdnja ispod je nezavisno provereva pre pisanja** (ne prepisana
iz nacrta zahteva) — dva reda ispod se razlikuju od inicijalno predloženog
statusa jer je provera repozitorijuma pokazala drugačije stvarno stanje
(v. napomene u tabeli).

---

## 1. Maturity Matrix

| Oblast | Status | Ključni Mehanizam | Dokaz / Referenca | Sledeći Korak |
|---|---|---|---|---|
| **Data Isolation — Ownership Checks** | ✅ | Eksplicitna `.eq("user_id", ...)` provera vlasništva na svakoj mutating ruti (SEC-001 obrazac), primenjena na svih 24 `{predmet_id}`-scoped mutation endpointa | `tests/test_sec001_predmet_ownership.py` (6/6 passed, provereno u ovoj sesiji) — **ne** `tests/test_rls.py`, koji ne postoji u repou; `docs/security/SECURITY_GAP_REGISTER.md` SEC-001 red; `FINDING_LIFECYCLE.md` pozicionira ovo na Stage 7 (formalna Stage-8 re-sertifikacija pod OVIM okvirom nikad urađena jer je fix stariji od samog okvira, ali fix je živ u produkciji od ranije sesije) | Formalna Stage-8 re-verifikacija SEC-001 pod `FINDING_LIFECYCLE.md` okvirom — administrativna praznina, ne funkcionalna |
| **Data Isolation — RLS kao strukturni mehanizam** | 🟡 (arhitektonska činjenica, ne bag koji se "popravlja") | `SUPABASE_SERVICE_KEY` (jedini app-wide klijent, `shared/deps.py:29,72-80`) **zaobilazi RLS u potpunosti** — izolacija ~150+ endpoint-a počiva 100% na ručnoj proveri po handler-u (red iznad), ne na Postgres RLS-u kao nezavisnom backstop-u | `docs/security/SECURITY_GAP_REGISTER.md` SEC-004 red — eksplicitno označeno "not fixable by adding a check... standing architectural fact", status "ongoing" | Automatizovan test koji tvrdi da SVAKA mutating predmet/klijent/dokument ruta filtrira po `user_id` (SEC-004-ov predlog #2 — defense-in-depth, ne RLS sam) |
| **DevSecOps Pipeline** | ✅ | Gitleaks (secret scan), Bandit (core+full SAST), pip-audit (dependency scan), Semgrep (core+full SAST) — svi na `push`/`pull_request` ka `main` | `.github/workflows/security.yml` (6 job-ova); `docs/SECURITY_SPRINT_PHASE1.md` — Semgrep lokalno pokrenut, 1 stvaran nalaz (mrtav kod u `routers/sef.py`) ispravljen, 0 nalaza posle | Nema hitnog — CI je aktivan i blokirajući od 2026-07-26 |
| **AI Output Protection & Quality Gate** | 🟡 (kod/testovi ✅, produkcija ❌ — v. napomena) | `staging_memory` tabela (nikad direktan upis AI nacrta u kancelarijski Pinecone namespace), `confidence_score >= 0.85` prag (`routers/drafting.py::_APPROVAL_CONFIDENCE_THRESHOLD`) + eksplicitna advokatska potvrda, oba uslova obavezna | `services/quality_gate.py`, `docs/INSTITUTIONAL_MEMORY_V2_IMPLEMENTATION.md`, `tests/test_institutional_memory_v2.py` (21/21 passed) — **ALI**: `migrations/088_staging_memory.sql` je **potvrđeno NEPRIMENJENA u produkciji** (živ test preko `scripts/audit_deployment_consistency.py`, ova sesija, `docs/SECURITY_SPRINT_PHASE1.md` §2.3) — tabela `staging_memory` fizički ne postoji dok se migracija ne pokrene | **Pokrenuti migraciju 088 u Supabase SQL Editor-u** (v. `docs/SECURITY_SPRINT_PHASE1.md` §2.4 za dry-run/rollback postupak) — dok se ovo ne uradi, Quality Gate kod postoji ali NE štiti ništa uživo |
| **Incident Response Readiness** | ✅ | P0-P3 severity matrica, 30-min playbook, evidence preservation, formalni post-mortem template (5 Whys) | `docs/INCIDENT_RESPONSE_PLAN.md` (kompletan, 2026-07-26) | Prva stvarna primena/vežba (v. §2 Tabletop kalendar ispod) |
| **Production Migration Integrity (SEC-031)** | ✅ **CLOSED, Stage 9** *(korekcija — nacrt zahteva je predložio 🟡 "čeka finalno izvršenje", provera je pokazala da je ovo POGREŠNO)* | `ON DELETE CASCADE` → `RESTRICT` na svih 18 `auth.users`-referencirajućih FK parova, izvršeno DIREKTNO u produkciji uz read-only verifikaciju posle svakog koraka | `docs/security/SEC031_PRODUCTION_EXECUTION_LOG.md` — "18/18 confirmed ON DELETE RESTRICT in production, zero data touched"; `FINDING_LIFECYCLE.md` navodi SEC-031 kao **jedini** nalaz u projektu koji je ikad prošao svih 9 faza | Nema za SEC-031 samo — ALI nove migracije OVE sesije (085-088) su ZASEBAN, tekući zadatak: 085/086/087 potvrđene APPLIED (živ test), 088 potvrđena NOT APPLIED (v. red iznad) |
| **Data Retention & GDPR (SEC-002)** | 🟡 *(korekcija — nacrt je predložio "čeka pravnu odluku", stvarnost je preciznija: automatizacija VEĆ RADI za većinu tabela)* | `services/retention_service.py` — konkretni retention periodi (`SECURITY_EVENTS_RETENTION_DAYS` itd.) već definisani i AUTOMATSKI se izvršavaju kroz `/api/cron/daily` Modul 9 | `docs/security/SECURITY_GAP_REGISTER.md` — "SEC-002 (2026-07-24) is now fully RESOLVED... automation now actually executes" — ALI 2 tabele (`usage_events`, `response_audit`) i dalje nemaju definisan retention period (nije "možda mrtve", nego "žive, bez odluke"); i nije potvrđeno da je puni dnevni cron ciklus (9 modula) stvarno posmatran uživo u produkciji | (1) Definisati retention period za `usage_events`/`response_audit`. (2) Potvrditi jedan pun live cron ciklus u produkcionim logovima (Render) |
| **Disaster Recovery** | 🟡 | DR runbook + restore procedure spremni, RTO ≤ 2h cilj definisan | `scripts/dr_runbook.py` (`--quick`/`--check` flagovi provereni u izvoru), `docs/security/DISASTER_RECOVERY_PLAN.md` | **Chaos Drill** (v. §2) — nikad izvršen; takođe DRP §4.5 već priznaje: nema wired uptime monitoring (detection zavisi od ručnog primećivanja) |
| **External Security Assessment** | ❌ | — | Nema evidencije o eksternom pentestu/audit-u nigde u `docs/` (provereno pretragom) | **Uslov za početak je sada ispunjen** — ranije planirano "posle produkcionog zatvaranja SEC-031", a SEC-031 je Stage 9 Closed (v. red iznad) — ovo je sada logički najprioritetniji sledeći korak u celoj tabli |

---

## 2. Operativni Ritam Vežbi (Drill Calendar & Framework)

### 2.1 Tabletop Exercises — Kvartalno

**Format:** walkthrough BEZ izmene koda — jedan operator (v. IRP §0,
jedan-operator realnost) prolazi kroz hipotetički scenario koristeći
`docs/INCIDENT_RESPONSE_PLAN.md` §2 (First 30-Minutes Playbook) korak po
korak, beleži gde je playbook nejasan/nedovoljan.

**Scenariji za rotaciju (jedan po kvartalu, ne svi odjednom):**
1. **SSRF** — da li bi neko od ~130 GPT poziva ili webhook handler-a
   (`routers/integracije.py`, `routers/portal_monitoring.py`) mogao biti
   naveden da pošalje zahtev ka internom resursu?
2. **IDOR** — pokušati (walkthrough, ne stvaran poziv) zamisliti novi
   endpoint koji NEMA SEC-001 obrazac — da li bi tim (operator) to
   primetio pre merge-a? Unakrsna provera sa DevSecOps skenerima (da li
   bi Semgrep/Bandit uhvatili IDOR obrazac — realno, verovatno NE, oba
   su SAST alati za poznate ranjivosti klase, ne poslovnu logiku —
   **ovo je sam po sebi vredan nalaz vežbe**, ne pretpostavka).
3. **RLS/namespace breach** — simulacija "korisnik A vidi
   `kancelarija_{B}` Pinecone namespace" (v. §1 red 2) — koji bi signal
   PRVI to otkrio (`security_events`? korisnička žalba? ništa?) —
   iskreno popuniti odgovor, ne pretpostaviti da monitoring postoji ako
   ne postoji.

**Izlaz vežbe:** kratak zapis (3-5 rečenica) šta je playbook propustio,
upisan kao Action Item (isti format kao IRP §4 post-mortem template) —
vežba koja ne proizvede nijedan nalaz je sumnjiva, ne uspešna.

### 2.2 Chaos Drills — Mesečno

**Format:** namerno simulirati pad SPOLJNE zavisnosti (ne pravi
production outage) da se proveri da li postojeći fail-soft mehanizmi
stvarno rade kako je dokumentovano, ne samo u testovima.

**Rotacija:**
1. **Pinecone outage** — privremeno pogrešan `PINECONE_API_KEY` u
   lokalnom/staging `.env`, potvrditi da `app/services/retrieve.py`
   degradira na LOW confidence prazan rezultat (postojeći fail-soft
   obrazac), ne baca 500.
2. **LLM timeout** — simulirati spor OpenAI odgovor (mock/staging),
   potvrditi da `shared/llm_retry.py`'s retry logika i korisnički
   vidljivi timeout rade kako je dokumentovano, ne da korisnik čeka
   beskonačno.
3. **Supabase degradation** — potvrditi da `shared/rate.py`'s fail-open
   ponašanje (SEC-005, `tests/test_sec005_failopen_limiter.py`) i dalje
   radi kako je testirano, PLUS ručno proveriti da li bi se isto
   ponašanje pokazalo i za druge Supabase pozive van rate limitera
   (koji danas nemaju isti fail-soft tretman — otvoreno pitanje, ne
   pretpostaviti da je rešeno svuda samo zato što je rešeno za rate
   limiter).

**Razlika od Tabletop-a:** Chaos Drill stvarno IZVRŠAVA kôd protiv
degradiranog/lažnog uslova (u lokalnom/staging okruženju, NIKAD protiv
prave produkcije bez eksplicitne najave), Tabletop je čist walkthrough.

### 2.3 Post-Mortem Policy

Obavezna analiza u roku od **48h** za SVAKI P0/P1 incident, po šablonu
iz `docs/INCIDENT_RESPONSE_PLAN.md` §4 (Incident ID, Timeline, 5 Whys,
Impact Analysis, Action Items sa vlasnicima). Nema izuzetka za "manji"
P0/P1 — ako je incident dovoljno ozbiljan da nosi tu oznaku, dovoljno je
ozbiljan za pun post-mortem, čak i ako je root cause trivijalan.

---

## 3. Verifikacija

**Linkovi/reference provereni da postoje u repozitorijumu** (ne
pretpostavljeni):

| Referenca | Status |
|---|---|
| `tests/test_sec001_predmet_ownership.py` | ✅ postoji, 6/6 passed (pokrenuto ovom sesijom) |
| `docs/security/SECURITY_GAP_REGISTER.md` | ✅ postoji |
| `docs/security/FINDING_LIFECYCLE.md` | ✅ postoji |
| `docs/security/EXECUTIVE_SECURITY_SUMMARY.md` | ✅ postoji |
| `docs/security/SEC031_PRODUCTION_EXECUTION_LOG.md` | ✅ postoji |
| `docs/security/DISASTER_RECOVERY_PLAN.md` | ✅ postoji |
| `.github/workflows/security.yml` | ✅ postoji |
| `docs/SECURITY_SPRINT_PHASE1.md` | ✅ postoji |
| `docs/INSTITUTIONAL_MEMORY_V2_IMPLEMENTATION.md` | ✅ postoji |
| `docs/INCIDENT_RESPONSE_PLAN.md` | ✅ postoji |
| `services/retention_service.py` | ✅ postoji |
| `scripts/dr_runbook.py` | ✅ postoji |
| `scripts/audit_deployment_consistency.py` | ✅ postoji |
| `tests/test_rls.py` (iz originalnog nacrta zahteva) | ❌ **NE postoji — uklonjeno iz table, zamenjeno tačnom referencom** |

**Pytest suite:** ovaj dokument je čista dokumentacija (nula izmena
koda) — pun pytest suite pokrenut radi potvrde, ne pretpostavke:

```
python -m pytest -q
```
