# FAZA 6.5 — CONFIRMATION + DISCLOSURE BOUNDARY: IMPLEMENTACIJA

## 1. Pocetni git state
```
HEAD pre faze  702e6bd0     origin/main = production  044c5310
kod/testovi/migracije: cisto   ·   migracija 127: NIJE pokrenuta
```

## 2. Sta je promenjeno
```
shared/rokovi.py            centralna politika `sme_pristupiti` + 4 potrosaca
shared/rok_potvrda.py       tri stanja + `odluke()` kao JEDINI citac
routers/rok_odluka.py       NOV — povrsina za ljudsku odluku (3 rute)
routers/client_portal.py    kanonska granica otkrivanja prema klijentu
routers/export.py           stanje odluke se pridruzuje pre PDF-a
predmet_pdf.py              nepotvrdjen/odbijen rok se OZNACAVA
api.py                      registracija rutera
tests/  1 nov + 3 azurirana                      11 fajlova, +245 / -37
```

## 3. Arhitektonski model
```
rok (predmet_hronologija.id)
        ↓
stanje odluke  (audit_immutable: rok_potvrdjen | rok_odbijen | ništa)
        ↓
politika potrosaca  (shared/rokovi.py::sme_pristupiti)
        ↓
ALLOW / DENY
```
Cetiri potrosaca, jedna funkcija:
```
stanje         INTERNAL   CLIENT   EXPORT_EXTERNAL   ACTION
UNCONFIRMED    vidi       NE       NE                NE
CONFIRMED      vidi       vidi     vidi              sme
REJECTED       vidi       NE       NE                NE
```
`INTERNAL` vidi sve **namerno**: advokat mora videti kandidata da bi ga
potvrdio, a odbijen rok mora ostati u istoriji. **ODBIJEN NIJE OBRISAN.**
Nepoznat potrosac je fail-closed.

## 4. Implementacija potvrde
`potvrdi_rok`/`odbij_rok` su zadrzani nepromenjeni — bili su semanticki
ispravni, samo bez pozivaoca. Dodato je:

- **`odluke(ids) -> {id: CONFIRMED|REJECTED}`** — jedini citac odluka.
  `potvrdjeni_ids` je sada IZVEDEN iz njega (dva nezavisna citaca bi se razisla).
  Redosled po `seq`, poslednja odluka pobedjuje, fail-closed na pad upita.
- **`routers/rok_odluka.py`** — tri rute:
  ```
  GET  /api/rokovi/kandidati          advokat vidi rokove + `stanje_odluke`
  POST /api/rokovi/{rok_id}/potvrdi   potvrda TACNO tog roka
  POST /api/rokovi/{rok_id}/odbij     odbijanje TACNO tog roka
  ```
  Nema grupne potvrde. Vlasnistvo se proverava `.eq("user_id", uid)` (backend
  radi kao `service_role`, pa je RLS zaobidjen). Tudji rok daje **404**, ne 403 —
  ne otkriva postojanje.

## 5. Implementacija otkrivanja
`routers/client_portal.py` — oba klijentska skupa (`hronologija`,
`kriticni_rokovi`) prolaze kroz `filtriraj_za(..., potrosac=POTROSAC_KLIJENT)`.
Upiti sada dovlace `id`. Stari filter (`[INTERNI]`, `vaznost`) **ostaje**, ali
kao ono sto jeste — skrivanje internih beleski — i primenjuje se **posle**
kanonske politike, ne umesto nje.

## 6. Exact-ID dokaz
```
rok-1 i rok-2: isti predmet, isti datum, isti naziv, ista vaznost, razlicit ID
potvrda {rok-1}:  rok-1 ALLOW   ·   rok-2 DENY   (CLIENT, ACTION, EXPORT)
odbijanje rok-1:  rok-1 DENY    ·   rok-2 nepromenjen
```

## 7. Klijentski portal — dokaz
```
{a: CONFIRMED, b: REJECTED, c: (nema zapisa)}  ->  klijent vidi samo [a]
```
`izvor`, `akter` i `vaznost` ne uticu ni u jednom smeru — provereno nad 8
vrednosti `izvor`-a x 3 potrosaca i 5 `akter` x 3 `vaznost`.

