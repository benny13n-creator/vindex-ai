# VINDEX AI

**AI infrastruktura za složen profesionalni rad**

> AI infrastruktura za složen profesionalni rad

Vindex AI je platforma koja povezuje dokumente, kontekst predmeta, znanje i AI modele u jedan radni sloj — sa proverljivim tragom o tome odakle svaki podatak dolazi.
Prvo tržište: advokatske kancelarije.

## PROBLEM

*Vreme profesionalca troši se na obradu informacija, ne na stručnu procenu.*

Rad na složenom predmetu znači rad sa velikim brojem dokumenata koji nisu međusobno povezani. Činjenice su razbacane po podnescima, prilozima i prepisci. Rokovi zavise od datuma koji se nalaze u tekstu, a ne u kalendaru.

Kada predmet traje mesecima, kontekst se gubi. Onaj ko se vrati na predmet posle nekoliko nedelja mora ponovo da rekonstruiše šta je utvrđeno, šta je sporno i šta sledi.

Cena propuštene informacije je nesrazmerno visoka, a provera je skupa jer zahteva ponovno čitanje.

> Ovaj opis proizlazi iz problema koji platforma rešava. Ne sadrži statistiku koju nismo sami izmerili.

## PRISTUP

*Vindex nije ćaskanje sa modelom. Vindex je sloj između predmeta i modela.*

Razlika je u tome šta model dobija. Kod običnog AI alata korisnik sam sastavlja pitanje i sam bira šta će zalepiti u njega. Kod Vindexa sistem održava strukturisan prikaz predmeta i taj prikaz prosleđuje modelu.

Svako polje tog prikaza nosi oznaku porekla — iz kog dokumenta potiče, ko ga je uneo i kada se osvežava. Zahvaljujući tome moguće je razlikovati utvrđenu činjenicu od zaključka koji je neko izveo.

- **DOKUMENTI** — unos, prepoznavanje teksta, klasifikacija
- **KONTEKST PREDMETA** — činjenice, rokovi, dokazi, poreklo podatka
- **AI SLOJ** — model dobija strukturisan prikaz, ne sirov tekst
- **REZULTAT** — analiza, nacrt, upozorenje — uz trag do izvora
- **TRAG** — nepromenljiv zapis ko je šta pokrenuo i kada

## ŠTA VINDEX DANAS RADI

*Ispod je samo ono što je implementirano i proverljivo u sistemu.*

**OBRADA DOKUMENATA** — Unos većeg broja dokumenata odjednom, prepoznavanje teksta iz skeniranih fajlova, automatska klasifikacija i povezivanje sa predmetom. Original se čuva.

**RAZUMEVANJE PREDMETA** — Strukturisan prikaz predmeta sa oznakom porekla za svako polje. Hronologija, stranke, dokazi i rokovi vode se kao povezani podaci, ne kao slobodan tekst.

**PRETRAGA I ZNANJE** — Semantička pretraga po sadržaju dokumenata i po bazi propisa i prakse, umesto pretrage po ključnoj reči.

**ANALIZA** — Prepoznavanje rokova i obaveza, uočavanje protivrečnosti između dokumenata, procena rizika predmeta.

**IZRADA PODNESAKA** — Generisanje nacrta vezanog za konkretan predmet i njegove dokumente.

**EVIDENCIJA I BEZBEDNOST** — Nepromenljiv zapis radnji, poreklo svakog AI odgovora, razdvajanje podataka između korisnika i kancelarija.

## ZAŠTO PRVO PRAVO

*Advokatura je prvo tržište jer je najzahtevnija sredina za proveru, a ne zato što je jedina.*

Pravni rad ima svojstva koja se retko sreću zajedno: veliki obim dokumenata, složene veze između njih, potrebu da se iz teksta izvuku činjenice i datumi, obavezujuće rokove, visoku osetljivost podataka i zahtev da se svaka tvrdnja može vratiti na izvor.

Sistem koji izdrži takav rad primenljiv je i tamo gde su zahtevi blaži. Zato je advokatura izabrana kao okruženje za proveru — ne kao granica poslovnog dometa.

## OD PRAVA KA DRUGIM DELATNOSTIMA

*Sposobnosti platforme nisu vezane za pravnu materiju.*

- ADVOKATURA — prvo tržište, sredina za proveru
- NOTARIJAT — velike količine isprava, strogi formalni zahtevi
- BANKARSTVO — dokumentacija, provera podataka, procena rizika
- OSIGURANJE — obrada odštetnih zahteva i prateće dokumentacije
- KORPORATIVNI PRAVNI POSLOVI — ugovori, obaveze, rokovi
- KONSALTING I REVIZIJA — rad zasnovan na dokumentima i analizi

