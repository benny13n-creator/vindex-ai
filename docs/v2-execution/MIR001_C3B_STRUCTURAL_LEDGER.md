# MIR001 C3b STRUCTURAL RECOVERY — ledger

Grana `night/miroslav-recovery` (worktree `C:/vindex-miroslav`). Pravac osnivača: **opcija C**, procesno stanje
utemeljeno na izvoru i provereno PRE nacrta za sud. Samo lokalni razvoj i testovi.
Granice: bez push/merge/deploy/migracija/Cron/NS007/reklasifikacije; bez drugog prepisivanja modelom; samo sintetički
podaci. Dokaz: `mir001_c3b_model/strukturalno/`. Prethodni ledger: `MIR001_C3B_LEDGER.md` (TASK-01–03, GATE-03 FAIL).

## TASK-00 — kontrolisano vraćanje i osnova

**Polazno stanje (provereno):**
- grana `night/miroslav-recovery`, HEAD `72dc01a4`;
- radno stablo čisto;
- `origin/main` je `f33dcce8`; grana je 0 iza i 24 ispred i nije na remote-u.

**Commitovi posle `ab63f913`:**

| SHA | sadržaj | kod |
|---|---|---|
| `c4cf8008` | C3b TASK-01, reprodukcija i dijagnoza | ne (samo dokazi) |
| `589cd4f0` | C3b TASK-02, ispravka uputstvom | **da**: `routers/multi_agent.py`, 2 test fajla + dokazi |
| `72dc01a4` | C3b TASK-03, slepo merenje (FAIL) | ne (samo dokazi i ledger) |

`72dc01a4` ne dira kod, pa od `589cd4f0` ne zavisi nijedan kasniji commit sa kodom.

**Šta je neuspela ispravka samo uputstvom (vraćeno):**
1. sistemska poruka nacrta: odeljak „PROCESNO STANJE — OBAVEZNA PRAVILA“ (pravila 1–6, uključujući obavezan odeljak
   „NAPOMENA ZA ADVOKATA“) i preformulisano pravilo o roku;
2. `_procesno_stanje_za_nacrt`: podsetnik koji upućuje na sistemska pravila → vraćeno staro PRAVILO ZA OVAJ NACRT;
3. docstring `_procesno_stanje_za_nacrt` (C3b napomena);
4. `tests/test_mir001_c3_procesno_stanje.py` → vraćen na `ab63f913`;
5. `tests/test_mir001_c3b_pravila.py`: od 4 testa iz `589cd4f0` uklonjena su 3 (jezgro u sistemskoj poruci;
   negativni scenario B koji traži ta pravila; pravilo o roku i jedan izvor pravila), a dodat je 1
   (`test_uputstva_savetnika_su_ab63f913_bez_neuspelih_pravila_c3b`, sha256 svih 6 savetnika); test provere ostaje.
   Neto −2 (237 → 235). Izgubljena je varijanta „bez odluke“ preko stvarnog brisanja DOK-07; odsustvo bloka i dalje
   pokriva `test_bez_odluke_u_spisu_nema_bloka_ni_oznake` (`test_mir001_c3_procesno_stanje.py:59`), ali preko
   monkeypatch-a.

**Šta je zadržano (selektivno, uz obrazloženje):**
- **Ispravka naknadne provere `_RE_SAMO_OZNAKA` (GATE-02 F4).** Nije tekst uputstva. Ispravlja grešku koja postoji i u
  `ab63f913`: `"[proveriti procesno stanje" in r` preskače SVAKU rečenicu u kojoj je oznaka, pa i golu tvrdnju
  „dopuna nije potrebna [PROVERITI …]“. Sužavanje je strože (označava više, ništa manje od `ab63f913` osim rečenice
  koja je samo oznaka — i nju je preskakao i `ab63f913`). Test ostaje.
- **Svi dokazi:** ledger C3b, `mir001_c3b_model/` (TASK-01 snimci i izlazi, dev1–dev4, mutacije `c3b_mut*`, t03
  slepi paketi, ključ, oznake, rezultat). Zato NIJE korišćen pun `git revert 589cd4f0`: on bi obrisao dokaze
  TASK-02 (mutacije, razvojne krugove) i odeljak ledger-a, a TASK-00 traži da se sačuvaju.
- Istorija grane: nema reset-a; vraćanje je nov commit.

**Provera vraćanja:**
- `git diff ab63f913 -- routers/multi_agent.py` = samo 2 hunka provere (`_RE_SAMO_OZNAKA` i njena upotreba);
- sha256 sistemskih poruka svih 6 savetnika = `ab63f913` (zaključano u
  `test_uputstva_savetnika_su_ab63f913_bez_neuspelih_pravila_c3b`);
- svi testovi koji diraju savetnike (20 fajlova, OCR stvarno uključen, `-p no:randomly`): **235/235** (ranije
  237 = 235 + 2 uklonjena testa teksta uputstva).

**Osnova C3b je i dalje ponovljiva:**
- Snimak poruke nacrta iz vraćenog koda (`strukturalno/t00/snimak_revert_head.json`, isti test
  `test_snimak_za_stvaran_model`) je, posle uklanjanja nasumičnih oznaka granice, **identičan** sa
  `t03/snimak_pre_A.json` i `snimak_A.json` (TASK-01), a razlikuje se od `t03/snimak_posle_A.json` tačno za vraćena
  pravila. Ulaz modela je dakle isti kao u slepo izmerenim grupama „pre A“ i „pre C1“ (TASK-03: pre A gola 1, O1 5;
  pre C1 gola 3, P 14/15, U ne 15/15).
