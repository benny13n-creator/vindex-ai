# SECOND EYE REVIEW — BETA-HARDENING-002

**Nezavisni protivnički pregled.** Baseline `005ebcd4`. Predmet pregleda: necommitovane
izmene u radnom stablu.

**VERDIKT: RED.**

Nijedan fajl nije trajno izmenjen ovim pregledom osim ovog izveštaja. Sve mutacije su
rađene preko byte-egzaktnog backup/restore ciklusa sa SHA256 proverom posle svakog
pokretanja; završna provera je zelena za sva tri produkcijska fajla.

---

## 0. Šta je sprint stvarno dirao (i šta nije)

`git diff --stat 005ebcd4` na početku pregleda:

| fajl | linija | status |
|---|---|---|
| `services/voice_orchestrator.py` | +72 | BYPASS-7 |
| `security/ai_forensics.py` | +80 | GT-001 |
| `api.py` | +15 | GT-001 (`/health`) |
| `tests/test_beta_hardening_001.py` | +110 | P0-B matrica |
| `tests/test_beta_hardening_002.py` | nov, 237 | BYPASS-7 + GT-001 |

**Prvi nalaz je administrativan, ali bitan: BILLING nije diran u ovom sprintu.**
`api.py` je dobio isključivo `/health` izmenu. Sve što mandat pripisuje ovom sprintu kao
zatvaranje naplate (`_delivered` pre prvog `yield`, SE-005/006/007, FS-003) već je stajalo
u `005ebcd4`. Ovaj sprint je za naplatu dodao **dokaznu matricu**, ne popravku. To ne
umanjuje vrednost matrice — ali tvrdnja „sprint je zatvorio BILLING" je netačna po
konstrukciji, i dole je merena kao tvrdnja o zatečenom kodu.

### 0.1 Radno stablo se menjalo TOKOM pregleda

Na početku pregleda `tests/test_voice_realtime.py` i `tests/test_sprint2_governance.py`
nisu bili izmenjeni. Sredinom pregleda jesu (+13 i +9 linija). Izmerio sam obe verzije.
Detalji u §1.6 — to nije kozmetika nego suština nalaza o BYPASS-7.

---

## 1. WSS GOVERNANCE (BYPASS-7) — **NIJE ZATVORENO**

Kapija radi. Tačka prinude postoji i **jeste** poboljšanje. Ali tvrdnja iz komentara u kodu —

> „dodaje se samo mehanizam koji cini nemogucim da se ona PRESKOCI"
> „`_ODLUKA` postavlja iskljucivo `proveri_voice_dozvolu()`"

— je **merljivo netačna**. Obe rečenice su oborene, i to seam-ovima koje sprint sam pominje.

Sve sonde ispod voze produkcijske funkcije bez mreže (`websockets.connect` mockovan,
`OPENAI_API_KEY` lažan).

### 1.1 S1 — legitiman put RADI (kontrola)

`VoiceOrchestratorSession.start()` sa kapijom koja prolazi otvara vezu:
`upstream=FakeWS`, `websockets.connect pozvan=True`. **Voice nije pokvaren u produkciji.**
Ovo je važno reći jer §1.7 pokazuje da to nijedan test ne dokazuje.

### 1.2 S2 — injektovana fabrika ZAOBILAZI prinudu (mandat je tražio baš ovo)

```
VoiceOrchestratorSession(ws, user, openai_ws_factory=moja_fabrika)
→ self._connect = moja_fabrika        # _connect_openai_realtime NIJE na putanji
```

Izmereno: **veza otvorena = True, `odluka_doneta = False`.** Nijedan izuzetak.

Prinuda stoji unutar `_connect_openai_realtime`, a `__init__` dozvoljava da se ta funkcija
u celini **zameni**. Komentar u kodu izričito tvrdi da je „injektovana fabrika" bila deo
problema koji se zatvara. Nije zatvorena — ostala je netaknuta.

### 1.3 S3 — `_oznaci_odluku` je javna funkcija bez ijedne provere prava

```
vo._oznaci_odluku({"user_id": "napadac"}, "izmisljen-cid")
await vo._connect_openai_realtime()
```

Izmereno: **veza otvorena, `connect pozvan = True`**, bez ijednog dodira sa
`feature_registry`, tarifom ili kill-switch-om.

