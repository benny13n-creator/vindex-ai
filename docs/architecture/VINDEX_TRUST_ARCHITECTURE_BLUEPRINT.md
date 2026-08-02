# VINDEX AI — TRUST ARCHITECTURE BLUEPRINT v1.0

**Status:** Master Architecture — Governing Document (Founder-authored, adopted 2026-08-01)
**Position in hierarchy:** This is the top of the security/trust documentation tree. It is the
**constitution** — principles, target architecture, and required capabilities. It does **not**
contain current-state evidence, findings, or maturity scoring; that lives in the implementation
layer below it (see `docs/SECURITY_MATURITY_DASHBOARD.md` and the traceability matrix that
connects the two: `docs/architecture/VINDEX_TRUST_ARCHITECTURE_TRACEABILITY.md`).

```
VINDEX TRUST ARCHITECTURE BLUEPRINT   (this document — principles, target state)
            │
            ├── SECURITY MATURITY DASHBOARD        (current state, per-capability status)
            ├── SECURITY GAP REGISTER              (findings, evidence, file:line)
            ├── STRIDE THREAT MODEL                (threat enumeration)
            ├── SECURITY ROADMAP                    (P0-P3 remediation sequencing)
            └── Future Security Programs            (net-new architectural build-out)
```

**Governing rule:** no new security functionality is implemented because it is "a good idea."
Every implementation must trace to one or more Security Capabilities defined in Part I §1.9,
have a stated threat model, a verification plan, and demonstrable value for protecting user data.
Every future feature — AI, backend, frontend, infrastructure, database, or integration — must be
traceable to one or more Blueprint capabilities. If it cannot be mapped, it is challenged before
implementation, not after.

---

# PART I — Executive Vision & Security Principles

## 1.0 Dokument Status

| Stavka | Vrednost |
|---|---|
| Dokument | Vindex AI Trust Architecture Blueprint |
| Verzija | 1.0 |
| Status | Master Architecture |
| Vlasnik | Vindex AI |
| Tip | Security Architecture Specification |
| Obavezujući | DA |

## 1.1 Misija

Vindex AI nije AI chatbot. Vindex AI nije AI editor. Vindex AI nije AI pomoćnik.

Vindex AI predstavlja Legal Operating System čiji je osnovni zadatak da omogući pravnicima da
koriste veštačku inteligenciju bez gubitka kontrole nad podacima, procesima i odgovornošću.

Svaka bezbednosna odluka u sistemu mora biti doneta u korist:

- poverljivosti podataka,
- integriteta pravnog procesa,
- dokazivosti svake AI odluke,
- očuvanja profesionalne tajne.

Bezbednost nije dodatna funkcionalnost. Bezbednost predstavlja osnovnu arhitekturu sistema.

## 1.2 Vizija

Cilj Vindex AI nije da postane još jedan AI alat. Cilj je izgradnja najpouzdanije AI platforme za
pravnu industriju. Sistem mora omogućiti da advokat može koristiti AI na isti način na koji danas
koristi računar: bez razmišljanja, bez straha, uz potpunu kontrolu.

## 1.3 Security Mission Statement

Svaki podatak koji uđe u Vindex AI mora biti identifikovan, klasifikovan, zaštićen, kontrolisan,
auditovan i po potrebi anonimizovan pre nego što bilo koji AI model dobije pristup.

Nijedan AI model nema direktan pristup podacima. Pristup uvek odobrava Vindex AI.

## 1.4 Security Philosophy

Vindex AI polazi od pretpostavke da svaka mreža može biti kompromitovana, svaki uređaj može biti
kompromitovan, svaki korisnik može napraviti grešku, svaki AI model može pogrešiti, svaka
integracija predstavlja rizik.

Zbog toga se bezbednost ne zasniva na poverenju. Bezbednost se zasniva na verifikaciji.

## 1.5 Trust Philosophy

Korisnik ne treba da veruje Vindex AI. Vindex AI mora omogućiti korisniku da proveri svaku odluku.

Sve AI akcije moraju biti rekonstruktivne, auditabilne, dokazive, objašnjive.

## 1.6 Security Goals

**Goal 1 — Zero Unauthorized Access.** Nijedan korisnik ne može pristupiti podatku bez
eksplicitne autorizacije.

**Goal 2 — Zero Silent AI Processing.** AI nikada ne obrađuje podatke bez evidentirane AI akcije.

