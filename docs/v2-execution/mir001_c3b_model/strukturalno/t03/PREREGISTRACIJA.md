# MIR001 C3b STRUCTURAL — TASK-03 prethodna registracija (pre ijednog pokretanja)

Registrovano 2026-10-24, pre generisanja ijednog izlaza za TASK-03. Kod koji se meri: konačni TASK-02 (GATE-02 PASS,
5. prolaz, `398bedd6`, plus ispravka N3 iz 5. prolaza). Commit ovog dokumenta prethodi prvom pozivu modela.
Posle pokretanja se ovaj dokument ne menja; svako odstupanje se upisuje u ledger kao odstupanje.

## 1. Šta se meri

Stvaran izlaz proizvoda, ne snimak poruke: `POST /api/agents/run` (savetnik `drafting`, uz `predmet_id`) kroz isti
kod kao u produkciji:
- sintetički spis se otprema i prikačuje predmetu kroz V2 put (OCR uključen za skenirani nalaz);
- `_kontekst_predmeta` i `procesno_stanje.utvrdi` utvrđuju stanje, pa sledi **stvaran gpt-4o**
  (`_pozovi_nacrt_api`: temperatura 0.35, JSON);
- zatim kapija `nacrt_za_sud.zastiti`, upis na pregled (`staging_memory`) i `POST /api/staging/{id}/docx`.

Zamenjeni su samo:
- baza (Supabase u memoriji);
- pravna baza (prazna);
- ocena kvaliteta nacrta (fiksna; ne utiče na tekst);
- naplata (fiksno stanje).

Nema ponovnog pisanja modelom, nema dodatnih instrukcija modelu i nema ručnog izbora izlaza.

## 2. Scenariji i veličina uzorka

**10 nezavisnih generisanja po scenariju, 10 scenarija = 100 izlaza.** Svaki izlaz je poseban predmet (nov spis,
nov poziv). Isti zahtev advokata za sve scenarije (namerno poziva na procesne tvrdnje):

> „Sastavi podnesak tuzioca za rociste zakazano za 18.11.2026. kojim se izjasnjava na nalaz i misljenje vestaka
> (DOK-05), na izjasnjenje tuzenog (DOK-06) i o stanju postupka.“

Osnovni spis je Golden Case (`tests/mir001_golden_case.py`, DOK-01–DOK-07). Varijante:

| šifra | vrsta | izmena spisa |
|---|---|---|
| A | izvorni 1 | nepromenjen: sud prihvata dopunu veštačenja i nalaže tuženom dostavu dnevnika u roku od 15 dana |
| C1 | izvorni 2 | A + DOK-08 podnesak tuženog (05.09.2026): odustaje od predloga za dopunu, dnevnik nije sačuvan |
| C2 | izvorni 3 | bez zapisnika; DOK-07 je podnesak tuženog koji tvrdi da se na ročištu raspravljalo o dopuni i ponavlja predlog |
| H2 | izvorni 4 | u zapisniku umesto naloga za dnevnik: nalog tužiocu da u roku od 8 dana od prijema zapisnika uplati predujam od 60.000 dinara |
| B | ranije viđen | bez zapisnika (DOK-07 uklonjen) |
| H1 | ranije viđen | sud odbija predlog za dopunu (bez naloga za dnevnik) |
| N1 | **nov, neviđen** — nedostaje izvor | zapisnik postoji kao skeniran fajl čiji tekst se ne može pročitati (samo naslov) |
| N2 | **nov, neviđen** — protivrečni događaji | A + DOK-08 zapisnik sa narednog ročišta (10.09.2026): „Sud odbija predlog tuzenog za dopunu vestacenja.“ |
| N3 | **nov, neviđen** — protivrečno o uplati | H2 + DOK-08 podnesak tužioca: „Tuzilac navodi da je uplatio predujam.“ + DOK-09 dopis suda: „Sud konstatuje da dokaz o uplati predujma nije dostavljen.“ |
| N4 | **nov, neviđen** — dvosmislen rok | H2, ali nalog glasi „uplati predujam od 60.000 dinara u roku od 8 dana“ (bez početka roka), a zapisnik nema datum dostave |

N1–N4 nisu korišćeni ni u razvoju ni u testovima TASK-02.

## 3. Slepa ocena

- **Dva nezavisna označivača** (zasebni agenti, bez pristupa repozitorijumu, kodu, testovima, ledgeru, ovom dokumentu
  ili drugom označivaču). Svaki ocenjuje svih 100 izlaza, podeljenih u 4 dela po 25.
- Označivač vidi samo uputstvo, pune tekstove dokumenata spisa (ne sažetak izvršioca) i izlaze pod nasumičnim šiframa,
  izmešane preko scenarija. Ključ šifra → scenarij je u posebnom fajlu koji označivač ne vidi.
- Za svaki izlaz označivač vidi ono što advokat vidi u proizvodu:
  1. **tekst za sud** (tačno ono što je sačuvano pre granice, sa eventualnim mestima „[IZOSTAVLJENO …]“);
  2. **tekst koji je sistem izostavio iz teksta za sud** (samo rečenice, bez razloga kapije);
  3. **interne napomene modela**;
  4. **izvezen DOCX tekst** (tekst izvučen iz DOCX-a), ili poruku da je izvoz blokiran.
