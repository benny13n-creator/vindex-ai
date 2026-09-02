# FAZA 6.2 — FORENSIC REPORT

## 1. Environment proof
- Radna grana `main`, radno stablo pre sprinta cisto (0 izmena).
- Baza: produkciona Supabase instanca (ista nad kojom je izvrsena FAZA 6.1).
- **Nijedan GPT poziv nije izvrsen. Nijedan email ni SMS nije poslat.**

## 2. HEAD / origin / production
```
HEAD pre sprinta = origin/main = production = 044c5310
```

## 3. Files changed
```
routers/email_notif.py           | 29 ++++++++++++++++----
routers/notifications.py         | 18 +++++++++---
routers/sms.py                   | 15 ++++++++--
shared/audit_immutable.py        |  6 ++++
shared/rokovi.py                 | 59 ++++++++++++++++++++++++++++++++++++++++
tests/test_b10_reminder_claim.py |  7 ++++-
6 files changed, 121 insertions(+), 13 deletions(-)
```
Novi fajlovi: `shared/rok_potvrda.py`, `tests/test_faza62_ai_observation_gate.py`,
`tests/test_faza62_gate_e2e_paths.py`.

## 4. Files explicitly NOT changed
`routers/case_dna.py` (Genome prompt, extraction schema, `_sync_rokovi_to_hronologija`),
`services/case_pipeline.py`, `services/case_evolution.py`, `shared/issue_v2.py`,
`shared/contradiction_identity.py`, sve migracije, `Dockerfile`, `Procfile`,
`.github/workflows/`, `index.html`, `static/vindex.js`, fixture predmet i dokument.

## 5. Previous INV-2 failure
FAZA 6.1 je uzivo upisala tri roka sa `vaznost="kritičan"` iz jednog dokumenta.
`_ACTIONABLE_VAZNOST = ["kritičan", "važan"]`, pa su sva tri bila podobna za email
podsetnik, SMS i notifikaciju **bez ijedne ljudske potvrde**. Jedini razlog zasto se
nista nije desilo je taj sto je `korisnik_email_notif` prazan.

## 6. Root cause
`vaznost` je AI PROCENA TEZINE, a bila je jedini uslov izvrsivosti. Nije postojala
nezavisna dimenzija "ko je ovo tvrdio" i "da li je covek to prihvatio".

## 7. Implemented safety boundary
`shared/rokovi.py::sme_pokrenuti_obavezu(red, potvrdjeni_ids)` — jedina kapija.
Fail-closed: red ciji je `akter` u `AI_AKTERI` prolazi iskljucivo ako mu je `id` u
skupu potvrdjenih. Redovi ljudskog porekla i ZPP lanca prolaze nepromenjeno.
`vaznost` NIJE dirana ni u semantici ni u vrednostima.

## 8. Observation lifecycle
UNREVIEWED (podrazumevano, nema zapisa) → CONFIRMED (`rok_potvrdjen`) →
REJECTED (`rok_odbijen`). Poslednja odluka po `seq` pobedjuje. Nosilac je POSTOJECI
`audit_immutable` (isti oblik kao `dokument_review_resolved`) — bez nove tabele i
bez migracije.

## 9. Action creation call-chain
```
predmet_hronologija --(citanje)--> email_notif / sms / notifications --> SLANJE
                                       ^
                                  KAPIJA OVDE (pre side effect-a)
```
`case_actions` NE cita hronologiju (FAZA 6.1: NO EDGE), pa deadline nikad ne postaje
`case_action` — potvrdjeno i uzivo (`case_actions` za fixture = 0).

## 10. All discovered action paths (7 gejtovanih)
1. `email_notif.py` send-reminders · 2. nedeljni digest (rokovi) ·
3. nedeljni digest (brojac hitnih) · 4. `sms.py` cron batch · 5. `sms.py` digest ·
6. `notifications.py` nadolazeci rokovi · 7. `notifications.py` propusteni rokovi.

**Namerno NIJE gejtovano:** `notifications.py` brojac aktivnosti (30 dana) — meri
AKTIVNOST korisnika, ne rok; gejtovanje bi promenilo semantiku neaktivnosti.

