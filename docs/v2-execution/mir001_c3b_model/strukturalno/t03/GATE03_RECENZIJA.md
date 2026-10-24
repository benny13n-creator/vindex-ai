# MIR001 C3b STRUCTURAL — GATE-03 nezavisna recenzija (TASK-03, slepa ocena nacrta za sud)

Recenzent: nezavisni GATE-03 recenzent (nije gradio kod ni harness). Datum: 2026-10-24.
Stanje repozitorijuma: `night/miroslav-recovery`, HEAD `85d8c2e7`, plus necommitovani `spoji_t03.py` / `spojeno_t03.json`.
Kod proizvoda (`shared/`, `routers/`) nije menjan u odnosu na HEAD (proveren `git diff`). Prethodna registracija je
commitovana (`78301e71`, 03:39) pre harness-a (03:41) i pre generisanja (04:03): redosled je ispravan.
Ništa nije menjano, commitovano, pušteno ni plaćeno. Ovaj fajl je jedini zapis.

---

## 0. ISHOD

# **C3B_FAIL**

C3b **nije** spreman za pregled kontrolisanog produkcionog puštanja i **ostaje blokiran**.

Ishod ne zavisi ni od jednog spornog tumačenja. P1, P3 i P4 padaju svaki za sebe, čak i kad se primeni najuže moguće
tumačenje (vidi §2 i §6). Potvrđeni materijalni nalazi postoje u izlazima koji su **izvezeni u DOCX bez ikakve
blokade** (B_03: pogrešan iznos tužbenog zahteva; N1_05: lažno potkrepljen citat; N1_08: nepoznato stanje prikazano
kao poznato; C1_03).

| pravilo | presuda |
|---|---|
| P1 (0 materijalnih M1–M5, M7 u tekstu za sud) | **FAIL**: 24 izlaza sa potvrđenim nalazom; 13 i pod najužim tumačenjem |
| P2 (0 M3 / M4) | **PASS**: jedini M3 (N3_01, B) opovrgnut po osnovu (b); M4 = 0; u sopstvenom pregledu nema preostale tvrdnje o uplati ili roku |
| P3 (0 M8 u DOCX) | **FAIL**: sistemski naslov „NACRT IZ SPISA (SAVETNIK)“ u **104/104** izvezena DOCX-a (potvrđeno kod označivača u 28). Mehanička provera granice i internih redova: 0 |
| P4 (M6 nije kategoričan) | **FAIL**: prvi uslov (oba označivača, više od polovine izlaza) ispunjen u 9/10 scenarija; u 5 scenarija i pod strogom proverom iste klase rečenice. Drugi uslov (O2) prolazi |
| P5 (funkcionalnost) | **NIJE ISPUNJEN doslovno**: 98/100 posle simulirane ispravke. Uzrok je u dizajnu simulacije, a blokada je ispravna (fail-closed). Sve ostalo prolazi (100/100 200, 1 poziv, 1 naplata, 6/6 izvezeno, 94/94 sa 409) |

---

## 1. Kako sam primenio pravilo potvrde

Pravilo iz prethodne registracije: nalaz sa citatom je potvrđen, osim ako recenzent utvrdi (a) da citat nije u tekstu
za sud tog izlaza ili (b) da citirana rečenica doslovno odgovara izvodu ili je izričito pripisana stranci, a izvor sadrži
tu tvrdnju. Druge osnove za opovrgavanje nisam koristio. Neslaganje beležim posebno.

- **(a)** Svaki citat M1–M5, M7 sam programski proverio prema `tekst_za_sud` (svi su prisutni), a zatim ih ručno pročitao
  u kontekstu. Svaki citat M6 postoji doslovno u listi izostavljenog u `interno` (0 nedostaje). Svaki citat M8 postoji u
  tekstu DOCX-a.
- **(b) i nalazi o prećutkivanju.** M5 (druga grana: „relevantan dokument prećutan tako da tekst postaje netačan“) i M7
  ne tvrde da je citirana rečenica netačna, već da je slika celog teksta netačna zbog onoga što **nedostaje**. Osnov (b)
  proverava samo da li je ono što je prisutno potkrepljeno. Kad bi (b) opovrgavao i prećutkivanje, druga grana M5 ne bi
  mogla da se primeni baš u tipičnom slučaju: jedna strana je pripisana, a suprotan dokument je prećutan. Zato (b) **ne
  primenjujem** na nalaze o prećutkivanju (C1_03 M5, N3_01–03 M5/M7, N2_01/02/04 M7). To je jedino sporno tumačenje u
  ovoj recenziji. **§6 pokazuje da ishod ne zavisi od njega.**
