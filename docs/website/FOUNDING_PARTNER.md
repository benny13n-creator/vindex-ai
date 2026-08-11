# VINDEX AI — FOUNDING PARTNER PROGRAM

Specifikacija za javnu stranicu i CTA. Stanje: `b6c62143`.

> Ovaj dokument definiše **strukturu** programa i **granicu onoga što se sme
> obećati**. Sve što traži poslovnu odluku izričito je označeno kao
> `ODLUKA VLASNIKA` i **ne pojavljuje se na sajtu dok odluka ne padne**.

---

# 1. ZAŠTO PROGRAM UOPŠTE POSTOJI

Vindex danas nema nijednog korisnika. To nije nedostatak koji treba sakriti —
to je stanje koje određuje kakva ponuda uopšte može biti iskrena.

Nemamo šta da prodamo: nijedan plan se ne može kupiti (`STRIPE_URL = ''`,
`static/vindex.js:124`), krediti se ne obnavljaju, a tarifa se menja isključivo
ručnim SQL-om nad bazom. Svaka „kupovina" bila bi lažna.

Ono što **imamo** je sistem koji radi i koji je prošao jedanaest talasa
dokazivanja. Ono što **nemamo** je ijedan advokat koji ga je koristio na svom
predmetu.

**Founding Partner program razmenjuje tačno to:** rani pristup stvarnom sistemu
za povratnu informaciju koja oblikuje proizvod.

---

# 2. POZICIONIRANJE

Ne „popust za rane korisnike". Ne „lista čekanja". Ne „demo".

> **Ograničen broj advokata koji koriste Vindex na stvarnim predmetima dok se
> proizvod još oblikuje — i čije primedbe menjaju šta se gradi sledeće.**

Ton: poziv na saradnju među profesionalcima, ne prodaja. Advokat koji ovo čita
treba da razume da mu se traži **vreme i pažnja**, a ne novac.

---

# 3. ŠTA UČESNIK DOBIJA — samo dokazivo

| Dobija | Zašto je to istina danas |
|---|---|
| Pristup sistemu koji radi | Beta baseline je zamrznut (`docs/beta_war/BETA_BASELINE_FROZEN.md`); 4818 testova prolazi na četiri nezavisna redosleda |
| Direktan kontakt sa osobom koja gradi proizvod | Nema podrške ni prodajnog tima — jedini kanal je direktan. To je ograničenje pretvoreno u prednost, i takvo se i opisuje |
| Uticaj na redosled razvoja | Iskreno: nema formalni proces. Sme se reći da primedbe stižu direktno onome ko odlučuje, ne da postoji glasanje o funkcijama |
| Rad na stvarnim predmetima, ne na demo podacima | Sistem je pun; ne postoji „demo režim" koji bi ograničavao |

---

# 4. ŠTA SE **NE** OBEĆAVA — obavezujuće

Ovo je najvažniji deo dokumenta. Nijedna od sledećih rečenica ne sme se pojaviti
ni u kom obliku:

| Zabranjeno | Zašto |
|---|---|
| **Cena, popust, procenat** | Nema komercijalnog modela. Svaki broj bi bio izmišljen. |
| **„Doživotni pristup"** | Obaveza koju niko ne može da garantuje. |
| **„Zaključana cena zauvek"** | Isto. |
| **Konkretan broj mesta** *(„samo 10 kancelarija")* | Broj nije određen. Veštačka oskudica je laž. |
| **Rok** *(„prijave do 1. septembra")* | Nema odluke o roku. |
| **SLA, vreme odgovora, dostupnost** | Ništa od toga se ne meri. |
| **Obećanje funkcije koja ne postoji** | Vidi `VINDEX_WEBSITE_CLAIMS_REGISTRY.md` — `ROADMAP` stavke smeju samo u „Vizija", nikad kao deo ponude. |
| **„Vaše primedbe će biti implementirane"** | Sme: „stižu direktno". Ne sme: obećanje izvršenja. |
| **Bilo koja tvrdnja o drugim učesnicima** | Nema ih. Nema „pridružite se kancelarijama koje…". |

## Posebno o ceni

`ODLUKA VLASNIKA`. Do nje, javna formulacija je:

> **Uslovi za Founding Partnere biće definisani pre nego što se otvori
> komercijalni model. Dogovaraju se direktno, ne preko cenovnika.**

Ova rečenica je istinita, ne obećava ništa, i ne zatvara nijednu buduću opciju.

---

# 5. CTA

**Primarni CTA na celom sajtu:** `Prijavite se za Betu`
**Founding Partner CTA:** `Prijavite interesovanje`

Namerno **nije** „Postanite Founding Partner" — to bi impliciralo da je prijava
dovoljna. Ovo je razgovor, ne registracija.

## Odnos prema Beta prijavi

Jedna forma, ne dve. Beta prijava je ulaz; Founding Partner je **ishod razgovora**
sa nekim ko se prijavio. Dve odvojene forme bi stvorile utisak dva proizvoda i
dva nivoa pristupa koja ne postoje.

Na Founding Partner stranici CTA vodi na **istu** Beta formu, sa dodatnim
opcionim poljem (v. §6).

---

# 6. FORMA — POLJA

Osnovna prijava (`POST /waitlist/prijava` — postojeći endpoint):

| Polje | Obavezno | Zašto postoji |
|---|---|---|
| Ime i prezime | da | obraćanje |
| E-pošta | da | jedini kanal |
| Kancelarija / grad | ne | kontekst, ne kvalifikacija |
| Kratka poruka | ne | *„Na kakvim predmetima biste ga koristili?"* |

**Najviše četiri polja, dva obavezna.** Bez telefona, bez veličine kancelarije,
bez padajućih lista o delatnosti, bez „kako ste čuli za nas".

> **Tehnička obaveza:** forma mora biti projektovana oko onoga što
> `POST /waitlist/prijava` stvarno prima. Ako endpoint ne prima neko od gornjih
> polja, polje se **izbacuje** — ne dodaje se backend izmena zbog forme.
> Provera je u `docs/website/FRONTEND_INTEGRATION_PLAN.md`.

## Kvalifikaciona pitanja — namerno ih NEMA na formi

Kvalifikacija se dešava u razgovoru, ne u obrascu. Obrazac koji filtrira
odbija ljude pre nego što ste čuli šta imaju da kažu — a u fazi bez ijednog
korisnika to je najskuplja greška koju možete napraviti.

---

# 7. ŠTA SE DEŠAVA POSLE PRIJAVE

Sajt sme da kaže samo ono što je sigurno:

> **Javljamo se lično. Nema automatskih poruka.**

Istinito je (nema onboarding automatike), i postavlja tačno očekivanje.

**Ne sme:** „odgovaramo u roku od 24 sata" — to je SLA koji niko ne meri.

---

# 8. VEZA SA BUDUĆIM KOMERCIJALNIM MODELOM

`ODLUKA VLASNIKA` — sve ispod je predlog, ništa ne ide na sajt bez potvrde.

Kad se komercijalni model otvori, Founding Partneri su ljudi koji su proizvod
koristili pre nego što je imao cenu. Šta to praktično znači — prelazni period,
uslovi, trajanje — **nije odlučeno i zato se ne pominje**.

Jedina rečenica koja danas sme:

> Uslovi se dogovaraju direktno, pre otvaranja komercijalnog modela.

## Šta bi trebalo odlučiti pre nego što program krene javno

1. Da li Founding Partner status išta znači posle otvaranja naplate — i šta.
2. Da li postoji gornja granica učesnika *(ne mora; ali ako postoji, mora biti
   stvarna)*.
3. Kako se meri da je saradnja uspela — sa obe strane.

Nijedno od ovoga ne blokira izradu stranice. Blokira samo **objavljivanje
konkretnih uslova**.

---

# 9. STRANICA — STRUKTURA

| Sekcija | Poruka | Vizuel |
|---|---|---|
| Uvod | Šta program jeste i šta nije | bez slike |
| Zašto postoji | Nemamo korisnike; tražimo prve — otvoreno | bez slike |
| Šta dobijate | četiri stavke iz §3 | tekstualne grupe, bez ikona |
| Šta ne obećavamo | **sekcija ostaje javna** | bez slike |
| Kome je namenjen | advokat koji vodi predmete i spreman je da javi šta ne valja | bez slike |
| Prijava | ista forma kao Beta | forma |

**Sekcija „Šta ne obećavamo" je javna namerno.** U kategoriji u kojoj svi
obećavaju sve, spisak onoga što ne obećavate je najjači signal da ostalom što
pišete može da se veruje.

---

# 10. TON — TRI PRAVILA

1. **Bez veštačke hitnosti.** Nema odbrojavanja, nema „ostalo je još X mesta".
2. **Bez laskanja.** Ne „za vizionarske advokate". Advokat prepoznaje prodaju.
3. **Prvo lice, jednina.** Proizvod gradi jedna osoba; množina „mi" zvuči kao
   kompanija koja ne postoji, i prva je stvar koju iskusan kupac prepozna kao lažnu.

---

# 11. OTVORENE ODLUKE — spisak za vlasnika

| # | Odluka | Blokira li stranicu? |
|---|---|---|
| 1 | Uslovi za Founding Partnere posle otvaranja naplate | **Ne** — stranica ide bez njih |
| 2 | Postoji li gornja granica učesnika | **Ne** — ne pominje se dok ne postoji |
| 3 | Kontakt podaci firme (pravno lice, adresa, PIB) za podnožje i pravne strane | **Da, za podnožje** — Phase A ih vodi kao `UNKNOWN` |
| 4 | Da li Founding Partner ima zasebnu stranicu ili sekciju na Beta stranici | **Ne** — predlog je zasebna stranica, sekcija je jeftinija varijanta |

Samo **odluka 3** stvarno blokira — i to samo podnožje i pravne stranice, ne ceo sajt.
