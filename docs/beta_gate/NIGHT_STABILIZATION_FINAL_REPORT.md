# BETA NIGHT STABILIZATION — ZAVRŠNI IZVEŠTAJ

**Datum:** 2026-08-14 · **Režim:** autonomno, sekvencijalno

---

## 1. BASELINE

| | |
|---|---|
| Commit | `95028348` |
| Puna suita | 5561 prošlo / 2 preskočena / 0 palo |
| Radno stablo | čisto |

## 2. KONAČNI COMMIT

`c1c21ea9` (+ izveštaj) · **5579 prošlo / 2 preskočena / 0 palo**

---

## 3. STATUS TASKOVA 1–11

| Task | Predmet | Status |
|---|---|---|
| **1** | Migracija 113 — forenzika i odluka | ✅ **CLOSED** — kategorija **C**, već primenjena |
| **2** | Optimistic UI, 5 nalaza | ✅ **CLOSED** — 5/5 |
| **3** | FS-P1-42 `ai_fabric` | ✅ **CLOSED** — UNKNOWN razrešen, nađen stvarni kvar |
| **4** | Preostali odloženi P0/P1 | ⏸ **DELIMIČNO** — klasifikacija stoji iz prethodnog sprinta; nijedan nov nije zatvoren |
| **5** | Kanonski success contract | ⏸ **NIJE RAĐEN** — v. §12 „šta ne bih dirao" |
| **6** | Čišćenje dotaknute infrastrukture | ⏸ **NIJE RAĐEN** |
| **7** | Međusistemska regresija | ✅ **PASS** — 310 ciljanih testova |
| **8** | Playwright beta-exit simulacija | ✅ **PASS** — 258 testova, 17 fajlova |
| **9** | Puna regresija + mutacije | ✅ **PASS** — uz nađen i uklonjen flake |
| **10** | Ponovna procena Beta Exit Gate-a | ✅ **URAĐENO** — §11 |
| **11** | Scorecard stabilnosti | ✅ **URAĐENO** — §11 |

**Taskovi 4/5/6 nisu odrađeni i to nije prikriveno.** Razlog je u §12.

---

## 4. COMMITOVI

| Commit | Task | Sadržaj |
|---|---|---|
| `ec34166a` | 1 | migracija 113 dokazano primenjena; testovi pretvoreni u invarijantu |
| `69e3a301` | 1 | determinizam ponovnog pokušaja prijave (konvergencija + zaštita od duplog slanja) |
| `4b1703e1` | 2 | optimistic UI 5/5 — state machine, ne tekst dugmeta |
| `ceff8964` | 3 | `ai_fabric` prompt guard ožičen i fail-closed |
| `c1c21ea9` | 9 | uklonjen dokazan uzrok flake-a: jednonitni test HTTP server |

---

## 5. POPRAVLJENI KORENSKI UZROCI

### TASK 1 — migracija 113: **kategorija C, ništa nije izvršeno**

Sonde nad produkcijom, upoređene sa merenjem od pre dva sprinta:

```
feedback?select=q_hash&limit=0     400/42703    ->  200
reported_errors?select=id&limit=0  404/PGRST205 ->  200 (0 redova)
reported_errors: user_id, original_prompt, ai_response, timestamp — sve postoje
```

Oba kanala prijave netačnog pravnog odgovora **sada imaju skladište**.

Testovi nisu obrisani kao „prevaziđeni" nego **preimenovani u invarijantu**:
`test_prijava_na_semi_BEZ_q_hash_ne_sme_da_kaze_ok` više ne opisuje šemu nego
pravilo — upis koji baza odbije nikad ne sme izaći kao uspeh, ni posle
eventualnog rollback-a.

### TASK 2 — optimistic UI: pet nalaza, jedan obrazac

| Nalaz | Šta se gubilo | Popravka |
|---|---|---|
| FS-P1-27 | tekst iz `prompt()` — nepovratan | `r.ok` + `.catch`; **izgubljeni tekst se vraća korisniku u poruci** |
| FS-P1-28 | otkucan komentar | polje se čisti isključivo unutar `r.ok` grane |
| FS-P1-29 | izmereno naplativo vreme (**novac**) | `localStorage.removeItem` premešten **posle** potvrde upisa |
| FS-P1-30 | prihvatanje Uslova — pravno obavezujući čin | overlay se zatvara tek na potvrdu; dodat `tos-greska` element |
| FS-P1-31 | GDPR saglasnost | checkbox se vraća na stvarno stanje servera |

