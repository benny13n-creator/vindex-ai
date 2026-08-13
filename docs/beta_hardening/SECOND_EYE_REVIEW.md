# SECOND EYE REVIEW — nezavisni protivnički pregled sprinta BETA-HARDENING-001

**Agent:** AGENT 5 (nezavisni pregled)
**Datum:** 2026-08-13
**Baseline:** `6fb4a99f` (= `HEAD`; sprint živi kao NEKOMITOVANE izmene radnog stabla)
**Predmet pregleda:** `api.py`, `shared/ai_client.py`, `services/voice_orchestrator.py`,
`tests/test_beta_hardening_001.py`, + tri izmenjena zatečena testa
**Metod:** merenje i mutaciono testiranje produkcijskog koda. Nijedan produkcijski
fajl nije trajno izmenjen — svaka mutacija je vraćena iz backup-a i potvrđena
`git diff --stat` (168 insertions / 20 deletions, identično stanju pre pregleda).
Nijedan test nije gađao stvarni OpenAI/Pinecone/Supabase.

---

## 0. VERDIKT

# 🔴 RED

**FS-001 — nalaz koji je sprint sam označio kao KRITIČAN i oko koga je izgradio
celu naraciju — NIJE zatvoren.** Popravka je pomerila granicu eksploatacije za
tačno 80 karaktera. Napadač koji prekine vezu jedan komad ranije i dalje dobija
pun AI odgovor besplatno.

Pogoršavajuća okolnost: **poslednjih 80 karaktera svakog odgovora je uvek rep
`DISCLAIMER`-a** (`main.py:2336`, 265 karaktera, dodaje se na SVAKI odgovor —
`main.py:1101, 1158, 3147, 3158, 3169`). Napadač koji žrtvuje poslednji komad
ne gubi **nijedan karakter pravnog sadržaja**. Cena zaobilaženja popravke je nula.

---

## 1. DA LI JE IJEDAN OD ČETIRI NALAZA NEZATVOREN