Odluka nije kriptografski ni strukturno vezana za kapiju — to je obična contextvar koju
svako može da postavi. „Postavlja je isključivo `proveri_voice_dozvolu()`" je **konvencija,
ne prinuda.**

### 1.4 S4 — pozadinski task nasleđuje odluku

Task napravljen POSLE odluke (`asyncio.create_task`) nasleđuje kontekst i sme da otvori
vezu: izmereno `connect pozvan = True`. Ovo je normalna semantika contextvar-a, ali je
relevantno jer `_uknjizi_voice_sesiju_provenance` **stvarno** koristi `shared.bg.spawn`
iz sesijskog konteksta — dakle nasleđivanje nije hipotetičko.

### 1.5 S5 / S8 — nekonzistentno i nevezano za korisnika

| sonda | rezultat |
|---|---|
| `asyncio.to_thread` | nasleđuje odluku (`True`) |
| `loop.run_in_executor` | NE nasleđuje (`False`) — fail-closed, ali nekonzistentno |
| **S8: odluka korisnika A → veza za korisnika B** | **veza otvorena** |

S8: kapija prođe za `korisnik_A`, zatim se u ISTOM toku otvori veza za `korisnik_B`.
`_connect_openai_realtime` proverava samo `is None` — **ne proverava kome odluka pripada**,
iako `_ODLUKA` nosi `user_id`. Trenutni ruter drži jednu vezu po tasku pa ovo danas nije
dohvatljivo, ali provera koja nosi identitet a ne koristi ga je poluzatvorena.

### 1.6 REGRESIJA: sprint je oborio 3 postojeća testa, pa ih „popravio" tako što je usvojio zaobilaznicu

Merenje na zatečenom stablu:

```
tests/test_voice_realtime.py::test_connect_openai_realtime_uses_bearer_auth_header      FAILED
tests/test_sprint2_governance.py::test_realtime_voice_refuses_to_run_under_eu_configuration  FAILED
tests/test_sprint2_governance.py::test_realtime_voice_still_connects_without_azure_configuration FAILED
```

Mutacija koja uklanja prinudu (`if _ODLUKA.get() is None:` → `if False:`) vraća sva tri u
zeleno (`53 passed`). Dakle uzrok je nedvosmisleno ovaj sprint.

Naročito boli druga dva:

- `..._refuses_to_run_under_eu_configuration` je jedini test koji dokazuje **S2-2 EU/data-residency
  odbijanje**. Nova provera je ubačena **iznad** Azure provere, pa poruka više ne pominje EU.
  Izmereno (S6): pod Azure konfiguracijom bez odluke dobija se `VoiceGovernanceBypass`,
  `poruka pominje EU = False`. **S2-2 poruka je zasenčena.**
- `..._still_connects_without_azure_configuration` je bio jedini test koji dokazuje da
  legitimna veza i dalje može da se otvori. Sprint ga je oborio.

Sredinom pregleda sprint je oba fajla izmenio. Popravka glasi:

```python
vo._oznaci_odluku({"user_id": "test"}, "cid-test")   # 3 nova poziva u testovima
```

To jest — **rešenje za pokvarene testove je bilo da se upotrebi baš zaobilaznica iz §1.3.**
Repo sada sadrži tri call-site-a koji fabrikuju governance odluku bez kapije. Posle toga je
suita zelena (`5250 passed, 2 skipped`), ali zelena zato što je merilo prilagođeno kodu.

### 1.7 Testovi BYPASS-7: dva od tri ne dokazuju ništa

Mutacije (produkcijska popravka revertovana → da li test pada?):

| mutacija | pada? | zaključak |
|---|---|---|
| M1 `if _ODLUKA.get() is None:` → `if False:` | **DA** (`test_bypass7_veza_bez_odluke_je_odbijena`) | valjan test |
| M2 kapija više ne zove `_oznaci_odluku` | **NE** — `59 passed` u celom voice skupu | **nepokriveno** |
| M3 kapija ne postavlja korelacioni kontekst | **NE** — `59 passed` | **nepokriveno** |

M2/M3 su ponovljeni i posle sprintovih izmena testova — i dalje preživljavaju.