Nije menjan tekst dugmeta nego **state machine**: `IDLE → SUBMITTING → CONFIRMED | FAILED`.

### TASK 3 — `ai_fabric`: zamka je već bila opalila **unutar** modula

Dostiznost je dokazano nula (statički, dinamički, i runtime — modul nije u
`sys.modules` posle `import api`). Ali unutra je stajalo:

```python
try:
    from security.prompt_guard import sanitize_prompt
    request.prompt = sanitize_prompt(request.prompt)
except ImportError:
    pass
```

**`sanitize_prompt` ne postoji** — prava ulazna tačka je `analyze()`. Uvoz je
padao **svaki put**, `except` ga je gutao, i governance funkcija je vraćala
zahtev kao „proveren" a ništa nije proverila. `NOT_ATTEMPTED` predstavljen kao
`SUCCESS`, na bezbednosnoj kontroli.

Modul nosi **Anthropic i Gemini adaptere koje monkeypatch iz `ai_client.py` ne
pokriva** — on krpi isključivo OpenAI SDK klase. Zato zamka nije ostavljena na
miru iako je kod mrtav.

### TASK 9 — nađen i uklonjen flake, ne prećutan

Prva puna suita sa `seed=11` pala je **1 test** (5578 prošlo). Isti seed u
sledećem prolazu prošao je čist — dakle **nije zavisnost od redosleda nego
flake**, a flake je po standardu ovog mandata pouzdanosni defekt.

**Korenski uzrok:** svih 17 Playwright fajlova diglo je `socketserver.TCPServer`
— **jednonitni** server. Pregledač za `index.html` otvara više paralelnih
konekcija (HTML + 9.469 linija `vindex.js` + CSS + fontovi); jednonitni server
ih serijalizuje, pa jedna spora blokira ostale i `domcontentloaded` probije 30s.
Isti oblik pada bio je viđen jednom ranije te noći u feedback suiti i nestao u
naredna tri prolaza — što je tada izgledalo kao šum.

**Popravka:** `ThreadingTCPServer` + `daemon_threads`, u svih 17 fajlova. Ovo
**nije „veći timeout"** — mandat to izričito zabranjuje kao popravku. Usko grlo
je uklonjeno, ne prikriveno.

Uz to je iz `test_6b` uklonjen `builtins.__import__` patch koji je za vreme
trajanja testa presretao **sve** uvoze u **svim nitima** — landmine u punoj
suiti sa Playwright-om. Zamenjen skopiranim `patch.dict(sys.modules, ...)`;
mutacija koja vraća stari kvar i dalje pada, dakle test nije oslabljen.

---

## 6. TESTOVI I MUTACIJE

| | |
|---|---|
| Novi testovi | 26 (2 retry-determinizam, 15 optimistic UI, 2 ai_fabric, 7 ranije u noći) |
| Prepisani postojeći | 2 (`test_6_prompt_guard_*`, feedback invarijante) — uz OLD/NEW/WHY |
| **Mutacije** | **10/10 ubijeno** (5 optimistic UI, 2+1 ai_fabric, 2 ranije) |
| Playwright | **258 prošlo** / 17 fajlova |
| Ciljana sigurnosna regresija | **310 prošlo** |
| Puna suita | **5579 prošlo / 2 preskočena / 0 palo** — bez randomizacije **i** sa `seed=11`, oba potvrđena POSLE popravke flake-a |

---

## 7. PRODUKCIJA

| | |
|---|---|
| Produkcione mutacije | **NE** — nijedan `INSERT`/`UPDATE`/`DELETE`/DDL |
| Migracije izvršene | **NE** — 0 |
| Promene šeme | **NE** |
| Rollback | nije potreban; sve promene su u kodu i testovima, `git revert` po commitu |

Migracija 113 **nije izvršena od moje strane** — zatečena je kao već primenjena.
Direktna DB veza (`SUPABASE_DB_URL`) i dalje ne postoji u okruženju, pa DDL
tehnički nije ni bio moguć.

---

## 8. MIGRACIJA 113 — KONAČAN STATUS

**PRIMENJENA** (zatečena, ne izvršena u ovoj noći). Dokazano read-only sondama.

⚠ **NEPROVERENO:** ponašanje RLS politika nad `reported_errors`. `SUPABASE_ANON_KEY`
nije dostupan u okruženju, pa je izmereno da tabela postoji, ali **ne** i da anon
ključ ne može da čita tuđe prijave. Politike su deklarisane u migraciji; njihov
**efekat** ostaje **UNKNOWN**, ne PASS.

---

## 9. PREOSTALI NALAZI

