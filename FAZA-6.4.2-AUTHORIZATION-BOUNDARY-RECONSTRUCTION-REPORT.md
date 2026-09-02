# FAZA 6.4.2 — AUTHORIZATION BOUNDARY RECONSTRUCTION

## 1. Baseline
```
HEAD pre faze  aa986192        origin/main = production  044c5310
kod/testovi/migracije pre faze: CISTO
migracija 127: NIJE pokrenuta · 0 DDL · 0 push · 0 deploy
```

## 2. RED-1 root cause
`IZVOR_SME_BEZ_POTVRDE = (AI_ASSISTED, HUMAN_DIRECT, DETERMINISTIC, SYSTEM)` i
`if red.get("izvor") in IZVOR_SME_BEZ_POTVRDE: return True`.

Atribut koji **opisuje** zapis dobio je moc da ga **odobri**. To je isti oblik
greske koji su faze 6.1–6.3 razotkrile kod `akter`, samo premesten na `izvor`.
Izmereno: 4/6 klasa je prolazilo nepotvrdjeno.

## 3. RED-2 root cause
`routers/viber.py::_briefing_tekst` je citao `predmet_hronologija` po
`vaznost="kritičan"` i slao kroz Viber bez ijedne kapije. Uzrok nije Viber nego
to sto **popis izlaznih puteva nikad nije bio potpun** — trazio se obrazac
„fajl koji citam `predmet_hronologija`", a citav sloj kanala cita rokove kroz
kanonski domenski citac `shared/rokovi.py::rokovi_za_korisnika`.

## 4. Novi kanonski model
```
akter    KO je izvrsio radnju      -> nikad ovlascenje
izvor    KAKO je sadrzaj nastao    -> opis porekla, audit, buduca politika
vaznost  KOLIKO je vazno           -> prioritet
potvrda  DA LI je covek odobrio    -> JEDINO ovlascenje
```
`sme_pokrenuti_obavezu` vise **ne grana ni po jednom polju sadrzaja**:
```python
rid = red.get("id")
if not rid:
    return False
return rid in (potvrdjeni_ids or set())
```

**Pojam „klase koje smeju bez potvrde" je UKLONJEN, ne zamenjen drugom listom.**
`IZVOR_SME_BEZ_POTVRDE` i `IZVOR_TRAZI_POTVRDU` vise ne postoje. Test
`test_nijedna_lista_bezbednih_izvora_ne_postoji` pada ako iko uvede novu.

## 5. Pre/post semantika kapije
| | pre (6.4) | posle (6.4.2) |
|---|---|---|
| ulaz u odluku | `izvor` + `id` + potvrde | **samo** `id` + potvrde |
| `HUMAN_DIRECT` nepotvrdjen | ALLOW | **DENY** |
| `AI_ASSISTED` nepotvrdjen | ALLOW | **DENY** |
| `DETERMINISTIC` / `SYSTEM` nepotvrdjen | ALLOW | **DENY** |
| nepoznato / odsutno / `None` | DENY | DENY |

## 6. Provenance × confirmation matrica (mereno)
```
                 UNCONFIRMED   CONFIRMED
AI_AUTONOMOUS       DENY         ALLOW
AI_ASSISTED         DENY         ALLOW
HUMAN_DIRECT        DENY         ALLOW
DETERMINISTIC       DENY         ALLOW
SYSTEM              DENY         ALLOW
LEGACY_UNKNOWN      DENY         ALLOW
None / "" / FUTURE_AGENT / odsutno   DENY   (i uz potvrdu: ALLOW po `id`)
```
Isto za `kritičan`, `važan` i `informativan` — 18 kombinacija u testu.

## 7. Kompletan outbound inventory — **13 poziva kapije, 7 modula, 7 kanala**

| Modul | Kanal | Kategorija (§7) | Poziva | Status |
|---|---|---|---|---|
| `email_notif.py` | email | A | 3 | 🟢 |
| `sms.py` | SMS | A | 2 | 🟢 |
| `notifications.py` | in-app | B | 2 | 🟢 |
| `viber.py` | Viber | A | 1 | 🟢 **novo (RED-2)** |
| `morning_briefing.py` | email brifing | A | 2 | 🟢 **novo** |
| `whatsapp_notif.py` | WhatsApp | A | 2 | 🟢 **novo** |
| `integrations.py` | Google Calendar | A | 1 | 🟢 **novo** |

