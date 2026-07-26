# Vindex AI — Evidence-Based Claims Policy

**Datum:** 2026-07-26. **Vlasnik politike:** Founder (svaka javna/
marketinška tvrdnja o bezbednosti ili usklađenosti mora proći kroz ovu
politiku pre objavljivanja — na sajtu, u sales materijalu, u Trust
Center-u, ili u odgovoru klijentu).

**Princip:** ovo je politika, ne predlog. Tvrdnja bez reda u tabeli
ispod, ili tvrdnja čiji dokaz ne prolazi Proveru statusa (v. §2), **ne
ide u javnu komunikaciju** — bez obzira koliko je tehnički blizu istine.
"Skoro tačno" i "tačno uz nepomenutu ogradu" su i dalje netačno kad ih
čita klijent koji ne zna internu arhitekturu.

**Odnos prema drugim dokumentima:** ovo je jedinstveni izvor istine za
javne tvrdnje (zamenjuje `docs/ROADMAP_2026_ENTERPRISE_SECURITY.md`'s
raniji DODATAK — v. taj fajl za istorijski snapshot). Status kolona
ispod se oslanja na `docs/security/FINDING_LIFECYCLE.md`'s 9-stage
model i `docs/SECURITY_MATURITY_DASHBOARD.md`'s ✅/🟡/❌ oznake — ne
izmišlja novu skalu.

---

## 1. Kako se čita tabela

| Kolona | Značenje |
|---|---|
| **Tvrdnja** | Tačna formulacija dozvoljena za javnu upotrebu — ne parafrazirati slobodnije od ovoga bez ponovne provere |
| **Minimalni dokaz** | Šta MORA postojati i biti proveljivo PRE nego što se tvrdnja prvi put objavi — ne "u planu je", nego postoji danas |
| **Status danas** | ✅ dokaz postoji i proveren u ovoj sesiji → tvrdnja se SME koristiti danas. 🟡 delimičan dokaz → tvrdnja se sme koristiti SAMO u ograđenoj formi navedenoj u koloni. ❌ dokaz ne postoji → tvrdnja se NE SME koristiti u bilo kom obliku |

---

## 2. Dozvoljene tvrdnje i njihov minimalni dokaz

