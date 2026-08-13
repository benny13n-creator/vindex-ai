# BETA-HARDENING-002 — FINAL FORENSIC REPORT

# VERDICT

## 🟡 YELLOW

Dve od tri stavke su zatvorene sa mutacionim dokazom. Treća (`GT-001`) je
zatvorena **u kodu**, ali **stanje produkcione šeme i dalje nije potvrđeno** —
a mandat izričito traži da nijedan `UNKNOWN` ne sme ostati da bi verdikt bio
zelen.

Uz to: protivnički pregled je našao **dve regresije koje je uveo ovaj sprint**,
i obe su ispravljene. To je razlog više da verdikt ne bude zelen na osnovu
prvog prolaza.

---

# BASELINE

```
commit:   005ebcd4
testovi:  5235 passed / 1 skipped / 0 failed
git:      clean
```

# ZAVRŠNO STANJE

```
testovi:   5255 passed / 2 skipped / 0 failed   (+20)
redosled:  no:randomly · seed=11 — oba zelena
migracije: NIJEDNA kreirana, nijedna izvršena
static/, index.html: NEDIRANO
```

---

# WSS (BYPASS-7)

| | |
|---|---|
| **stara putanja** | `voice_realtime.py:139` → `VoiceOrchestratorSession.start()` → `_connect_openai_realtime()` → sirov `websockets.connect(wss://api.openai.com/v1/realtime)` |
| **governance granica** | `proveri_voice_dozvolu()` — postojeća kapija, **nije uveden nov sistem** |
| **mehanizam prinude** | kapija kuje token `_Odluka` u contextvar-u; **granica sesije** i **tačka povezivanja** obe odbijaju bez njega |
| **korelacija** | kapija postavlja `shared.ai_provenance` kontekst — WS opseg ne prolazi kroz HTTP middleware, pa je ovo bila jedina putanja bez korelacionog ID-ja |
| **provenance** | `"started"` na otvaranju, terminalni status po stvarnoj isporuci (FS-002/SE-004 iz prethodne noći) |

## Šta je protivnički pregled oborio — i šta je zbog toga promenjeno

Prva verzija je prinudu stavila **samo unutar** `_connect_openai_realtime()`.
Recenzent je izmerio tri rupe:

| # | Rupa | Merenje | Popravka |
|---|---|---|---|
| **S2** | `openai_ws_factory` (test seam) zamenjuje **celu** funkciju povezivanja | veza otvorena uz `odluka_doneta=False` | prinuda premeštena **i na granicu sesije**, gde nijedna fabrika ne može da je zaobiđe |
| **S3** | `_oznaci_odluku` je bila **javna funkcija bez ijedne provere** | veza otvorena bez dodira sa registry-jem, tarifom i kill switch-om | token `_Odluka` može da nastane samo uz privatni ključ modula koji se nigde ne izvozi |
| **S8** | provera je gledala samo **da** odluka postoji, ne **čija** je | odluka korisnika A otvara vezu za korisnika B | odluka nosi `user_id` i proverava se protiv korisnika sesije |

**Recenzentova ocena prve verzije je bila tačna:** komentar je tvrdio
„čini nemogućim da se preskoči", a tri puta je bilo moguće.

---

# BILLING

| | |
|---|---|
| **ugovor** | **≥ 1 isporučen komad → naplaćeno; 0 komada → refund** |
| **zašto taj ugovor** | kredit je jedinica po upitu, ne po znaku; `UsageService` nema pojam delimične naplate. Alternativa „naplati srazmerno" ne postoji u proizvodu. |
| **rana isporuka** | `_delivered` se podiže **pre prvog** `yield` |
| **98% / pretposlednji / poslednji** | testirano na 1/25/50/75/90/98/99% — nijedan procenat nije profitabilan |
| **prekid pre prvog komada** | refund živ (SOA-012) |
| **ponovljeni obrazac** | 3 uzastopna prekida na pretposlednjem komadu → 3 naplate, 0 refunda |

## Regresija koju je uveo prethodni sprint — i koju je pregled našao

`SE-007` je dodao zaštitu `not _delivered` u `except Exception`. Recenzent je
izmerio da ta zaštita **guši i legitiman ponovni pokušaj refundacije**: kod
keš-pogotka ili `status="error"` prvi `refund()` može da padne, `_refunded`
ostane `False`, a rukovalac je onda odbijao da pokuša ponovo jer je odgovor već
isporučen. **Korisnik ostaje naplaćen za keširan ili neuspeo odgovor** — gore
nego pre `6fb4a99f`.