**Posledica M2:** ne postoji nijedan test, nigde u repou, koji dokazuje da kapija označava
odluku. Ako se ta linija ikad izgubi, `_connect_openai_realtime` odbija **svaku** sesiju —
totalni ispad glasovnog modula uz potpuno zelenu suitu od 5250 testova. Fail-closed jeste,
ali neprimetno.

Jedini test koji bi pokrio M2 i M3 je `test_bypass7_kapija_postavlja_i_korelacioni_kontekst`
— i on je **SKIPPED** (`6 passed, 1 skipped`). Njegov `try/except → pytest.skip` znači da u
ovom okruženju ne izvršava nijednu tvrdnju.

`test_bypass7_odluka_iz_druge_sesije_se_ne_moze_pozajmiti` **prolazi iz pogrešnog razloga**:
ne dodiruje tačku prinude uopšte, nego zove `_oznaci_odluku` + `voice_odluka_doneta` i
proverava da `asyncio.create_task` ne curi kontekst unazad. To je svojstvo CPython-a, ne
Vindex-a. Komentar u samom testu priznaje da je prvobitna hipoteza oborena merenjem — ali
test je zadržan iako više ne meri ništa specifično za ovu popravku.

*(Pozitivno i mereno: curenje odluke IZMEĐU testova ne postoji — instrumentovao sam
`pytest_runtest_setup` preko svih voice fajlova, nijedan test ne ulazi sa zatečenom
odlukom. `asyncio.run`/anyio izoluju kontekst. Tvrdnja o task-lokalnosti u tom užem
smislu drži.)*

### 1.8 Šta BYPASS-7 zapravo jeste

Jedini produkcijski put do provajdera je `websockets.connect` na `voice_orchestrator.py:482`
(provereno grep-om; nema drugog `websockets.connect`, nema ephemeral-token/WebRTC rute).
Ruter je jedini pozivalac i ide kroz `start()` → kapija → connect. Danas dohvatljivog
zaobilaska **nema**.

Vrednost popravke je odbrana od BUDUĆEG pozivaoca. Ali budući pozivalac ima dva trivijalna
seam-a (§1.2, §1.3), a treći (§1.5) čini odluku nevezanom za korisnika. Zato: **poboljšanje
DA, „nemoguće preskočiti" NE.**

---

## 2. BILLING — **UGOVOR DRŽI PROTIV NAPADAČA, ALI NIJE ZATVOREN PROTIV KORISNIKA**

Sve sonde voze pravi `api.pitanje_stream` generator, sa brojačima umesto `UsageService`.

### 2.1 Napadačka strana: nijedan profitabilan put nije nađen

| sonda | rezultat |
|---|---|
| B4 pun odgovor + prekid veze | `naplata=1, refund=0` — FS-001 drži |
| P0-B matrica 1/25/50/75/90/98/99 % | svih 7 zeleno |
| prekid na pretposlednjem, 3 uzastopna puta | `naplata=3, refund=0` |
| B10 dvostruki `aclose()` | `refund=0` posle oba |
| B5 `balance()` puca posle refunda | jedan refund, jedan `[DONE]`, protokol čist |
| dvostruki `consume` | nije nađen put — `consume` je izvan generatora, jednom po zahtevu |

Mutacija M8 (vraćanje `_delivered = True` ispod petlje, tj. originalni NIGHT-005 kvar)
obara **12 testova**. Matrica je stvarna, ne dekorativna. M10/M11/M12 takođe obaraju
testove — SE-005, SE-006 i SOA-012 su pokriveni.

**Zaključak: besplatno korišćenje AI-ja nisam uspeo da reprodukujem.** To je najjači deo
celog paketa.

### 2.2 B1/B2 — `except Exception` GUTA legitiman refund koji je ranije radio

Mandat je pitao tačno ovo. Odgovor je DA.

`6fb4a99f` (pre SE-007), `api.py:3507`:
```python
if not _refunded:
    try: await UsageService.refund(...)
```
Danas:
```python
if not _refunded and not _delivered:
```

Scenario koji sam merio: rezultat je **legitimno refundabilan** (`from_cache=True`, ili
`status="error"`), komadi su isporučeni pa je `_delivered=True`, i onda **sam `refund()`
padne** (mrežna greška, Supabase timeout). Kontrola izleti u `except Exception`, gde
`_delivered=True` skreće u `elif _delivered:` — samo se loguje „bez refunda".