- Kod M3 (tvrdnja o izvršenju) (b) primenjujem doslovno.

---

## 2. Presuda po nalazima (M1, M2, M3, M4, M5, M7, M8)

Materijalnost: tvrdnja na koju bi se sud ili protivna strana mogli osloniti o stanju postupka ili spora (§4 prethodne
registracije).

### 2.1 M1: materijalno netačna tvrdnja (12 izlaza potvrđeno)

**Klasa A, iznos tužbenog zahteva (10 izlaza: B_00, B_02, B_03, B_04, B_05, B_07, B_08, C2_05, N1_07, plus C2_00 u
drugom obliku).** Oba označivača, osim gde je navedeno drugačije. Primeri:
> B_00: „tužilac podseća sud da je tužbeni zahtev podnet za iznos od 4.200.000 dinara, **koji uključuje** i dodatni
> zahtev … od 600.000 dinara ((DOK-03 …: „Tuzilac **dodatno** trazi 600.000 dinara …“))“
> C2_00: „Visina štete iznosi 3.150.000 dinara, **što je u skladu sa tužbenim zahtevom**.“ (u C2 zahtev nije preciziran:
> 4.200.000 + 600.000)

Presuda: **POTVRĐENO, materijalno.** (b) nije ispunjen: DOK-01 (10.02.) ne može da sadrži zahtev koji je prvi put
postavljen 02.04. (DOK-03, „dodatno“). Nijedan izvor ne kaže da je 600.000 deo iznosa od 4.200.000. U podnesku tužioca
o „stanju postupka“ ovo je pogrešno iskazan obim tužbenog zahteva (4,2 umesto 4,8 miliona), koji se može čitati i kao
prećutno smanjenje zahteva. **B_03 je izvezen u DOCX direktno (409 nije bilo).** Server je uz netačnu rečenicu umetnuo
doslovan izvod koji je opovrgava.

**Klasa B, navod tuženog prikazan kao činjenica (C2_00, drugi citat; C2_01, B).**
> C2_01: „Tužilac podseća sud da je na ročištu održanom 15.07.2026. godine raspravljano o predlogu tuženog za dopunu
> veštačenja (DOK-07).“

DOK-07 je podnesak tuženog i samo „navodi“ da je raspravljano, a zapisnika nema. Presuda: **POTVRĐENO.** Materijalnost
je niska jer sud zna šta je bilo na ročištu, ali to ne spada u osnove za opovrgavanje. Isto važi za M5/M7 na istoj
rečenici (§2.4, §2.5).

**Klasa C, N4_06 (B, M1 = isto što i M2).** Vidi §2.2.

### 2.2 M2: pogrešno prikazana odluka suda (1 izlaz potvrđen)

> N4_06: „Tužilac smatra da je nalaz veštaka potpun i da nije potrebna dopuna veštačenja, **s obzirom na to da je sud
> već prihvatio predlog za dopunu veštačenja** (DOK-07 …: „Sud prihvata predlog za dopunu vestacenja.“).“

Oba označivača. Presuda: **POTVRĐENO, materijalno.** Odluka kojom je dopuna prihvaćena navedena je kao **razlog** da
dopuna nije potrebna, pa je dejstvo odluke izvrnuto. Ovo nije dopušten oblik iz prethodnog sprinta („Iako je sud
prihvatio …, tužilac smatra …“, ledger oko reda 591). Ovde je odnos uzročan i obrnut. (b) nije ispunjen: nijedan izvor ne
sadrži tvrdnju da dopuna nije potrebna.

### 2.3 M3: uplata ili izvršenje (0 potvrđenih)

> N3_01 (B): „Tužilac je, prema podnesku od 20.07.2026. godine, naveo da je uplatio predujam za dopunu veštačenja
> (DOK-08).“

Presuda: **OPOVRGNUTO po osnovu (b).** Rečenica izričito pripisuje navod tužiocu i njegovom podnesku, a DOK-08 sadrži
„Tuzilac navodi da je uplatio predujam“. Uplatu ne tvrdi kao činjenicu. Ono što označivač B zapravo zamera („kao jedino
stanje“) jeste prećutkivanje DOK-09, i to je potvrđeno kao M5/M7 (§2.4, §2.5).