## 8. Izvoz
PDF izvoz (`/api/predmeti/{id}/pdf-export`) je **INTERNAL** — advokatov radni
spis. Nepotvrdjen rok **ostaje**, ali je oznacen `[NEPOTVRĐENO]`, odbijen
`[ODBIJENO]`. Tiho izostavljanje roka iz spisa bilo bi gore od prikaza
kandidata — to je ista klasa greske („tihi gubitak") koja je vec dva puta
prijavljena u ovom programu.

`EXPORT_EXTERNAL` politika postoji u kodu i testirana je, ali **danas je nijedan
put ne koristi** — nijedan izvoz nije klasifikovan kao „napusta advokatov
prostor". Kad se takav pojavi, politika ga ceka.

## 9. Outbound regresija (6.4.2 nepromenjen)
Svih 7 modula i dalje zove kapiju u istom broju (email 3, SMS 2, notifikacije 2,
Viber 1, brifing 2, WhatsApp 2, kalendar 1). `sme_pokrenuti_obavezu` je sada
**tanak sloj** nad `sme_pristupiti(..., ACTION)` — jedan vlasnik odluke, sedam
poziva nepromenjeno.

## 10. Mutacije — **14/14 KILLED**
```
M1  klijent vidi nepotvrdjeno              KILLED
M2  odbijen se tretira kao potvrdjen       KILLED
M3  nepoznat potrosac dobija sve           KILLED
M4  `odluke` fail-OPEN na pad upita        KILLED
M5  odbijanje se cita kao potvrda          KILLED
M6/M7  portal ne filtrira (2 skupa)        KILLED
M8  ruta ne proverava vlasnistvo           KILLED
M9  ruta cuti kad audit padne              KILLED
M10 PDF ne oznacava nepotvrdjeno           KILLED
M11 ACTION prestaje da delegira            KILLED
M12 interni pogled gubi kandidate          KILLED
M13 drugi pozivalac potvrde                KILLED
M14 prazan ulaz ipak zove bazu             KILLED
```

**Dva prolaza su bila nevazeca i to se prijavljuje:**
1. Prvi prolaz je pokazao 12/12, ali je **baseline imao 1 pad**
   (`test_ne_postoji_nijedan_pozivalac_potvrde` — legitimno, jer je 6.5 dodala
   prvog pozivaoca). Svaka „KILLED" oznaka je tada dolazila od tog pada.
   Dodata je **kontrola bez mutacije** na pocetak svakog prolaza.
2. U vazecem prolazu su **M4 i M5 PREZIVELE** — `odluke()` je bio pokriven samo
   posredno. Dodato je 6 jedinicnih testova nad laznim Supabase-om. Mutacije
   nisu menjane.
3. **M14 je prezivela** jer `odluke` hvata `Exception`, pa je test koji je
   detektovao poziv baze bacanjem izuzetka prolazio i bez zastite. Test je
   prebacen na **brojac poziva**.

## 11. Regresija
```
1426 prosla · 1 preskocen · 5 palo
```
Svih 5 su **pre-postojeci `[trio]`** (`test_prg_night_register` 2,
`test_coi_intake_convergence` 3) — dokazani na cistom HEAD-u u FAZI 6.4.
**0 novih padova.**

Azurirani postojeci testovi i razlog (nijedan assert nije oslabljen):
- `test_faza643::test_ne_postoji_nijedan_pozivalac_potvrde` → sada
  `test_potvrdu_poziva_TACNO_JEDNA_povrsina`. To je **uza** tvrdnja: „nema
  nijednog" je zamenjeno sa „ima tacno jednog, i to namenskog".
- `test_client_portal.py`, `test_beta_p1_portal_readonly.py` — mere skrivanje
  internih beleski i oblik odgovora, sto su i dalje vazeci ugovori. Dobili su
  autouse fixture koji modeluje advokata koji je rokove **vec potvrdio**.

## 12. Poznata praznina zivotnog ciklusa (§X)
```
Observation A  ->  REJECTED  ->  refresh  ->  Observation B (NOV id)
```
`predmet_hronologija` je insert-only, pa refresh sa promenjenim datumom pravi
nov red sa novim `id` (6.1: 3/3). Odbijanje **ne prelazi** na B.

**Status: KNOWN GAP — OBSERVATION LIFECYCLE / CONCEPTUAL IDENTITY.**
**NON-BLOCKING za autorizaciju**, jer je potvrda bezbedno vezana za tacan ID i
ne moze slucajno preci na drugi. B je nov kandidat i trazi novu odluku.
Nikakvo heuristicko povezivanje nije uvedeno — i namerno nece biti.

## 13. Migracija 127
**Nije pokrenuta, nije menjana.** Implementacija je kompatibilna: `izvor` ostaje
provenijencija i ne ucestvuje ni u jednoj odluci ove faze.

## 14. VERDICT

# 🟢 GREEN — CONFIRMATION + DISCLOSURE BOUNDARY CLOSED

| # | Uslov | |
|---|---|---|
| 1 | exact-ID potvrda radi | 🟢 |
| 2 | odbijanje je exact-ID vezano | 🟢 |
| 3 | UNCONFIRMED ne moze ACTION | 🟢 |
| 4 | UNCONFIRMED ne moze CLIENT DISCLOSURE | 🟢 |
| 5 | REJECTED ne moze ACTION | 🟢 |
| 6 | REJECTED ne moze CLIENT DISCLOSURE | 🟢 |
| 7 | CONFIRMED prolazi po politici potrosaca | 🟢 |
| 8 | advokat vidi kandidate i moze da odluci | 🟢 `/api/rokovi/kandidati` + 2 rute |
| 9 | audit ostaje nepromenjiv | 🟢 `audit_immutable`, bez nove tabele |
| 10 | poreklo/akter/prioritet nepromenjeni | 🟢 modul odluke ne dira hronologiju |
| 11 | 6.4.2 granica ostaje zatvorena | 🟢 7/7 modula, 13 poziva |
| 12 | nema heuristickog identiteta | 🟢 |
| 13 | praznina zivotnog ciklusa dokumentovana kao NON-BLOCKING | 🟢 |

## 15. Sta i dalje nije zavrseno (izvan ovog mandata)
1. **Nema UI-ja** — rute postoje, ekran ne. Advokat trenutno moze da potvrdi rok
   samo pozivom API-ja.
2. **Svi postojeci rokovi su nepotvrdjeni**, pa dok se ne potvrde, klijentski
   portal i izlazni kanali za njih cute. Fail-closed po dizajnu.
3. `EXPORT_EXTERNAL` nema nijednog korisnika — cim se pojavi izvoz koji napusta
   advokatov prostor, mora ga koristiti.

**NIJE pushovano. NIJE deployovano. Migracija 127 NIJE pokrenuta.**
`origin/main` = `044c5310`.