Progresija popisa: FAZA 6.2 tvrdila **7** → 6.4.1 nasla **8** → 6.4.2 nasla **13**.
Pet novih je nadjeno tek kad je pretraga prosirena sa `predmet_hronologija` na
**kanonski domenski citac** (`rokovi_za_korisnika`, `rok_po_id`).

**Nisu izlazni putevi** (provereno pojedinacno, obrazlozeno u testu):
`client_portal.py` (read-only prikaz, kat. D), `api.py` (pogoci su
`include_router`), `case_evolution.py` (notifikacije iz `case_actions`),
`ccc.py`, `search.py`, `intake.py`.

## 8–11. Trace po kanalima
- **Viber** — `POST /api/viber/send-briefing` → `_briefing_tekst`. Upit sada
  dovlaci `id`; `hitni` je rezultat kapije. `vaznost="kritičan"` ostaje
  **selekcija kandidata**, ne dozvola.
- **email brifing** — `morning_briefing.py`, i predstojeci i propusteni rokovi
  prolaze kroz kapiju jednim upitom potvrda.
- **WhatsApp** — dva izlaza: `POST /api/whatsapp/posalji-rok` (nepotvrdjen rok
  daje **409**, ne tiho preskakanje) i dnevni brifing (filtriranje liste).
- **Google Calendar** — `POST /api/integrations/gcal/sync-rokovi`. Bez ovoga bi
  AI nalaz zavrsio u advokatovom spoljasnjem kalendaru kao obaveza.
- **email/SMS/notifikacije** — nepromenjeni; vec su zvali kapiju iz 6.4.

## 12. Scheduler / background (§17)
Cron ulazi (`/email-notif/send-reminders`, `/sms/send-reminders`,
`/api/briefing/cron`) zovu **iste funkcije** koje su gejtovane — nema zasebne
background putanje koja gradi poruku mimo njih. `case_evolution` posledice na
sabirnici pisu `case_actions`/`notifications`, ne izlazne poruke.

## 13. Direct-send pretraga (§16)
Popisani primitivi u repou: `smtplib`/`sendmail` (10+5), `_smtp_send` (17),
`twilio` (55), `viber` (189), `whatsapp` (112), `requests.post` (22),
`httpx.post` (2), `webhook` (187), `telegram` (1). Za svaki je utvrdjeno da li
mu ulaz dolazi iz rokova. Rezultat je tabela u §7. Cuvar
`test_nema_nepopisanog_izlaznog_puta` prolazi kroz **ceo repo** i pada ako se
pojavi modul koji cita rokove i ima odlazni kanal, a nije ni gejtovan ni
obrazlozen.

## 14. `akter` separation — 🟢
`akter` se ne pojavljuje u telu kapije. `je_ai_poreklo`/`AI_AKTERI` imaju **0
pozivaoca** u produkcionom kodu.

## 15. `vaznost` separation — 🟢
Kapija ne cita `vaznost`. Testirano nad 3 vrednosti × 3 klase: ishod zavisi
iskljucivo od potvrde. Na Viber putu, gde je ranije `vaznost` bila jedini
uslov, sada je samo selekcija kandidata.

## 16. Client portal — 🟡 INFORMATION DISCLOSURE (prijavljeno, nedirano)
`routers/client_portal.py:434,452` prikazuje `dogadjaj`, `datum`, `datum_iso`,
`akter` i `vaznost` **klijentu**. Nepotvrdjen AI rok je time vidljiv trecem
licu. Nije push i ne proizvodi spoljasnji efekat, pa po §12 nije popravljano —
ali se **ne oznacava kao bezbedno**. Zahteva zasebnu odluku.

## 17. Mutacije — **12/12 KILLED**
```
M1  vrati listu "bezbednih izvora"        KILLED
M2  `izvor != AI_AUTONOMOUS` daje ALLOW   KILLED
M3  `vaznost == kritičan` daje ALLOW      KILLED
M4  kapija uvek propusta                  KILLED
M5  red bez `id` postaje dozvoljen        KILLED
M6–M12  ukloni kapiju sa svakog od 7 kanala  KILLED (7/7)
```

## 18. Testovi
```
novi:  tests/test_faza642_authorization_boundary.py  -> 72 prosla
ukupno ciljano: 1379 prosla, 1 preskocen, 5 palo
```
Svih 5 padova su **pre-postojeci `[trio]`** (`test_prg_night_register` 2,
`test_coi_intake_convergence` 3) — dokazani na cistom HEAD-u jos u FAZI 6.4
(tamo ih je 8 kad se ceo fajl selektuje). **0 novih padova.**