Popravka razdvaja dva različita pojma koja su bila spojena u jedan:

```
_delivered       = da li je korisnik dobio tekst
_refund_dugovan  = da li mu po ugovoru SLEDUJE povraćaj
```

Prekid veze gleda prvo; neuspeo upis povraćaja gleda drugo.

---

# PROVENANCE (GT-001)

| | |
|---|---|
| **migracija 089 primenjena** | **NEPOZNATO** — i to je sada **merljivo u runtime-u**, ne pretpostavka |
| **dokaz** | prvi širok upis meri stanje: uspeh ⇒ `089` primenjena; „kolona ne postoji" ⇒ nije |
| **stara politika** | tih pad na 10 legacy kolona bez `correlation_id`/`predmet_id`/`status`; potpuni neuspeh `logger.debug` |
| **nova politika** | **fail-open sa izričitim degradiranim statusom**: red se i dalje upisuje, ali se degradacija pamti, loguje kao `ERROR` i izlaže na `/health` |
| **potpuni neuspeh** | `logger.error`, ne `debug` |

## Dve rupe koje je pregled našao u mojoj popravci

**P2 — latch koji se otključava a nikad ne zaključava.** Jedan uspešan upis
posle degradiranog vraćao je `migracija_089_potvrdjena` na `True` i praznio
`izgubljene_kolone`. Dohvatljivo preko PostgREST schema-cache staleness i
rolling deploy-a. **Degradacija je sada lepljiva** — bolje lažno pesimistično
nego lažno sigurno, jer je ovo forenzički trag a ne metrika performansi.
Uz to, `izgubljene_kolone` je bila **konstanta**; sada je stvarno merenje.

**P6b — javni `/health` je curio tekst izuzetka.** Moja dijagnostika je vraćala
`str(_exc)[:120]`, iz čega je izmereno da izlazi
`postgres://korisnik:LOZINKA@host/baza`. **Ovo je bila jedina nova bezbednosna
površina u paketu, i uveo sam je ja.** Sada se spolja vidi samo
`{"dostupno": false}`, a detalj ide u serverski log.

---

# MUTATION PROOF

| Mutacija | Ishod |
|---|---|
| uklonjena prinuda u tački povezivanja (BYPASS-7 vraćen) | **1 pao** |
| `_Odluka` se opet može konstruisati spolja (S3) | **1 pao** |
| odluka se ne proverava po vlasniku (S8) | **1 pao** |
| degradacija šeme opet tiha | **1 pao** |
| širok upis ne beleži uspeh (089 nikad potvrđena) | **1 pao** |
| latch opet bezuslovan (P2) | **1 pao** |
| `/health` opet vraća tekst izuzetka (P6b) | **1 pao** |
| vraćena ranjiva delivery semantika | **12 palo** |
| uklonjena zaštita od dvostruke refundacije | **2 pala** |

---

# ADVERSARIAL REVIEW

Recenzent je dobio mandat da **obori** sprint i dao verdikt **RED**.

| Nalaz | Ishod |
|---|---|
| S2 — `openai_ws_factory` zaobilazi prinudu | **rešeno** |
| S3 — `_oznaci_odluku` javna bez provera | **rešeno** |
| S8 — odluka drugog korisnika otvara sesiju | **rešeno** |
| P2 — latch se otključava a ne zaključava | **rešeno** |
| P6b — `/health` curi tekst izuzetka | **rešeno** |
| B1/B2 — `SE-007` guši legitiman refund | **rešeno** |
| testovi koji mere CPython contextvars umesto prinude | **prepisani** |
| M2/M3/M7 — nepokrivene tvrdnje | **pokrivene** novim testovima |

**Recenzentova najoštrija primedba bila je tačna i vredi je ponoviti:** tri
postojeća testa koja je prva verzija oborila „sanirana" su tako što je u njih
upisan `_oznaci_odluku(...)` — dakle **usvajanjem zaobilaznice iz S3**. Zato je
S3 zatvoren tako da ta funkcija više ne može da posluži kao zaobilaznica:
token traži privatni ključ modula. Testovi je i dalje zovu, ali sada zovu
**jedini legitiman interni put**, a ne rupu.

---

# IZMENJENI FAJLOVI

**Produkcija (3):**
```
api.py                          _treba_refundirati, _refund_dugovan, /health dijagnostika
security/ai_forensics.py        merljivo stanje šeme, lepljiva degradacija, ERROR umesto debug
services/voice_orchestrator.py  token odluke, prinuda na dve granice, provera vlasnika
```

