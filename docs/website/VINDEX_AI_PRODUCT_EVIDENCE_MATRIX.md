# VINDEX AI — MATRICA PRODUKTNIH DOKAZA

Stanje: `ed1974ca`. Frontend je vanilla JS: `static/vindex.js` (23.303 linije).

**Nijedan ekran nije snimljen niti pregledan uživo** — aplikacija nije pokretana (naplativi AI
pozivi, produkcijski podaci). Sve ispod izvedeno je iz koda i označeno po pouzdanosti.

---

## GLAVNI NALAZ — pročitati prvi

Centralna tvrdnja proizvoda je **„Vindex zna odakle zna"**. Da bi sajt to pokazao, mora
postojati ekran na kome se **vidi oznaka porekla**.

U kodu postoje elementi `rag-source-info` i `rag-confidence-badge` — dakle prikaz izvora i
pouzdanosti AI odgovora **postoji kao komponenta**. Ali u pronađenim isečcima oba se
**skrivaju** (`display` postavljen na `none`), uz komentar da se badge „ranije prikazivao
iznad hero kartice".

**Da li korisnik danas vidi poreklo — UNVERIFIED.**

To je jedino pitanje koje odlučuje da li sajt uopšte može da pokaže svoj glavni
diferencijator. Rešava se za dva minuta: otvoriti aplikaciju, postaviti pitanje nad predmetom,
pogledati da li se izvor prikazuje. Nagađanje ovde ne bi vredelo ništa.

---

## MATRICA

| Tvrdnja | UI dokaz | Gde | Status | Spremno za snimak | Javno bezbedno |
|---|---|---|---|---|---|
| Strukturisan kontekst | prikaz predmeta sa poljima | app | **UNVERIFIED** — backend dokazan, UI nepregledan | NE | traži sintetičke podatke |
| **Poreklo podatka** | `rag-source-info`, `rag-confidence-badge` | `static/vindex.js` | **UNVERIFIED — možda skriveno** | **NE** | traži sintetičke podatke |
| Nepromenljiva evidencija | — | **korisnički ekran NIJE pronađen** | **NEMA UI** | NE | — |
| Obrada dokumenata | tok unosa | app | verovatno postoji | verovatno | traži sintetičke podatke |
| Analiza informacija | AI odgovor | app | verovatno postoji | verovatno | traži sintetičke podatke |
| Semantička pretraga | RAG tok | app | verovatno postoji | verovatno | traži sintetičke podatke |
| Rokovi i obaveze | kalendar / rokovi | `routers/kalendar.py`, `rokovi_lanac.py` | backend dokazan, UI UNVERIFIED | NE | traži sintetičke podatke |
| Uloge i ovlašćenja | ekran kancelarije | `routers/kancelarija.py` | backend dokazan, UI UNVERIFIED | NE | **NE — otkriva strukturu tima** |
| Javni API | ekran API ključeva | `routers/export.py` | backend postoji | **NE** | **NE — prikazuje kredencijale** |

---

## TRI NAJJAČA POSTOJEĆA DOKAZA

1. **AI odgovor sa oznakom izvora** — jedini ekran koji direktno pokazuje centralnu tezu.
   **Uslov: potvrditi da je vidljiv.**
2. **Strukturisan prikaz predmeta** — pokazuje da Vindex nije skladište dokumenata.
3. **Tok unosa dokumenta** — pokazuje rad sa stvarnim fajlovima, ne sa nalepljenim tekstom.

## ŠTA NEMA UI I NE SME SE IZMIŠLJATI

**Nepromenljiva evidencija nema korisnički ekran.** Postoji `saradnja_audit` sa endpointom
`GET /api/saradnja/audit/{predmet_id}`, ali to je **istorija saradnje na predmetu**, a ne
hash-ulančani `audit_immutable`.

Za sajt to znači: nepromenljiva evidencija se objašnjava **dijagramom, ne snimkom ekrana**.
Lažni prikaz nepostojećeg ekrana bio bi upravo ono što ovaj proizvod tvrdi da sprečava.
