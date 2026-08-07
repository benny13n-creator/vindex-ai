# Operation Living System — Executive Report za Bennija

**Datum**: 2026-08-07

## Šta je ovo bilo

Prva misija ove vrste: umesto testiranja pojedinačnih ruta/modula, 14 nezavisnih AI timova je
simuliralo kompletan radni dan advokatske kancelarije — prijava ujutru, novi dokumenti, hitan
poziv klijenta, izrada podneska, naplata, prekid rada (pad interneta, zatvaranje taba), dva
zaposlena koji rade na istom predmetu istovremeno, veliki portfolio (1000 dokumenata, 100
ročišta), i namerni napadi na svih 20 ključnih sistema platforme.

## Šta je pronađeno

Oko 70 stvarnih, potvrđenih problema, od kozmetičkih do ozbiljnih. Popravio sam 7 odmah (svaki sa
pravim testom koji dokazuje da je problem stvarno zatvoren), a preostalih ~63 sam formalno
zapisao sa tačnim objašnjenjem zašto nisu popravljeni u ovoj misiji — ništa nije sakriveno.

## Šta je popravljeno (7 stvari)

1. **AI Copilot je mogao pokazati "82% šanse za uspeh" za predmet koji je istovremeno na drugom
   ekranu (Court Predictor) pokazivao "max 50%"** — ista greška koju smo već zatvorili za 3 druga
   AI ekrana, sad zatvorena i za Copilot.
2. **KRITIČNO: email podsetnici za rokove su stizali i za ZATVORENE predmete.** Ako ste zatvorili
   predmet, a rok je i dalje bio zapisan u istoriji, sistem je i dalje slao email "Sutra ističe
   rok!" — direktno u inbox, ne na dashboard koji birate da otvorite. Ovo je bio najozbiljniji
   nalaz cele misije jer je to proaktivna poruka, ne nešto što advokat sam bira da pogleda.
3. **Fakturisan iznos je mogao biti izmenjen ili obrisan POSLE što je već ušao u fakturu** ako su
   se 2 zahteva preklopila u pogrešnom trenutku — sada je to nemoguće, sistem to blokira.
4. **Copilot "dodaj rok" funkcija je bila POKVARENA za većinu unosa** — AI je tražio od GPT-a
   vrednosti koje baza podataka ne prihvata, pa je dodavanje roka prirodnim jezikom gotovo uvek
   bacalo grešku, osim ako niste rekli baš reč "kritičan".
5. **Link za klijentski portal generisan od strane saradnika (ne vlasnika predmeta) nije radio** —
   klijent je dobijao email "evo vam pristup" ali link je uvek vraćao grešku "predmet nije
   pronađen", a vlasnik predmeta nije mogao ni da vidi ni da opozove taj link.
6. **Kad Genome (procena predmeta) ne uspe da se sačuva u bazu, korisnik je i dalje video "zeleno,
   uspešno"** iako baza nije sačuvala ništa novo — backend je to ispravno detektovao, ali frontend
   to nije proveravao.
7. **Isti problem kao #2, ali na početnoj strani (Command Center)** — zatvoreni predmeti su se
   pojavljivali među "današnjim ročištima"/"hitnim rokovima" na glavnom ekranu.

## Šta NIJE popravljeno i zašto (najvažnije stavke)

- **NAJOZBILJNIJI preostali nalaz**: brzo generisanje podneska (`/api/nacrt`) traži od GPT-a da
  SAM izmisli broj člana zakona (npr. "čl. 200 ZOO") bez ikakve provere protiv stvarnog teksta
  zakona. Ako advokat ne proveri ručno, u sud može otići dokument sa izmišljenim brojem člana.
  Ovo zahteva pravu integraciju sa bazom zakona (RAG), ne brzu popravku — nazvao sam ga jasno kao
  dug, prioritet #1 za sledeću misiju.
- Sistem je mogao naplatiti kredit i kada AI generisanje POTPUNO ne uspe (3 potvrđena mesta:
  brzi nacrt, podnesak, komandant predmeta) — postoji ispravan obrazac za ovo na drugom mestu u
  kodu, samo nije primenjen svuda.
- Isti "zatvoreni predmet se i dalje pojavljuje" problem postoji na još 4 mesta (CIO izveštaj,
  radna lista zadataka, AI podsetnik za zastarelost, kalendar) — popravljena su 2 najozbiljnija,
  ostala 4 su imenovana kao dug istog tipa.
- Skoro nijedna AI funkcija (osim 3 od ~60) nema pravu zaštitu od duplog klika koji bi mogao
  duplo naplatiti kredit — ovo zahteva izmenu u bazi (migraciju) koju, po našem standardnom
  pravilu, ja ne pokrećem — to ostaje na tebi.

Pun spisak sa tačnim tehničkim razlogom za svaku odloženu stavku je u
`docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` (traži `LIVINGSYS-DEBT-001` do `-063`).

## Testovi

Cela test-suita je zelena: **3.220 prošlo, 1 preskočeno, 0 palo.** Svaka od 7 popravki ima svoj
pravi test koji dokazuje da problem stvarno više ne postoji (ne samo da kod "izgleda ispravno").

## Šta preporučujem sledeće

Tri stvari bih prioritetizovao pre nego što se platforma javno predstavi kao "jedan koherentan
sistem":
1. Izmišljeni broj člana zakona u brzom nacrtu (`LIVINGSYS-DEBT-013`) — najveći reputacioni rizik.
2. Naplata kredita kad AI ne uspe (`LIVINGSYS-DEBT-002/-006/-027`) — direktan finansijski gubitak
   za korisnika.
3. Battle Report bez ograničenja procenata (`LIVINGSYS-DEBT-001`) — poslednji preostali "2 AI
   ekrana se ne slažu" nalaz.

I dalje čekam `SUPABASE_DB_URL` (samo za čitanje) da nezavisno proverim da li su migracije 102/103
zaista primenjene u produkciji — ovo je sada 7. misija zaredom da ovo pominjem.