Izmereno:

| sonda | pokušaja refunda | ranije bi bilo | ishod za korisnika |
|---|---|---|---|
| B1 keš-pogodak, `refund()` puca | **1** | 2 | naplaćen za **kеširan** odgovor |
| B2 LLM greška, `refund()` puca | **1** | 2 | naplaćen za **neuspeo** poziv |

Kod `status="error"` je posebno ružno: poruka o grešci se strimuje kroz istu petlju, pa
diže `_delivered=True` — dakle **poruka „Došlo je do greške" se računa kao isporuka** i
time gasi ponovni pokušaj refunda.

Ovo je regresija iz `005ebcd4`, ne iz ovog sprinta — ali jeste živa i jeste unutar tvrdnje
koju mandat pripisuje sprintu („SE-007 zaštita"). Nijedan test je ne pokriva: mutacija M9
(uklanjanje `not _delivered`) obara 1 test, ali samo u smeru „ne refundiraj isporučeno";
smer „ponovi neuspeli refund" nema nijedan test.

### 2.3 B3 — klijent prekine PRE prvog čitanja: kredit nestaje

Ugovor sprinta glasi doslovno: **„0 komada → refund."** Merenje ga obara.

```
it = response.body_iterator
await it.aclose()          # klijent odustane pre prvog reada
→ naplata = 1, refund = 0, isporučeno 0 znakova
```

Uzrok: `consume()` je izvan generatora, a generator koji nikad nije startovao ne prima
`GeneratorExit` — `try:` blok se ne izvrši, pa ni `except BaseException` ne opali.
Realno se dešava kod brzog prekida kartice, HTTP/2 RST-a i LB timeout-a.

Novi test `test_p0b_nula_isporuceno_je_jedini_slucaj_refunda` **ovo ne hvata** jer prvo
pokrene generator (`ensure_future(it.__anext__())` pa `cancel`), pa meri već pokrenut tok.
Rupa je tačno u koraku pre toga.

Nije eksploatabilno (šteti korisniku, ne firmi), ali je **direktna protivrečnost objavljenom
ugovoru**.

### 2.4 Non-stream `/api/pitanje`

Ista rupa NE postoji — odgovor se gradi u celini pre slanja, `_treba_refundirati` se zove
jednom, `_credit_consumed=False` sprečava dupli refund u `except`. Predikat je zajednički
(FS-003) i mereno ne puca na `dict` (B8, SE-006 drži).

---

## 3. PROVENANCE (GT-001) — **NIJE ZATVORENO**

Teza sprinta: „stanje se MERI, ne pretpostavlja". Merenje je obara.

### 3.1 P2 — stanje šeme se MOŽE lažno prikazati kao potvrđeno *(mandat je pogodio)*

Mandat je pitao: „prvi upis prođe (True) pa sledeći padne — ostaje li True?" Ne, tu grana
radi ispravno. **Ali obrnuti smer briše dokaz.**

```
1. degradiran upis  → prosirena_sema=False, izgubljene_kolone=19, degradiranih=1
2. uspešan upis     → prosirena_sema=True,  izgubljene_kolone=0,
                      migracija_089_potvrdjena=True   ← /health sada TVRDI da je 089 primenjena
```

Redovi upisani u koraku 1 su i dalje u bazi, bez `correlation_id`/`predmet_id`/`status`.
`/health` više ne pokazuje nijedan trag toga osim brojača `degradiranih_upisa=1`, koji
nijedno polje ne dovodi u vezu sa `migracija_089_potvrdjena=True`.

Mešano stanje je dohvatljivo: **PostgREST kešira šemu** — posle pokretanja migracije 089
keš je neko vreme ustajao (`PGRST204`), pa upisi degradiraju, pa se keš osveži i stanje
skoči na `True`. Isto važi za rolling deploy i za delimično primenjenu migraciju.

`migracija_089_potvrdjena` je **latch koji se otključava, a nikad ne zaključava** — a to je
tačno ono svojstvo koje polje treba da ima da bi bilo upotrebljivo kao dokaz.

### 3.2 P3 — druga epizoda degradacije je potpuno nema

`_upozorenje_izdato` se postavlja jednom i **nikad ne vraća na False** (ni pri flipu na
`True`). Izmereno: posle flipa `False → True → False`, **5 uzastopnih degradiranih upisa
proizvelo je 0 ERROR logova**, dok je `degradiranih_upisa` narastao na 6.

Dakle „loguje se kao ERROR jednom po procesu" znači jednom po procesu **zauvek**, bez obzira
na to koliko različitih epizoda degradacije nastupi. Uz restart/skaliranje (mandat je i to
pitao) signal se dodatno gubi: stanje je procesno, a `/health` iza balansera pogađa
nasumičnog radnika — jedan može reći `None`, drugi `True`, treći `False`, za isti klaster.

### 3.3 P4 — `izgubljene_kolone` nije izmereno nego prepisano

`provenance_stanje_seme()` vraća `list(_KOLONE_089)` — celu statičku listu. Log poruka
računa presek sa stvarnim upisom (`set(_KOLONE_089) & set(safe.keys())`), ali `/health` ne.

Izmereno: prijavljeno **19** izgubljenih kolona za upis koji je stvarno nosio **5**.
Polje koje treba da bude merenje je konstanta.

### 3.4 P6b / P7 — NOVA površina za curenje na JAVNOM endpointu

`/health` je `@app.get("/health")` **bez ijedne autentikacije** (`inspect.signature` →
nema parametara, nema `Depends`). Sprint je na njega dodao:

```python
except Exception as _exc:
    return {"greska": str(_exc)[:120]}
```

Izmereno: izuzetak čiji tekst sadrži `postgres://user:pw@host/db` **izlazi kroz javni
`/health` neizmenjen**.

`str(exc)[:120]` nije sanitizacija — DSN-ovi, imena hostova, putanje i PostgREST poruke
staju u 120 znakova. Uz to, i normalan odgovor sada javno objavljuje da li je migracija
primenjena i koliko je upisa degradirano — to je posture-informacija koja ranije nije bila
javna.

### 3.5 P5 — svaki AI poziv na legacy bazi plaća dva round-tripa

Stanje se ne memoizuje: i posle utvrđene degradacije svaki naredni poziv ponovo šalje
osuđen širok upis. Izmereno: 4 insert pokušaja za 2 AI poziva. Zatečeno ponašanje, nije
uvedeno sada, ali GT-001 ga je učinio merljivim i nije ga zatvorio.

### 3.6 Testovi GT-001

| mutacija | pada? |
|---|---|
| M4 uspešan širok upis ne postavlja `True` | **DA** |
| M5 degradacija se ne meri | **DA** |
| M6 `/health` ne izlaže stanje | **DA** |
| M7 `logger.error` → `logger.debug` na potpunom neuspehu | **NE** — `83 passed` u 4 forensics suite-a |

M7 preživljava svuda. Tvrdnja „potpuni neuspeh je ERROR umesto `debug`" **nema nijedan test**.

Pozitivno: P1 je pokušaj lažne potvrde preko minimalnog poziva (bez 089 vrednosti) — **ne
prolazi**, jer `module_name`, `knowledge_sources` i `retrieved_context_ids` uvek uđu u
`safe`. Ta grana je čvrsta.

---

## 4. Testovi koji prolaze iz pogrešnog razloga — spisak

1. `test_bypass7_odluka_iz_druge_sesije_se_ne_moze_pozajmiti` — ne dodiruje tačku prinude;
   meri semantiku CPython contextvar-a.
2. `test_bypass7_kapija_postavlja_i_korelacioni_kontekst` — **SKIPPED**; nula tvrdnji.
   Jedini test koji bi pokrio M2 i M3.
3. `test_connect_openai_realtime_uses_bearer_auth_header` *(izmenjen u sprintu)* — sada sam
   fabrikuje odluku preko `_oznaci_odluku`; više ne prolazi kroz kapiju.
4. `test_realtime_voice_refuses_to_run_under_eu_configuration` *(izmenjen)* — isto.
5. `test_realtime_voice_still_connects_without_azure_configuration` *(izmenjen)* — isto;
   više ne dokazuje da legitiman tok može da se poveže, nego da zaobilaznica radi.

Nepokrivene tvrdnje (mutacija preživi, nijedan test ne padne): **M2** (kapija označava
odluku), **M3** (kapija postavlja korelaciju), **M7** (ERROR na potpunom neuspehu).

---

## 5. Regresije koje je sprint uveo

| # | regresija | dokaz |
|---|---|---|
| R1 | 3 postojeća testa oborena | mutacija M1 ih vraća u zeleno |
| R2 | S2-2 EU/residency poruka zasenčena novom proverom | S6: `poruka pominje EU = False` |
| R3 | zaobilaznica `_oznaci_odluku` institucionalizovana u 3 testa | `git diff` na dva test fajla |
| R4 | javno curenje teksta izuzetka na `/health` | P6b: `postgres://user:pw@host/db` izašao |
| R5 | `migracija_089_potvrdjena` može da pređe iz `False` u `True` i obriše dokaz | P2 |

Radno stablo je na kraju pregleda zeleno: **`5250 passed, 2 skipped`** (puna suita, 8m21s,
`-p no:randomly`). Zelenilo za R1 je postignuto izmenom testova, ne koda.

---

## 6. Verdikt — **RED**

Naplata je najjači deo i skoro da nosi sprint: napadački put nisam našao ni na jednom od
devet merenih preseka, a matrica stvarno umire kad se popravka revertuje. Da je paket bio
samo to, bilo bi YELLOW.

RED je zbog druge dve stavke:

1. **GT-001 sam sebe obara.** Cela svrha je bila „stanje se meri, ne pretpostavlja".
   Izmereno: stanje se može lažno prikazati kao potvrđeno (§3.1), druga epizoda degradacije
   je nevidljiva (§3.2), a `izgubljene_kolone` je konstanta a ne merenje (§3.3).
2. **Uvedeno je novo javno curenje.** `/health` je neautentikovan i sada vraća sirov tekst
   izuzetka (§3.4). To je jedina stavka u paketu koja pravi **novu** bezbednosnu površinu,
   i to na najizloženijem endpointu koji aplikacija ima.
3. **BYPASS-7 tvrdi više nego što isporučuje.** „Nemoguće preskočiti" oboreno je dvema
   sondama (§1.2, §1.3), a sprint je sopstvenu regresiju sanirao tako što je tu istu
   zaobilaznicu upisao u tri testa (§1.6). Uz to, kritična veza kapija→odluka nema
   **nijedan** test (§1.7) — sistem može tiho da ostane bez glasa, sa zelenom suitom.

### Šta bi verdikt pomerilo u YELLOW

- `/health` da ne vraća `str(_exc)`, nego samo booleanov indikator kvara dijagnostike.
- `migracija_089_potvrdjena` da bude lepljivo `False` (jednom degradirano = degradirano dok
  se proces ne restartuje), a `izgubljene_kolone` da bude ono što je stvarno mereno.
- `test_bypass7_kapija_postavlja_i_korelacioni_kontekst` da prestane da skipuje — tj. da
  mockuje `get_policy`/`_ensure_profile` i vozi kapiju do kraja. Time M2 i M3 dobijaju
  pokriće.
- `openai_ws_factory` seam da bude uklonjen ili da i sam prolazi kroz proveru odluke, a
  `_oznaci_odluku` da postane privatan po ugovoru (npr. da prima token koji izdaje samo
  kapija) — inače tri postojeća testa ostaju živ dokaz da zaobilaznica radi.
- Refund koji padne na legitimno refundabilnom rezultatu da se ponovi (§2.2), i
  `consume` da se pomeri unutar generatora ili da postoji kompenzacija za tok koji nikad
  nije startovao (§2.3).

---

### Metodološka napomena

Mutacije su izvođene skriptom sa byte-egzaktnim backup/restore i SHA256 verifikacijom posle
svakog ciklusa; završna provera sva tri produkcijska fajla je `OK`. Sonde ne rekonstruišu
logiku — voze `proveri_voice_dozvolu`, `_connect_openai_realtime`,
`VoiceOrchestratorSession.start`, `api.pitanje_stream`, `log_provenance_from_wrapper`,
`provenance_stanje_seme` i `api.health` direktno. Nijedan poziv nije otišao na stvarni
OpenAI, Pinecone ni Supabase. `F2-001` i 13 odloženih helpera nisu dirani.