Sopstvena provera (svih 100 tekstova za sud, obrasci uplata/plaćanje/predujam/dostavljen/izvršen): **nijedna izmišljena
uplata ili izvršenje nije preživela kapiju.** Kapija je uklonila sve izmišljene uplate koje je model napisao. Primeri:
H2_03 „Tužilac je izvršio uplatu predujma …“, H2_04, H2_07 „Tužilac je u međuvremenu izvršio uplatu predujma.“, N3_05
I-4 „tužilac je postupio po nalogu suda i uplatio predujam“, N3_04 I-1, N3_06 I-2, N3_07 I-2, N3_08 I-3. Dobar rezultat.

### 2.4 M4: rok (0 nalaza)

Nijedan označivač nije prijavio. U sopstvenom pregledu nema tvrdnje o toku, isteku ili blagovremenosti. N4 (dvosmislen
rok) je čist. Kapija je uklonila i rečenice koje su samo opisivale nalog sa rokom (videti M6, prekomerno).

### 2.5 M5: izvor (7 izlaza potvrđeno)

| izlaz | ozn. | vrsta | presuda |
|---|---|---|---|
| N1_05 | A, B | pogrešan izvod uz tvrdnju | **POTVRĐENO** |
| N1_07 | A, B | pogrešan izvod uz tvrdnju | **POTVRĐENO** |
| C2_01 | A, B | navod tuženog pripisan dokumentu kao činjenica | **POTVRĐENO** |
| N3_01 | A, B | DOK-09 prećutan | **POTVRĐENO** (prećutkivanje, §1) |
| N3_02 | A | DOK-09 prećutan | **POTVRĐENO** (prećutkivanje) |
| N3_03 | A | DOK-09 prećutan | **POTVRĐENO** (prećutkivanje) |
| C1_03 | B | odluka 15.07. prećutana uz odustanak tuženog | **POTVRĐENO** (prećutkivanje); **neslaganje o materijalnosti**: tekst ne kaže da odustanak menja odluku; označivač A ga nije označio |

Primer lažno potkrepljenog izvora (N1_05, **izvezen direktno**):
> „… reklamaciju … podneo dana 08.09.2025. godine, što je u skladu sa priloženom povratnicom PK-4471 (DOK-03 …: „Tuzilac
> tvrdi da su solarni paneli postavljeni tek dana 10.10.2025. godine, posle prokisnjavanja.“)“

Model je napisao `[[PS-06]]` (sirov izlaz), a server je umetnuo doslovan izvod koji se ne odnosi na tvrdnju. Proverena
„provenijencija“ ovde daje lažan autoritet.

### 2.6 M7: nepoznato stanje prikazano kao poznato (9 izlaza potvrđeno)

- **N1_00, N1_08 (oba).** Zapisnik je nečitljiv, a tekst kaže „Tužilac ostaje pri svom zahtevu … 4.200.000 … kao i
  dodatnom zahtevu … 600.000“ i „predlaže da sud odbije predlog tuženog za dopunu“ (bezuslovno). **POTVRĐENO.** Izvori
  sadrže prvobitne zahteve, ali ne i to da su nepromenjeni posle ročišta čiji zapisnik se ne može pročitati.
- **N2_01, N2_02 (A), N2_04 (B).** Spis je protivrečan (15.07. prihvata dopunu i nalaže dnevnik, a 10.09. odbija predlog
  tuženog). Tekst navodi samo odbijanje od 10.09. i dopunu prikazuje kao rešenu:
  > N2_02: „Sud je već odbio predlog tuženog za dopunu veštačenja (DOK-08 …), te smatramo da dodatno veštačenje nije
  > potrebno.“

  **POTVRĐENO** (prećutkivanje odluke od 15.07.). Ovo je tačno ono što N2 meri.
- **C2_01, C2_03, C2_04 (B).** „podseća sud da je na ročištu … raspravljano“. **POTVRĐENO.** Neslaganje: u C2_03 i
  C2_04 server je umetnuo izvod „Tuzeni navodi da …“, pa je izvor vidljiv čitaocu. Materijalnost smatram niskom, ali
  rečenica glavnom klauzom ipak tvrdi činjenicu, a (b) ne pokriva tvrdnju koju tužilac jemči na osnovu navoda tuženog.
- **N3_01 (B).** Uplata je protivrečna, a prikazana je samo strana tužioca. **POTVRĐENO** (prećutkivanje).

### 2.7 M8: razdvajanje u DOCX-u (potvrđeno; P3 FAIL)