| Tvrdnja | Minimalni dokaz | Status danas |
|---|---|---|
| "Podaci su enkriptovani AES-256 algoritmom, sa upravljanjem ključevima." | `security/crypto.py` (`encrypt_field`/`decrypt_field`, `_MIN_KEY_BYTES` = 256-bit zahtev, Argon2id za lozinke) + prolazak `tests/test_sec009_pii_encryption.py` | ✅ Provereno u ovoj sesiji: `python -m pytest tests/test_sec009_pii_encryption.py -v` → 4/4 passed (`test_pib_never_written_as_plaintext`, `test_encrypted_pib_decrypts_back_to_original`, `test_row_without_pib_unaffected`, `test_manual_and_bulk_produce_same_ciphertext_format`). **Ograda:** ovo pokriva PIB/JMBG/pasoš polja u `klijenti` tabeli — ne tvrditi "sve enkriptovano", tvrditi "osetljiva lična dokumenta enkriptovana" |
| "Podaci svake kancelarije su vlasnički izolovani — eksplicitna provera na svakoj operaciji nad predmetom/klijentom." | `tests/test_sec001_predmet_ownership.py` (SEC-001 obrazac, `.eq("user_id", ...)` provera na svih 24 `{predmet_id}`-scoped mutation endpointa) | ✅ 6/6 passed (v. `docs/SECURITY_MATURITY_DASHBOARD.md` red 1). **Ograda:** ne tvrditi "RLS izoluje podatke" — `SUPABASE_SERVICE_KEY` zaobilazi RLS u potpunosti (SEC-004, arhitektonska činjenica); izolacija počiva na ovoj ručnoj proveri, ne na Postgres RLS-u kao nezavisnom mehanizmu. Javna formulacija mora reći "eksplicitna provera vlasništva", ne "RLS štiti vaše podatke" |
| "AI pretraga jedne kancelarije tehnički ne vidi podatke druge kancelarije." | `shared/kancelarija_utils.py::rag_owner_namespace` (Pinecone `kancelarija_{id}`/`user_{id}` namespace šema) + cross-case test `test_returns_document_from_past_case_in_same_kancelarija` | ✅ Provereno, ista ograda kao red iznad — ovo je namespace izolacija na Pinecone nivou, ne generalna "sve je izolovano" tvrdnja |
| "Svaki AI-generisan nacrt prolazi kroz proveru kvaliteta i zahteva eksplicitnu potvrdu advokata pre nego što postane deo baze znanja kancelarije." | `routers/drafting.py::_stage_draft_for_review`/`_promote_staged_draft_to_pinecone`, `services/quality_gate.py`, `tests/test_institutional_memory_v2.py` (21/21 passed) | 🟡 **Kod/testovi ✅, produkcija ❌.** `migrations/088_staging_memory.sql` potvrđeno NEPRIMENJENA u produkciji (v. Maturity Dashboard red 4, `scripts/audit_deployment_consistency.py`). **Dok se migracija 088 ne primeni: ova tvrdnja se NE SME koristiti javno** — kod postoji, ali mehanizam ne štiti nijedan živi nacrt danas. Nakon primene migracije: dozvoljeno bez daljih ograda |
| "Imamo dokumentovan plan za odgovor na bezbednosne incidente, sa definisanim vremenima odziva po ozbiljnosti (P0-P3)." | `docs/INCIDENT_RESPONSE_PLAN.md` (severity matrica, 30-min playbook, evidence preservation, post-mortem template) | ✅ Dokument postoji i kompletan. **Ograda:** ne dodavati "testiran u praksi" ili "dokazano funkcioniše" dok bar jedan Kvartalni Tabletop (v. `docs/ROADMAP_2026_ENTERPRISE_SECURITY.md` §4.2) stvarno ne bude izvršen — do tada dozvoljena formulacija je "definisan i dokumentovan", ne "battle-tested" |
| "Automatizovan bezbednosni pipeline skenira svaki commit za otkrivene tajne (secrets), poznate ranjivosti u zavisnostima, i rizične obrasce u kodu." | `.github/workflows/security.yml` — 6 job-ova: Gitleaks (secret-scan), Bandit (sast-core + sast-full), pip-audit (dependency-scan), Semgrep (semgrep-core + semgrep-full) | ✅ Provereno da postoji i pokreće se na `push`/`pull_request` ka `main` (v. `docs/SECURITY_SPRINT_PHASE1.md`) |
| "Sprovodimo redovnu internu bezbednosnu reviziju sopstvenog koda." | `docs/security/SECURITY_GAP_REGISTER.md` (SEC-001 do SEC-036, dokumentovana istorija nalaza) | ✅ Istinito, opsežna dokumentovana istorija |
| "Imamo definisan disaster recovery plan sa ciljanim vremenom oporavka." | `docs/security/DISASTER_RECOVERY_PLAN.md` (RTO ≤ 2h cilj), `scripts/dr_runbook.py`/`scripts/verify_backup_restore.py` | 🟡 Plan i alati postoje i provereni (read-only test protiv žive produkcije, 2026-07-24). **Ograda:** ne tvrditi "testirano" dok prvi PUN restore-from-backup na test projektu (Roadmap §1.4/§4.3) stvarno ne bude izvršen — do tada, "definisan RTO cilj", ne "dokazan RTO" |
| "Nezavisno bezbednosno testirani (penetration tested)." | Potpisan izveštaj nezavisne pentest firme, sa CVSS ocenjenim nalazima i re-test potvrdom da su HIGH/CRITICAL zatvoreni | ❌ **NE POSTOJI DANAS.** Zabranjeno do `docs/ROADMAP_2026_ENTERPRISE_SECURITY.md` §1.1 (prvi eksterni pentest) stvarno ne bude završen i izveštaj potpisan. Korišćenje ove formulacije pre toga je lažno predstavljanje, bez obzira na nameru |
| "Sub-procesori (Supabase, Render) imaju sopstvene SOC 2 Type II sertifikate." | Javno dostupne SOC 2 stranice tih dobavljača; VEĆ ispravno formulisano u repou kao "kroz partnere" | ✅ Provereno u ovoj sesiji (`static/security.html:204` — "Kroz partnere" / "Supabase, OpenAI, Render imaju SOC 2"; `privacy.html:93,114` — navedeno pod karticom svakog pod-obrađivača pojedinačno, ne kao Vindex-ova sopstvena sertifikacija). **Ova formulacija je već ispravno ograđena u postojećem kodu — primer kako TREBA da izgleda, ne kršenje.** Videti §3 zašto je razlika između ovoga i "Vindex je SOC 2 sertifikovan" kritična |

---

## 3. Eksplicitno zabranjene tvrdnje