**Goal 3 — Zero Unknown Data Flow.** Svaki bajt koji napusti sistem mora imati razlog.

**Goal 4 — Complete Auditability.** Svaka odluka mora biti rekonstruisana.

**Korolar (dodato 2026-08-02, po nalazu iz Program 1 Architecture Specification):
Nemogućnost upisa audit događaja nikada ne sme proći neprimećeno.** Tih neuspeh upisa je gori od
odsustva audit-a — sistem tada deluje kao da je auditovan, a nije. Svaka komponenta koja piše u
`audit_immutable` mora tretirati sopstveni neuspeh upisa kao događaj koji sam po sebi zahteva
vidljivost (alert, degradovan status, ili — za operacije čija kritičnost to zahteva — promenu same
odluke), ne kao tihu, apsorbovanu grešku. Kriterijum za KOJU odluku audit-nedostupnost sme tiho
apsorbovati, a koju mora eskalirati/blokirati, zavisi od kritičnosti same operacije — v.
`docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md` §7.1 za konkretnu, već projektovanu
primenu ovog pravila (Audit Requirement tiers: OPTIONAL/RECOMMENDED/REQUIRED/MANDATORY).

**Goal 5 — Privacy First.** Privatnost ima prednost nad AI mogućnostima. Ako postoji konflikt
između funkcionalnosti i privatnosti, pobeđuje privatnost.

**Goal 6 — Human Authority.** AI nikada ne donosi konačnu pravnu odluku. Odgovornost ostaje na
korisniku.

## 1.7 Core Security Principles

1. **Default Deny** — sve je zabranjeno dok eksplicitno nije dozvoljeno.

   **Korolar — Escalation-Only Invariant (dodato 2026-08-02, po nalazu iz Program 1 Architecture
   Specification):** kad god politika (Policy) deklariše minimalni nivo zaštite za neku klasu
   operacije, procena rizika (Risk Scoring, Anomaly Detection) sme SAMO da podigne taj nivo za
   konkretan slučaj, nikad da ga spusti. Formalno: `effective_requirement = max(policy_floor,
   risk_derived_requirement)`. Razlog nije tehnički nego bezbednosni: politika deklarisana za
   "prosečan slučaj" jedne funkcije (npr. "prevod → OPTIONAL audit") ne sme tiho važiti i za
   neuobičajeno rizičnu instancu te iste funkcije (npr. dokument koji je advokatska tajna,
   GDPR-relevantan, sudski dokument). Ovo pravilo važi za svaki budući Program koji kombinuje
   deklarativnu politiku sa procenom rizika, ne samo za Program 1 — v.
   `docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md` §1.2 za konkretnu primenu.
2. **Least Privilege** — svaki korisnik ima najmanja moguća prava.
3. **Need To Know** — korisnik vidi samo ono što mu je potrebno.
4. **Defense In Depth** — ne postoji jedna zaštita, postoji više nezavisnih slojeva.
5. **Zero Trust** — ne verujemo korisniku, uređaju, mreži, browseru, LLM-u, pluginu, API-ju.
   Verifikujemo sve.
6. **Privacy By Design** — privatnost nije opcija, ona predstavlja deo arhitekture.
7. **AI Is Untrusted** — eksterni AI modeli smatraju se spoljnim sistemima. Nikada ne dobijaju
   više podataka nego što je neophodno.
8. **Secure Before Smart** — ako postoji izbor između pametnijeg AI ili bezbednijeg AI, uvek
   pobeđuje bezbedniji.
9. **Explain Before Execute** — svaka AI akcija mora imati razlog.
10. **Evidence Over Assumption** — bezbednosne tvrdnje moraju biti dokazive. Nikada marketinške.

## 1.8 Zabranjene tvrdnje

Vindex AI nikada neće koristiti sledeće marketinške tvrdnje:

- ❌ 100% bezbedan
- ❌ Nemoguće hakovati
- ❌ GDPR compliant bez pravnog osnova
- ❌ AI nikada ne greši
- ❌ Podaci su apsolutno sigurni

Dozvoljene tvrdnje:

- ✔ Privacy by Design
- ✔ Defense in Depth
- ✔ Zero Trust Architecture
- ✔ End-to-End Auditability
- ✔ AI Governance
- ✔ Local Processing Where Applicable
- ✔ Encryption at Rest
- ✔ Encryption in Transit
- ✔ Human-in-the-loop