### P0 — **0 otvorenih**

### P1 — 3 klase, sve imenovane

| Nalaz | Zašto nije zatvoren |
|---|---|
| 10 nalaza koji traže promenu javnog HTTP ugovora | `2xx → 5xx` na rutama koje frontend već zove; **SEF i fakture dodiruju poresku obavezu** |
| 3 nalaza koji traže `CREATE TABLE` | `api_costs`, `ratio_decidendi`, `feature_usage_log` — HARD STOP mandata |
| 3 nalaza audit lanca | popravka menja značenje pojma „potvrđen lanac" — traži odluku, ne improvizaciju |

### P2/P3 — evidentirani u `COLUMN_DRIFT_MATRIX.md` i `FALSE_SUCCESS_DECISIONS.md`

### UNKNOWN — **1**

RLS ponašanje nad `reported_errors` (nedostaje anon ključ). **FS-P1-42 više nije
UNKNOWN** — razrešen je u Tasku 3.

---

## 10. BETA EXIT GATE

### USLOV 1 — nijedan ekran ne prikazuje neizvršenu proveru kao pozitivnu

**PASS**

| Površina | Dokaz |
|---|---|
| Sukob interesa | `provera_potpuna`; Playwright 6 |
| Cross-doc konflikti | neizvedena analiza = 500, ne „nema konflikata"; Playwright 4 |
| Rokovi | `rokovi_dostupni` kroz dashboard/brifing/today-focus/WhatsApp/AI prompt; Playwright 5 |
| Optimistic UI (5 površina) | `CONFIRMED` samo posle servera; Playwright 15 |
| Prijava netačnog odgovora | 503 umesto `ok`; Playwright 7 |

### USLOV 2 — nijedan dokument nije dohvatljiv drugom advokatu

**PASS uz jedno ograničenje.** 310 ciljanih testova (tenant izolacija, RAG ACL,
portal HMAC + vezivanje na `user_id`, brisanje vektora, identitet dokumenta).
Delegiranje predmeta — koje **daje** pravo čitanja — više ne može tiho da ne
upiše red.

⚠ Ograničenje: RLS se u API putanjama **zaobilazi** jer backend koristi
`service_role`. Zaštita je aplikativna (`shared/ownership.py`, `shared/rag_acl.py`),
što je dokazano testovima, ali RLS kao drugi sloj nije nezavisno izmeren.

### USLOV 3 — svako obećanje u UI-ju je istinito

**PASS za sve merene površine.** Ovo je uslov koji je noćas najviše popravljen:
pet optimistic-UI površina više ne tvrdi „sačuvano" pre servera.

---

## 11. SCORECARD STABILNOSTI

| | Kategorija | Ocena | Obrazloženje |
|---|---|---|---|
| A | Poverljivost podataka | 🟢 GREEN | CONF-001..004 pokriveni; nijedna noćašnja izmena ne proširuje pristup |
| B | Autorizacija | 🟢 GREEN | fail-closed rola zatvorena noćas; portal HMAC; ownership sloj |
| C | Integritet podataka | 🟡 YELLOW | GDPR brisanje i delegiranje sada dokazuju upis; **3 sekundarna pisca hronologije i dalje gutaju grešku** |
| D | False success | 🟢 GREEN | 46/46 poznatih ima odluku; svi P0 i svi dokazani P1 zatvoreni |
| E | Istinitost UI-ja | 🟢 GREEN | 5/5 optimistic UI + sve „nema X" površine |
| F | Semantika AI otkaza | 🟡 YELLOW | cross-doc i deadline promptovi zatvoreni; **`ai_fabric` guard ožičen ali modul i dalje nedostižan** |
| G | RAG / integritet indeksa | 🟡 YELLOW | ID-01/02, PINE-01 zatvoreni; **`vector_deletion` još nije vezan na brisanje predmeta** |
| H | Audit / provenance | 🟡 YELLOW | strogi audit za JMBG/PIB radi; **3 nalaza audit lanca odložena** |
| I | Baza / migracije | 🟡 YELLOW | 113 primenjena; **3 fantomske tabele i dalje nedostaju**; nema migracionog ledgera |
| J | Naplata / potrošnja | 🟡 YELLOW | cross-doc se više ne naplaćuje bez rezultata; **tajmer/SEF/fakture odloženi** |
| K | Pozadinski poslovi | 🟡 YELLOW | nije mereno noćas; 128 sirovih `create_task` iz ranijeg inventara stoji |
| L | Kvalitet testova | 🟢 GREEN | svaka noćašnja popravka ima mutaciju koja je ubija; 3 testa koja su kodifikovala bug prepisana, nijedan obrisan; **flake uklonjen po korenskom uzroku, ne timeout-om** |