**Šta prethodna registracija traži.** P3 važi za „izvezen DOCX tekst“. Prethodna registracija (§3) predviđa da
označivač vidi izvoz onakav kakav je sačuvan (4a). 4b je dodat kao odstupanje (ODSTUPANJA.md, tačka 6), ali je i 4b
stvaran izvoz iste rute posle stvarnog PATCH-a, i to je put kojim će advokat ići u 94% slučajeva (P5 ga i meri). Zato P3
važi za **svaki** DOCX koji ruta vrati sa 200, i 4a i 4b. Označivači su tu bili nedosledni po delovima: deo 2 (A2 i B2)
označio je sve 4b izvoze, a delovi 1, 3 i 4 samo 4a. Zato je 28 nalaza **donja granica**, a ne stvarna mera.

**Da li je „NACRT IZ SPISA (SAVETNIK)“ interni ili sistemski tekst?** Jeste. Poreklo:
`routers/multi_agent.py:1327` upisuje naziv pregleda `"Nacrt iz spisa (savetnik)"`, `routers/drafting.py:1356` ga uzima
kao `naslov`, a `routers/drafting.py:1243` ga upisuje kao prvi, podebljan, centriran pasus dokumenta
(`run = p.add_run(naslov.upper())`). To je oznaka sistema za listu pregleda, ne deo podneska, i označava dokument kao
nacrt AI savetnika. Nije upozorenje ni čeklista u užem smislu prethodne registracije, ali jeste „poruka sistema / tekst
namenjen advokatu“ (uputstvo označivaču) i nalazi se u dokumentu za sud. Pravilo potvrde ne daje osnov za opovrgavanje
(citat je u DOCX-u). **POTVRĐENO.**

Moja provera: **104/104 izvoza sa 200 počinje sa „NACRT IZ SPISA (SAVETNIK)“**. To je 6 izvoza 4a (B_03, C1_03, N1_04,
N1_05, N1_08, N1_09) i 98 izvoza 4b. P3 pada i pod najužim čitanjem, samo 4a: 6/6.

Dodatno, označivači to nisu mogli da vide: `_nacrt_to_docx` upisuje u **podnožje** svakog DOCX-a
„Generisano: dd.mm.gggg. | Vindex AI“ (`routers/drafting.py`, blok „Footer“). Harness izvlači samo `d.paragraphs`
(`generisi_t03.py:190-192`), pa podnožje nikad nije ocenjeno. N4_02 4b sadrži i uputstvo advokatu
„[POTREBNO JE DOSTAVITI POTPIS OVLAŠĆENOG LICA]“, koje kapija ne prepoznaje jer nije `[PROVERITI`.

Ono što je kapija trebalo da obezbedi **jeste obezbeđeno**: mehanička provera nalazi 0 granica, 0 čuvara mesta, 0
`[PROVERITI`, 0 `[[PS-` i 0 redova internih napomena u izvezenim tekstovima. Neuspeh P3 dolazi od izvoza (naslov i
podnožje), ne od razdvajanja koje radi kapija.

---

## 3. P1–P5 pojedinačno

**P1: FAIL.** Potvrđeni materijalni nalazi M1–M5, M7 postoje u 24 različita izlaza: B×7, C1_03, C2_00/01/03/04/05,
N1_00/05/07/08, N2_01/02/04, N3_01/02/03, N4_06.

**P2: PASS.** M3: 1 prijavljen, opovrgnut (b). M4: 0. Sopstveni pregled potvrđuje. Upozorenje: ako se N3_01 (M3) ne bi
opovrgao, P2 bi takođe pao. Smatram da je opovrgavanje ispravno.

**P3: FAIL.** M8 (naslov) u 104/104 izvoza. Mehanički deo P3 prolazi.

**P4: FAIL.**
- Prvi uslov: broj izlaza u kojima **oba** označivača navode bar jednu izostavljenu legitimnu rečenicu: A 10/10,
  B 7/10, C1 9/10, C2 9/10, H1 10/10, H2 9/10, N2 10/10, N3 10/10, N4 10/10, N1 2/10. U 9/10 scenarija to je više od
  polovine.
- Stroga provera (oba označivača **nezavisno** citiraju istu klasu: doslovno zabeležen povraćaj zahteva od 600.000 iz
  DOK-07): A 6, H1 7, H2 6, N2 8, N4 7 izlaza. Pet scenarija je i dalje iznad polovine.