Izmenjeni postojeci testovi i razlog:
- `test_faza62_*` — tvrdili su „ljudski rok ne trazi potvrdu". FAZA 6.4.1 je
  dokazala da je to bas RED-1. Ocekivanja ispravljena, ugovor pooostren.
- `test_b10`, `test_lz001`, `test_omega_006/007`, `test_onetruth`,
  `test_blackswan_001` — mere SVOJE ugovore (rezervacija, recnik `vaznost`,
  dedup, prioritet, propusteni rokovi), koji su i dalje vazeci. Dodat im je
  autouse fixture koji modeluje **advokata koji je rokove vec potvrdio**, i
  `id` u fixture redove. Nijedan njihov assert nije oslabljen.

## 19. Preostali rizici
1. **Nema povrsine za potvrdu.** `potvrdi_rok`/`odbij_rok` postoje kao funkcije
   bez rute i UI-ja. Dok je tako, **nijedan kanal ne salje nista** — fail-closed
   po dizajnu, ali proizvodno mrtav.
2. **Client portal** (§16).
3. `W-UPLOAD` i dalje prima `vaznost` iz LLM-a — sada bezopasno, jer `vaznost`
   nigde nije ovlascenje.

## 20. Migration impact — **NEMA**
Migracija 127 nije menjana ni pokretana. Njen ugovor (`NOT NULL`, `CHECK` nad 6
vrednosti, bez `DEFAULT`) ostaje ispravan; `izvor` i dalje treba za audit i
buducu politiku, samo vise ne odlucuje o izvrsenju.

## 21. Izmenjeni fajlovi
```
shared/rokovi.py                     kapija + uklonjene liste
routers/viber.py                     RED-2
routers/morning_briefing.py          novi izlaz
routers/whatsapp_notif.py            2 nova izlaza
routers/integrations.py              gcal izvoz
tests/  1 nov + 9 azuriranih
                       16 fajlova, +261 / -92
```
Nedirano u ovoj fazi: `api.py`, `services/`, `email_notif.py`, `sms.py`,
`notifications.py` (vec gejtovani u 6.4), migracija 127, UI, Dockerfile.

## 22. Git
```
git diff --check : cisto
origin/main      : 044c5310   (NE pushovano)
```

## 23. VERDICT

# 🟢 FAZA 6.4.2 GREEN — AUTHORIZATION BOUNDARY CLOSED

| Kriterijum | |
|---|---|
| `PROVENANCE ≠ AUTHORIZATION` | 🟢 kapija ne cita `izvor` |
| `AKTER ≠ PROVENANCE` | 🟢 0 pozivaoca |
| `VAZNOST ≠ AUTHORIZATION` | 🟢 |
| `UNCONFIRMED = NO ACTION` | 🟢 18/18 kombinacija |
| `UNKNOWN / MISSING / INVALID = NO ACTION` | 🟢 |
| `AI ≠ AUTO-AUTHORIZED` | 🟢 |
| `HUMAN_DIRECT / DETERMINISTIC / SYSTEM ≠ IMPLICIT CONFIRMATION` | 🟢 |
| `LEGACY_UNKNOWN ≠ ACTIONABLE` | 🟢 |
| 0 provenance-based implicit authorization | 🟢 |
| 0 direct outbound bypasses | 🟢 13/13 gejtovano |
| 0 Viber / scheduler / background bypass | 🟢 |
| 0 channel-specific semantics | 🟢 nijedan kanal nema svoju kapiju |
| 0 semantic overload | 🟢 |

Odgovor na §23 („kako bi buduci developer vratio gresku?"):
- **novi izlazni put bez kapije** → obara `test_nema_nepopisanog_izlaznog_puta`
  (pretraga kroz ceo repo, ne kroz poznatu listu);
- **promena `izvor` vrednosti radi ALLOW-a** → nemoguce, kapija ga ne cita;
- **nova lista „bezbednih izvora"** → obara
  `test_nijedna_lista_bezbednih_izvora_ne_postoji`;
- **grana po `vaznost`/`akter` u kapiji** → obara
  `test_kapija_ne_grana_po_sadrzaju_reda`.

**MIGRACIJA 127 NIJE POKRENUTA. Ne pokrecem je. Cekam eksplicitnu naredbu.**