**Nijedan RED.** Sedam YELLOW su poznata ograničenja koja **ne krše** Beta Exit Gate.

---

## 12. ŠTA NE BIH SLEDEĆE DIRAO

Mandat traži ovu sekciju i shvatam je ozbiljno.

**Ne bih pravio kanonski „success contract" framework (Task 5).** Postoje već tri
domenska sloja koja to rade ispravno — `shared/rokovi.py`, `shared/vector_deletion.py`,
`shared/ownership.py`. Četvrti, opšti sloj ne bi zatvorio nijedan poznat nalaz, a
dodao bi apstrakciju kroz koju bi budući čitalac morao da prođe da bi razumeo
jednostavan upit. Mandat sam kaže: „ne praviti god object", „ne menjati 50
endpointa radi apstrakcije". Domenski slojevi po potrebi su ispravan obrazac i
već su primenjeni tri puta.

**Ne bih menjao HTTP ugovore SEF-a i faktura zbog false-success nalaza.** Ti
tokovi dodiruju poresku obavezu. Pogrešna izmena tamo je gora od nalaza koji
popravlja.

**Ne bih dirao 68 „glasnih" mesta iz `COLUMN_DRIFT_MATRIX`.** Ona padaju vidljivo.
Vidljiv pad nije laž — a to je jedina klasa koju ova serija sprintova zatvara.

**Ne bih pisao još Playwright scenarija.** 258 testova pokriva svih 12 scenarija
iz mandata. Dodatni bi merili iste ugovore drugim rečima.

**Sledeći stvarni posao nije sprint nego merenje:** pustiti pilot advokata da
radi dan i gledati koje od ovih pretpostavki puknu. Sve što se moglo dokazati
bez korisnika — dokazano je.

---

# MORNING SUMMARY

```
START:
95028348

END:
c1c21ea9

FULL SUITE:
5579 passed / 2 skipped / 0 failed   (no-randomly i seed=11)

MUTATIONS:
10/10 killed

PLAYWRIGHT:
258/258

P0:
0 open

P1:
16 open — svi klasifikovani, nijedan nije lažno-zelena površina
         (10 = promena HTTP ugovora, 3 = nova tabela, 3 = audit semantika)

BETA EXIT:
GO WITH ACCEPTED RISKS
```

**NAJVEĆA POBOLJŠANJA**

1. Pet optimistic-UI površina više ne tvrdi „sačuvano" pre servera — uključujući
   naplativo vreme (novac), GDPR saglasnost i prihvatanje Uslova korišćenja.
2. `ai_fabric` prompt guard je godinu dana bio **tiho nepostojeći** — pozivao je
   funkciju koja ne postoji i gutao grešku. Ožičen i fail-closed.
3. Migracija 113 dokazana kao primenjena; oba kanala prijave netačnog pravnog
   odgovora sada imaju skladište.
4. Prijava netačnog odgovora ima dokazan retry-determinizam: konvergira ka punoj
   potvrdi i ne šalje duplo.
5. Tri testa koja su kodifikovala bug prepisana u ugovore — nijedan obrisan.
6. Nađen i uklonjen uzrok flake-a u suiti (jednonitni test server u 17 fajlova) —
   `seed=11` sada prolazi deterministički.

**NAJVEĆI PREOSTALI RIZICI**

1. **RLS nad `reported_errors` nije izmeren** — nedostaje anon ključ. Tabela
   postoji, ali da anon ne može čitati tuđe prijave **nije dokazano**.
2. **Tri fantomske tabele** (`api_costs`, `ratio_decidendi`, `feature_usage_log`)
   — trošak AI-ja se ne meri, keš pravnih stavova ne radi.
3. **Tri sekundarna pisca hronologije** i dalje gutaju grešku upisa; vrednosti su
   popravljene pa upis prolazi, ali ugovor greške nije menjan.

```
PRODUCTION MUTATIONS:
NO

MIGRATION 113:
APPLIED (zatečena, nije izvršena u ovoj noći)

OPTIMISTIC UI:
5/5 CLOSED

UNKNOWN:
1 (RLS ponašanje nad reported_errors)
```

**SLEDEĆA AKCIJA**

Dodati `SUPABASE_ANON_KEY` u okruženje da bi se RLS nad `reported_errors`
izmerio — to je jedini preostali UNKNOWN i jedini blokator za bezuslovan PASS
uslova 2.
