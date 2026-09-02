# FAZA 6.4.3 — CONFIRMATION SEMANTICS + INFORMATION DISCLOSURE

## 1. Baseline
```
HEAD 773213e2 · origin/main = production 044c5310
kod/testovi/migracije: cisto   ·   migracija 127: NIJE pokrenuta
0 DDL · 0 push · 0 deploy · 0 produkcionih izmena
```

## 2. Semantika potvrde — sta `CONFIRMED` zapravo znaci

`potvrdi_rok(rok_id, user_id, napomena=None)` upisuje **jedan red u
`audit_immutable`**: `action='rok_potvrdjen'`, `resource_type='rok'`,
`resource_id=str(rok_id)`. **Nista drugo se ne menja.**

Odgovor na §1 pitanje: `CONFIRMED` danas znaci **iskljucivo authorization za
akciju**, ne „verified case fact". Nema polja, tabele ni stanja koje bi rok
proglasilo proverenom cinjenicom — postoji samo auditni zapis odluke i kapija
koja ga cita. To je uzak, ali cist ugovor.

## 3. Semantika odbijanja
`odbij_rok` upisuje `action='rok_odbijen'` nad istim `resource_id`.
`potvrdjeni_ids` cita oba tipa, sortira po `seq` i **poslednja odluka pobedjuje**.
Odbijanje posle potvrde gasi izvrsivost; potvrda posle odbijanja je vraca.

## 4. Identitet potvrde — 🟢
Vezan je za `predmet_hronologija.id` i ni za sta drugo. Dokazano izvorom:
`_zapisi` ne pominje `datum`, `naziv`, `vaznost`, `akter` ni `dokument`;
`potvrdjeni_ids` upareuje `.in_("resource_id", ids)` uz
`.eq("resource_type", "rok")`.

Adversarial (§3 A/B/C) — sve prolazi:
```
A  potvrda roka A ne potvrdjuje rok B
B  isti datum + naziv + vaznost, razlicit ID -> potvrda ne prelazi
C  isti tip, razlicit datum                  -> potvrda ne prelazi
```

## 5–7. Potvrda ne menja poreklo, aktera ni prioritet — 🟢
`shared/rok_potvrda.py` **nema nijedan upit nad `predmet_hronologija`** (jedini
`table(...)` poziv je nad `audit_immutable`). `izvor`, `akter` i `vaznost` su
ocuvani **po konstrukciji** — ne postoji kod koji bi ih prepisao.
`AI_AUTONOMOUS` + potvrda ostaje `AI_AUTONOMOUS`.

## 8. Implicit-confirmation inventory — 🟢 (prazan skup)

**`potvrdi_rok` i `odbij_rok` imaju NULA pozivaoca** — nema rute, nema UI-ja,
nema pozadinskog posla. Pretraga kroz ceo repo (`.py` + `.js`) van samog modula:
0 pogodaka.

Posledica je dvostruka i obe strane treba izgovoriti:
- **§16/§17/§18 su prazni skupovi.** Nijedan klik, upload, kreiranje predmeta,
  otvaranje dokumenta ni Copilot poziv ne moze potvrditi rok — jer nista ne moze.
  Provereno i da nijedan od 16 pisaca ne upisuje potvrdu pri kreiranju roka.
- **Ali ni advokat ne moze nista da potvrdi**, pa je ACTION sloj mrtav.

Test `test_ne_postoji_nijedan_pozivalac_potvrde` **namerno pada** cim se doda
prvi pozivalac — tada se mora ponovo dokazati da nova povrsina ne uvodi
implicitnu potvrdu.

## 9. Klijentski portal — trace

`GET /api/client-portal/view` · **`X-Portal-Token`, BEZ logina** — token drzi
klijent, dakle **trece lice**.

Vraca:
| polje | sadrzaj | limit |
|---|---|---|
| `hronologija` | `dogadjaj, datum, datum_iso, akter, vaznost` | 50 |
| `kriticni_rokovi` | `dogadjaj, datum_iso, vaznost`, narednih 30 dana | 10 |
| `rocista` | sud, datum, vreme, sudnica, broj predmeta | 20 |

Filter je **iskljucivo tekstualni/prioritetni**:
```python
if not dogadjaj.startswith("[INTERNI]") and vaznost != "interni"
```

**Ni `izvor` ni potvrda se ne citaju.** Nepotvrdjen AI rok — ukljucujuci onaj
koji je model izmislio — vidljiv je klijentu, zajedno sa imenom aktera.

## 10. Information-disclosure inventory

**43 modula sa rutama dodiruju rokove. Potvrdu cita 7. Ostalih 36 ne.**

| Kategorija (§10) | Moduli | Cita potvrdu |
|---|---|---|
| **ACTION** | `email_notif`, `sms`, `notifications`, `viber`, `morning_briefing`, `whatsapp_notif`, `integrations` | 🟢 7/7 |
| **DISCLOSURE — klijent** | `client_portal` | 🔴 NE |
| **DISCLOSURE — izvoz** | `export`, `data_export`, `billing_reports` | ⚪ politika nedefinisana |
| **INTERNAL** | `dashboard`, `kalendar`, `portfolio`, `intelligence_timeline`, `case_commander`, `zadaci`, `voice`, `api.py` (68 ruta) … | ⚪ politika nedefinisana |

## 11. Action vs disclosure
FAZA 6.4.2 je zatvorila **ACTION**. **DISCLOSURE nije ni definisan** — to je
tacno greska koju §10 upozorava da se ne ponovi. Zatvaranje slanja ne zatvara
otkrivanje.