> Navedene delatnosti su mogućnosti proširenja. Vindex u njima trenutno nema korisnike niti sprovedenu proveru tržišta.

## BEZBEDNOST I POVERENJE

*Bezbednost je deo proizvoda, ne dodatak.*

**RAZDVAJANJE PODATAKA** — Pripadnost svakog zapisa proverava se u samoj operaciji nad bazom, a ne samo pre nje. Ovaj mehanizam je bio predmet više nezavisnih unutrašnjih provera.

**NEPROMENLJIVA EVIDENCIJA** — Zapisi o radnjama vezani su u lanac zaštićen kriptografskim otiskom i ograničenjima na nivou baze koja sprečavaju naknadnu izmenu ili brisanje.

**POREKLO AI ODGOVORA** — Za svaki AI poziv beleži se koji je model korišćen, u okviru kog predmeta i sa kojim identifikatorom zahteva. Sadržaj upita i odgovora se u tu evidenciju ne upisuje.

**KONTROLA PRISTUPA** — Prava unutar kancelarije razdvojena su po ulogama; administrativne radnje odbijaju se korisniku bez odgovarajućeg ovlašćenja.

**ZAŠTITA UPITA** — Ulazni sadržaj prolazi kroz proveru pre nego što se prosledi modelu.

> Ne tvrdimo potpunu bezbednost niti posedovanje sertifikata. Navedeni su mehanizmi koji postoje u sistemu.

## ARHITEKTURA AI SLOJA

*Model je komponenta koju platforma koristi, a ne sam proizvod.*

Vindex je projektovan tako da AI model bude zamenljiva komponenta. Platforma održava kontekst predmeta, pravila i evidenciju; model obavlja pojedinačan zadatak nad onim što mu platforma prosledi.

U sistemu postoji sloj koji odvaja Vindex od pojedinačnog dobavljača AI modela: jedinstven oblik zahteva i odgovora, kontrola pre poziva, normalizovane greške i evidencija posle poziva. Time se izbegava vezanost proizvoda za jednog dobavljača.

**U PRODUKCIJI** — Jedan dobavljač AI modela opslužuje sve postojeće funkcije.

**IMPLEMENTIRANO, NIJE U PRODUKCIONOM TOKU** — Sloj za rad sa više dobavljača, sa pripremljenim priključcima za tri različita dobavljača. Nijedna postojeća funkcija još ne ide kroz taj sloj.

**PLANIRANO** — Unakrsna provera odgovora između dva modela.

## TRENUTNO STANJE

*Proizvod je u završnoj pripremi pred testiranje sa prvim korisnicima.*

**RAZVOJ** — Funkcionalna celina je implementirana i pokrivena automatizovanim testovima koji se izvršavaju nad svakom izmenom.

**PROVERA TRŽIŠTA** — U toku su razgovori sa više advokata. Ostvaren je i kontakt sa Stefanom Gojkovićem, sudijskim pomoćnikom.

**TESTIRANJE** — Priprema zatvorenog testiranja sa ograničenim brojem korisnika.

**PRISUTNOST NA MREŽI** — Postoji uvodna stranica. Potpun sajt je u planu.

> Sagovornici navedeni iznad nisu korisnici, klijenti ni poslovni partneri. Reč je o ranim razgovorima radi provere pretpostavki.

## VIZIJA

*Od pravnog proizvoda ka infrastrukturi za profesionalni rad.*

Dugoročni cilj nije da Vindex bude još jedan alat koji odgovara na pitanja. Cilj je da bude sloj koji drži uređen prikaz stvarnosti jedne organizacije — dokumenata, obaveza, odluka i njihovog porekla — i da taj prikaz stavlja na raspolaganje AI modelima, ma koji model sutra bio najbolji.

Vrednost u tom slučaju ne leži u modelu, koji se menja, nego u uređenom kontekstu i proverljivom tragu, koji ostaju.

## SLEDEĆI KORAK

Vindex AI trenutno traži ograničen broj advokatskih kancelarija spremnih da učestvuju u zatvorenom testiranju.

Za razgovor o učešću, partnerstvu ili proveri primenljivosti u drugoj delatnosti, obratite se osnivaču putem kanala kojim ste primili ovaj dokument.

_Ovaj dokument opisuje stanje proizvoda u trenutku izrade. Ne sadrži obećanja o učinku niti garancije rezultata._