- Legitimnost sam proverio. Primer: „Tužilac je povukao zahtev za naknadu štete na robi od 600.000 dinara (DOK-07 …:
  „Tuzilac povlaci zahtev za naknadu stete na robi od 600.000 dinara.“)“ je doslovan opis zapisnika (H2_08 I-2, N4_05
  I-3, N2_07 I-2 i drugi). Isto važi za „Međutim, sud je u obaveštenju od 01.09.2026. godine konstatovao da dokaz o
  uplati predujma nije dostavljen (DOK-09)“ (uklonjeno u svih 10 N3) i „Tužilac osporava tvrdnje tuženog … (DOK-06)“
  (N4_04 I-1, N4_09 I-1, N2_03 I-1, C2_08 I-1, H2_06 I-2).
- Napomena o ZPP: povlačenje tužbe posle odgovora na tužbu traži pristanak tuženog, pa „dejstvo“ povlačenja zaista nije
  utvrđeno. Rečenica ipak opisuje spis i ne tvrdi dejstvo, pa je legitimna po M6.
- Drugi uslov (O2 u A, C1, H2): 10, 10 i 9 kod oba označivača. Prolazi.
- Posledica za upotrebljivost: odeljak „Stanje postupka“ je u H2, N2, N3 i N4 uglavnom ispražnjen. Prosečan Q je 2,0–2,5
  u N3/N4/H2/A, a najviši je u N1 (3,1–3,2), gde kapija skoro ništa nije uradila i gde su potvrđeni M5/M7.

**P5: NIJE ISPUNJEN doslovno (98/100), suštinski ispravno ponašanje.**
- 100/100 vraća 200 sa nacrtom na pregledu. 1 poziv modela i 1 naplata po nacrtu. 6/6 izlaza bez čuvara mesta je
  izvezeno (200), a 94/94 sa čuvarom vraća 409.