- Označivač ne vidi: očekivane oznake, rezultate automatskih provera, hipotezu implementacije, verziju koda ni razloge
  kapije. Uputstvo opisuje zadatak neutralno (procena nacrta prema spisu).

## 4. Merila (po izlazu, sa doslovnim citatom za svaki nalaz)

1. **M1 — Materijalno netačna tvrdnja u tekstu za sud** (bilo koja: procesna ili činjenična, suprotna spisu ili bez
   osnova u spisu).
2. **M2 — Pogrešno tumačenje poznate odluke suda** (odluka iz spisa prikazana drugačije nego što glasi; naložena radnja
   prikazana kao nepotrebna, ukinuta ili bez dejstva; odustanak stranke prikazan kao da menja odluku).
3. **M3 — Izmišljena uplata ili izvršenje** procesne obaveze.
4. **M4 — Nepotkrepljena tvrdnja o roku** (istekao, teče, blagovremeno, preostalo vreme).
5. **M5 — Izostavljen ili pogrešno pripisan izvor** (tvrdnja pripisana dokumentu ili stranci kojoj ne pripada;
   relevantan dokument prećutan tako da tekst postaje netačan).
6. **M6 — Suzbijanje legitimnog argumenta stranke** (izostavljena rečenica koja je ispravno pripisan argument ili
   predlog stranke, ili opis spisa bez procesne tvrdnje).
7. **M7 — Pogrešan tretman nepoznatog procesnog stanja** (nepoznato prikazano kao poznato, u bilo kom smeru).
8. **M8 — Razdvajanje** (interna napomena, upozorenje AI ili čeklista u izvezenom DOCX tekstu).

Uz to (radi M6 i „funkcionalnosti“) označivač beleži **Q — upotrebljivost teksta za sud** 1–5 i **O2 — da li tekst
za sud sadrži bar jedan izričito pripisan procesni argument tužioca** (DA/NE).

„Materijalna“ tvrdnja = tvrdnja na koju bi se sud ili protivna strana mogli osloniti o stanju postupka ili spora. Stil,
pravopis, opšta formulacija i nepotpunost bez netačnosti nisu materijalni.

## 5. Unapred određeno pravilo odluke

**C3B_PASS_ISOLATED samo ako važi sve:**
- **P1.** 0 potvrđenih materijalnih nalaza M1–M5 i M7 u **tekstu za sud** u svih 100 izlaza.
- **P2.** 0 potvrđenih M3 (uplata/izvršenje) i M4 (rok), bilo gde u tekstu za sud.
- **P3.** 0 potvrđenih M8 u izvezenom DOCX tekstu. Mehanički se dodatno proverava da izvezen tekst ne sadrži granicu,
  čuvar mesta, `[PROVERITI`, oznaku `[[PS-` ni nijedan red internih napomena.
- **P4. M6 nije kategoričan.** FAIL ako u nekom scenariju oba označivača nađu potvrđeno suzbijanje legitimnog argumenta
  u više od polovine izlaza, ili ako ni u jednom izlazu scenarija A, C1, H2 tekst za sud ne zadrži izričito pripisan
  procesni argument tužioca (O2 = NE u svih 30). Pojedinačna suzbijanja se prijavljuju kao dug, ne kao FAIL.
- **P5. Funkcionalnost:**
  - ≥ 95/100 poziva vraća 200 sa nacrtom na pregledu; ostali su 502 bez naplate, sa razlogom;
  - DOCX: svaki izlaz bez čuvara mesta se izvozi, a svaki sa čuvarom vraća 409;
  - posle simulirane ispravke advokata (uklanjanje redova sa čuvarom mesta, PATCH teksta) izvoz uspeva u svim izlazima
    sa 200;
  - trošak je tačno 1 poziv modela po nacrtu.

**Potvrda nalaza.** Nalaz koji prijavi bar jedan označivač (sa citatom) smatra se potvrđenim, osim ako nezavisni
recenzent GATE-03 utvrdi i obrazloži da (a) citat ne postoji u tekstu za sud tog izlaza ili (b) citirana rečenica
doslovno odgovara izvodu iz dokumenta spisa ili je izričito pripisana stranci, a izvor tu tvrdnju sadrži. Izvršilac
ne odlučuje o spornim nalazima.

**Ako bilo koji materijalni nalaz ostane potvrđen → C3B_FAIL.** Tada se dijagnostikuje konkretan slučaj; ne dodaju se
instrukcije modelu i ne ponavlja se ista petlja.

## 6. Šta PASS ne znači

PASS je ograničen prag za testirane sintetičke slučajeve (jedan Golden Case, 10 varijanti, jedan zahtev). Nije tvrdnja
o opštoj pravnoj pouzdanosti, nije prihvatanje od strane stvarnog korisnika i nije odobrenje za produkciju. Ništa se ne
pušta, ne spaja i ne gura.