| Nalaz | Zatvoren? | Dokaz |
|---|---|---|
| **FS-001** | ❌ **NE** | Prekid na PRETPOSLEDNJEM komadu → refund. Izmereno: 320/392 (81 %), 3920/4000 (98 %), 80/81 karaktera isporučeno, `refund` pozvan 1× u sva tri slučaja. |
| **FS-002** | ⚠️ **DELIMIČNO — sa NOVIM lažnim tragom** | Terminalni status radi za slučaj koji test meri, ali sesija koja je isporučila transkript i rezultat alata bez ijedne `response.audio.delta` sada se beleži kao `error`. Lažni USPEH je zamenjen lažnom GREŠKOM. Ožičenje brojača nema nijedan test. |
| **FS-003** | ⚠️ **DELIMIČNO** | Predikat je ispravan i deljen. Ali simptom koji FS-003 opisuje („prazan ekran koji izgleda kao uredno završen odgovor") ostaje živ za odgovor od BELINA — kredit se vrati, korisnik i dalje vidi prazan ekran i uredan `[DONE]`. |
| **FS-004** | ⚠️ **KOD JESTE ISPRAVAN, DOKAZ NE POSTOJI** | Redosled u kodu je tačan. Ali mutacija koja vraća TAČNO stari kvar u OBE grane prolazi kroz **408 testova bez ijednog pada**. Nula ponašajne zaštite. |

---

## 2. NALAZI

### SE-001 — KRITIČNO — FS-001 je pomeren za 80 karaktera, nije zatvoren

**Tvrdnja sprinta** (`api.py:3520-3521`):
> „Zastavica se zato podiže PRE poslednjeg `yield`: u trenutku kad poslednji
> komad pređe u transport, odgovor je napustio server."

**Šta je stvarno zaštićeno:** samo klijent koji pročita **sve** komade pa prekine.
Klijent koji prekine posle **pretposlednjeg** komada zatiče `_delivered = False`
(jer se postavlja tek kad `_idx == _poslednji`), pa `except BaseException`
refundira kredit.

**Merenje** (pravi `api.pitanje_stream` generator, prekid posle `N-1` komada):

| Dužina odgovora | Komada | Primljeno | % | `consume` | `refund` |
|---|---|---|---|---|---|
| 392 znaka | 5 | 320 znakova | **81 %** | 1 | **1** |
| 4000 znakova | 50 | 3920 znakova | **98 %** | 1 | **1** |
| 81 znak | 2 | 80 znakova | **99 %** | 1 | **1** |

Neto cena AI odgovora: **0 kredita**. Ponovljivo do granice `10/minute`;
`UsageService.refund` nema gornju granicu ni vezu sa naplatom.

**Zašto je gubitak od 80 karaktera beznačajan:** `DISCLAIMER` (265 znakova) se
dodaje na kraj svakog odgovora. Poslednji 80-karakterni komad je uvek rep
pravne napomene („...Pre donošenja bilo kakvih pravnih odluka, obratite se
stručnjaku."). Napadač gubi boilerplate, zadržava 100 % pravnog sadržaja.

**Reprodukcija:**
```python
# odgovor = "Z"*4000; potrosi tacno 49 od 50 komada, pa `break` + `aclose()`
# -> refund pozvan 1x, primljeno 3920/4000 znakova
```

**Zaključak:** kvar je istog roda i iste ozbiljnosti kao pre sprinta. Popravka
menja cenu eksploatacije sa „0 karaktera" na „80 karaktera boilerplate-a".

---

### SE-002 — VISOKO — FS-004 nema NIJEDAN ponašajni test; sprint je reprodukovao sopstveni nalaz FS-014

Sprint je u `FAILURE_STREAMING_MATRIX.md` sam formulisao **FS-014 — „testovi koji
čuvaju ove putanje ne izvršavaju ih"**, i u zaglavlju `test_beta_hardening_001.py`
napisao: *„Zato se ovde ništa ne čita iz izvora."* Za FS-004 se čita isključivo
iz izvora.

**Mutacija 4** — vraćen TAČNO originalni kvar u obe grane
(`shared/ai_client.py`, sync + async):
```python
except Exception as _exc_fw:
    _capture_chat_provenance(self, kwargs, response, _ms)   # bez error= -> status="success"
    raise
```
Ovim odbijen odgovor ponovo dobija `ai_forensics.status = "success"` — doslovno
ono što FS-004 opisuje. Rezultat:

```
408 passed, 4812 deselected, 14 warnings in 43.06s
```

**Nijedan test nije pao.** Testovi prolaze jer proveravaju samo redoslede niski
(`_telo.index(...) < _telo.index(...)`), a mutacija taj redosled ne dira.

**Mutacija 3** — firewall potpuno progutan (`_provereno = response` umesto
`raise`), tj. sirov, neproveren OpenAI odgovor ide pozivaocu:
- `tests/test_beta_hardening_001.py` + `tests/test_gov2_runtime_interception.py`:
  **21 passed** — sprintovi testovi ne primećuju ništa.
- Uhvaćeno tek ZATEČENIM testovima: `test_gov3_response_firewall.py` (4 pada) i
  `test_rc_beta_flows.py::test_e3_firewall_ne_pusta_pokvaren_odgovor_i_ne_naplacuje_ga`.

**Uzrok:** `test_fs004_blokiran_odgovor_se_belezi_kao_greska` (linija ~283) ne
zove produkcijski kod. On **prepisuje granu unutar samog testa**:
```python
def _guarded(response):          # <- lokalna kopija, ne `_guarded_create`
    ...
```
Test bi prošao i da `shared/ai_client.py` uopšte nije menjan. Docstring tvrdi
„Mutaciona provera nad ponašanjem, ne nad izvorom" — to je netačno.

---

### SE-003 — VISOKO — FS-002: ožičenje brojača nema nijedan test

**Mutacija 5** — uklonjen jedini upis koji povezuje stvarnost sa statusom:
```python
# services/voice_orchestrator.py, handle_upstream_event
- self._isporucenih_delti += 1
+ pass
```
Posledica u produkciji: **svaka** glasovna sesija bi se beležila kao `error`.
Rezultat: `91 passed, 5129 deselected` — nijedan pad.

Razlog: `test_fs002_terminalni_status_prati_stvarnu_isporuku` gradi objekat sa
`VoiceOrchestratorSession.__new__(...)`, zaobilazi `__init__` i **ručno postavlja**
`_isporucenih_delti`. Testira se aritmetika `> 0`, ne ožičenje. Isto važi i za
`__init__` — da atributi nisu inicijalizovani, test bi i dalje prošao.

---

### SE-004 — VISOKO — FS-002 uvodi NOVI lažni trag: lažna GREŠKA umesto lažnog USPEHA

`_isporucenih_delti` broji **isključivo** događaje `response.audio.delta`.
Sve ostalo što ide browseru (`response.audio_transcript.delta`, `response.done`,
`vindex.confirmation_required`, rezultati alata, `vindex.error`) prolazi kroz
`self.client_ws.send_json(event)` **bez uvećanja brojača**
(`services/voice_orchestrator.py:287-297`).

**Merenje:** sesija koja je browseru isporučila 2 poruke (transkript odgovora +
`response.done`), bez ijedne audio delte:
```
[E3] browseru poslato 2 poruka; provenance upisi=['error']
```
Sesija u kojoj je advokat dobio pun tekstualni odgovor i izvršen alat beleži se
kao **neuspeh**. Za privilegovan razgovor to je jedini forenzički trag koji
postoji — i sada je netačan u suprotnom smeru.

**Drugi slučaj:** napuštena sesija (mikrofon otvoren, ništa izgovoreno, zatvoren):
```
[E4] napustena sesija -> provenance=['error']
```
Svaka napuštena sesija sada upisuje `error` red. Migracija `043` ima parcijalni
indeks `idx_ai_forensics_status ... WHERE status = 'error'` — taj indeks i svaka
buduća stopa grešaka izvedena iz `ai_forensics` biće naduvani napuštenim sesijama.
(Danas nijedan Python potrošač ne filtrira po `status='error'` — proveren ceo
`routers/`, `services/`, `scripts/`, `shared/`, `security/` — pa je posledica
kvalitet podataka, ne lažni alarm.)

**Ocena:** FS-002 je zamenio jednu netačnost drugom. Tvrdnja „terminalni status
po STVARNOM ishodu" ne stoji — meri se jedan kanal isporuke, ne ishod sesije.

---

### SE-005 — SREDNJE — FS-003 je zatvorio predikat, ne simptom

FS-003 je opisan kao: *„prazan ekran koji izgleda kao uredno završen odgovor"*.
Popravka pokriva samo `data == ""`. Za odgovor od belina:

```
[E1] sirovo=['data:    \n  \n\n', 'data: [DONE]\n\n', 'data: [CREDITS:10]\n\n'] refund=1
```
Kredit se vrati (predikat radi), ali korisnik dobija **prazan ekran + uredan
`[DONE]`**, bez poruke „Sistem nije vratio odgovor" — jer se ta poruka emituje
samo u grani `if not _delovi`, a `"   "` proizvodi jedan komad.

Isto na non-stream putanji:
```
[E2] normalizuj_rezultat({"status":"success","data":"   "}) -> {'odgovor': '   '}
     `not resp.get("odgovor")` = False   -> fallback poruka NE opali
```
`api.py:3364` (`if not resp.get("odgovor")`) ne hvata beline.

---

### SE-006 — SREDNJE — `_treba_refundirati` je NOVA površina za pad

Stari uslov je koristio isključivo `.get()` poređenja i nije mogao da baci.
Novi predikat zove `.strip()`:
```python
if rezultat.get("status") == "success" and not (rezultat.get("data") or "").strip():
```

**Izmereno:**

| `data` | Ishod |
|---|---|
| `["a","b"]` | ❌ `AttributeError: 'list' object has no attribute 'strip'` |
| `{"k":"v"}` | ❌ `AttributeError: 'dict' object has no attribute 'strip'` |
| `42` | ❌ `AttributeError: 'int' object has no attribute 'strip'` |
| `0` | ✓ `True` |
| `None` | ✓ `True` |
| `b"bajtovi"` | ✓ `False` |
| ključ odsutan | ✓ `True` |

`ask_agent` danas uvek vraća `str`, pa je rupa latentna. Ali predikat je
namerno nazvan generički i proglašen „kanonskim", a `main.py::ask_analiza_v2`
(`main.py:4230`) vraća `{"status": "success", "data": <dict>}`. Prvo ponovno
korišćenje predikata na tom obliku obara zahtev.

Na non-stream putanji posledica bi bila: `AttributeError` unutar `try` →
`except Exception` → `_credit_consumed` je još `True` (postavlja se na `False`
tek POSLE bloka refundacije) → refund + HTTP 500, umesto isporučenog odgovora.

**Ispravno bi bilo:** `str(rezultat.get("data") or "").strip()` ili eksplicitna
`isinstance` provera.

---

### SE-007 — SREDNJE — isti kvar preživljava u sestrinskom rukovaocu

Zaštita `not _delivered` postoji **samo** u `except BaseException`.
`except Exception` (`api.py:3553`) i dalje refundira bezuslovno:
```python
if not _refunded:
    await UsageService.refund(...)
```

**Merenje** (izuzetak nastupa POSLE isporuke svih komada):
```
[D1] isporuceno=437/400 znakova, refund=1
[D1] poslednji komadi: ['data: [DONE]', 'data: Došlo je do greške. Pokušajte ponovo.', 'data: [DONE]']
```
Pun odgovor isporučen → kredit vraćen → korisnik uz to dobija **dva `[DONE]`** i
poruku o grešci POSLE odgovora, bez `[CREDITS:]` (to je zatečeni FS-008).

Prozor između `_delivered = True` i kraja generatora je uzak (dva `yield`-a,
`_treba_refundirati`, `max(preostalo, 0)`), pa je okidač u današnjoj produkciji
uzak — ali to je isti rod kvara koji je sprint proglasio zatvorenim, u susednom
rukovaocu, netaknut.

---

### SE-008 — NISKO — kompromis koji nije imenovan: SOA-012 je sužen za kratke odgovore

Za odgovor `≤ 80` znakova postoji tačno jedan komad, pa je `_idx == _poslednji`
već u prvoj iteraciji: `_delivered = True` se postavlja **pre nego što ijedan bajt
može da dođe do transporta**. Ako veza pukne u tom trenutku, korisnik plaća
odgovor koji nikad nije video. Pre sprinta bi tu opalio refund iz SOA-012.

Izmereno: `[A3]` 29 znakova → `refund=0`; `[A4]` tačno 80 znakova → `refund=0`.

Kompromis je verovatno prihvatljiv (pravni RAG odgovori su reda 400-4000 znakova
uz obavezni 265-znakovni `DISCLAIMER`, pa je jednokomadni odgovor praktično
nemoguć), ali nigde nije imenovan — komentar u kodu tvrdi da je zastavica
sinonim za „odgovor je napustio server", što za jedan komad nije tačno.

---

### SE-009 — KONTEKST — cela FS-001 putanja nema prvostranog potrošača

`grep -rn "api/pitanje" --include=*.js --include=*.html` daje isključivo
`/api/pitanje` (`static/vindex.js:7619`, `:10712`). **Nijedan klijent aplikacije
ne zove `/api/pitanje/stream`.** Endpoint je autentifikovan i ograničen na
`10/minute`, ali dostupan svakom ulogovanom korisniku sa skriptom.

To NE zatvara SE-001 (zloupotreba ostaje trivijalna), ali menja profil:
slučajno okidanje kroz UI je nemoguće; namerna zloupotreba je jednako laka kao
pre. Sprint je ovo tačno naveo u matrici (linija 53) — beležim radi potpunosti
ocene rizika.

---

### SE-010 — NISKO — paritet je uspostavljen u USLOVU, ne u POSLEDICI

Sprint tvrdi: „obe putanje dele JEDAN uslov". Uslov jeste deljen. Posledica nije:

| | non-stream `/api/pitanje` | stream `/api/pitanje/stream` |
|---|---|---|
| uslov | `_treba_refundirati(rezultat)` | `_treba_refundirati(rezultat)` |
| prikazani saldo posle refunda | `preostalo = preostalo + 1` | `await UsageService.balance(...)` |

`preostalo + 1` je tačno ono što je SOA-016 imenovao kao netačno za svaku
funkciju skuplju od 1 kredita, i popravio — ali samo na stream putanji.
Sprint koji je otvorio obe funkcije radi ujednačavanja ostavio je neujednačenost
jedan red niže.

---

## 3. DA LI JE IJEDNA POPRAVKA UVELA NOV KVAR (REGRESIJU)

| Popravka | Nova regresija? |
|---|---|
| FS-001 | ⚠️ **Da, uska** — SE-008: za odgovore `≤ 80` znakova legitiman SOA-012 refund je izgubljen. |
| FS-002 | ⚠️ **Da** — SE-004: sesija bez audio delti ali sa isporučenim transkriptom/alatom sada je lažno `error`; napuštena sesija upisuje `error` red. |
| FS-003 | ⚠️ **Latentno** — SE-006: nova `AttributeError` površina na ne-`str` `data`. |
| FS-004 | ✅ **Ne.** |

**Provereno i NEGATIVNO (nema kvara):**

- **Dvostruka naplata na normalnom putu:** NE. Izmereno `consume=1, refund=0`,
  pun odgovor, uredan `[DONE]` + `[CREDITS]`.
- **Dvostruki upis provenance-a (FS-004):** NE. Po jedan `_capture_chat_provenance`
  u svakoj grani, uzajamno isključive.
- **Izuzetak iz `_capture_chat_provenance` guta pravi izuzetak firewall-a:** NE.
  Funkcija je fail-soft — ceo blok je u `try/except Exception`
  (`shared/ai_client.py:478`), nikad ne baca. Firewall izuzetak se uredno
  re-raise-uje.
- **`_ms` merenje:** NE, netaknuto. I stara i nova verzija računaju deltu PRE
  `_enforce_response`; semantika latencije je identična.
- **`close()` pre `start()` (FS-002):** NE `AttributeError` — oba atributa se
  postavljaju u `__init__` (`:199-200`). Dodatno, `routers/voice_realtime.py`
  radi `return` pre `finally` bloka kad `start()` padne, pa se `close()` u tom
  slučaju i ne poziva.
- **Dvostruko zatvaranje (FS-002):** NE. `_provenance_zatvoren` čuva; izmereno
  `close()` × 2 → tačno 1 upis.
- **Puna regresija:** `pytest tests/ -q -p no:randomly` →
  **`5219 passed, 1 skipped`** (8 min 31 s). Nijedan pad.

---

## 4. TESTOVI KOJI PROLAZE IZ POGREŠNOG RAZLOGA

| Test | Problem | Dokaz |
|---|---|---|
| `test_fs004_blokiran_odgovor_se_belezi_kao_greska` | **Prepisuje granu u samom testu** (`def _guarded(response)`) umesto da zove `_guarded_create`. Prolazi i kad je produkcijski kod potpuno vraćen. | Mutacija 2 (pun revert `ai_client.py`) → ovaj test prolazi. |
| `test_fs004_provenance_se_upisuje_tek_posle_firewall_provere` | Poređenje indeksa niski u izvoru — tačno anti-obrazac koji zaglavlje fajla osuđuje. | Mutacija 4 (originalni kvar vraćen, redosled niski očuvan) → prolazi. |
| `test_fs002_start_ne_belezi_uspeh` | Čista provera prisustva niske `'...status="started")' in src`. Ne izvršava `start()`. | Po konstrukciji. |
| `test_fs002_terminalni_status_prati_stvarnu_isporuku` | `__new__` zaobilazi `__init__`, brojač se postavlja ručno. Ne dokazuje da produkcija ikad uveća brojač. | Mutacija 5 (uklonjen `+= 1`) → 91 test prolazi. |
| `test_fs003_predikat_je_zajednicki_za_obe_putanje` | Meri `src.count(...)` + direktne pozive predikata. **Non-stream putanja `/api/pitanje` se ne izvršava ni u jednom testu ovog fajla.** | Nema `pokreni`-driven testa za `api.pitanje`. |
| `test_gov2 ... test_e_izlazni_sloj_je_ozicen_na_kanonsku_tacku` (izmenjen) | I dalje potpuno leksičan. | Mutacija 3 (firewall progutan) → prolazi. |

**Testovi koji MERE ono što tvrde (pozitivno):**
`test_fs001_pun_odgovor_pa_prekid_ne_vraca_kredit` (Mutacija 1 → pada, tačno),
`test_fs001_uredan_zavrsetak_takodje_naplacuje`,
`test_fs001_prekid_pre_prvog_komada_i_dalje_vraca_kredit`,
`test_fs003_prazan_odgovor_vraca_kredit_i_javlja_korisniku`,
`test_fs002_dvostruko_zatvaranje_ne_pise_dva_reda`.

**Nijedan test u fajlu ne pokriva prekid na pretposlednjem komadu (SE-001).**
Test `_pokreni_stream` je konstruisan tako da prekida TEK po prijemu svih
`ceil(len/80)` komada — dakle tačno na jedinom mestu koje je popravka pokrila.

---

## 5. DA LI SU TRI ZATEČENA TESTA OSLABLJENA

**NE. Sva tri su pojačana ili neutralna.**

| Test | Pre | Posle | Ocena |
|---|---|---|---|
| `test_commit4_p0.py::test_t2_stream_generator_refunds_on_no_deduct_branch` | `"from_cache" in body and "blocked" in body` | provera niske predikata **+ 3 IZVRŠENE tvrdnje** nad `api._treba_refundirati`, uključujući negativnu kontrolu (`svež odgovor NE sme biti refundiran`) | ✅ **pojačan** |
| `test_lambda008_certification.py::test_pitanje_refund_condition_includes_error_status` | dve provere niske `'rezultat.get("status") == "error"'` | dve provere niske **+ izvršena tvrdnja** `api._treba_refundirati({"status":"error"}) is True` | ✅ **pojačan** |
| `test_gov2_runtime_interception.py::test_e_izlazni_sloj_je_ozicen_na_kanonsku_tacku` | `izvor.count("return _enforce_response(kwargs, response)") == 2` | po-wrapper provera tela + provera redosleda | ↔️ **neutralno** (leksičan i pre i posle; hvata pun revert, ne hvata semantički kvar — v. SE-002) |

Nijedan test nije izgubio tvrdnju koju je imao. Izvorni kvar koji su čuvali i
dalje se hvata: verifikovano Mutacijom 1 (`test_commit4_p0` i `test_lambda008`
ostaju zeleni jer njihov kvar nije mutiran) i Mutacijom 2 (`test_gov2` pada,
tačno).

---

## 6. NALAZI KOJE SU PRETHODNI AGENTI PROPUSTILI

1. **SE-001** — prekid na pretposlednjem komadu. Ceo sprint je merio jednu tačku
   (poslednji komad) i zaključio da je klasa kvarova zatvorena. Nijedan raniji
   agent nije parametrizovao tačku prekida.
2. **SE-004** — brojač delti meri jedan kanal isporuke, ne ishod sesije;
   transkript i rezultati alata se ne broje.
3. **SE-006** — `.strip()` uvodi novu klasu pada u „kanonski" predikat.
4. **SE-007** — `except Exception` nema zaštitu `not _delivered`; ista klasa
   kvara preživljava u sestrinskom rukovaocu.
5. **SE-005** — FS-003 pokriva `""`, ne pokriva `"   "` — ni na jednoj putanji.
6. **SE-010** — `preostalo + 1` vs `UsageService.balance()`: SOA-016 popravljen
   samo na jednoj putanji, a sprint je otvorio obe radi ujednačavanja.
7. **SE-002/SE-003** — sprint je formalno imenovao FS-014 („testovi ne izvršavaju
   putanje koje čuvaju") i reprodukovao ga u polovini sopstvenog test-fajla.

---

## 7. ŠTA TREBA DA SE URADI PRE ZATVARANJA

**P0 (blokira zatvaranje):**
1. **SE-001** — zastavica isporuke ne sme da bude vezana za indeks komada. Ispravno
   je da `except BaseException` refundira samo ako je isporučeno **0** komada
   (npr. brojač `_poslato_komada`, refund iff `== 0`), ili da se zastavica podigne
   pri prvom komadu. Trenutna semantika („poslednji komad") je proizvoljna granica
   koju napadač bira.
2. **SE-001-test** — parametrizovati tačku prekida (`1 .. N`) i tvrditi da za svako
   `k >= 1` nema refunda.

**P1:**
3. **SE-004** — brojati SVE što je poslato browseru, ili razdvojiti
   `status="empty"` od `status="error"`; napuštena sesija nije greška.
4. **SE-002/SE-003** — zameniti leksičke provere izvršavanjem: pozvati
   `_guarded_create` sa lažnim `_orig_create` i `_enforce_response` koji baca, pa
   tvrditi `status` upisa; pozvati `handle_upstream_event` pa `close()`.
5. **SE-006** — `str(... or "").strip()`.
6. **SE-007** — dodati `and not _delivered` i u `except Exception`.

**P2:**
7. **SE-005**, **SE-010**, **SE-008** (imenovati kompromis u komentaru).

---

## 8. GRANICE OVOG PREGLEDA

- Sve merenje je na Python nivou (`body_iterator` generatora), sa lažnim
  `UsageService`. Ponašanje pravog Starlette/uvicorn transporta pod prekidom
  socket-a nije mereno — ali `GeneratorExit` semantika koju testovi voze je ista
  koju Starlette koristi (`aclose()`).
- Nijedan poziv nije išao ka stvarnom OpenAI/Pinecone/Supabase.
- `F2-001` i 13 odloženih helpera iz `DEADCODE_FORENSICS.md` nisu dirani ni
  pregledani.
- Nalazi `FS-005` … `FS-014` iz matrice nisu bili u opsegu sprinta i ostaju
  otvoreni; potvrđeno usput da je **FS-008** i dalje živ (`[D1]`: putanja greške
  šalje `[DONE]` bez `[CREDITS:]`).
- Produkcijski fajlovi su vraćeni u stanje pre pregleda; potvrđeno
  `git diff --stat` = `168 insertions(+), 20 deletions(-)` i odsustvom markera
  `MUTACIJA-AGENT5` u `git diff`.