**Testovi (5):**
```
tests/test_beta_hardening_002.py         NOV, 11 testova + 1 skip
tests/test_beta_hardening_001.py         +10 (matrica prekida 1…99%)
tests/test_beta_gate_credit_second_order.py  leksički brojač → svojstvo
tests/test_sprint2_governance.py         2 testa usklađena sa novim ugovorom
tests/test_voice_realtime.py             1 test usklađen
```

**Migracije:** `NONE — verified no migration required.` Migracija `089` već
postoji kao fajl; kreiranje `090` „na slepo" bilo bi pogađanje bez pristupa
produkcionoj šemi, što mandat izričito zabranjuje.

---

# ODGOVORI NA JEDANAEST PITANJA

**1. Može li korisnik glasovnim WSS putem izvršiti AI operaciju bez governance odluke?**
**NE.** Prinuda stoji na dve granice; token može da nastane samo u kapiji;
odluka se proverava i po vlasniku. Sve tri mutacije obaraju testove.

**2. Može li dobiti gotovo kompletan odgovor pa refund prekidom veze?**
**NE.** Testirano na 1/25/50/75/90/98/99%, na pretposlednjem i poslednjem
komadu. Vraćanje ranjive semantike obara **12** testova.

**3. Može li retry proizvesti duplu naplatu ili duplu refundaciju?**
**NE za refundaciju** — svaka grana je pod `_refunded`, i mutacija to dokazuje.
**Za naplatu: nije potpuno dokazano** — `audit_log` nema ključ idempotencije,
pa dva identična zahteva daju dva reda. To je zatečeno, ne uvedeno.

**4. Znamo li dokazano da je provenance šema spremna u runtime-u?**
**NE.** Znamo da će se **saznati pri prvom upisu** i da to više ne može proći
tiho. Sam status je i dalje `UNKNOWN` bez pristupa bazi.

**5. Može li provenance tiho pasti na legacy trag?**
**NE.** Degradacija se pamti, lepljiva je, loguje se kao `ERROR` i vidi se na
`/health`.

**6. Padaju li svi novi kritični testovi kad se popravka revertuje?**
**DA** — 9 mutacija, svaka obara bar jedan test; najveća obara 12.

**7. Je li recenzent našao nešto što prvi prolaz nije video?**
**DA — šest stvari**, uključujući **dve regresije koje sam ja uveo**
(`/health` curenje i ugušen legitiman refund).

**8. Postoji li kritični `UNKNOWN`/`BYPASS`?**
**DA, jedan:** stanje migracije `089`.

**9. Bi li pustio advokata na WSS?**
**DA za kapiju** — sesija se ne može otvoriti bez governance odluke, i to je
mutaciono dokazano.
**NE za sadržaj** — sirov WSS i dalje ne prolazi kroz prompt guard ni response
firewall (to je transportno pitanje, ne kapija). Imenovano kao otvoreno.

**10. Bi li verovao naplati sa stvarnim kreditima?**
**DA.** Svi merljivi napadi na povraćaj su zatvoreni; ugovor je eksplicitan i
testiran nad pravim generatorom.

**11. Bi li provenance zapis koristio kao forenzički dokaz?**
**NE dok se `089` ne potvrdi.** Ali sada bar znamo kada nije upotrebljiv —
ranije nismo.

---

# OPEN RISKS

1. **Migracija `089` — status nepoznat.** Runtime to sada meri i glasno
   prijavljuje, ali potvrda traži pristup bazi (`SUPABASE_DB_URL`, dug od
   Black Swan sprinta).
2. **Sadržaj glasovne sesije ne prolazi kroz prompt guard ni response
   firewall.** Kapija je zatvorena; transport nije. Traži proxy sloj ili
   preseljenje na SDK realtime klijent — arhitektonska odluka.
3. **`audit_log` nema ključ idempotencije** — dva identična korisnička zahteva
   daju dva reda. Zatečeno.

Ništa drugo nije dodato na listu; spekulativne stavke nisu rizici.

---

# ČETRNAESTO PRAVILO

> **Kad popravka obori zatečeni test, provera nije „uskladi test" nego
> „da li sam upravo usvojio zaobilaznicu".**

Prva verzija ove popravke oborila je tri testa. Sanirao sam ih tako što sam u
njih upisao `_oznaci_odluku(...)` — a to je bila tačno ona rupa (`S3`) koju je
recenzent zatim izmerio kao bypass. Test je bio zelen, prinuda je bila fiktivna.

Ispravan redosled je obrnut: prvo dokazati da je izmena testa **jedini legitiman
put**, pa tek onda je upisati.