*(Cross-reference: `docs/security/PUBLIC_SECURITY_CLAIMS.md` is the existing operational
implementation of this rule — what can/cannot be said publicly, evidence-checked per claim.)*

## 1.9 Security Capability Model

Blueprint definiše bezbednost kao skup sposobnosti (capabilities), a ne pojedinačnih funkcija.
Ključne sposobnosti koje Vindex AI mora da razvije su:

1. Pouzdana autentikacija i autorizacija.
2. Klasifikacija i zaštita podataka.
3. Upravljanje pristupom na nivou predmeta i dokumenata.
4. AI Governance Layer za kontrolu svih AI interakcija.
5. Zaštita od prompt injection i drugih LLM napada.
6. Forenzički audit svih AI odluka.
7. Kontrolisana upotreba eksternih AI modela.
8. Sigurno čuvanje i oporavak podataka.
9. Detekcija anomalija i pokušaja zloupotrebe.
10. Potpuna sledljivost (traceability) svake kritične operacije.

Ove sposobnosti predstavljaju ciljnu arhitekturu sistema i vode implementaciju svih narednih
programa. **Svaka buduća implementacija mora se mapirati na jednu ili više ovih 10 stavki** — v.
`docs/architecture/VINDEX_TRUST_ARCHITECTURE_TRACEABILITY.md` za trenutno stanje mapiranja.

---

# PART II — Current Architecture Assessment (Methodology)

**Napomena o statusu ovog dela:** Part II definiše *metodologiju* procene, ne sam nalaz. Za
domene navedene ispod, procena je već sprovedena u periodu 2026-07-23 do 2026-07-26 kroz
`docs/security/SECURITY_GAP_REGISTER.md`, `docs/SECURITY_MATURITY_DASHBOARD.md`,
`docs/security/STRIDE_THREAT_MODEL.md` i `docs/security/SECURITY_ROADMAP.md` — vidi traceability
dokument za mapiranje domen-po-domen umesto ponavljanja tog rada ovde.

Ne želimo mišljenje. Želimo dokazivo stanje sistema. Claude Code ne sme da pretpostavlja ništa —
svaka tvrdnja mora biti potkrepljena referencom na konkretan kod, migraciju, konfiguraciju ili
test.

### Pravilo rada

Za svaku oblast, procena mora odgovoriti kroz sledeću tabelu:

| Polje | Obavezno |
|---|---|
| Trenutno stanje | Da |
| Dokaz (fajl/klasa/linija) | Da |
| Rizik | Da |
| Kritičnost (Critical/High/Medium/Low) | Da |
| GAP u odnosu na Blueprint | Da |
| Predlog implementacije | Da |
| Rizik regresije | Da |
| Procena složenosti | Da |
| Test strategija | Da |

### Oblasti koje moraju biti analizirane

Identity & Authentication; Authorization / RBAC; Tenant Isolation; Database Security; Storage
Security; Encryption; Secret Management; API Security; File Upload Pipeline; OCR Pipeline; Case
Genome; Knowledge Base; Legal Reasoning Engine; AI Pipeline; Prompt Construction; External LLM
Integrations; Audit System; Logging; Monitoring; Backup & Recovery; Data Retention; Data
Deletion; AI Governance (trenutno stanje); Incident Handling; Dependency & Supply Chain Security.

### Završni rezultat Assessment-a

Assessment ne implementira ništa. On isporučuje:

- Security Maturity Matrix (po domenima),
- Risk Register sa prioritetima,
- Dependency Map (šta od čega zavisi),
- Implementation Order koji minimizuje rizik regresija.

Tek kada taj izveštaj bude pregledan i odobren, prelazi se na implementaciju Programa 1.

### Governing napomena (važi za ceo projekat)

Nijedna nova bezbednosna funkcionalnost ne sme biti implementirana zato što je "dobra ideja".
Svaka implementacija mora biti direktno povezana sa jednom ili više definisanih Security
Capability-ja iz ovog Blueprint-a, imati jasan threat model, plan verifikacije i dokazivu
vrednost za zaštitu podataka korisnika. Ovo pravilo sprečava da Vindex vremenom sklizne u
gomilanje "security feature-a" bez jasne arhitektonske svrhe — gradi se koherentan sistem
poverenja, a ne zbir nepovezanih zaštitnih mehanizama.