## 12. Disclosure matrica (mereno)
```
izvor            potvrda      ACTION   KLIJENT  INTERNAL  EXPORT
AI_AUTONOMOUS    UNCONFIRMED   DENY     VIDI     VIDI      VIDI
AI_AUTONOMOUS    CONFIRMED    ALLOW     VIDI     VIDI      VIDI
AI_ASSISTED      UNCONFIRMED   DENY     VIDI     VIDI      VIDI
HUMAN_DIRECT     UNCONFIRMED   DENY     VIDI     VIDI      VIDI
DETERMINISTIC    UNCONFIRMED   DENY     VIDI     VIDI      VIDI
SYSTEM           UNCONFIRMED   DENY     VIDI     VIDI      VIDI
LEGACY_UNKNOWN   UNCONFIRMED   DENY     VIDI     VIDI      VIDI
```
Kolona ACTION je jedina u kojoj potvrda nesto menja. Ostale tri su konstantne —
**nijedna povrsina otkrivanja ne razlikuje potvrdjeno od nepotvrdjenog.**

## 13. Audit dovoljnost — 🟢
`audit_immutable` nosi: `user_id` (KO), `action` (STA/odluka), `created_at`
(KADA), `resource_id` (KOJI tacno rok), `seq` (REDOSLED), `prev_hash`/
`entry_hash` (nepromenjivost), `metadata` (napomena). **Nova tabela nije
potrebna.**

## 14. Ugovor koji buduci UI mora ispuniti
```
prikazi kandidata -> pokazi izvor/dokaz -> potvrdi TACNO tog kandidata
                                        -> ili odbij TACNO tog kandidata
```
Obavezno: **eksplicitno · pojedinacno · auditabilno · vezano za `rok.id`**.
Zabranjeno bez zasebne odluke: „Potvrdi sve AI rokove". Potvrda ne sme biti
posledica pregleda, otvaranja ni cuvanja.

## 15. 🟡 IDENTITY-DEPENDENT REJECTION RISK (prijavljeno, nereseno)

`predmet_hronologija` je **insert-only** (dokazano u 6.3: 0 UPDATE/DELETE
putanja). FAZA 6.1 je izmerila da refresh sa promenjenim datumom pravi **NOV
red sa NOVIM `id`** (3/3 na stvarnim podacima).

Dakle: odbijen rok se pri sledecoj ekstrakciji vraca kao **nov kandidat sa
drugim `id`**, i odbijanje ga ne pokriva. Sistem danas ne razlikuje:
```
ispravka  ·  duplikat  ·  ponavljanje  ·  novo opazanje
```
Ovo se **ne resava u ovoj fazi** (§13) — trazi identity model koji je FAZA 6.1
dokazala nereivim sa danasnjim signalima.

## 16. Testovi
```
tests/test_faza643_confirmation_disclosure.py  (nov)  15 prosla
```
Nijedan postojeci test nije menjan. Nula novih padova.

## 17. Preostali blokeri
1. 🔴 **Klijent vidi nepotvrdjen AI rok** bez ijedne definisane politike.
2. 🔴 **Politika otkrivanja ne postoji** ni za jednu od tri kategorije osim
   ACTION — 36/43 modula ne zna za pojam potvrde.
3. 🟡 **Nema povrsine za potvrdu** → ACTION sloj je mrtav.
4. 🟡 **Rejection ne prezivljava re-ekstrakciju** (§15).

## 18. Migration impact — NEMA
Migracija 127 nije menjana ni pokretana. Nista u ovoj fazi ne menja njen ugovor.

---

## VERDICT

# 🔴 BLOCKED

Po §22, GREEN trazi da **svaki** uslov bude dokazan. Dokazano je osam:

| | |
|---|---|
| CONFIRMATION = explicit authorization/review | 🟢 |
| vezana za tacan `rok.id` | 🟢 |
| ne menja `izvor` | 🟢 |
| ne menja `akter` | 🟢 |
| ne menja `vaznost` | 🟢 |
| UNCONFIRMED ne moze proizvesti ACTION | 🟢 (6.4.2) |
| VIEW / UPLOAD / CASE CREATION / AI ASSISTANCE ≠ CONFIRMATION | 🟢 (prazan skup) |
| AUDIT: ko/sta/kada/koji/odluka/redosled | 🟢 |
| **UNCONFIRMED ne curi na klijentske povrsine** | 🔴 **curi** |
| **CLIENT DISCLOSURE ima eksplicitnu politiku** | 🔴 **ne postoji** |
| REJECTION je identity-bound | 🟡 jeste za dati red, ali ne prezivljava novu ekstrakciju |

Blokada nije tehnicka nego **produktna**: arhitektura IMA stanje potrebno da se
politika izrazi (`potvrda`), ali politika **nije definisana**. Po §8 mi je
izricito zabranjeno da je izmislim heuristikom, a po §23 da napravim brzo
resenje — pa staje ovde.

### Tri odluke koje su tvoje

1. **Sme li klijent da vidi nepotvrdjen rok?** Opcije: (a) ne — portal prikazuje
   samo potvrdjene; (b) da, ali oznaceno kao „nepotvrdjeno"; (c) da, kao sada.
2. **Vazi li ista politika za advokatov INTERNAL pogled?** Advokat verovatno
   treba da vidi kandidate — inace ih ne moze ni potvrditi. Ali to treba reci.
3. **Sta sa izvozima** (`export`, `data_export`, `billing_reports`) — koji
   napustaju sistem kao fajl?

**MIGRACIJA 127 NIJE POKRENUTA. Ne pokrecem je.** Pet commita i dalje ceka.