| Zabranjena tvrdnja | Zašto |
|---|---|
| **"Vindex AI je SOC 2 sertifikovan"** (ili bilo koja formulacija koja ne eksplicira da se sertifikat odnosi na pod-obrađivača, ne na Vindex) | Nijedan dokument u repou ne pokazuje da je Vindex AI (kompanija/proizvod) sam prošao SOC 2 audit. Postojeće ispravne reference (`static/security.html:204`, `privacy.html:93,114`) navode SOC 2 status POD-OBRAĐIVAČA (Supabase/Render), eksplicitno označeno "kroz partnere" — to je dozvoljeno (v. §2, poslednji red). Bilo koja formulacija koja izostavi "kroz partnere"/"sub-procesor" i ostavi utisak da je Vindex sam sertifikovan je **lažno predstavljanje** |
| **"ISO 27001 usklađeni"** | `static/security.html:205` ga navodi kao "U planu, Q2 2027" — status je namera, ne stanje. Ne pominjati kao trenutnu tvrdnju dok formalno ne bude završeno |
| **"100% GDPR usklađeni"** (bez ograde) | GDPR usklađenost nije binarno stanje koje se "100%" postiže i zaboravi — SEC-002 red u Maturity Dashboard-u pokazuje da 2 tabele (`usage_events`, `response_audit`) i dalje nemaju definisan retention period. Dozvoljena formulacija: "Automatizovana politika čuvanja podataka za većinu kategorija (v. `services/retention_service.py`)" — konkretno, ne apsolutno |
| **"Penetration tested" / "Nezavisno bezbednosno sertifikovani"** (van konteksta §2 reda) | V. §2 — dokaz ne postoji do Roadmap §1.1/§4.1 |
| **"Vojna enkripcija" / "bank-grade security" / "military-grade encryption"** | Marketinški žargon bez tehničke definicije — AES-256-GCM (stvarna implementacija, v. §2) je precizna, proverljiva formulacija; "vojna"/"bank-grade" nije proverljiva tvrdnja i ne dodaje informaciju iznad stvarne specifikacije |
| **"Nikad nismo imali bezbednosni incident"** | Neproverljivo unapred (odsustvo dokaza nije dokaz odsustva) i postaje lažno onog trenutka kad se prvi incident desi — umesto toga koristiti "Imamo dokumentovan proces odgovora na incidente" (v. §2) |
| **"Testirano od strane hiljada korisnika"** ili slične brojčane tvrdnje o obimu korišćenja bez internog brojčanog dokaza dostupnog na zahtev | Ako se koristi konkretan broj, mora postojati interni izvor (analytics/usage_events) koji ga potkrepljuje na dan objavljivanja — ne aspiraciona/zaokružena cifra |

---

## 4. Proces odobravanja nove tvrdnje

1. Predložena tvrdnja + predloženi dokaz se dodaju kao novi red u §2 (draft status).
2. Dokaz se proverava na isti način kao u ovoj sesiji: pokrenuti pomenuti test/skript, pročitati pomenuti fajl — ne pretpostaviti da postoji na osnovu naziva.
3. Status (✅/🟡/❌) se dodeljuje na osnovu STVARNOG rezultata provere, ne namere.
4. Tek posle ✅ ili odobrene 🟡-ograde, tvrdnja se sme koristiti javno — u tačnoj formulaciji iz tabele, ne slobodnoj parafrazi.
5. Svaka izmena statusa nekog reda (🟡→✅, ili unazad ako dokaz prestane da važi — npr. test počne da pada) mora biti odražena u ovoj tabeli ISTOG DANA kad se otkrije, ne na sledećem redovnom review-u.

---

## 5. Verifikacija

Sve reference iznad provereno da postoje pre pisanja ovog dokumenta:

`security/crypto.py`, `tests/test_sec009_pii_encryption.py` (4/4 passed,
pokrenuto u ovoj sesiji), `tests/test_sec001_predmet_ownership.py` (6/6
passed), `shared/kancelarija_utils.py`, `routers/drafting.py`,
`services/quality_gate.py`, `tests/test_institutional_memory_v2.py`,
`migrations/088_staging_memory.sql`, `docs/INCIDENT_RESPONSE_PLAN.md`,
`.github/workflows/security.yml`, `docs/security/SECURITY_GAP_REGISTER.md`,
`docs/security/DISASTER_RECOVERY_PLAN.md`, `scripts/dr_runbook.py`,
`scripts/verify_backup_restore.py`, `static/security.html` (linije
204-205), `privacy.html` (linije 93, 114), `services/retention_service.py`,
`docs/SECURITY_MATURITY_DASHBOARD.md`, `docs/security/FINDING_LIFECYCLE.md`,
`docs/ROADMAP_2026_ENTERPRISE_SECURITY.md` — svih 19 potvrđeno postojećih.

**Nusputno otkriveno tokom ove provere:** `index.html:4681,4720` i
`privacy.html:93,114` sadrže SOC 2 reference — provereno da su SVE
ispravno skopirane pod pod-obrađivačevom karticom (Supabase/Render), ne
predstavljene kao Vindex-ova sopstvena sertifikacija. Nijedna izmena
koda nije bila potrebna — ovo je zabeleženo u §2/§3 kao potvrda da
postojeći sadržaj već poštuje pravilo, ne kao pronađeno kršenje.

### Pytest suite

Ovaj dokument je čista dokumentacija (nula izmena koda van dokumentacije).
Pun pytest suite pokrenut posle pisanja radi potvrde da nema regresija:

```
python -m pytest -q
```