- Sveže, stvaran gpt-4o, parametri proizvoda, 5 + 5 nacrta (`strukturalno/t00/t00_A.json`, `t00_C1.json`, svi
  `stop`). **Ovo NIJE slepo merenje**, samo potvrda da se obrazac i danas javlja (čitanje izvršioca + provera):
  - A: 4/5 tvrdi da je naložena dopuna ili uvid u dnevnik nepotreban (A#1 „dopuna veštačenja nije potrebna“, A#2
    „dodatni uvid u građevinski dnevnik nije neophodan“, A#3, A#0);
  - C1: #3 kasniji odustanak tuženog (DOK-08) koristi kao razlog („s obzirom da je tuženi u međuvremenu odustao“);
    #4 „nalaz veštaka potpun i … ne zahteva dopunu“; #1 „građevinski dnevnik irelevantan“, „veštak već utvrdio“ i
    „očekuje … u roku od 15 dana“ za nalog od 15.07. (rok kao da teče); provera ne označava nijedan C1 nacrt (0/5);
  - za C1 nije snimljen poseban t00 snimak: jednakost sa `pre_C1` je izvedena (ista sistemska poruka i isti kod bloka),
    a ne snimljena;
  - propisana oznaka `[PROVERITI PROCESNO STANJE` 0/10.

**Changed files:** `routers/multi_agent.py`, `tests/test_mir001_c3_procesno_stanje.py`,
`tests/test_mir001_c3b_pravila.py`, ovaj ledger, `mir001_c3b_model/strukturalno/t00/`.

**Independent reviewer finding:** GATE-00 **PASS** (recenzent; bez blokirajućih nalaza). Potvrđeno samostalno:
obim vraćanja (2 hunka provere; sha256 6 savetnika = `ab63f913` iz `git show`); samo `589cd4f0` i ovaj commit diraju kod
posle `ab63f913`; `git diff --name-status 72dc01a4 HEAD` = samo dodati fajlovi u `docs/`; 235 passed / 0 skipped uz
OCR; `_RE_SAMO_OZNAKA` je stvarna greška u `ab63f913` (gola tvrdnja uz oznaku: 0 → 1 nalaz; samo-oznaka i oprezna
negacija 0 u obe verzije); snimak identičan `pre_A`; C3b reprodukovan (A 4/5, C1 #3, oznaka 0/10).
Neblokirajuće:
1. tačka 6 traži STOP + predlog selektivnog vraćanja; izvršilac ga je izvršio sam — ishod je minimalan, lokalan,
   obelodanjen, ali **osnivač treba izričito da potvrdi zadržavanje `_RE_SAMO_OZNAKA`** (slepo merena samo uz
   `589cd4f0`);
2. C1 brojanje prijavljeno manje (#4, #1) → ispravljeno gore;
3. „uklonjena 2 testa“ netačno (3 uklonjena, 1 dodat) → ispravljeno gore;
4. C1 snimak izveden, ne snimljen → obelodanjeno gore;
5. revert snimak nema ključ `_odluke_suda` (poruka identična) — trivijalno.
→ 2–4 unete (izvršilac).


## TASK-01 — izvodljivost procesnog stanja utemeljenog na izvoru

**Baseline SHA:** `544f778f` (GATE-00 PASS). **Kod nacrta nije menjan.** Dodat je samo nepovezan prototip ugovora
(`shared/procesno_stanje.py`, čista funkcija, bez upisa, modela i mreže) i njegovi testovi. Nijedna ruta ga ne poziva.
1. prolaz je bio `744911fa` (GATE-01 FAIL, nalazi ispod). Ovaj odeljak opisuje ispravljen ugovor.

### Šta postojeći podaci podržavaju (pregled koda i šeme)

| traženo polje | postojeći izvor | klasa u ugovoru | napomena |
|---|---|---|---|
| identitet dokumenta | `predmet_dokumenti.id`, `redni_broj` (→ `DOK-nn`), `predmet_id`, `user_id` (`supabase_setup.sql:355`, `user_id NOT NULL`) | deo VERIFIED izvoda | vlasništvo već proverava `_kontekst_predmeta` (`predmeti.user_id`); modul dodatno odbacuje tuđ red, a prazan identitet je greška |
| tačan izvod | `predmet_dokumenti.tekst_sadrzaj` (ceo tekst, OCR ili digitalni) | **VERIFIED_SOURCE_FACT** = samo „ovaj dokument sadrži tačno ovaj izvod na ovom mestu“ | `potvrdi_izvod`: sha256 celog teksta + položaj + tekst; snimci t03 su OCR izlaz |
| vrsta događaja i akter rečenice | obrazac nad rečenicom (glas suda, lični i bezlični u oba poretka — „Sud nalaže“, „Nalaže se“, „Tuženom se nalaže“, „Tuženi se obavezuje“; stranka kao subjekat SAMO u nominativu, bez pasiva sa „se“; preneseni govor SAMO „… da (je) sud“; negacija, ukidanje, narativ ranije odluke, više odluka u jednoj rečenici) | **tumačenje: UNKNOWN (kandidat) ili CONTESTED, nikad VERIFIED** | heuristika; nerazvrstano je glasno |
| vrsta dokumenta po naslovu | red u glavi koji POČINJE reči vrste (ZAPISNIK/REŠENJE/PRESUDA/ZAKLJUČAK naspram PODNESAK/ODGOVOR/IZJAŠNJENJE/TUŽBA/ŽALBA…) | kandidat (UNKNOWN) | „Veza: … rešenje“, „Predmet: … zapisnik“ nisu naslov |
| vrsta dokumenta, potvrđena | audit zapis ljudske odluke `dokument_vrsta_ispravljena` (`audit_immutable`; ruta QA-02 `routers/evidence.py:699–766`, CAS + vraćanje kad audit padne, audit `:748`) | **HUMAN_CONFIRMED** samo iz audit traga (parametar `potvrde_vrste`, daje ga pozivalac) | sukob sa naslovom → CONTESTED. **Smart Intake ispravka vrste se NE računa:** njen audit (`routers/smart_intake.py:776`, ruta `:709`) je nad `intake_documents.id`, a jedina veza sa `predmet_dokumenti.id` je `ai_tags.intake_document_id`, kome ugovor ne veruje → dokument ostaje kandidat po naslovu (fail-closed) dok TASK-02 ne nađe pouzdanu vezu |
| `ai_tags._vrsta_advokat` | upisuju ga QA-02 i Smart Intake (`smart_intake.py:2164`), ali `ai_tags` piše i izlaz modela (`routers/evidence.py:315`) | **ne koristi se** | GATE-01 nalaz 8: oznaka u `ai_tags` nije nezavisna |
| AI vrsta (`tip_dokaza`) | GPT-4o-mini klasifikacija | ne koristi se | nije nezavisna |
| datum dokumenta | samo oznaka na POČETKU reda, sopstvene vrste („Datum podneska:“ u podnesku; „Datum:“; „U <mestu>, dana“; „Ročište održano dana“ samo u sudskom) | VERIFIED (izvod oznake) / UNKNOWN | „Datum rešenja:“ ili „ročište održano dana“ u podnesku NISU datum podneska; više različitih → UNKNOWN; `redni_broj` se ne koristi kao procesni redosled. Datum dokumenta nije datum događaja koji dokument pominje |
| kasniji događaji koji mogu menjati odluku | rečenice stranke, konstatacija suda i drugi akti suda o istom predmetu radnje (≥ 2 zajedničke osnove reči); akt koji ukida bez prepoznatog predmeta osporava sve ostale odluke | CONTESTED, dejstvo UNKNOWN | nevezan odustanak ili navod o izvršenju → glasno upozorenje |
| protivrečnosti | naslov naspram potvrđene vrste; kasniji podnesak ili akt; identični sudski dokumenti; nejasan datum | CONTESTED | — |
| dokaz izvršenja / uplate | **nema strukturisanog izvora**; konstatacija u zapisniku se vezuje kao kasniji događaj | UNKNOWN („uplata nije utvrđena iz pročitanih dokumenata“) | navod stranke („uplatio“) ostaje navod; nikad „nije izvršeno“ ni „nema dokumenta“ |
| rok: trajanje i početak iz izvoda | izvod („u roku od 15 dana“, „od prijema zapisnika“) | deo VERIFIED izvoda | — |
| rok: tok / istek | **nije utvrdiv** — početak (dostava) nije u spisu, pravilo računanja ovaj ugovor ne utvrđuje | UNKNOWN | ljudska potvrda roka postoji (`shared/rok_potvrda.py`), ali je vezana za red hronologije, ne za red naloga (FAZA 6.1: identitet činjenice nije rešiv) — zato se NE vezuje |
| nerešeno | lista `nepoznato` | UNKNOWN | nepročitani dokumenti, dokument nepoznate vrste, nerazvrstana rečenica suda (sa izvodom), narativ, negacija, više odluka, ćirilični ili neobični znaci, nevezan odustanak |

Hronologija (`predmet_hronologija`) i tvrdnje (`predmet_dokazi`) postoje i vezane su za dokument, ali njihov
sadržaj piše model (migracija 127: 49/55 redova bez dokazive provenance). Zato **nisu ulaz** u ugovor. Ugovor ne
dodaje entitet, kolonu ni migraciju.

### Ugovor (`shared/procesno_stanje.utvrdi`)

Ulaz su redovi dokumenata (`id, predmet_id, user_id, oznaka, tekst`), oznake nepročitanih dokumenata i
`potvrde_vrste` iz audit traga. Izlaz modela nema ulaz (potpis zaključan testom).

Po događaju se dobija:
- **izvod (VERIFIED):** `id, dokument_id, oznaka, tekst_sha256, početak, kraj, izvod, klasa=VERIFIED_SOURCE_FACT`;
- **tumačenje (heuristika):** `akter, vrsta, kandidati`, `klasa_tumacenja` (UNKNOWN ili CONTESTED) i
  `vrsta_dokumenta` (`akter, osnov` NASLOV/ADVOKAT, `klasa` UNKNOWN/HUMAN_CONFIRMED/CONTESTED, `naslov`);
- **datum:** `datum_dokumenta`;
- **veze:** `kasniji[]` (`odnos`: KASNIJE/RANIJE/ISTOG_DANA/ISTI_DOKUMENT/NEPOZNAT_REDOSLED/NEPOZNAT_PREDMET;
  `dejstvo`: UNKNOWN) i `stanje` (CONTESTED);
- **nerešeno:** `rok` (`tok_i_istek`: UNKNOWN), `uplata`, `izvrsenje` (UNKNOWN) i `nepoznato[]`.

Nijedno polje ne tvrdi važenje, prestanak, istek, tok, izvršenje ni uplatu.

### Scenariji A–D na stvarnim tekstovima spisa (`strukturalno/t01/t01_stanje_scenarija.json`)

Ulaz su tačni tekstovi dokumenata iz slepo merenih snimaka t03, odnosno OCR izlaz Golden Case-a.

| scenario | kandidati odluka suda (izvod VERIFIED, tumačenje UNKNOWN) | stanje | nepoznato (skraćeno) |
|---|---|---|---|
| A — sud nalaže dopunu (`pre_A`) | DOK-07 „Sud prihvata predlog za dopunu vestacenja.“ i „Sud nalaze tuzenom da dostavi … u roku od 15 dana.“ (datum dokumenta 15.07.2026) | raniji predlog DOK-06 = RANIJE, nije sporno | tok/istek roka; postupanje po nalogu; povlačenje 600.000 u zapisniku nije vezano za odluku (v. ograničenje 6) |
| B — kasniji odustanak (`pre_C1`) | iste (ne uklanjaju se) | **CONTESTED**: DOK-08 odustanak i DOK-08 „dnevnik nije sačuvan“, KASNIJE, dejstvo UNKNOWN | „da li DOK-08 (stranka_odustaje, kasnije) menja ovu odluku … — nije utvrđeno“ |
| C — zapisnika nema (`pre_C2`) | nema | navod tuženog o ročištu = TUZENI, STRANKA_NAVODI_O_SUDU | nema dokumenta prepoznatog kao sudski; zapisnik od 15.07.2026 nije prepoznat među pročitanim — ishod NEPOZNAT |
| D — predujam (`posle_H2`) | DOK-07 „Sud nalaze tuziocu da u roku od 8 dana od prijema zapisnika uplati predujam …“ | `uplata` UNKNOWN, početak roka „od prijema zapisnika“, tok UNKNOWN | tok/istek roka; „uplata nije utvrđena iz pročitanih dokumenata“; postupanje |
| H1 — sud odbio | DOK-07 SUD_ODBIJA | — | povlačenje 600.000 (ograničenje 6) |
| B0 — nema DOK-07 (`pre_B`) | nema | — | nema dokumenta prepoznatog kao sudski |

### Testovi, napadi i mutacije

`tests/test_mir001_c3b_procesno_stanje_ugovor.py`: **65/65** (3. prolaz: proširen test C). Pozitivni: A, B, C, D, uključujući navod stranke o
uplati i konstataciju u zapisniku. Negativni slučajevi uključuju sve napade recenzenta GATE-01 (1. prolaz) kao
regresije, kao i napade 2. prolaza:
- ostaju glas suda: bezlični nalog u dativu (scenario D: „Tuziocu se nalaze da u roku od 8 dana od prijema zapisnika uplati predujam“), „Strankama se nalaze“, „Tuzenom sud nalaze“, „Nakon sto je tuzeni predlozio …, sud prihvata“, „Sud nalaze …, kako tuzilac predlaze“, „… se prihvata“ i izreka „Tuzeni se obavezuje“;
- rečenica pripisana stranci koja pominje odluku suda je glasna;
- inicijal („M. Markovic“) i „din.“ ne seku izvod;
- dva naslova različite vrste su sukob, a naslov se ne spaja sa telom;
- „ranije“ u pravoj odluci nije narativ;
- nevezan odustanak je glasan i kad nijedan nalog nije prepoznat;
- datum citiran usred reda nije datum dokumenta;
- tekst stranke nikad nije odluka suda (red „Veza: … rešenje“, red „Predmet: … zapisnik“, podnesak koji citira sud);
- stranka kao subjekat ili preneseni govor u zapisniku nije glas suda;
- predlog stranke u istom zapisniku je pozadina, a odustanak u istom zapisniku čini odluku spornom;
- narativ ranije, ukinute odluke nije važeća odluka;
- kasniji akt suda koji ukida čini odluke spornim, i kad se ne zna koje;
- dve odluke u rečenici → SUD_VISESTRUKO; dve rečenice u redu → dve radnje; bez sečenja posle datuma i skraćenice;
- izreka velikim slovima je odluka; negacije (5 oblika) nikad nisu prihvatanje i uvek su glasne;
- nerazvrstana rečenica suda je glasna i kad postoje druge odluke;
- nevidljivi znak se uklanja; ćirilični znak i ćirilični dokument su glasni;
- datum druge vrste u podnesku nije datum podneska; „Datum:“ i „U mestu, dana“ se prepoznaju; „đ“ čuva položaj;
- izvod modela, pomereno mesto, izmenjen tekst, `bool` i obrnut opseg se odbijaju;
- tuđ red se odbacuje; prazan identitet je greška;
- `ai_tags` i `tip_dokaza` ne potvrđuju ništa, a potvrda vrste iz audita daje HUMAN_CONFIRMED (sukob → CONTESTED);
- odustanak opisan drugim rečima je glasan; nepročitani dokumenti → NEPOTPUNO.

**Probe recenzenta ponovljene na novom kodu**, sa istim ulazima i preimenovanim poljima
(`strukturalno/t01/gate01_probe_recenzenta_v2.py`, izlaz `…_izlaz.txt`). Nijedan tekst stranke ni narativ više nije
odluka suda.

Probe 2. prolaza su u `gate01_probe3_recenzenta.py`, a izlaz u `gate01_probe3_izlaz_posle_ispravke.txt`:
- N1 (dativ, preneseni govor) sada se prepoznaje kao nalog;
- N2 (inicijal, „din.“): izvod se više ne seče;
- N3: „ranije“ u pravoj odluci ostaje odluka;
- N5: dva naslova su sukob.

Ostaju obelodanjeni N4 (red „U Beogradu, dana …“ citiran sam u svom redu podneska i dalje postaje datum podneska) i N6 (šum). Promašaj obrasca NIJE uvek glasan (v. ograničenje 1).

**Mutacije 49/49 uhvaćene stvarnim `failed`**, bez `error` (`strukturalno/t01/t01b_mut.json`, `t01b_mut_out.txt`;
fajlovi vraćeni bajt-identično). Dve mutacije u prvom krugu nisu bile uhvaćene, pa su dodati testovi:
- U2 (stranka u istom zapisniku uvek osporava);
- U6 (preneseni govor). Opis U6/U7 u specifikaciji je bio zamenjen i ispravljen je.

U 2. prolazu dodate su mutacije V1–V12:
- dativ; pasiv; širok preneseni govor;
- tiha rečenica stranke sa odlukom; obrnut bezlični nalog; izreka „obavezuje se“;
- inicijal; dva naslova; spojen naslov;
- datum usred reda; nevezan odustanak bez naloga; golo „ranije“.

V1, V2 i V9 u prvom pokušaju nisu bile uhvaćene, pa su dodati testovi:
- dativ bez „se“;
- izreka presude, koja do tada nije bila obrazac i bila je tiha;
- datum sa tekstom posle oznake.

### Ograničenja (obelodanjeno)

1. **Promašaj obrasca NIJE uvek glasan.** Obrasci su napisani za izmereni Golden Case, napade GATE-01 (dva prolaza)
   i uobičajene oblike (lični i bezlični glas suda u oba poretka, latinica). Glasno je:
   - rečenica sudskog dokumenta sa sudskim rečnikom koja nije razvrstana („nije razvrstana — «izvod»“), npr. „Sud,
     posle izjašnjenja tuženog koji predlaže dopunu, prihvata predlog“, gde je glas suda razdvojen umetkom;
   - rečenica pripisana stranci koja liči na odluku;
   - sudski dokument bez ijedne prepoznate odluke i dokument nepoznate vrste.

   **Tiho ostaje:**
   - odluka bez ijedne reči sudskog rečnika (npr. „Izvodi se dokaz …“, „Tuženi se poziva …“);
   - rečenica stranke u sudskom dokumentu koja ne liči na odluku. Takva rečenica nije ni kandidat ni upozorenje;
   - **obrnuto (GATE-01 3. prolaz R2):** izjava stranke u zapisniku u nominativu sa „se obavezuje“ („Tuženi se
     obavezuje da će … dostaviti“) i preneseni govor bez „da“ („Prema navodima tuženog, sud je već odbio …“)
     tiho postaju KANDIDAT odluke suda. Tumačenje je UNKNOWN, a izvod doslovno nosi pripisivanje stranci, pa
     TASK-02 sme samo da citira izvod, nikad da ga iznese kao odluku.
   Preostali rizik meri slepa provera (TASK-03), a ne ovaj ugovor.
2. Veza kasnijeg podneska sa odlukom je tekstualna (≥ 2 zajedničke osnove). Odustanak ili navod o izvršenju koji nije
   vezan daje glasno upozorenje, ali odluka tada nije CONTESTED. Ostali nevezani navodi stranke se ne prijavljuju.
3. Ćirilica nije podržana (fail-closed, glasno).
4. Ugovor vidi samo dokumente koje `_kontekst_predmeta` čita: najviše 12 i ceo tekst uključenih. Ostali → NEPOTPUNO.
5. Autentičnost dokumenta i pravna kvalifikacija nisu utvrđivane:
   - dokument stranke sa naslovom „ZAPISNIK …“ je kandidat za sudski (klasa vrste UNKNOWN, tumačenje UNKNOWN);
   - skup vrsta nema „zapisnik“, pa advokat bira `court_decision`;
   - Smart Intake potvrda vrste se ne računa (v. tabelu).
6. Šum u internim napomenama (upozorenja su tačna):
   - upozorenje za nevezan odustanak javlja se i za delimično povlačenje tužbenog zahteva zabeleženo u zapisniku
     (Golden Case: „Tuzilac povlaci zahtev … 600.000“), za „dostavlja punomoćje“ i za „povlači prigovor“;
   - identični sudski dokumenti međusobno se označavaju CONTESTED.
7. Red „U <mestu>, dana <datum>“ citiran sam u svom redu podneska postaje datum podneska (N4). Posledica je
   ograničena: odustanak i navod o izvršenju čine odluku spornom bez obzira na redosled. U suprotnom smeru, datum
   dokumenta u redu iza koga sledi tekst („… godine, sa početkom u 10 časova“) NIJE datum dokumenta (UNKNOWN), ali se
   za proveru „zapisnik ročišta“ datum ročišta iz sudskog dokumenta prepoznaje i tada (R1). Poruka kaže „nije
   prepoznat“, nikad „nema“.
8. Oznaka vrste događaja stranke može biti pogrešna (R3): „Stranka koja ne uplati predujam snosi posledice“ →
   STRANKA_NAVODI_IZVRSENJE; rečenica sa dva navoda dobija samo prvi. Oba primera su glasna kroz „nije tekstom
   vezan“.
9. **Pokrivenost ročišta je široka (GATE-01 4. prolaz R4):** svaki sudski dokument koji pomene datum ročišta (npr. rešenje: „Na ročištu održanom 15.07.2026. tuženi je predložio …“) gasi upozorenje „zapisnik … nije prepoznat“. Ništa se ne tvrdi kao utvrđeno: ishod ročišta nigde nije označen kao poznat, a rečenica je glasna kao nerazvrstana. Gubi se samo nagoveštaj. **TASK-02 mora da smatra ročište pokrivenim samo kad naslov dokumenta počinje sa ZAPISNIK i datum tog dokumenta je datum ročišta.**

### Primena u TASK-02 (izvodljivost u postojećoj arhitekturi; NIJE implementirano)

- **Čitanje stanja:** `_kontekst_predmeta` već čita ceo tekst izabranih dokumenata. Treba samo proširiti `select` za
  `user_id, predmet_id` i pročitati potvrde vrste iz `audit_immutable` za ta dokumenta. Bez migracije i bez novog
  poziva modela.
- **Tekst za sud:** u njega smeju samo izvodi pripisani dokumentu („u zapisniku DOK-07 stoji: «…»“). Tumačenje (da je
  to odluka, da važi) ne sme biti izneto kao utvrđeno.
- **Razdvajanje napomena:** interne napomene se moraju odvojiti od teksta za sud (danas `_napomena_za_pregled` ide u
  isti `staging_memory.tekst`, pa u DOCX). Rešava se u TASK-02.
- **Izolacija zakupca:** isti upiti, ista provera vlasništva, plus odbacivanje tuđeg reda u modulu.

**BLOCKED_EVIDENCE_MODEL nije potreban** (potvrdio i recenzent GATE-01). Za svaki od četiri poznata kvara podaci daju
proveren izvod ili izričito UNKNOWN, a ispravan ishod za UNKNOWN je upravo „nije utvrđeno“.

**Changed files:** `shared/procesno_stanje.py` (nov), `tests/test_mir001_c3b_procesno_stanje_ugovor.py` (nov), ovaj
ledger, `mir001_c3b_model/strukturalno/t01/`.

**Independent reviewer finding:** 1. prolaz **FAIL** (recenzent GATE-01, `744911fa`). Podaci podržavaju ugovor, pa
BLOCKED_EVIDENCE_MODEL nije opravdan. Prototip je pao na lažnim poklapanjima i tumačenjima. Blokirajući nalazi:
1. podnesak sa redom „Veza: … rešenje“ ili „Predmet: … zapisnik“ postajao je sudski dokument;
2. stranka ili preneseni govor u zapisniku („Punomoćnik … predlaže da sud odbije“) čitali su se kao odluka suda;
3. narativ ranije, ukinute odluke bio je VERIFIED odluka, a kasniji akt suda koji ukida nije osporavao nalog;
4. tihi promašaji, suprotno tvrdnji ledger-a da je promašaj glasan: izreka velikim slovima, „se ne usvaja“, „odlučio
   da ne prihvati“, nevidljivi i ćirilični znaci.

Neblokirajući nalazi:
5. datum druge vrste u podnesku i neprepoznat „Datum:“;
6. „nema dokumenta o uplati“ je tvrdnja o odsustvu;
7. dve odluke u jednoj rečenici;
8. HUMAN_CONFIRMED preko `ai_tags`, koji može upisati i model;
9. `None == None` u proveri identiteta.

Preporuka: VERIFIED samo za izvod, a tumačenje kao zasebna, niža klasa. → **sve unete** (izvršilac; v. gore).
Dodatno sam izvršilac našao dve rečenice u istom redu i nevezan odustanak opisan drugim rečima.

2. prolaz **FAIL** (recenzent GATE-01, `06fdc92c`). Svih 9 nalaza iz 1. prolaza je zatvoreno, što je recenzent
potvrdio sopstvenim probama.

Nov blokirajući nalaz:
- **N1:** `_RE_SUBJEKAT_STRANKA` je hvatao dativ („Tuziocu/Tuzenom/Strankama se nalaze“), a `_RE_PRENESEN_GOVOR`
  svako „predlaže … sud“. Nalog suda u najčešćem obliku zato je tiho postajao STRANKA. To važi za bezlični oblik
  scenarija D i za scenario A u obliku „Nakon što je tuženi predložio …, sud prihvata“. Ledger je preterivao kad je
  tvrdio da je svaki promašaj glasan.

Neblokirajući nalazi:
- N2: inicijal i „din.“ seku izvod;
- N3: „ranije“ u pravoj odluci, a nevezan odustanak tada nije prijavljen;
- N4: „U Beogradu, dana“ citiran u podnesku;
- N5: dva naslova bez sukoba; naslov se spajao sa telom;
- N6: šum;
- N7: Smart Intake audit je nad `intake_documents.id`, a `:709` je ruta.

→ Unete ispravke (izvršilac):
- subjekat samo u nominativu, bez pasiva sa „se“; preneseni govor samo „… da (je) sud“;
- bezlični nalog u oba poretka i izreka „obavezuje se“;
- glasna rečenica pripisana stranci koja liči na odluku;
- inicijali i „din“ među skraćenicama;
- „ranije“ samo u narativnom obliku;
- nevezan odustanak se prijavljuje uz bilo koji sudski dokument;
- dva naslova → sukob, a jedinice teksta počinju posle naslova;
- red datuma mora biti samo oznaka i datum;
- usklađena ograničenja 1, 5, 6 i 7; Smart Intake potvrda se ne računa.

Testovi 65/65, mutacije 47/47.

3. prolaz **FAIL** (recenzent GATE-01, `643d7cb0`). N1–N7 su zatvoreni sopstvenim probama recenzenta, a Golden
regresija A–D i H1 se poklapa sa tabelom.

Blokirajući nalaz:
- **R1:** sidro `$` na redu datuma odbacuje „Ročište održano dana 15.07.2026. godine, sa početkom u 10 časova“, pa
  modul tvrdi da zapisnika NEMA među pročitanim, iako je pročitan.

Neblokirajući nalazi:
- R2: izjava stranke sa „se obavezuje“ i preneseni govor bez „da“ tiho postaju kandidat odluke suda, a ograničenje 1
  opisuje samo suprotan smer;
- R3: pogrešna oznaka vrste događaja stranke.

→ Unete ispravke (izvršilac):
- datum ročišta iz sudskog dokumenta se prepoznaje i kad iza njega sledi tekst;
- poruka „nije prepoznat među pročitanim dokumentima“ (odsustvo se ne tvrdi), uz regresioni test;
- mutacije W1 i W2;
- ograničenja 1, 7 i 8 dopunjena sa R1–R3.

Testovi 65/65, mutacije 49/49.

4. prolaz **PASS** (recenzent GATE-01, `41c52c00`). R1 je zatvoren, i to u varijantama: „sa početkom u 10 časova“,
„na ročištu održanom dana“, samo podnesak („nije prepoznat“) i zapisnik drugog datuma (upozorenje ostaje). Regresija
N1–N7 i Golden A–D i H1 se poklapa sa tabelom, a zapis 3. prolaza je veran. Kriterijumi:

| kriterijum | ocena |
|---|---|
| referenca na izvor | PASS |
| tačan izvod | PASS |
| model nije izvor | PASS |
| nepoznato ostaje nepoznato | PASS |
| izolacija zakupca | PASS |
| izvodljivost | PASS |

BLOCKED_EVIDENCE_MODEL nije opravdan. Neblokirajući nalaz R4 (široka pokrivenost ročišta) → obelodanjen kao
ograničenje 9 (izvršilac).

Napomene recenzenta za TASK-02:
- u tekst za sud ulaze samo doslovni izvodi pripisani dokumentu, a kandidat odluke se nikad ne iznosi kao utvrđen
  (važi i za R2);
- Smart Intake potvrda ostaje van ugovora;
- R4 se rešava strožim pravilom pokrivenosti.

**TASK-01 ZATVOREN — GATE-01 PASS.**


## TASK-02 — zaštićen nacrt za sud (minimalno)

**Baseline SHA:** `caa997c4` (GATE-01 PASS).

### Tok (nacrt iz spisa: `POST /api/agents/run`, agent `drafting`, predmet potvrđen)

1. **Kontekst predmeta:** `_kontekst_predmeta(..., procesno=True)` čita isto što i ranije (vlasništvo, najviše 12
   dokumenata, ceo tekst izabranih).
2. **Procesno stanje:**
   - računa ga `shared/procesno_stanje.utvrdi` iz CELOG teksta uključenih dokumenata (red mora imati isti
     `predmet_id` i `user_id`);
   - potvrda vrste dolazi samo iz `audit_immutable` (`dokument_vrsta_ispravljena`, `_potvrde_vrste`);
   - nepročitani dokumenti, dokumenti bez teksta, greška čitanja, nepotpun spisak ili odbačen red → `greska`, pa
     kapija radi najstrože (kao da nalog postoji);
   - novi upit je samo jedan čitajući upit audit traga, bez migracije.
3. **Poruka modelu:**
   - blok „PROCESNO STANJE IZ SPISA — utvrdio SISTEM“ (oznake `[[PS-nn]]`, doslovni izvodi, kandidati i NIJE
     UTVRĐENO) je u granici poverenja, posle spisa i pre zahteva;
   - pravila (`PRAVILA_ZA_MODEL`, JSON format, zabranjene procesne tvrdnje, stav stranke uz oznaku odluke) su u
     sistemskoj poruci, pre granice instrukcionog autoriteta.
4. **Jedan poziv modela** (`_pozovi_nacrt_api`): isti model i temperatura, `response_format=json_object`,
   `max_tokens` 2.500 (bilo 2.000, zbog JSON omotača).
   - Neispravan JSON, prazan `tekst_za_sud` ili `finish_reason=length` → 502. Nacrt se ne pravi, ništa se ne upisuje
     na pregled i ništa se ne naplaćuje (provera ide PRE naplate); nema automatskog ponavljanja.
5. **Kapija teksta za sud** (`shared/nacrt_za_sud.zastiti`) čita svaku rečenicu. Oznaka `[[PS-nn]]` postaje doslovan
   izvod sa oznakom dokumenta. Rečenica sa nepotvrđenom procesnom tvrdnjom se izostavlja: u tekstu ostaje vidljivo
   `[IZOSTAVLJENO I-n …]`, a rečenica i razlog idu u interne napomene. Kategorije:
   - uplata;
   - izvršenje ili ispunjenje naloga;
   - tok ili istek roka;
   - pravosnažnost ili konačnost;
   - buduće izvršenje naloga sa rokom čiji tok nije utvrđen;
   - već doneta odluka prikazana kao uslovna;
   - nepotrebnost, prestanak ili dejstvo naloga bez stava stranke uz pozivanje na odluku suda;
   - odluka suda opisana sopstvenim rečima, bez izvoda ili potvrđene parafraze;
   - „veštak/sud utvrdio“;
   - odustanak bez odluke suda;
   - predlog o predmetu odluke bez pozivanja na nju;
   - bezuslovan predlog o pitanju čiji ishod ročišta nije poznat.

   Upozorenja, napomene i čekliste iz teksta za sud (⚠️, „NAPOMENA ZA ADVOKATA“, `[PROVERITI …]`) prelaze u
   napomene. Granicu i čuvar mesta iz izlaza modela ili iz dokumenta server neutrališe.
6. **Nacrt na pregledu** = tekst za sud + serverska `GRANICA` + interne napomene. Napomene sadrže:
   - procesno stanje (doslovni izvodi, kandidati, kasniji događaji sa dejstvom NEUTVRĐENO);
   - NIJE UTVRĐENO;
   - izostavljeno, sa razlozima;
   - premešteno;
   - napomene savetnika (AI);
   - postojeću serversku proveru (citati, nepročitani dokumenti).

   Pregled, izmena, odobravanje i odbijanje se ne menjaju (isti `staging_memory`, bez migracije). API vraća i
   `tekst_za_sud` i `izostavljeno_iz_teksta_za_sud`.
7. **DOCX:**
   - nova ruta `POST /api/staging/{id}/docx` izvozi SAČUVAN tekst iz baze, samo za vlasnika (inače 404), i samo deo
     pre JEDINE granice;
   - 409 kad granica nije jedinstvena ili kad u tekstu za sud ostane `[IZOSTAVLJENO I-n]` ili `[PROVERITI …]`;
   - opšta ruta `/api/nacrti/export/docx` odbija tekst sa granicom (409);
   - V2 (`nacrt-predmeta.js`) za otvoren nacrt sa pregleda prvo čuva nesačuvanu izmenu, pa izvozi preko servera;
     za tek izrađen `/api/podnesak` nacrt put ostaje isti.

Savetnici koji nisu nacrt i nacrt bez predmeta nisu dirnuti (test). Niz (`/pipeline`) poziva `/run` i za korak
nacrta, pa i on ide zaštićenim tokom.

### Promenjeni fajlovi

- `shared/nacrt_za_sud.py` (nov);
- `routers/multi_agent.py`: `_potvrde_vrste`, `procesno` u `_kontekst_predmeta`, `_pozovi_nacrt_api`, zaštićen tok
  u `run_agent`;
- `routers/drafting.py`: `_firma_za_zaglavlje`, odbijanje granice u opštem izvozu, `POST /api/staging/{id}/docx`;
- `frontend-v2-ng/src/nacrt-predmeta.js`;
- testovi:
  - novi: `tests/test_mir001_c3b_nacrt_za_sud.py` i `tests/nacrt_json_zamena.py` (pakuje postojeće zamenike modela u
    JSON ugovor);
  - usklađeni sa novim ugovorom: `tests/test_mir001_c3_procesno_stanje.py` (C3 blok i oznaka → C3b stanje i
    kapija), `test_mir001_t06…`, `test_mir001_t10…`, `test_mir001_c4_e2e.py`;
  - zamenik `_pozovi_nacrt_api` dodat u 9 fajlova i u `osb003_solo_server.py`;
- `frontend-v2-ng/tests/fixtures/pisanje-api.mjs` i `frontend-v2-ng/tests/live-nacrt.mjs` (scenario DOCX sa
  pregleda).

### Razvoj kapije — UNUTAR UZORKA, nije dokaz

Kapija je razvijana nad 110 nacrta slepog merenja t03 (`strukturalno/t02/kapija_t03.py`). Ti nacrti su pisani
BEZ oznaka `[[PS-nn]]` i bez novih pravila, pa merenje pokazuje samo da detektori hvataju poznate obrasce. Ne pokazuje
šta će nov tok proizvesti.

- Posle razvoja su uklonjene sve slepo označene procesne tvrdnje O1 i R u A, C1, H2 i u „pre“ grupama, kao i
  10/13 P u C2.
- Neuklonjeno ostaje:
  - prećutkivanje bez oblika („Molimo sud da uzme u obzir … na ročištu 18.11.“; „izjasniti se po izvršenju … ukoliko
    bude potrebno“);
  - greške iznosa tužbenog zahteva (B, C2), koje NISU procesno stanje i van su obuhvata C3b.
- Na starim nacrtima kapija izostavlja oko 2–4 rečenice po nacrtu, pretežno tačne parafraze odluke bez oznake.
  Rizik suzbijanja legitimnog teksta (TASK-03 merilo 6) meri se tek na nacrtima novog toka.

### Testovi (`-p no:randomly`, OCR stvarno uključen)

- novi i usklađeni (`c3b_nacrt_za_sud` 48, `c3` 9, `t06`, `c4`, `t10`, `c3b_procesno_stanje_ugovor` 65): prolaze;
- svi test fajlovi koji pominju savetnike, overu, DOCX, `/api/podnesak`, procesno stanje ili kapiju (63 fajla):
  **775 passed, 29 skipped, 0 failed**;
- V2 Playwright `frontend-v2-ng/tests/live-nacrt.mjs`: **54/54 PASS**, uključujući nov scenario:
  - DOCX nacrta iz spisa ide preko servera, a ne iz polja za tekst;
  - čuvar mesta → 409 sa porukom;
  - posle razrešenja: PATCH pa DOCX, a izvezen je samo tekst za sud.

**Mutacije 26/26 uhvaćene stvarnim `failed`, bez `error`** (`strukturalno/t02/t02_mut.json`, `t02_mut_out.txt`,
`t02b_mut*`; fajlovi vraćeni bajt-identično). Pokrivaju:
- neutralizaciju granice i čuvara mesta iz izlaza modela;
- izvoz bez jedinstvene granice ili sa čuvarom mesta;
- svaku kategoriju kapije: uplata, rok, pravosnažnost, buduće izvršenje, uslovna odluka, nepotrebnost (bez
  priznanja i nikad), sopstvene reči, svaka parafraza „potvrđena“, utvrdio, odustanak, nepoznato ročište;
- interne redove u tekstu za sud;
- napomene bez izostavljenog;
- najstrožu kapiju pri nepouzdanom stanju;
- odsečen i prazan odgovor;
- nacrt bez internog dela;
- `procesno=False`;
- opšti izvoz sa granicom;
- DOCX sa pregleda bez vlasnika ili ceo tekst.

X7, X8 i X15 u prvom krugu nisu bile uhvaćene, jer je svaki postojeći primer hvatao i neko drugo pravilo. Dodati su
čisti primeri (jedno pravilo po primeru), pa su sve tri uhvaćene.

**Pun paket** (`tests`, `-p no:randomly`, OCR uključen; `strukturalno/t02/pun_paket_*`):

| | zbir |
|---|---|
| HEAD | 24 failed, 11.887 passed, 374 skipped, 2 xfailed |
| osnova `caa997c4` (privremeni worktree, isto okruženje) | 23 failed, 11.840 passed, 374 skipped, 2 xfailed |

- **Svih 23 padova osnove su isti na HEAD-u.** Jedini dodatni pad na HEAD-u je
  `tests/test_website_v2_remediacija.py::test_dve_istovremene_prijave_iste_adrese` (istovremena prijava na sajtu).
- Taj fajl ne dira nijedna izmena ovog zadatka. Pokrenut 6× zasebno na HEAD-u i 6× na osnovi: 69/69 svaki put.
- Zaključak: nestabilan test u dugom paketu, a ne regresija.
- +47 prolaza su novi testovi.

### Invarijante

| invarijanta | kako |
|---|---|
| izolacija zakupca | isti upiti i ista provera vlasništva; `utvrdi` odbacuje tuđ red; audit upit filtriran po `user_id`; DOCX sa pregleda samo vlasnik (test: tuđ → 404) |
| provenanca na nivou dokumenta | svaki izvod nosi `DOK-nn`, `dokument_id`, sha256 i položaj; u tekst za sud ide samo doslovan izvod sa oznakom dokumenta |
| bez izmišljenog prava, rokova i dokaza | rok, uplata, izvršenje i pravosnažnost nikad nisu utvrđeni; tvrdnja o njima se izostavlja kad je kapija prepozna (pravilo predmeta + detektori); čuvar citata nepromenjen |
| bez nepotvrđene uplate | detektor uplate (glagoli i imenice) i pravilo predmeta za nalog o predujmu izostavljaju tvrdnju o uplati, pripisan navod stranke ne oslobađa uplatu osim ako izvod dokumenta stranke sadrži istu tvrdnju (3. krug, B1); pokrivenost meri TASK-03 |
| bez samostalnog podnošenja ili slanja | ništa se ne šalje; nacrt ide samo na postojeći pregled |
| postojeći pregled i odobravanje | isti `staging_memory`, PATCH i approve/reject; DOCX samo iz sačuvanog teksta |
| idempotentnost i ograničen trošak | jedan poziv modela po nacrtu (bez ponavljanja); neuspeh razdvajanja se ne naplaćuje; postojeći prozor protiv duplog upisa na pregled je nepromenjen; +500 `max_tokens` |
| nepoverljiv tekst dokumenta nije instrukcija | stanje je u granici poverenja; izvodi i napomene modela su neutralisani (granica, čuvar mesta) |
| bez redizajna frontenda | samo grana izvoza u `docx()` i poruka za 409 |

### Ograničenja i dug (obelodanjeno)

1. Kapija je heuristika nad rečenicama. Izostavljanje legitimnog teksta i propuštene tvrdnje meri TASK-03. Tihi
   promašaj ostaje moguć za tvrdnju bez prepoznatljivog oblika.
2. ~~`/run-parallel` nacrt nije zaštićen~~ → posle GATE-02 (1. prolaz) `/run-parallel` odbija `drafting` uz
   predmet (422, pre modela i naplate). Nacrt iz spisa ide samo kroz `/run`, a `/pipeline` ga poziva.
3. Stari C3 delovi (`_procesno_stanje_za_nacrt`, `_protivreci_odlukama`, `_oznaci_protivrecnosti`, `_RE_SAMO_OZNAKA`,
   `_odluke_suda` u izvorima) više nisu na putu nacrta iz spisa. Ostaju samo zbog postojećih čistih testova, kao dug
   za uklanjanje.
4. Advokat koji iz nacrta obriše granicu ne može da izveze DOCX (409) dok je ne vrati ili ne izradi nacrt ponovo.
   To je namerno: razdvajanje se ne pogađa.
5. Legacy `/app-legacy` (`static/vindex.js`) izvozi preko opšte rute. Tekst sa granicom tamo dobija 409, kao i na
   `/export/docx` (`routers/export.py`, dodato posle GATE-02).
7. Dokument predmeta koji je otpremio drugi korisnik (saradnik) `utvrdi` odbacuje, pa stanje dobija `greska` i
   kapija radi najstrože (GATE-02 N8). Smer je bezbedan, ali je moguće suvišno izostavljanje.
8. Advokat može ručno da prepravi čuvar mesta da izgleda drugačije (na primer bez zagrade) i tako izveze tekst.
   To je njegova izričita radnja (GATE-02 N7); mala i velika slova se sada ne razlikuju.
6. Smart Intake potvrda vrste se ne računa (TASK-01, ograničenje 5). Potvrđen rok (`rok_potvrda`) se ne koristi.

**Independent reviewer finding:** _(upisuje se posle GATE-02)_

**Independent reviewer finding:** 1. prolaz **FAIL** (recenzent GATE-02, `18a235a6`). Razdvajanje i DOCX su ispravni
(vlasnik, 404, jedna granica, 409, neutralizacija u napomenama, V2 minimalno), testovi 213/213, `live-nacrt` 54/54.

Blokirajući nalazi:
- **B1:** nepotvrđena uplata prolazi kao imenica ili parafraza: „Uplata predujma je izvršena.“, „izmirio“, „položio
  na račun“, „deponovan“, „postupio po [[PS-02]]“. Ledger je tvrdio „uvek izostavlja“.
- **B2:** prirodne parafraze svih pet poznatih klasa prolaze (kapija je fail-open):
  - nalog: „… te je ista izgubila svrhu“, „neće se sprovoditi“, „opozvao“, „van snage“;
  - C2: „treba odbiti kao neosnovan“, „ne postoje razlozi“;
  - rok: „je prošao“, „zakasnio“;
  - izvršenje: „podneo/priložio dnevnik“;
  - pranje oznakom dokumenta: „… i tužbeni zahtev (DOK-07)“, „sud potvrdio …“, „[[PS-04]] i time potvrdio“;
  - prelom reda.

  Predlog recenzenta: pravilo po PREDMETU naloga umesto spiska reči.

Neblokirajući nalazi:
- N1: lažan razdelnik oznake daje pad kapije POSLE naplate;
- N2: oznaka nepostojećeg događaja ide u DOCX;
- N3: `/run-parallel` nije zaštićen;
- N4: `/export/docx` bez provere granice;
- N5: pripisan navod stranke bio je izostavljen;
- N6: lažna granica sličnog izgleda;
- N7: čuvar mesta osetljiv na velika i mala slova;
- N8: dokument saradnika daje najstroži režim.

→ Unete ispravke (izvršilac):
- **Kapija prepisana oko PRAVILA PREDMETA** (`_razlog`). Rečenica o predmetu naloga suda čije stanje nije utvrđeno
  ostaje samo kao:
  - doslovan izvod;
  - potvrđena parafraza: ceo predmet posle glagola u izvodu, bez oznake bar 2 osnove, a glagoli „potvrdio“,
    „opozvao“, „zaključio“ i slični nikad;
  - pripisan navod stranke uz oznaku dokumenta (u 3. krugu suženo na proveren izvor stranke, vidi B1 2. prolaza);
  - stav ili predlog stranke uz pozivanje na odluku.

  Isto važi za predmet ročišta čiji ishod nije poznat (samo uslovno ili kao preneseni navod).
- **Detektori po rečima su dopunjeni i ostaju kao drugi sloj:**
  - uplata (imenice, „izmirio/položio/deponovan“);
  - „nije učinio“;
  - rok („prošao“, „zakasnio“);
  - nepotrebnost („izgubila svrhu“, „neće se sprovesti“, „neosnovan“, „van snage“, „opozvan“);
  - izvršenje uz oznaku naloga.
- **Ostale ispravke:**
  - rečenica preko preloma reda (red koji počinje malim slovom nastavlja rečenicu);
  - ćirilica se preslovljava;
  - nepostojeća oznaka izostavlja rečenicu;
  - U+2063 i lažna ili slična granica se neutrališu;
  - čuvar mesta se prepoznaje bez obzira na velika i mala slova;
  - kapija ide PRE naplate, a njen pad vraća 502 bez naplate;
  - `/run-parallel` odbija `drafting` uz predmet;
  - `/export/docx` odbija granicu;
  - suvišan skup reči plaćanja je uklonjen (mutacija Y27 pokazala da ga izvod i detektor već pokrivaju).
- Sve probe recenzenta su postale regresije (30+ primera, uključujući legitimne parove).

**Posle 2. kruga:**
- Testovi `c3b_nacrt_za_sud` 85 (+ 8 OCR rute), `c3`, `t06`, `c4`, `t10`: **110 passed**.
- Širi skup (71 fajl: savetnici, pregled, DOCX, `/export`, `/api/podnesak`, stanje, kapija): **1.164 passed, 29
  skipped, 2 xfailed, 0 failed**.
- `live-nacrt` **54/54**.
- Mutacije `strukturalno/t02/t02c_mut*`, `t02d_mut*`: **35/35 stvarnim `failed`**. U prvom krugu 9 mutacija sloja
  detektora nije bilo uhvaćeno, jer je svaki primer hvatalo i pravilo predmeta. Dodati su primeri u kojima okida samo
  taj sloj, pa su sve uhvaćene.
- Pun paket nije ponovljen posle 2. kruga (poslednji je bio na `18a235a6`: 0 novih padova). Promene posle toga su
  pokrivene skupom od 71 fajla.

**U uzorku t03** (nije dokaz; `kapija_t03_izlaz.txt` ponovljen):
- Uklonjene su sve slepo označene tvrdnje O1 i R u C1, H2, pre A i pre C1.
- **U posle A ostaju 4 O1 (#0, #4, #5, #11).** Sve su oblika „Iako je sud prihvatio predlog za dopunu (DOK-07),
  tužilac smatra da dopuna nije potrebna jer …“, što je recenzent GATE-03 prethodnog sprinta izričito ocenio kao
  dopušten pripisan argument. Ostaju namerno (merilo 6: legitiman argument se ne suzbija).
- H2 #7 je greška merenja: citat počinje prethodnom rečenicom, a sporna rečenica je uklonjena.
- Neuklonjeno ostaje i prećutkivanje bez oblika (C2 #11, C1 #8, C1 #14).
- Na starim nacrtima (bez oznaka) kapija izostavlja oko 3–5 rečenica po nacrtu. Suzbijanje se meri na novom toku u
  TASK-03.

### GATE-02 — 2. prolaz recenzenta (HEAD `3b3d7f77`): **FAIL**

Svih 60 primera iz 1. prolaza recenzent je potvrdio kao zatvorene; razdvajanje i DOCX potvrđeni ispravnim.
Recenzent je pokrenuo 11 fajlova (258 passed) i `live-nacrt` 54/54. Probe: `strukturalno/t02/gate02_probe/probe4.py`,
`probe5.py`.

BLOKIRAJUĆE:
- **B1. „Pripisan navod“ nije proveravan prema izvoru.** `preneseno` = glagol navođenja + **bilo koja** oznaka
  `DOK-nn`/`[[PS]]`, bez provere da dokument postoji, da je dokument stranke i da izvod sadrži tvrdnju. Taj izuzetak
  gasio je detektore uplate, izvršenja i roka i pravilo predmeta („Tužilac u podnesku (DOK-99) navodi da je uplatio
  predujam.“ ostajalo je u tekstu za sud). Isto je važilo za izuzetak „stav uz priznanje odluke“ („Iako je sud
  [[PS-05]], tužilac ističe da je rok istekao.“). Test je zaključavao takav primer kao legitiman.
  **Tvrdnja ovog ledgera iz 2. kruga („osim izričitog navoda stranke uz oznaku dokumenta“) bila je preširoka.**
- **B2. Zamenica posle rečenice o nalogu nosila je stanje** („… [[PS-05]]. Isti je dostavljen.“, „To je urađeno.“,
  „Tuženi nije postupio.“, „Tih 15 dana je prošlo.“).

NEBLOKIRAJUĆE: sinonimi predmeta („knjiga gradilišta“, „dodatna ekspertiza“), parafraza sa podskupom osnova uz
[[PS]] i u sadašnjem vremenu, prekomerno izostavljanje legitimnog teksta, N7 (čuvar bez zagrade posle ručne izmene).

→ **Unete ispravke (3. krug, izvršilac):**
- **Pripisivanje se proverava prema izvoru:**
  - `preneseno` važi samo ako rečenica nosi [[PS]] događaja stranke, ili `DOK-nn` dokumenta stranke/veštaka koji
    postoji u pročitanom spisu. `procesno_stanje.utvrdi` zato sada vraća i spisak `dokumenti` (oznaka, akter);
  - izvor mora da deli predmet sa rečenicom;
  - uplata, izvršenje/ispunjenje, rok i odustanak **nikad** se ne oslobađaju samim glagolom navođenja ni stavom
    stranke: rečenica ostaje samo ako izvod tog izvora sadrži istu tvrdnju iste grupe radnje (`_izvor_kaze`);
  - „izričito priznanje odluke“ (`priznaje_jasno`) više nije bilo koja oznaka DOK: traži sudski tok, potvrđenu
    parafrazu ili reč odluke/naloga/rešenja/zapisnika uz oznaku.
- **Zamenice i rečenice bez predmeta:** predmet prethodnog segmenta se prenosi kada je u stanju nalog
  (`prethodni_predmet`) i rečenica nema svoj sadržaj ili počinje anaforom („isti“, „to“, „ona“, „takva radnja“…).
  Glagoli stanja (dostavljen, izvršen, urađen, sproveden, postupio, ispunjen, istekao, prošlo, završio, obavio,
  učinio, pasivan, nije preduzeo) uz postojeći nalog se ne oslobađaju bez potvrde iz izvoda.
- **Detektor pravnog dejstva** (prestala da važi, bez dejstva, ukinut, van snage, opozvan, otpala, neće se
  sprovesti) — uz nalog ili prenesen predmet, i ako je pripisan stranci.
- **Uplata drugim rečima** (obezbeđen novac, prenet iznos, namirio obavezu, snosio troškove) — samo kada postoji nalog
  o uplati.
- **Sinonimi predmeta** („knjiga gradilišta“, „dnevnik radova“, „dodatni/dopunski/novi nalaz, ekspertiza“).
- **Parafraza:** uloge stranaka moraju se poklopiti sa izvodom, a opšte reči (veštak, predmet, tužba, iznos…) ne
  računaju se kao razlikujuće; sadašnje vreme glagola se hvata.
- Sve probe 4 i 5 su postale regresije, uključujući legitimne parove (pripisan argument uz priznanje odluke,
  prigovor/predlog, opis činjenica, pravna argumentacija).

**Posle 3. kruga:**
- `tests/test_mir001_c3b_nacrt_za_sud.py`: **132 passed, 8 skipped** (bez OCR).
- Širi skup (71 fajl, OCR uključen): **1.211 passed, 29 skipped, 2 xfailed, 0 failed**
  (`strukturalno/t02/t02_siri3.txt`).
- `live-nacrt` **54/54**.
- Mutacije `strukturalno/t02/t02e_mut*`: 47 mutacija, u prvom pokretanju 44 uhvaćene. **Y13** (nepotrebnost uz bilo
  kakvo priznanje), **Z2** (navod bez provere izvora) i **Z5** (bez prenosa predmeta na zamenicu) nisu bile uhvaćene,
  jer je svaki primer hvatao i drugi sloj. Dodata su tri primera sa jednim pravilom; ponovljeno u `t02f_mut*`:
  **3/3 stvarnim `failed`**. Ukupno **47/47**; fajlovi vraćeni bajt-identično.
- Probe recenzenta 4 i 5 na novom kodu: svi BLOKIRAJUĆI primeri izostavljeni; legitimni pripisani argumenti
  zadržani.

**Preostalo, otkriveno (NEBLOKIRAJUĆE, meri TASK-03):**
- Prekomerno izostavljanje: „Građevinski dnevnik je ključan dokaz o redosledu radova.“ i „Tužilac smatra da
  građevinski dnevnik nije od značaja …“ izostavljaju se (pravilo predmeta). Ishod je bezbedan (čuvar mesta je vidljiv i
  blokira izvoz), ali advokat mora ručno da vrati tekst.
- N7: čuvar mesta koji advokat ručno prepiše bez zagrade više se ne prepoznaje pri izvozu. To je ljudska izmena posle
  pregleda, ne izlaz modela.
- Pokrivenost detektora po rečima je konačna; kapija ne dokazuje da prirodan jezik nema drugih oblika. To meri slepi
  TASK-03.

### GATE-02 — 3. prolaz recenzenta (HEAD `7b2ac201`): **FAIL**

Recenzent je potvrdio da su probe 1–5 zatvorene i da realan A podnesak od 10 rečenica prolazi bez izostavljanja.
Pokrenuo je 11 fajlova uz OCR (305 passed, 0 skipped) i `live-nacrt` 54/54. Probe: `strukturalno/t02/gate02_probe/probe6.py`,
`probe7.py`.

BLOKIRAJUĆE:
- **B1. Provera izvora nije gledala polaritet.** Izvod „Tuzilac navodi da **nije** uplatio predujam“ potvrđivao je
  rečenicu „Tužilac u podnesku (DOK-08) navodi da **je uplatio** predujam“, jer `_RE_UPLATA` hvata i „nije uplatio“.
  Isto za „nije dostavio“. **Tvrdnja 3. kruga ovog ledgera („ostaje samo ako izvod tog izvora sadrži istu tvrdnju“)
  bila je netačna.**
- **B2. Interne napomene u tekstu za sud su curile u DOCX.** Premeštan je samo red sa markerom; redovi ispod naslova
  („NAPOMENA ZA ADVOKATA:\n- Model nije pročitao DOK-03.“) ostajali su u tekstu za sud i izvozili se. Naslovi u
  množini i varijante („INTERNE NAPOMENE:“, „Napomena:“, „UPOZORENJE ZA ADVOKATA:“) nisu prepoznavani. Postoji od 1.
  kruga. **Zapis 2. prolaza „razdvajanje i DOCX potvrđeni ispravnim“ bio je nepotpun** (recenzent je to sam naveo).
- **B3. Zamenica uz glagol van spiska** („Tuženi je dokument predao.“, „Tražena isprava je stigla u sud.“, „Sud je
  dokument primio.“) posle naloga za dostavu.

NEBLOKIRAJUĆE: N1 dve tvrdnje u rečenici (drugu izvor ne potvrđuje); N3 „On je uredno platio cenu radova.“ se
izostavlja i bez naloga o uplati (detektor uplate je bezuslovan); N4 prekomerno izostavljanje u kratkom H2 podnesku (3
od 4 rečenice); N5 lažna granica sličnog izgleda ide u DOCX kao „(natpis uklonjen) …“; N6 čuvar bez zagrade posle
ručne izmene.

→ **Unete ispravke (4. krug, izvršilac):**
- **B1:** `_izvor_kaze` sada traži i isti **polaritet** (`_polaritet`): pojava tvrdnje je odrečna ako sama sadrži
  „nije/ne/niti“ ili joj u prethodne tri reči prethodi negacija. Polaritet rečenice mora biti podskup polariteta
  izvoda. „Navodi da nije uplatio“ uz izvod „nije uplatio“ ostaje; „navodi da je uplatio“ uz isti izvod se izostavlja.
- **B2:** red sa markerom napomene nosi sa sobom redove koji ga nastavljaju: posle naslova koji se završava sa „:“ sve
  do praznog reda, a inače stavke liste (`-`, `•`, `*`, `1.`). Takav blok (i red lažne granice, N5) ide u interne
  napomene, a **na njegovom mestu ostaje čuvar mesta, pa izvoz u DOCX ostaje blokiran dok advokat ne razreši mesto**.
  Jedan izolovan red napomene (npr. „⚠️ …“) se i dalje samo premešta. Prepoznaju se množina i varijante naslova.
  Oznaku mesta bloka (U+2064) piše samo server; iz izlaza modela se uklanja.
- **B3:** glagoli predaje i prijema (predao/predat, stigla/stigao, primio/primljen, zaprimljen) su glagoli stanja, a
  „tražena/pomenuta/navedena …“ preuzima predmet prethodne rečenice.
- Sve probe 6 i 7 su pokrenute na novom kodu: B1 (negacija i namera u izvodu) i B3 se izostavljaju; legitiman navod
  istog polariteta ostaje.

**Posle 4. kruga:**
- C3b skup (6 fajlova, OCR uključen): **237 passed**.
- Širi skup (71 fajl, OCR uključen): **1.227 passed, 29 skipped, 2 xfailed, 0 failed** (`strukturalno/t02/t02_siri4.txt`).
- `live-nacrt` **54/54**.
- Nove mutacije `strukturalno/t02/t02g_mut*`: 11, u prvom pokretanju 9 uhvaćenih; G4 (naslov sa „:“ ne nastavlja
  blok) i G11 (oznaka bloka iz izlaza modela) bez testa. Dodat test sa jednim pravilom, ponovljeno u `t02h_mut*`:
  **2/2**. Ukupno **11/11** stvarnim `failed`.
- Ranijih 47 mutacija ponovljeno na novom kodu (`t02e2_mut_out.txt`, `t02e3_mut*`; Y23, Z3 i Z4 preusmereni na izmenjene redove): 45 uhvaćeno u prvom pokretanju. **Z3** (izvor ne mora da sadrži tvrdnju) i **Z4** (izvor druge grupe radnje) više nisu bili uhvaćeni, jer ih nova provera polariteta pokriva u svim postojećim primerima. Dodata su dva primera u kojima odlučuje samo taj sloj (`propustio` nije glagol stanja; uvid ≠ dostava); `t02i_mut*`: **2/2**. Ukupno **47/47**.
- **Sve mutacije TASK-02 posle 4. kruga: 58/58** stvarnim `failed`; fajlovi vraćeni bajt-identično.
- C3b skup posle poslednjih primera (6 fajlova, OCR): **240 passed** (`test_mir001_c3b_nacrt_za_sud.py` 158 testova).

**Preostalo, otkriveno (NEBLOKIRAJUĆE, meri TASK-03):**
- N1: „… navodi da je uplatio predujam, pa dopuna veštačenja može da počne.“ i „… pa tuženi nije ni mogao da postupi po
  nalogu.“ ostaju: druga tvrdnja nije proverena prema izvoru.
- N3: plaćanje ugovorne cene se izostavlja i bez naloga o uplati. Ostavljeno namerno, jer je invarijanta „nema
  nepotvrđenih tvrdnji o uplati“ opšta; ishod je vidljiv čuvar mesta.
- N4: u kratkom H2 podnesku pravilo predmeta izostavlja „Tužilac se izjašnjava povodom zapisnika [[PS-02]].“, „…
  spreman da snosi troškove dopune veštačenja.“ i „Tužilac ostaje pri predlogu da se dopuna veštačenja sprovede u
  celosti.“ Suzbijanje legitimnog teksta meri TASK-03.
- Novi glagoli stanja („primio“) povećavaju izostavljanje rečenica bez sopstvenog predmeta kada nalog postoji
  („Tužilac je primio nalaz veštaka.“). Ishod je bezbedan (čuvar mesta).
- N6 ostaje (ručna izmena posle pregleda).

### GATE-02 — 4. prolaz recenzenta (HEAD `6b4aa0c9`): **FAIL**

Recenzent je potvrdio da su polaritet (B1 3. prolaza) i glagoli predaje (B3) zatvoreni i da nijedan ranije
blokirajući primer iz proba 1–7 više ne prolazi. Pokrenuo je 11 fajlova uz OCR (323 passed) i `live-nacrt` 54/54.
Probe: `strukturalno/t02/gate02_probe/probe8.py`, `probe9.py`.

BLOKIRAJUĆE:
- **B1. Naslov napomene u markdownu ili bez „:“ propuštao je telo napomene u DOCX.** Uz „**NAPOMENA ZA ADVOKATA:**“,
  „NAPOMENA ZA ADVOKATA“ (bez dvotačke) i „### Napomena za advokata“ server je tiho uklanjao naslov, a redovi ispod
  njega ostajali su u tekstu za sud i izvozili se bez čuvara mesta. Uzrok: `naslov = red.rstrip().endswith(":")`.
  **Tvrdnja 4. kruga ovog ledgera („prepoznaju se množina i varijante naslova“; „na njegovom mestu ostaje čuvar
  mesta“) bila je preširoka:** važila je samo za naslov koji se završava sa „:“ i za stavke liste.

NEBLOKIRAJUĆE: N1 polaritet bez modaliteta i sa prozorom od 3 reči („nije u celosti i na vreme uplatio“, „bi uplatio da
je …“, „će proveriti da li je uplatio“, „ni uplatio ni obezbedio nije“); N2 neprepoznati naslovi („NAPOMENA ADVOKATU:“,
„Interna napomena:“ zbog greške `interne?`, „Šta treba proveriti:“, „Ograničenja AI analize:“ …), napomena u istom redu
iza teksta podneska, lista bez naslova i rečenica o AI savetniku; N3 izolovan red napomene premeštan je bez čuvara mesta
(tiha izmena teksta za sud, i za legitiman red „Napomena: tužilac je promenio adresu.“); N5 lažno izostavljanje glagola
predaje je ograničeno; N6 otvoreno iz 3. prolaza.

→ **Unete ispravke (5. krug, izvršilac):**
- **B1:** pre provere reda uklanja se markdown (`* # _ > \``). Red koji je ceo naslov napomene (`_RE_NASLOV`: počinje
  rečju napomene, upozorenja, „interno“, „za advokata“, „za proveru“, „šta treba proveriti“, „proveriti pre
  podnošenja“, „ograničenja“ …, bez kraja rečenice) uvek nosi redove do praznog reda i uvek ostavlja čuvar mesta, sa
  dvotačkom ili bez nje.
- **N3:** svaki premešten tekst ostavlja čuvar mesta (izvoz blokiran), **osim reda koji je samo oznaka AI porekla**
  (⚠️, „generisala je AI“, „izradio AI savetnik“, „ukloniti pre podnošenja“). Takav red se premešta u napomene bez
  čuvara, jer nije tekst podneska.
- **N2:** ispravljeno `interna/interne/interni napomena`; dodati „napomena advokatu“, „napomene za proveru“,
  „napomena (interno)“, „ograničenja … AI“, „model nije pročitao/pregledao/potvrdio“ i napomena u istom redu iza kraja
  rečenice („… zahtevu. Napomena: …“).
- **N1:** polaritet se gleda u **istoj klauzi** (granica: `, ; : . ( )` i „pa, jer, a, ali, te, dok“), do 6 reči pre
  tvrdnje. Uslovna, upitna i buduća pojava („bi“, „da li“, „će“, „ako“, „ukoliko“) dobija oznaku „?“, i takav izvod
  ništa ne potvrđuje.
- Probe 8 i 9 su postale regresije. Na novom kodu svaki oblik naslova iz probe8 blokira izvoz (17 oblika, uključujući
  markdown i naslov bez dvotačke). Izvoz prolaze samo dva reda koji su čista oznaka AI porekla, a oni se premeštaju iz
  teksta za sud. U probe9 svi primeri sa daljom negacijom ili modalitetom se izostavljaju. Legitiman navod istog
  polariteta ostaje.

**Posle 5. kruga:**
- C3b skup (6 fajlova, OCR): **264 passed**.
- Širi skup (71 fajl, OCR): **1.253 passed, 29 skipped, 2 xfailed, 0 failed** (`strukturalno/t02/t02_siri5.txt`).
- `live-nacrt` **54/54**.
- Mutacije `strukturalno/t02/t02j_mut*`: 15 (nove H1–H10 i G1–G5 preusmerene na izmenjene redove). U prvom pokretanju
  9 uhvaćenih. G4, H1, H2, H5, H8 i H9 nisu bile uhvaćene: telo napomene u testovima je bila lista ili rečenica koju već
  hvata drugo pravilo („model nije pročitao“). Dodata su tela napomena bez oznake liste i po jedan primer za svako
  pravilo; ponovljeno u `t02k_mut*`: **6/6**. Y23 je preusmeren na novi red (`t02l_mut*`): uhvaćen.
- Ostalih 46 mutacija iz 3. kruga ciljaju redove koji u ovom krugu nisu menjani, a testovi su samo dodavani. Zato
  nisu ponovo pokretane.

**Preostalo, otkriveno (NEBLOKIRAJUĆE, meri TASK-03):**
- Napomena bez ijednog prepoznatog markera (npr. obična rečenica „Iznos treba uskladiti sa nalazom.“ usred podneska)
  ostaje u tekstu za sud. Vidljiva je advokatu, ali je izvoz ne blokira. Prepoznavanje napomena je konačan spisak oblika.
  Glavna linija razdvajanja ostaje JSON polje `napomene_za_advokata`.
- Polaritet ostaje leksički (klauza, 6 reči, spisak modalnih reči).
- N1 dve tvrdnje u rečenici, N4 prekomerno izostavljanje u kratkom H2 podnesku, N5 i N6 ostaju kako su opisani u 3.
  prolazu.

### GATE-02 — 5. prolaz recenzenta (HEAD `398bedd6`): **PASS**

Recenzent je potvrdio da je B1 4. prolaza zatvoren (naslov napomene u markdownu, bez „:“ i u množini nosi telo i
ostavlja čuvar mesta) i da nijedan ranije blokirajući primer iz proba 1–9 ne prolazi. Proba:
`strukturalno/t02/gate02_probe/probe10.py`.

NEBLOKIRAJUĆE (prenosi se u TASK-03 i dug):
- **N1.** Neprepoznati naslovi napomena („II. NAPOMENE“, „Interne beleške“, „Rizici:“, „Komentar:“, „Note for
  lawyer:“ …) propuštaju svoje telo u tekst za sud **bez čuvara mesta**. Nijedan takav oblik se ne javlja u 120
  stvarnih nacrta iz TASK-02, ali je spisak oblika konačan. Glavna linija razdvajanja je JSON polje
  `napomene_za_advokata`, a prepoznavanje oblika u tekstu je druga linija.
- **N2.** Zarez prekida negaciju („nije, zbog bolesti, uplatio“ se čita kao „+“); ugnežđeno „lažno tvrdi“ se ne vidi.
  Polaritet je leksički.
- **N3.** Red teksta podneska koji sadrži oznaku AI („Tuženi je izvođač ⚠️ i odgovara …“) premeštan je **tiho, bez
  čuvara mesta**. Zato je tvrdnja 5. kruga ovog ledgera („osim reda koji je samo oznaka AI porekla“) bila netačna: uslov
  je bio „red sadrži oznaku AI“, a ne „red je samo oznaka AI“. → **ispravljeno, vidi ispod.**
- **N4.** Raniji dug ostaje: prekomerno izostavljanje („Tužilac je primio nalaz veštaka.“, 3 od 4 rečenice kratkog H2
  podneska), dve tvrdnje u jednoj rečenici, čuvar mesta koji advokat prepiše bez zagrada (N6).
- **N5.** Pre TASK-03 ponoviti sve mutacije nad `_RE_INTERNO`, `_izvor_kaze` i petljom blokova. Obrazloženje 5. kruga
  („46 mutacija cilja nemenjane redove, zato nisu ponovo pokretane“) bilo je preširoko: petlja blokova i polaritet
  jesu menjani, a novi testovi mogu promeniti koje pravilo odlučuje. → **ponovljeno, vidi ispod.**

→ **Ispravka posle 5. prolaza (izvršilac):**
- **N3:** red se premešta bez čuvara mesta samo kada je ceo red rečenica o samom nacrtu (`_RE_RED_O_NACRTU`: počinje sa
  ⚠️, sa „ovaj/ovo nacrt/tekst/dokument/podnesak/odgovor“, „generisao/izradio“ ili „ukloniti pre podnošenja“, i ima
  najviše jednu rečenicu) **i** nosi oznaku AI porekla. Svaki drugi red sa oznakom AI dobija čuvar mesta. Regresija:
  `test_red_podneska_sa_oznakom_ai_ne_nestaje_tiho`.
- **N5:** pun skup mutacija TASK-02 ponovljen nad konačnim kodom (`strukturalno/t02/t02m_mut.json`,
  `t02m_mut_out.txt`, `gradi_t02m.py`). Sastav: 47 iz 3. kruga (Y23, Z3, Z4 preusmereni), 15 iz 5. kruga (G5, H3, H4
  preusmereni na red N3), G9–G11 i nova **H11** (red sa oznakom AI se premešta bez čuvara). **66/66 uhvaćeno stvarnim
  `failed`, 0 `error`**; fajlovi vraćeni bajt-identično.
- N1, N2 i N4 nisu menjani. Prijavljuju se kao dug, a TASK-03 meri da li se javljaju u stvarnim izlazima.

**Posle ispravke N3:**
- C3b skup (6 fajlova, OCR): **266 passed**.
- Širi skup (71 fajl, OCR): **1.255 passed, 29 skipped, 2 xfailed, 0 failed** (`strukturalno/t02/t02_siri6.txt`).
- `live-nacrt` **54/54**.

**GATE-02 ishod: PASS (5. prolaz), uz ispravku N3 i ponovljene mutacije N5.** Sledi TASK-03 (prethodna registracija:
`strukturalno/t03/PREREGISTRACIJA.md`, commitovana pre prvog poziva modela).

## TASK-03 — slepa ocena stvarnih izlaza (2026-10-24)

Prethodna registracija `strukturalno/t03/PREREGISTRACIJA.md` (commit `78301e71`) prethodi prvom pozivu modela.
Odstupanja: `strukturalno/t03/ODSTUPANJA.md` (prvo pokretanje bez poziva zbog mrežnih brana u testovima; zaseban
agent po delu; DOCX posle simulirane ispravke dodat paketu).

- **Generisanje:** 10 scenarija × 10 = 100 stvarnih gpt-4o izlaza kroz `POST /api/agents/run` (`izlazi/`). 100/100
  vraća 200; po 1 poziv modela i 1 naplata. 94 izlaza imaju čuvar mesta (DOCX 409), 6 nemaju (DOCX 200).
- **Mehaničke provere** (`mehanicke_provere_rezultat.json`): granica, čuvari mesta, `[PROVERITI`, `[[PS-` i interni
  redovi se nikad ne javljaju u DOCX-u. Posle simulirane ispravke 2/100 (H1_09, N1_00) i dalje vraća 409, zbog
  `[PROVERITI: adresa]` usred reda zaglavlja.
- **Slepa ocena:** 2 označivača (A, B), po 4 dela od 25, svaki deo zaseban agent. Paketi, ključ i oznake su u
  `strukturalno/t03/slepo/`, a spoj u `spojeno_t03.json`. Prijavljeno je 275 nalaza: M6 172, M8 56, M1 22, M5 11,
  M7 11, M2 2, M3 1.
- **GATE-03, nezavisni recenzent** (`strukturalno/t03/GATE03_RECENZIJA.md`): **C3B_FAIL.**
  - Pod pravilom potvrde ostaju potvrđeni materijalni nalazi u 24 izlaza; i pod najužim tumačenjem ostaje 13.
  - **M1 (12):** iznos zahteva pogrešno prikazan, „4.200.000 dinara, koji uključuje i dodatni zahtev … 600.000“, uz
    izvod koji server umeće i koji to opovrgava („Tuzilac dodatno trazi 600.000“). Primeri: B_00, B_02–B_05, B_07,
    B_08, C2_00, C2_05, N1_07; zatim C2_01 i N4_06.
  - **M2 (1):** N4_06.
  - **M5 (7):** pogrešan izvod uz tvrdnju (N1_05, N1_07); dopis suda DOK-09 prećutan (N3_01–N3_03).
  - **M7 (9):** u N2 je naveden samo kasniji „odbija“, a prihvatanje od 15.07. je prećutano (N2_01, N2_02, N2_04);
    nečitljiv zapisnik (N1_00, N1_08); C2_01, C2_03, C2_04, N3_01.
  - **M8:** svaki izvezen DOCX ima naslov „NACRT IZ SPISA (SAVETNIK)“, koji upisuje izvoz
    (`routers/drafting.py:1243`, naziv sa pregleda), a ne model.
  - **M3 i M4: 0 potvrđeno.** Kapija je izostavila svaku izmišljenu uplatu i tvrdnju o roku.
  - **P1 FAIL, P2 PASS, P3 FAIL (naslov), P4 FAIL** (suzbijanje u > ½ izlaza u 9/10 scenarija, oba označivača),
    **P5 nije doslovno ispunjen** (98/100). Ostatak funkcionalnosti radi.
  - Neki potvrđeni nalazi su izvezeni bez ikakve blokade (B_03, N1_05, N1_08, C1_03).
- **Dijagnoza (recenzent; izvršilac je proverio B_00, N2_01 i poreklo naslova):**
  - D1: procesne radnje stranaka (dodatni zahtev, preciziranje, povlačenje) nisu stanje u `procesno_stanje`, pa kapija
    nema s čim da uporedi iznos.
  - D2: server umeće izvod za oznaku `[[PS-nn]]` koju je izabrao model, bez provere da izvod potvrđuje rečenicu.
  - D3: kapija ne čita spornost koju `procesno_stanje` već utvrđuje (N2); izuzetak „stav stranke + citirana odluka“
    pušta jednostranu tvrdnju.
  - D4: pripisan navod stranke prolazi, a opis akta suda ne prolazi (DOK-09 je uklonjen u svih 10 N3).
  - D5: nečitljiv zapisnik ne pooštrava kapiju.
  - D6: sama reč „ročište“ ili „zapisnik“ važi kao uslov.
  - D7: prekomerno brisanje (povlačenje zahteva čita se kao „odustanak“, „veštak nije izvršio uvid“ kao izvršenje
    naloga, „u roku od N dana“ kao rok).
  - D8: naslov i podnožje DOCX-a upisuje izvoz.
  - Zajednički uzrok: kapija je leksička heuristika koja **istovremeno propušta i prekomerno briše**. Još jedan krug
    istih detektora ili instrukcija modelu nije sledeći korak. To je arhitektonska odluka osnivača (npr. tekst za sud
    sastavljen iz strukturisanih, serverom proverenih tvrdnji umesto filtriranja slobodnog teksta; ručna potvrda
    stanja pre izrade nacrta).
- **Nedostaci merenja (recenzent; ishod ne zavisi od njih):**
  - označivači su instance istog modela;
  - ključ je bio čitljiv u folderu iznad paketa (nema dokaza da je čitan);
  - opseg M8 se razlikovao po delovima;
  - podnožje DOCX-a nije izvučeno;
  - simulirana ispravka briše cele redove;
  - označivači su propustili neke nalaze iste klase.

**Ishod TASK-03 / GATE-03: `C3B_FAIL`.** C3b **nije** pogodan za pregled kontrolisanog produkcionog puštanja i ostaje
blokiran. Paket za pregled puštanja nije pripremljen (pravi se samo uz PASS). Ništa nije pushovano, spojeno ni
pušteno. Kod proizvoda posle GATE-02 nije menjan. U skladu sa misijom nije pokrenuta nova petlja instrukcija ni
ponovno pisanje modelom.