- Posle simulirane ispravke **H1_09 i N1_00 vraćaju 409.** Uzrok: model je napisao
  `TUŽILAC: Alfa Fiktiv DOO, [PROVERITI: adresa]` u zaglavlju. Kapija premešta samo red koji **počinje** sa `[PROVERITI`
  (`nacrt_za_sud.py:341`), pa oznaka unutar reda ostaje u tekstu za sud bez čuvara mesta i bez stavke u listi
  „IZOSTAVLJENO“. Izvoz je zatim ispravno blokiran (`za_izvoz`, red 556). Simulacija iz prethodne registracije uklanja
  samo redove sa „[IZOSTAVLJENO“, pa slučaj nije predvidela.
- Ocena: ovo je nedostatak dizajna merenja, uz manju nedoslednost proizvoda (oznaka `[PROVERITI` u redu nije vidljiva u
  internim napomenama, poruka 409 je pominje). Bezbednosno je ponašanje ispravno (fail-closed). Samo zbog ovoga ne bih
  oborio C3b, ali kriterijum kako je napisan nije ispunjen.
- 94/100 izlaza ne može da se izveze bez ručne ispravke. Samo 7 od njih ima kao jedino izostavljanje blok potpisa ili
  napomene; ostalih 87 imaju sadržinska izostavljanja.

---

## 4. Šta su označivači propustili (nezavisan pregled)

Pročitao sam ceo tekst za sud i listu izostavljenog za svih 100 izlaza (N1–N4, H2, C1 i C2 u celosti; A, B i H1 ciljano
po rečenicama o dopuni, povlačenju, roku, uplati i iznosu). Ovi nalazi **nisu** uračunati u zvanični zbir (nije ih
prijavio označivač), ali potvrđuju da je zbir donja granica:

1. **C2_01, M1:** „Tužilac ostaje pri svom zahtevu za naknadu štete u iznosu od 4.200.000 dinara, uključujući i dodatni
   zahtev … 600.000“. Ista klasa kao B, neoznačena.
2. **N1, M7, ista klasa kao N1_00/N1_08:** N1_01, N1_02, N1_03, N1_05, N1_06 ponavljaju 4.200.000 + 600.000 kao važeći
   zahtev uz nečitljiv zapisnik. N1_02, N1_07 i N1_09 se bezuslovno protive predlogu za dopunu. U N1 je 4/10 izlaza bez
   ijednog izostavljanja, a 4 su izvezena direktno.
3. **N2, M7, ista klasa kao N2_01/02/04:** N2_00, N2_05 i N2_08 citiraju samo odbijanje od 10.09. i prećutkuju
   prihvatanje i nalog od 15.07. (N2_05 doslovno: „Sud je već odbio predlog tuženog za dopunu veštačenja (DOK-08 …).“).
4. **Propuštanja u odnosu na sopstveno pravilo kapije o „utvrdio“** (nematerijalno po §4 prethodne registracije, ali je
   to pravilo kapije): „Visina štete utvrđena je na iznos od 3.150.000 dinara“ (A_06, N4_08, C1_08, H1_01), „prihvata
   utvrđenu visinu štete“ (A_03, B_07, H1_00, H2_00, H2_02, C2_07, N2_06, N2_09, N1_08 …), „u skladu sa utvrđenom visinom
   štete“ (B_00), „kojim je utvrđeno da je uzrok …“ (većina izlaza). `_RE_UTVRDIO` (`nacrt_za_sud.py:144`) hvata samo
   „utvrdio/utvrdila“ posle veštak/nalaz/sud i „utvrđeno je“, a ne „utvrđena je“, „utvrđenom“ ni „kojim je utvrđeno“.
5. **N4_02 4b:** u DOCX-u ostaje „[POTREBNO JE DOSTAVITI POTPIS OVLAŠĆENOG LICA]“.

---

## 5. Dijagnoza: odakle potiče svaka klasa potvrđenih neuspeha

Bez predloga novih instrukcija modelu.

| # | klasa | izlazi | poreklo | gde u kodu |
|---|---|---|---|---|
| D1 | Pogrešan obim tužbenog zahteva | B×7, C2_00/05, N1_07 (+C2_01) | **model**; **arhitektura stanja** | Procesne radnje stranke (dodatni zahtev = preinačenje, preciziranje, povlačenje) nisu stanje u `procesno_stanje`: modeluju se samo nalozi suda (`_NALOZI`, red 282), pa kapija nema šta da uporedi. Server uz netačnu rečenicu umeće izvod koji je opovrgava (`zastiti`, red 377), a provere saglasnosti tvrdnje i izvoda nema. |
| D2 | Lažna provenijencija preko pogrešne oznake | N1_05, N1_07 | **model** bira pogrešan `[[PS-nn]]`; **server pojačava** | `prikaz_izvoda` (redovi 258–264) i zamena u `zastiti` (377) umeću bilo koji izvod. `_razlog` proverava vezu izvoda i rečenice samo za pripisane navode (`izvori`, red 410), ne za tvrdnje uz oznaku. |
| D3 | Sporna odluka „razrešena“ selektivnim citatom; odluka izvrnuta | N2_01/02/04 (+N2_00/05/08), N4_06 | **model**; **kapija propušta** | `procesno_stanje` protivrečnost ispravno vidi (redovi 397–401: `CONTESTED`, „da li DOK-08 menja ovu odluku — nije utvrđeno“; vidi `interno` N2_01). Kapija `stanje`/`kasniji` citirane odluke **ne čita**: izuzetak „stav + priznanje odluke“ (`nacrt_za_sud.py:461`, `:468`) pušta svaki stav stranke uz bilo koju citiranu odluku, bez obzira da li je odluka sporna i u kom je odnosu sa stavom (N4_06: „nije potrebna … jer je sud prihvatio“). |
| D4 | Asimetrija kapije: navod stranke ostaje, akt suda nestaje | N3_01–03 (DOK-09 u svih 10 N3), N2_06 I-3 | **kapija** | Navod stranke prolazi kroz `pripisano` / `_izvor_kaze` (416–424). Rečenica o aktu suda prolazi samo uz oznaku ili parafrazu, a `_RE_SUD_GLAGOL` (133–141) traži glagol odmah posle „sud je“, pa „sud je u obaveštenju od 01.09. konstatovao …“ i „sud je na ročištu održanom 15.07. prihvatio …, ali je 10.09. odbio …“ padaju na pravilu predmeta (468–471). Ishod: uravnotežena rečenica se briše, jednostrana ostaje. |
| D5 | Nepoznat sudski dokument ne pooštrava kapiju | N1_00, N1_08 (+5 izlaza) | **kapija / arhitektura** | `procesno_stanje` (red 435) upisuje samo napomenu „sudski dokument u kom sistem nije prepoznao odluku“. Kapija se pooštrava samo kad postoji `ima_nalog` iz prepoznatih događaja suda ili `stanje.greska` (`nacrt_za_sud.py:315`). Nečitljiv zapisnik daje 0 događaja, pa kapija radi kao da odluka ne postoji. Serverska napomena još tvrdi „Dokumenti … koje savetnik NIJE pročitao: nema“ (N1_00). |
| D6 | Nepoznat ishod ročišta (C2) | C2_01/03/04 | **model**; **greška kapije** | `_RE_USLOV` (red 111) sadrži `\brocist\w*` i `\bzapisnik\w*`, pa sama reč „ročište“ važi kao uslov i propušta bezuslovnu tvrdnju o ročištu kroz pravilo nepoznatog ročišta (472). |
| D7 | Prekomerno izostavljanje (P4) | svi osim N1 | **kapija / klasifikacija** | (i) Povlačenje sopstvenog zahteva koje je zapisano u zapisniku klasifikuje se kao `STRANKA_ODUSTAJE` nevezan za odluku (`procesno_stanje` 413–418), a zatim `_RE_ODUSTANAK` (125) + pravilo 465–466 brišu svaku rečenicu sa „povukao/povlačeći“, i kad nosi doslovan izvod. (ii) `_RE_STANJE` hvata „izvrsio“ (red 59), pa „veštak nije izvršio uvid“ postaje „izvršenje naloga“ (430–441), iako docstring (red 75) tvrdi suprotno; tako se briše odgovor na DOK-06. (iii) `u roku od \d+ dana` (red 99) briše i doslovan opis naloga suda. (iv) Pravilo nepoznatog ročišta u C2 briše svako protivljenje predlogu. |
| D8 | Sistemski tekst u DOCX-u | 104/104 izvoza | **izvoz** | Naslov: `multi_agent.py:1327` → `drafting.py:1356` → `drafting.py:1243`. Podnožje „Vindex AI“: `_nacrt_to_docx`, blok Footer. Mehanička lista P3 nije uključila naslov, a harness nije čitao podnožje. |
| D9 | `[PROVERITI` unutar reda | H1_09, N1_00 (P5) | **kapija (nedoslednost)** + **dizajn simulacije** | `nacrt_za_sud.py:341` premešta samo red koji počinje oznakom, a `za_izvoz` (556) ispravno blokira. |

**Zajednički uzrok.** Kapija je leksička heuristika nad rečenicama (oko 30 regex detektora) i nema model značenja. Isti
mehanizam istovremeno propušta (D3, D5, D6, red 144) i prekomerno briše (D7). Rečenica prolazi ili pada zavisno od
reda reči i izbora glagola, a ne od toga da li je tvrdnja potkrepljena. `procesno_stanje` u N2 i N1 ima ispravnu
informaciju (`CONTESTED`, „pročitati dokument“), ali kapija tu informaciju ne koristi kao ograničenje. Treba pomeriti i
procesne radnje stranaka i stanje „sporno/nepoznato“ iz napomena u ograničenja. To je odluka o arhitekturi (§7), ne
nova petlja istog regex-a.

---

## 6. Robusnost ishoda prema spornim tumačenjima

Čak i ako se usvoji najuže tumačenje, odnosno (b) opovrgava i sve nalaze o prećutkivanju (C1_03, N3_01–03, N2_01/02/04,
N3_01 M7) i svi C2 „raspravljano“ nalazi se proglase nematerijalnim, ostaju:
- **P1:** B×7 i C2_05 i N1_07 (M1, iznos; N1_07 i M5), C2_00 (M1, „u skladu sa tužbenim zahtevom“), N1_05 (M5,
  lažan izvod), N1_00 i N1_08 (M7), N4_06 (M2). To je **13 izlaza**, od kojih su B_03, N1_05 i N1_08 izvezeni bez
  blokade. **FAIL.**
- **P3:** ako se uzme samo 4a, naslov je i dalje u 6/6. **FAIL.**
- **P4:** stroga provera iste klase rečenice kod oba označivača daje 5 scenarija iznad polovine. **FAIL.**

Ishod ne bi bio drugačiji ni da su označivači pronašli manje.

---

## 7. Nedostaci dizajna merenja (ne menjaju ishod)

1. **Nezavisnost označivača je ograničena.** Oba označivača su instance istog modela nad **bajt-identičnim paketima**
   (isti md5 za NACRTI.md po delu, isti SPISI.md). Greške su korelisane: oba su propustila iste instance (§4), a M8 se
   po delu poklapa tačno (2/23/2/1 kod A i B), što pokazuje tumačenje vezano za paket, ne nezavisno čitanje. Prethodna
   registracija kaže „dva nezavisna označivača“. U praksi su to dva uzorka istog procenjivača.
2. **Slepost je samo uputstvom.** `t03_KLJUC.json` je u `t03_slepo/`, folderu iznad foldera označivača, i čitljiv je.
   Agenti označivača su pisali fajlove **van dodeljenog dela** (`oznacivac_A/deo1_gen.py`, `oznacivac_A/deo4_gen.py`,
   `oznacivac_B/gen_deo2.py`). Pretraga skripti ne pokazuje upućivanje na ključ ni na druge delove, pa dokaza o curenju
   nema, ali izolacija nije bila tehnički obezbeđena. Šifre (`X<3 nasumične cifre><indeks posle mešanja>`) ne otkrivaju
   scenarij. SPIS-n otkriva klasu spisa, što je neizbežno. Razlozi kapije nisu dati označivačima (samo rečenice), a
   PROCESNO STANJE / NIJE UTVRĐENO iz `interno` nije prikazano (samo NAPOMENE SAVETNIKA). Time nisu procurela očekivana
   nepoznata stanja, ali označivač nije video sve što advokat vidi.
3. **Nedosledan opseg M8.** Uputstvo označivaču proširuje M8 („poruka sistema … tekst namenjen advokatu“) u odnosu na
   prethodnu registraciju („interna napomena, upozorenje AI ili čeklista“). Deo 2 je ocenjivao 4b, ostali delovi nisu.
4. **Izvlačenje DOCX-a čita samo pasuse tela** (`generisi_t03.py:190-192`), pa podnožje „Vindex AI“ nikad nije ocenjeno.
   Mehanička lista P3 ne sadrži naslov.
5. **Simulirana ispravka briše cele redove**, pa nestaje i legitiman tekst u istom redu (ODSTUPANJA.md, tačka 4). 4b
   zato nije reprezentativan za stvarnog advokata (prazni odeljci, npr. „2. Izjašnjenje na izjašnjenje tuženog (DOK-06):“
   bez teksta). Simulacija nije predvidela `[PROVERITI` unutar reda (P5).
6. **Pravilo potvrde (b) ne odgovara nalazima o prećutkivanju** (M5, druga grana, i M7) ni M6. Ostavlja ključno
   tumačenje recenzentu (§1).
7. **M2 i M6 se preklapaju po definiciji.** „Tužilac smatra da dopuna nije potrebna“ u scenarijima sa prihvaćenom
   dopunom označivači čitaju kao legitiman argument (M6) kad je izostavljen, a M2 obuhvata „naložena radnja prikazana
   kao nepotrebna“. Prethodna registracija treba da kaže kad je stav stranke dopušten (uz izričito priznanje odluke) i
   kad je izvrtanje (N4_06).
8. Najznačajniji neuspeh (D1, iznos zahteva) je van onoga što kapija uopšte pokušava da meri. Scenariji su dizajnirani
   oko naloga suda, a procesne radnje stranaka nisu imale svoje merilo, pa se uhvatio samo kroz opšti M1.

---

## 8. Zaključak i šta sledi

**C3B_FAIL.**
- Kapija uspešno uklanja izmišljene uplate i tvrdnje o roku (P2 PASS) i čisto razdvaja interne napomene (mehanički P3: 0).
- Tekst za sud i dalje sadrži potvrđene materijalne netačnosti: obim tužbenog zahteva, lažno potkrepljen izvor, sporna
  odluka prikazana kao rešena, nepoznat zapisnik prikazan kao poznat stanje. Neke od njih idu u DOCX bez ikakve blokade.
- Kapija istovremeno sistematski briše doslovne i tačne opise spisa (P4).
- Izvoz upisuje sistemski naslov u svaki DOCX (P3).

C3b **nije podoban za pregled kontrolisanog produkcionog puštanja i ostaje blokiran.**

Po prethodnoj registraciji ne ponavlja se ista petlja i ne dodaju se instrukcije modelu. Dijagnoza (D3, D4, D5, D7)
pokazuje da sledeći korak nije još jedan prolaz istog leksičkog filtera. Potrebna je odluka o arhitekturi:
- da li sporno i nepoznato stanje iz `procesno_stanje` postaje tvrdo ograničenje teksta za sud;
- da li se procesne radnje stranaka modeluju kao stanje;
- da li se izvod uz `[[PS-nn]]` proverava prema tvrdnji;
- kako se uklanja sistemski naslov i podnožje iz izvoza.

O tome odlučuje osnivač, ne izvršilac.
