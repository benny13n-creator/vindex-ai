# BOJAN N2–N9 — dnevnik izvršenja

Grana `feature/bojan-n2-n9` (worktree `C:/vindex-intake`), lokalni commitovi, **bez push-a, merge-a, deploya i migracija**.
Izvor zahteva: Bojanov tekst iz zadatka (fajl `VINDEX_BOJAN_ORIGINAL_REQUIREMENTS_2026-10-26.md` NE postoji u repozitorijumu — provereno).
Odluka osnivača: AI predlog roka/obaveze ostaje predlog dok ga advokat ne potvrdi.

## Pre-flight (2026-10-26)

| Provera | Rezultat |
|---|---|
| `origin/main` | `11475df8` (= produkcija posle #55/#56/#57) |
| PR #58 (N0+N1) | otvoren, Draft, NIJE spojen; glava `71593846` = lokalna i udaljena grana, bez razilaženja |
| Osnova N2–N9 | `71593846` (main + N1), nova grana `feature/bojan-n2-n9` |
| Radno stablo | čisto |
| CI na `71593846` | 10/11; pad `pytest (Python 3.13)` = 1 test `test_website_v2_remediacija.py::test_nova_adresa_se_upisuje_jednom_uz_jedno_obavestenje` (pozadinska nit + `sleep(0.2)`); commit menja samo dokumentaciju, isti kod prošao na `5eb1289b`, lokalno 5/5 → flaky, nevezan za prijem |
| N1 preduslov na osnovi | `live-zlatni-prijem-e2e` 48/48, `tests/test_n1_zlatni_prijem.py` 6/6 |

## N2 — čarobnjak prijema — `VERIFIED_IMPLEMENTED` (`71c1a238`)

Zahtev: „wizard koji traži od tebe da uneseš podatke klijenta/skeniraš dokumentaciju, te mu kažeš šta je cilj/spor/predmet“.
Postojeće (N1, PR #58): jedan predmet po prijemu, opis + cilj sačuvani, 4 vrste dokumenata, OCR istinit, nepoznat ishod, izolacija.

Nađeni kvarovi (PROVEN, merenjem pre ispravke):

| # | Kvar | Dokaz pre | Ispravka |
|---|---|---|---|
| N2-1 | Dva klijenta istog imena u izboru čarobnjaka = dve iste stavke („Marko Marković“ ×2); advokat ne zna kome otvara predmet | e2e [1] FAIL | stavka i potvrda izbora nose kontakt i datum upisa |
| N2-2 | Postojeći klijent NE MOŽE da dobije drugi aktivan predmet: provera sukoba prijavljuje njega samog („klijent u kartoteci, kao klijent“) u njegovom aktivnom predmetu → tvrda blokada (isto pravilo u kartici Klijenti) | e2e [2] FAIL | nalaz o ISTOM izabranom zapisu sa izričitom ulogom klijenta → „pregled“ uz potvrdu (ne blokada); ishod vezan za klijenta za koga je rađen |
| N2-3 | Dva istovremena `POST /api/intake/kreiraj` za isti naziv → 200/200 i DVA predmeta | e2e [4] + pytest `[200,200,200]` | oznaka „otvaranje u toku“ (uid, naziv) u procesu → 200/409 |
| M1 (pregled) | Sloj 2 provere sukoba čita staru kolonu `uloga` (samo podrazumevano 'stranka'); svi upisi veze pišu `uloga_klijenta` → protivna strana čitana kao „klijent“; posle N2-2 bi bila spuštena na pregled | probe nezavisnog pregleda + pytest | sloj 2 čita `uloga_klijenta`; V2 spušta SAMO uz `uloga_klijent === true` |
| m1 (pregled) | Ime klijenta u nazivu NJEGOVOG predmeta (sloj 1) i dalje tvrdo blokira | probe | sloj 1 nosi `klijenti_predmeta` (izričite uloge klijenta) |
| m2 (pregled) | Imenjak vezan za isti predmet sakriven iza prvog reda | čitanje + pytest | sloj 2 deduplikuje po (predmet, klijent) |

Nepromenjeno i namerno: server i dalje vraća `status: conflict` (V2 odlučuje po identitetu); imenjak, protivna strana, bivši klijent, nepotpuna provera i nalaz bez identiteta → kao ranije.

Dokazi:

| TEST → UKUPNO → PASS → FAIL → SKIP | |
|---|---|
| `node tests/live-n2-carobnjak-e2e.mjs` | 27 → 27 → 0 → 0 |
| `pytest tests/test_n2_carobnjak.py` | 7 → 7 → 0 → 0 |
| COI + prijem backend (18 fajlova) | 249 → 246 → 3 → 0 (3 = `[trio]` varijante; `trio` nije instaliran lokalno; `[asyncio]` iste provere prolaze) |
| V2 regresija: zlatni 48, klijenti 40, nov-predmet 41, čarobnjak 37, prijem 53, oporavak 18, izolacija 25, brand 335, states 99, runtime 92, session 38, primary 51, api 49, solo-tok 23, praćenje 29, organizacija 16, vrsta-dokumenta 15 | sve PASS |
| Mutacije (`n2_mutacije.py`) | 11 → 10 ubijeno; preživela browser varijanta N2-3 (vremenski zavisna), istu ubija deterministički pytest [0] |

Ograničenja: zaštita N2-3 važi za jedan proces (produkcijski Dockerfile pokreće jedan uvicorn proces); m3/m4 iz pregleda (409 dok kompenzacija briše predmet; otkazan zahtev) — retki, nepromenjeno ponašanje 5-s prozora; server i dalje ne zahteva proveru sukoba (API poziv bez provere → 200) — odluka osnivača, nije autorizacija (samo sopstveni podaci). Istovremeno upisivanje KLIJENTA istog imena ima isti obrazac 5-s prozora (nije mereno).

## N3 — ročišta i kalendar — `VERIFIED_IMPLEMENTED` (`99cf37b3`)

Zahtev: „da on sam radi zakazivanje u kalendaru“, „da se automatizuje … ročišta“.
Postojeće: ručno zakazivanje u predmetu (V2), 30-s zaštita od duplikata, Danas (30 dana, ročišta + potvrđeni rokovi), PATCH/DELETE na serveru, `.ics` na serveru (nije u V2 — nije ni dodato).

| # | Kvar (PROVEN pre ispravke) | Ispravka |
|---|---|---|
| N3-1 | Danas prikazuje otkazano i odloženo ročište kao predstojeće („za 4 dana Ročište OTKAZANI sud“) | Danas samo zakazana |
| N3-2 | V2 nema održano / odloženo / otkazano; odlaganje nema istoriju | akcije stanja uz `if_updated_at`; „Odloženo“ ostavlja staro kao istoriju i otvara zakazivanje nastavka |
| N3-3 | Datum iz sudskog poziva se prekucava ručno | PREDLOZI iz teksta dokumenata predmeta (izvor + citat), „Proveri i zakaži“ popunjava formu, „Odbaci“ trajno (audit_immutable); predlog nikad nije ročište |
| P1/P2 (dva kruga nezavisnog pregleda) | izvlačenje predlagalo odložena/otkazana/održana ročišta, datum akta, rok „do …“, spajalo stari datum i novo vreme; propuštalo „biće održana“ | izvlačenje po rečenicama, oznake stanja u oba redosleda i u sledećem pasusu, datum posle glagola zakazivanja, „umesto/pomerio/prekida“, skraćenice; 53 formulacije iz pregleda su regresioni testovi |

Dokazi: `live-n3-rocista-e2e` 24/24 (Danas, stanja, 409 zastareo prikaz, odlaganje + nastavak, predlozi, dupli klik → 1 ročište, B 404 na sve nove rute i PATCH, prelaz na zimsko vreme 24→26.10. = „za 2 dana“); `tests/test_n3_rocista.py` 73/73 (stvaran prijem PDF poziva → predlog); regresija ročišta/kalendara 241 pytest + rocista-pretraga 38, danas 54, rad 44, matter 56, rok-odluka 76, states 99, runtime 92, brand 335, verify 98, send 100; mutacije 19/19.

Ograničenja: datum ispred glagola („Dana 15.11. održaće se ročište“) se ne prepoznaje; datum rečima se ne prepoznaje; „Vrati na zakazano“ odloženog ročišta posle zakazanog nastavka ostavlja dva zakazana (bez upozorenja); „Odloženo“ resetuje već otvorenu formu; predlozi se računaju pri svakom učitavanju (do 500 dokumenata); test harness za browser preskače `AUDITABLE_ACTIONS` (pytest `lanac` ga proverava).

## N4 — rokovi, obaveze, podsetnici — `VERIFIED_IMPLEMENTED` (`8990773b`)

Zahtev: „podsetnike za ročišta“, „rokovi, podsetnici“. Odluka osnivača (nepromenjena): AI predlog roka je predlog dok ga advokat ne potvrdi.
Postojeće (PROVEN): predlozi u Danas sa Potvrdi/Odbij; stanje iz lanca `audit_immutable` (odbijanje apsorbujuće); email samo za POTVRĐEN rok (`_filtriraj_izvrsive`); rezervacija pre slanja (UNIQUE predmet+datum+dan); profil u V2 Podešavanjima. **Produkcija: email cron 26.10.2026. HTTP 200, `poslato=0`, „nijedan potvrđen rok nije dospeo“** (log run 40341533804) — autorizacija radi, stvarna isporuka NIJE posmatrana.

| # | Kvar (PROVEN) | Ispravka |
|---|---|---|
| N4-1 | Kalkulator rokova u V2: od 26 stavki 4 tačne prema lokalnom tekstu zakona; 15 pogrešan član/zakon, više pogrešan rok ili nepostojeće pravilo (komunalije 3 g. umesto 1 g. ZOO 378; žalba ZPP „357“ → 367; revizija „393“ → 403; neosnovano lišenje slobode „6 meseci“ → 3 g. ZKP 591; „nasledna 3 g.“ ne postoji) | katalog prepisan, svaka stavka proverena tekstom člana (test automatski čita lokalni tekst); neproverljive uklonjene |
| N4-2 | Poslednji dan roka na subotu/nedelju/praznik se nije pomerao (ZPP 103 st. 4–5, ZUP 80 st. 5, ZKP 224, ZOO 77 st. 3); tabele Vaskrsa samo 2025–2027 | `shared/neradni_dani.py` (Vaskrs računat), prikaz kalendarskog dana, razloga, pravila i izvora neradnih dana |
| N4-3 | Ročišta nemaju dnevni podsetnik (samo nedeljni pregled) | zakazana ročišta aktivnih predmeta u dnevnom podsetniku; otkazana/odložena/održana ne (ni u nedeljnom) |
| N4-4 | „Već poslato“ po korisniku gasilo podsetnik za drugi predmet istog datuma | po predmetu (isti ključ kao rezervacija) |
| N4-5 | Pogrešno pročitan datum predloga nije mogao da se ispravi (samo odbij) | `POST /api/rokovi/{id}/ispravi` + „Ispravi datum“ u Danas: nov HUMAN_DIRECT rok (isti dokument) potvrđen, predlog odbijen; isti datum → 409 („Potvrdi“) |
| pregled M1 | isti datum kroz „Ispravi“ bi AI datum upisao kao advokatov | 409 + prazno polje |
| pregled m1–m4 | Vaskrs 2027 + Prvi maj; telefon bez uslova domaćinstva; ponovni pokušaj → drugi rok; ispravka bez pytest-a | ispravljeno + testovi |

Dokazi: `tests/test_n4_rokovi_izvori.py` (izvori, pravila računanja, praznici, prelaz godine, prestupna, Veliki petak 2030), `test_n4_podsetnici.py` (ročište sutra → email sa sudom i vremenom; otkazano/odloženo/održano/arhivirano/isključen profil → ne; nepotvrđen AI rok ne ulazi; po predmetu; SMTP pad = neisporučeno bez ponavljanja; nedeljni pregled), `test_n4_ispravka_roka.py` (stvaran lanac, 404/409/422, delimičan neuspeh); 122 N4 pytest; regresija rokova/podsetnika 1363 pytest; `live-n4-rokovi-e2e` 12/12; zastarelost 23, danas 54, rok-odluka 76, rad 44, brand 335; mutacije 17/17.

Ograničenja: stvarna isporuka emaila nije dokazana (nema testnog primaoca/SMTP pristupa; produkcija 0 poslato); Zakon o državnim i drugim praznicima nije u lokalnim izvorima (rečeno uz svaki rezultat); subota kao „dan kad sud/organ ne radi“ za ZPP/ZUP je tumačenje (izričito samo u ZKP); ročište dodato posle rezervacije roka istog predmeta i datuma u istom danu se ne šalje u tom pokretanju; `routers/zastarelost.py::/api/rokovi/procesni` i `rokovi_lanac.py` (nisu u V2) i dalje imaju stare tabele praznika; delimičan/ručni unos roka bez predloga u V2 ne postoji.

## N5 — evidencija naplate — `VERIFIED_IMPLEMENTED` (`e332a5fb`)

Zahtev: „da vodi evidenciju o naplati“. Postojeće: stavke po predmetu (tarifa/satnica/iznos), tajmer, nacrt fakture, lista faktura, zbirovi (NUMERIC u bazi). Delimične uplate, datum uplate, valuta (samo RSD), slanje/SEF/PDF fakture u V2 — NE postoje (nisu dodavani).

| # | Kvar (PROVEN) | Ispravka |
|---|---|---|
| N5-1 | V2 ne može da zabeleži da je faktura izdata ili plaćena | dugmad „Označi kao izdatu“ / „Plaćena“ / „Vrati na neplaćenu“ uz očekivano stanje |
| N5-2 | `PATCH …/status` prihvatao svaki prelaz (i „plaćena → nacrt“, koji otključava finansijska polja izdate fakture), bez provere stanja i bez traga | tabela prelaza, `iz_statusa` → 409, uslovni upis, `audit_immutable` `faktura_status_promenjen` |
| N5-3 | Dva istovremena zaustavljanja tajmera → 200/200 i DVE stavke za isti rad | uslovno gašenje (`aktivan=true`); pad upisa stavke vraća tajmer (rad se ne gubi) |
| pregled | „Storniraj“ bi stavke ostavio trajno obračunatim (rad nenaplativ) | storno NIJE izložen u V2 — odluka osnivača |

Dokazi: `tests/test_n5_naplata.py` 13/13 (trka tajmera, deterministički oblik trke, pad upisa, zbirovi/PDV na decimalama, prelazi, zastareo prikaz, istovremene promene statusa, B 404); `live-n5-naplata-e2e` 16/16; regresija naplate 202 pytest (53 preskočena — postojeći testovi koji traže pravu bazu/Playwright), `live-naplata` 83/83; mutacije 10/12 ubijeno, preživele 2 su ekvivalentne (uz preostala V2 dugmad svaki zastareo klik odbija i tabela prelaza; serversku proveru `iz_statusa` ubija pytest).

## N6 — izveštaji — `VERIFIED_IMPLEMENTED` (`8b0e7582`)

Zahtev: „da može da izvuče izveštaje i sl.“ — format nije zadat; korišćeni su POSTOJEĆI izveštaji (PDF predmeta, mesečni, CSV naplate), bez novih kategorija. V2 je ranije nudio samo potpuni izvoz podataka.

| # | Kvar (PROVEN) | Ispravka |
|---|---|---|
| N6-1 | PDF: č/ć/đ/Č/Ć/Đ kao „I“ („Zlatić protiv Đorđević“ → „ZlatiI protiv IorIeviI“), ćirilica nestaje | font sa latinicom i ćirilicom (DejaVu u slici — **Dockerfile: `fonts-dejavu-core`**), inače preslovljavanje uz napomenu |
| N6-2 | PDF: „[NEPOTVRĐENO]“ i na običnim događajima | oznaka samo na rokovima |
| N6-3 | PDF bez ročišta | sekcija ročišta sa stanjem |
| N6-4 | Tag u tekstu (beleška/tip) obara PDF (500) | escape korisničkog teksta |
| N6-5 | Mesečni: nacrti i stornirane fakture u „fakturisano/neplaćeno“ (prikazan dug koji nije ispostavljen) | samo izdata + plaćena |
| N6-6 | Mesečni: „narednih 14 dana“ = svi redovi hronologije, AI predlozi bez oznake; otkazana ročišta brojana | samo rokovi sa `stanje_odluke`, bez odbijenih/izvršenih; ročišta bez otkazanih/odloženih |
| N6-7 | CSV naplate ne kaže da li je faktura plaćena | kolone broj i status fakture |
| N6-8 | V2 nema izveštaje | „Preuzmi PDF“ (pregled predmeta), „Evidencija naplate (CSV)“ |

Dokazi: `tests/test_n6_izvestaji.py` (PDF tekst čitan pymupdf-om: slova, ćirilica obe grane, ročišta, oznake, B 404; mesečni; CSV); `live-n6-izvestaji-e2e` 8/8 (stvarno preuzimanje iz V2, sadržaj fajla); regresija izveštaja/izvoza 164 + 73; V2 api 49, matter 56, naplata 83, podešavanja P1–P3, states, runtime, brand; mutacije 10/10.

Ograničenja / odluke: prekoračeni rokovi u mesečnom broje samo `kritičan` (postojeće pravilo `je_hitan_za_prikaz`; potvrđen „važan“ rok koji je prošao se ne broji — odluka osnivača); legacy ekran mesečnog izveštaja ne prikazuje `stanje_odluke` (V2 ga ne koristi); PDF fakture (nije u V2) verovatno ima isti problem fonta — nije menjano; izmena Dockerfile-a stupa na snagu tek posle deploya.

## N7 — automatsko ažuriranje predmeta — `VERIFIED_EXISTING` (testovi `18cbbc6a`)

Zahtev: „automatizuje … ažuriranje predmeta“ (bez prepuštanja kontrole nad činjenicama). Proizvodni kod NIJE menjan.
Dokazano čitanjem (PROVEN): polja `predmeti` menja samo advokatov PATCH (i kanban faza); pozadina samo DODAJE redove u `predmet_hronologija`/`predmet_dokazi`; odluke su u nepromenljivom lancu; Genome (`case_dna`) se zamenjuje celim uz istoriju (`predmet_genome_history`), a istovremena osvežavanja istog predmeta se spajaju (u jednom procesu); Genome nema put ručne izmene, pa nema advokatom proverenih Genome činjenica koje bi bile prepisane.
Dokazano testom (`tests/test_n7_azuriranje_predmeta.py`, stvaran prijem): dokument ide u taj predmet; tužilac/tuženi/vrednost/opis neizmenjeni; potvrđen rok ostaje CONFIRMED; nov rok iz dokumenta = 1 predlog UNCONFIRMED, `AI_AUTONOMOUS`; ročište iz dokumenta = predlog sa izvorom, ništa zakazano; isti sadržaj se ne prikačuje dvaput, izmenjen dokument je nov dokument; ispravka advokata ostaje; B → 404. Ubačeni kvarovi (prepisivanje polja, AI rok kao advokatov, tuđ predmet) uhvaćeni 3/3. Browser: `live-prijem` 53, `live-n3-rocista-e2e` 24 (predlozi iz dokumenata), N9 integrisani tok.
Ograničenje: spajanje osvežavanja Genome-a je unutar procesa (produkcija = 1 proces); Genome i dalje zamenjuje celu analizu (AI sloj, ne advokatov).

## N8 — nadležnost (mesna i stvarna) sa tačnim citatima — `VERIFIED_IMPLEMENTED` (`2eb662c9`, sa ograničenjima)

Zahtev: „rezonovanje o nadležnosti (mesna i stvarna) sa tačnim citatima“. Istina = LOKALNI tekst ZPP-a (`data/laws/pdfs/zakon_o_parnicnom_postupku.pdf`), član po član; model nije izvor. Merenje: stvarni tok (`main.ask_agent`, OpenAI + Pinecone, **Supabase isključen**) nad 15 sintetičkih pitanja o nadležnosti + 5 kontrolnih (R1–R5, radno/obligaciono), ocena skriptom prema tekstu ZPP-a.

| # | Kvar (PROVEN, stvaran tok) | Ispravka |
|---|---|---|
| N8-1 | 0/5 osnovnih pitanja odgovoreno: pretraga je vezivala pitanje za MATERIJALNI zakon iz činjenica („zajam“ → ZOO, „otkaz“ → ZR), pa ZPP-ova pravila nisu ni pretražena → LOW/blok | pitanje o građanskoj nadležnosti → ZPP (osim kad pitanje IMENUJE drugi zakon), +60 za čl. 27–33/38–65, 8 ciljanih pretraga (opšta, pravno lice, više tuženih, izdržavanje, šteta, potrošač, nepokretnost, radni spor) |
| N8-2 | Opšta nadležnost vezana za prebivalište TUŽIOCA; izmišljena nadležnost „po mestu izvršenja ugovora“ | provereni okvir pravila (ZPP čl. 39, 40, 42 uz 205 st. 1 tač. 1, 43, 44, 45, 46, 48, 51, 53 st. 3, 55, 57, 58, 59, 60, 65; stvarna: ZUS čl. 27/480) u sistemskoj poruci samo za ta pitanja; zabranjena tvrdnja „opšta mesna nadležnost … po prebivalištu tužioca“ (samo pozitivan iskaz) |
| N8-3 | Neproverena sudska praksa prolazila kad praksa NIJE data modelu („Vrhovni sud, Us 14/2023“ — stvarna odluka o drugom predmetu, pogođena po imenu grada) | bez bloka prakse: odluke i rečenice koje ih navode se uklanjaju; za pitanja o nadležnosti praksa se ne pretražuje |
| N8-4 | Broj odluke iz konteksta, ali STAV izmišljen („Už-12306/2019 — nadležnost prema prebivalištu tužioca“; odluka je o naknadi štete) | stav mora biti podržan sažetkom koji je model video (preklop sadržajnih osnova ≥ 50%, ili isti član + ≥ 2 osnove); tačno poređenje broja odluke; nepodržana odluka se uklanja sa rečenicama |
| N8-5 | Izmišljen član u padežu („prema članu 999“) nije prepoznat | padeži `člana/članu/članom` |
| N8-6 | Stvarna nadležnost tvrđena bez izvora (Zakon o uređenju sudova nije u bazi) | determinističko „NAPOMENA O IZVORU“ |
| N8-7 | Lažna premisa („po čl. 39 ZOO nadležan je…“) prihvaćena | „ISPRAVKA PREMISE“ samo kad lokalni tekst citiranog člana NE sadrži pravilo o nadležnosti (ZOO 39/84 — da; ZOO 328, PZ 209 — ne) |
| N8-8 | Više tuženih (M8): model ponavljano citira čl. 39 | doslovna napomena čl. 42 (+205 st. 1 tač. 1) |

Kalibracija (R1–R5): prva verzija provere stava uklanjala je 5/5 odluka; uzrok — sažetak je ćirilica + 300 znakova, isti član („чл. 187“) nije računat, zarez u nazivu organa („Ministarstvo rada, zapošljavanja, …“) pomerao ključ. Posle ispravke: R2 (Gž1 3141/2019, čl. 187 ZR, trudnoća) ostaje; R4 (Gž1 1900/20 — pripisano „zabrana zahteva naknadu“, sažetak kaže suprotno) ispravno uklonjena; R3/R5 uklonjene konzervativno (sažetak samo citira ZOO / ne pominje strah) — gubitak preciznosti u bezbednom smeru. Članovi i pouzdanost R1–R5 nepromenjeni (ZR 189, 187, ZOO 376, ZR 161, ZOO 200).

Nezavisna revizija (adversarijalna, kod bez zaključka): 11 nalaza, 4 blokera — svi ispravljeni i pokriveni testom: F1 imenovan drugi zakon se tražio u ZPP-u; F2 detektor preširok („nadležni organ“, „kom sudu se izjavljuje žalba“, izvršni/ostavinski/stečajni); F3 zabranjena pravila blokirala TAČNE iskaze (čl. 43, 46, negacije, čl. 53 st. 3); F4 „ispravka premise“ i za ZIO čl. 7; F5 rubrika „ZPP ne poznaje mesto ispunjenja“ netačna (čl. 53 st. 3, 55, 59); F6 broj odluke kao podniz („Rev 1/20“ ⊂ „Rev 1/2019“); F7 višeredni sažetak; F9 brisanje „Sl. glasnik RS br 111/2009“ i „čl. 154“; F10 „članova 3000“; F11 napomena stvarne uz „osnovni sud je mesno nadležan“. **Nije ispravljeno (ograničenje):** F8 — preklop reči ne vidi negaciju („nije dužan“ uz sažetak „dužan je“).

Dokazi: `tests/test_n8_nadleznost.py` 60/60 (istina iz lokalnog ZPP-a, usmeravanje, padeži, sanitizacija, stav prema sažetku, ožičenje kroz `_parsiraj_strukturni_odgovor`, napomene, zabranjena pravila sa tačnim iskazima); mutacije **21/21 ubijeno**; stvaran tok posle ispravki: **13/15 strogo PASS** (M1–M7, N1, N2, S1, F1, F2, K1), M8 i I1 tačan sud i zaključak, ali telo odgovora citira čl. 39 / čl. 38 (M8 ima i determinističku napomenu čl. 42); injekcija (I1) ignorisana. Odgovori: `scratchpad/n8_odgovori.json`, ocena `n8_ocena.py`.

**Incident (prijavljeno):** prvo pokretanje stvarnog toka (M1, 2026-10-27 01:32:37) upisalo je JEDAN sintetički red u produkcioni `ai_cache` (sintetičko pitanje M1, bez ličnih podataka, TTL 7 dana). Red NIJE obrisan (brisanje produkcionih podataka nije dozvoljeno bez osnivača). Skripta je odmah izmenjena: Supabase ključevi se ne učitavaju, `_get_supa` baca izuzetak, keš je zaobiđen — sva naredna pokretanja bez ijednog čitanja/upisa baze.

Ograničenja: stvarna nadležnost se ne može potvrditi izvorom (Zakon o uređenju sudova nije u korpusu); ishod modela je nedeterministički (S1 je u jednom od tri pokretanja bio bezbedno blokiran); provera stava je leksička (negacija, F8); pitanja o nadležnosti u izvršnom/ostavinskom/stečajnom/vanparničnom postupku ostaju na starom toku (namerno, imaju sopstvena pravila); sistemska napomena „tematska neusklađenost“ (postojeći proverivač) se ponekad javlja uz tačan čl. 51.

## N9 — višestruki povrat (KZ čl. 55a) + integrisani tok N2–N9 — `VERIFIED_IMPLEMENTED` (sa ograničenjima)

Zahtev: „izračunavanje raspona kazne kod višestrukog povrata (KZ čl. 55a)“. Istina = LOKALNI tekst KZ (`data/laws/pdfs/krivicni_zakonik.pdf`): čl. 55a (uslovi i „iznad polovine raspona propisane kazne“), čl. 45 st. 1–2 (30 dana – 20 godina; pune godine i meseci preko šest meseci), čl. 54, 55, 56–57, 97. Pinecone ima čl. 55a kao poseban vektor (proveren upitom, samo čitanje); kolizija 55/55a u proveri citata NIJE potvrđena (prva proba je bila neispravna — kontekst < 100 znakova se preskače).

| # | Kvar (PROVEN, stvaran tok, pre ispravke) | Ispravka |
|---|---|---|
| N9-1 | Opšte pitanje (V1) i pitanje sa činjenicama (V2: dve osude po 2 god., otpust pre 3 god., propisano 1–8 god.) BLOKIRANI — nema odgovora ni raspona | `shared/visestruki_povrat.py`: deterministička provera uslova i raspon; blok se dodaje odgovoru na svaku povratnu granu (`@_sa_proracunom_povrata` oko `ask_agent`, i blokiran odgovor i keš), nikad se ne kešira |
| N9-2 | V5: ranije kazne po 6 meseci → model: „uslovi iz čl. 55a su ispunjeni“ (NETAČNO) | uslov 1 računa kod (≥ 2 osude, umišljaj, ≥ 1 godina); zaključak modela zamenjen; drugi deo AI teksta koji tvrdi suprotno → UPOZORENJE |
| N9-3 | V6: otpust pre 7 godina → model: „ispunjeni uslovi“ (NETAČNO) | uslov 2 (tačni datumi; približan navod 54–66 meseci = NEPOZNATO) |
| N9-4 | V3: izmišljen „čl. 55b“ — bez objašnjenja | „Član 55b ne postoji u Krivičnom zakoniku (proveren lokalni tekst)“ |

Raspon: donja granica = min + (max − min)/2, ISKLJUČIVO („iznad“); najviše propisani maksimum; najniža kazna na pune mesece (preko 6 meseci) ili +1 dan (do 6 meseci); bez propisanog minimuma — 30 dana (čl. 45 st. 1). Primer V2: **više od 4 godine i 6 meseci, najviše 8 godina; najniža 4 godine i 7 meseci**. Blok uvek kaže: zakonski okvir, NE predviđanje (čl. 54); proveriti rehabilitaciju (čl. 97 st. 1); otvoreno pitanje (odnos prema ublažavanju čl. 56–57, „izrečena kazna“ kod više kazni) — **stav sudske prakse/Vrhovnog suda nije naveden jer nije u bazi**.

Nezavisna revizija (14 reprodukovanih nalaza, 7 sa pogrešnim DA/NE): negiran umišljaj čitan kao umišljaj; jedna krivica za sve ranije osude; osude druge osobe (saučesnik); uslovna osuda/uslovni otpust kao izdržan zatvor; godina iz datuma kao broj osuda; prvi pomen otpusta/raspona ranijeg dela; regex upozorenja obrtao smisao („nisu ispunjeni uslovi“); bez upozorenja u smeru DA/NEPOZNATO; rezervni oblik zaključka; lažni pozitivi detektora (povrat avansa/PDV-a/predmeta/jemstva, „povratak“); „54 i“ kao član; gramatika („više od 1 godine“). **Sve ispravljeno**: parser je prepisan po načelu „nikad ne bira između dva čitanja — nejasno = NEPOZNATO“ i prikazuje „Prepoznato iz pitanja: …“ da advokat vidi šta je pročitano.

Integrisani tok (deo D, `tests/test_n9_integrisani_tok.py`, stvarne rute nad bazom u memoriji, modeli simulirani): klijent + COI → predmet → dokument (ročište + rok) → predlog ročišta → zakazano → AI rok predlog → ispravka (potvrđena, predlog odbijen) → podsetnik (tema „Sutra: rok i ročište“, sadrži zakazano ročište 09:30 i ispravljen rok, ne AI predlog) → stavka + faktura nacrt→izdata→plaćena (+409 zastareo prikaz) → PDF predmeta (B 404) → mesečni izveštaj (naplaćeno 7.200 RSD, 14 dana: ispravka CONFIRMED, odbijen predlog odsutan) → nadležnost (čl. 42) i povrat (raspon). Harness ne primenjuje DEFAULT kolona — `datum_fakture` (DEFAULT CURRENT_DATE, migracija 003) postavljen u testu uz komentar.

Dokazi: `tests/test_n9_visestruki_povrat.py` 84/84; integrisani tok 1/1; mutacije **28/28 ubijeno** (4 preživele u prvom krugu → dodati ciljani testovi); stvaran tok posle ispravki: V1 NEPOZNATO (zakon + šta treba navesti), V2 DA sa tačnim rasponom, V3 nepostojeći član imenovan, V4 opšti odgovor modela zadržan, V5/V6 NE + zaključak zamenjen + UPOZORENJE; regresija: puna svita 12.396 passed / 18 failed — **istih 18 kao na osnovi** (`18cbbc6a`, 12.293 passed), 0 novih; testovi koji pozivaju `ask_agent` 450/450.

Ograničenja: prepoznavanje činjenica je pravilo nad tekstom (ne razume svaku formulaciju — tada NEPOZNATO); pitanja u nastavku razgovora (istorija) ne dobijaju proračun; raspon iz drugih sekcija AI teksta se ne poredi brojčano (samo tvrdnja o primeni); tumačenje uslovne osude / uslovnog otpusta i „izrečene kazne“ kod više kazni ostaje otvoreno (NEPOZNATO); kombinacije sa novčanom kaznom i doživotni zatvor se ne računaju; postojeći proverivač „tematska neusklađenost“ se javlja uz tačan čl. 55a (V2).