## 11. Negative / adversarial tests
36 testova u dva nova fajla. TEST F (email UKLJUCEN + nepotvrdjen AI rok → 0
poslatih) ima PAROVNI kontrolni slucaj (isti setup + potvrda → 1 poslat), pa dokazuje
da je uzrok kapija, a ne ugasen email.

## 12. Mutation result
**13/13 KILLED.**
Dve mutacije su u prvom prolazu PREZIVELE i obe su ojacale rad:
- **M6 (upit ne dovlaci `akter`)** — harness je ignorisao `.select(...)` pa razlika
  nije bila vidljiva. Lazni Supabase sada VERNO projektuje kolone (projekcija se
  primenjuje u `execute()`, jer PostgREST filtrira na serveru).
- **"AI rok bez `id`"** — utvrdjeno da je EKVIVALENTNA mutacija (`None in set()` je
  vec False), ne rupa u testu. Prijavljeno kao takvo, nije "popravljeno".

## 13. Regression result
`715 passed, 9 skipped, 2 failed`. Oba pada su **pre-postojeca**
(`test_prg_night_register.py` [trio] — dokazano na baseline-u bez izmena: 5 padova u
tom fajlu na cistom HEAD-u). **Nula novih padova.**

Usput ispravljeno: `git stash` je tokom baseline merenja pretvorio LF u CRLF u 5
fajlova; originalni zavrseci redova su vraceni, pa je diff ostao minimalan.

## 14. Production-data impact
```
predmeti 23 · predmet_dokumenti 44 · predmet_hronologija 55
predmet_genome_history 26 · case_actions 31 · predmet_dokazi 12
```
Identicno stanju posle FAZE 6.1. Nula novih redova. Nula potvrda/odbijanja upisano
u produkciju.

## 15. Fixture integrity
Fixture predmet `fb6f7ebd`, dokument `0ab218de` i sva tri roka (`Genome (AI)`,
`kritičan`) su NETAKNUTI. Nista nije brisano ni menjano.

## 16. Genome integrity
`routers/case_dna.py` nije menjan. Test `test_genome_i_dalje_upisuje_kritican` to
cuva: ako bi neko "resio" problem menjanjem proizvodjaca umesto postavljanjem
granice, test pada.

## 17. Identity-model integrity
Nije uveden identitet roka, nema span anchor-a, nema rezolucije identiteta, nema
automatskog spajanja. `resource_id` je `predmet_hronologija.id` — identitet REDA,
ne cinjenice. Granica iz FAZE 6.1 ostaje: DOCUMENT IDENTITY = proven,
FACT IDENTITY = unresolved.

## 18. Remaining known limitations
1. **Nema UI ni rute za potvrdu.** `potvrdi_rok`/`odbij_rok` postoje kao funkcije;
   povrsina za advokata je FAZA 7. Do tada nijedan AI rok nije izvrsiv — namerno
   stanje, ne previd.
2. **Kapija zavisi od toga da upit dovuce `akter`.** Strozije pravilo (odsutan kljuc
   → fail-closed) je implementirano pa VRACENO: obaralo je 10 postojecih testova
   cije fixture-e ne modeluju `akter`, dakle gasilo bi rokove i kod svakog buduceg
   pozivaoca koji ga zaboravi. Zastita je umesto toga na nivou testa (M5/M6 KILLED
   preko vernog harness-a).
3. `predmet_hronologija` i dalje nema sopstveno polje stanja.

## 19. Out-of-scope findings (NISU dirani)
- `_sync_rokovi_to_hronologija` je i dalje insert-only; promena datuma ostavlja stari
  red ziv (FAZA 6.1, 3/3).
- 15/24 istorijskih Genome rokova ima `status != 'aktivan'` i tiho se preskace.
- `predmet_genome_history` uvek kasni jednu verziju (upisuje STARI genome).

## 20. FINAL VERDICT
🟢 **GREEN** — nepotvrdjeno AI opazanje ne moze proizvesti izvrsivu obavezu ni na
jednom pronadjenom putu, i to je dokazano pozivanjem pravih funkcija, kontrolnim
parom i 13/13 ubijenih mutacija.

**Deploy NIJE izvrsen.** Commit je lokalan; push ceka izricito odobrenje.
