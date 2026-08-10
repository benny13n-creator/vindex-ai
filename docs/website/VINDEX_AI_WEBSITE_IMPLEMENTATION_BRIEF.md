# VINDEX AI — WEBSITE IMPLEMENTATION BRIEF

Stanje: `ed343453`. Obavezujući izvor tvrdnji: `docs/website/VINDEX_AI_PUBLIC_CLAIMS.md`.
**Ovo nije prompt za izradu.** Ovo je strateška specifikacija iz koje se on piše.

---

## 1. POZICIONIRANJE — HIJERARHIJA

```
NIVO 1  KATEGORIJA     Operativni sloj za rad zasnovan na dokumentima i predmetima
NIVO 2  SUŠTINA        Sistem evidencije: uređen kontekst + poreklo + nepromenljiv trag
NIVO 3  PRVO TRŽIŠTE   Advokatura — najzahtevnija sredina za proveru
NIVO 4  PROŠIRENJE     Banke, notarijat, osiguranje, korporativna pravna služba, revizija
```

Posetilac ne sme pomisliti *„pravni proizvod koji će možda raditi i druge stvari"*, nego
*„operativni sloj čija je prva ozbiljna primena pravni rad"*.

## 2. ANALIZA IZRAZA „OPERATIVNI SISTEM" — ključna odluka ovog dokumenta

**Šta arhitektura stvarno podržava:** trajan strukturisan kontekst (`shared/case_context.py`),
entitete, činjenice, rokove, obaveze, dokaze, poreklo po polju, nepromenljivu evidenciju,
upravljanje pristupom, radne tokove — **i javni API sa ključevima** (`/v1/query`,
`api_kljucevi` u `routers/export.py`), dakle treće strane mogu da čitaju iz sloja.

**NAJJAČA ODBRANJIVA VERZIJA:** *„operativni sloj"* / *„sistem evidencije za predmet"*.
Trajan je, autoritativan, i drugi sistemi mogu da ga čitaju.

**PREJAKA VERZIJA:** *„operativni sistem"* kao doslovna tehnička tvrdnja. Operativni sistem
podrazumeva da drugi **grade i pokreću** aplikacije na njemu. To ne postoji — nema modela
aplikacija, nema SDK-a, nema ekosistema.

**PREPORUKA:** izraz „operativni sistem" koristiti **isključivo kao viziju**, jasno označenu
kao pravac, i **nikada u hero naslovu**. Kategorija je **„operativni sloj"**. Tehničkom
sagovorniku je razlika očigledna, a lažna tvrdnja skuplja od efektne reči.

## 3. UNIVERZALNI PROBLEM

**UNIVERZALNI PROBLEM:** profesionalac radi sa velikim brojem dokumenata iz kojih moraju
ostati povezani činjenice, obaveze, rokovi i odluke — a svaka tvrdnja mora moći da se vrati
na izvor. Danas ta veza postoji samo u glavi osobe koja predmet vodi.

**UNIVERZALNI ODGOVOR:** Vindex održava tu vezu izvan glave — kao uređen prikaz u kome svako
polje zna odakle potiče, uz trag ko je šta menjao.

| Delatnost | Izraz problema | Podržano arhitekturom? |
|---|---|---|
| **Advokatura** | spis, rokovi u tekstu, dokazi, ročišta | **DA — implementirano** |
| Korporativna pravna služba | ugovori, obaveze, rokovi | DA — isti mehanizam |
| Notarijat | isprave, formalni zahtevi, evidencija | DA — traži prilagođavanje pojmova |
| Banke | dokumentacija klijenta, provera, rizik | **DELIMIČNO — traži integracije** |
| Osiguranje | odštetni zahtev i prateća dokumentacija | DELIMIČNO |
| Revizija / konsalting | rad na osnovu dokumenata | DELIMIČNO |

Na sajtu se **imenuje** samo advokatura kao prva primena; ostalo se pominje kao primenljivost,
nikad kao vertikala.

## 4. TEST POZICIONIRANJA — 6 kandidata (1–5 po kriterijumu)

| Kandidat | Tačnost | Diferenc. | Razumljivost | Skalabilnost | Odbranjivost | Σ |
|---|---|---|---|---|---|---|
| „AI platforma za pravo" | 3 | 1 | 5 | **1** | 4 | 14 |
| „Operativni sistem za profesionalce" | 2 | 4 | 3 | 5 | **2** | 16 |
| **„Operativni sloj za rad na predmetima"** | **5** | 4 | 4 | 5 | **5** | **23** |
| „Infrastruktura za profesionalno znanje" | 4 | 3 | 2 | 5 | 4 | 18 |
| „Case intelligence" | 3 | 3 | 2 | 4 | 3 | 15 |
| **„Sistem evidencije za složen rad"** | **5** | **5** | 3 | 5 | **5** | **23** |

**PREPORUKA — spoj dva najbolja.** Kategorija je *operativni sloj*; diferencijator je
*sistem evidencije sa poreklom*. Kategorija govori tržištu gde pripadamo, diferencijator zašto
smo drugačiji. Nijedan sam nije dovoljan: prvi je tačan ali neupečatljiv, drugi upečatljiv ali
ne smešta proizvod u kategoriju.

## 5. HERO

**NASLOV (≤10 reči, za razradu):**
> Uređen predmet. Poznato poreklo svakog podatka.

**PODNASLOV (≤30 reči):**
> Vindex održava strukturisan prikaz onoga na čemu radite — dokumenata, činjenica, rokova — i za svaki podatak zna iz kog dokumenta potiče. Prva primena: advokatske kancelarije.

**PRIMARNI CTA:** Prijavite se za zatvoreno testiranje
**SEKUNDARNI:** Preuzmite bezbednosni list *(dokument već postoji u `static/`)*

**VIZUELNI DOKAZ:** prikaz jednog polja konteksta sa vidljivom oznakom porekla.
**SCREENSHOT REQUIRED** — upotrebljiv prikaz ne postoji u repozitorijumu. Do tada: dijagram.

## 6. HIJERARHIJA PORUKE

| Vreme | Posetilac mora razumeti |
|---|---|
| **5 s** | Vindex drži uređen predmet i zna odakle mu je svaki podatak |
| **15 s** | To rešava gubitak konteksta i ručnu proveru |
| **30 s** | Unos → uređen predmet → AI nad uređenim prikazom → trag do izvora |
| **2 min** | Zašto je to pouzdanije od lepljenja dokumenata u ćaskanje sa AI-jem |
| **5 min** | Bezbednost, razdvajanje podataka, stanje proizvoda, kako se prijaviti |

## 7. STRATEGIJA VIŠE DELATNOSTI

**PREPORUKA: C — platforma prva, delatnosti kao primeri.**

Navigacija po delatnostima (A) zaključava proizvod u vertikale koje nisu validirane i traži
sadržaj koji ne postoji. Navigacija po funkcijama (B) pretvara sajt u listu robe široke
potrošnje — a OCR, pretraga i sažimanje danas ima svako. Platforma prva, uz **jednu sekciju**
„Gde se još primenjuje", daje širinu bez praznih strana.

**Advokatura:** imenovana u podnaslovu heroja i u jednoj sekciji. **Ne** u naslovu, **ne** u
navigaciji, **ne** u domenu. Ostale delatnosti: jedan red, uz izričito *„mogućnosti
proširenja, bez korisnika"*.

## 8. POVERENJE — potvrđeno da ide pre liste funkcija

**PORUKA:** „Svaka tvrdnja ima izvor koji možete proveriti."
**DOKAZ:** poreklo po polju · nepromenljiva evidencija · razdvajanje podataka po vlasniku ·
uloge i ovlašćenja · sadržaj upita se ne upisuje u evidenciju.
**CTA:** preuzimanje bezbednosnog lista, bez formulara.

**Na početnoj:** tri rečenice i tri dokaza. **Na strani Bezbednost:** DPA, bezbednosni list,
AI disclosure, detalji mehanizama. **Nikad javno:** imena tabela i ruta, service-role,
struktura migracija, ime dobavljača modela.

## 9. ARHITEKTURA — potvrđeno P0 = 3 strane

Šira pozicija **ne** zahteva više strana. Zahteva **drugačiji naslov** na istoj strani.

| Strana | Svrha | Publika | Sekcije | CTA | Prio |
|---|---|---|---|---|---|
| Početna | pozicija, poverenje, stanje | advokat vlasnik | hero, problem, kako radi, zašto verovati, šta radi, za koga, stanje | prijava | **P0** |
| Bezbednost | ukloniti blokator | oprezan kupac | mehanizmi, dokumenti | preuzmi | **P0** |
| Kontakt | ≤3 polja | oboje | forma | pošalji | **P0** |
| Kako radi | razrada sa prikazima | zainteresovan | tok, scenario | prijava | P1 — **čeka prikaze** |

## 10. NAVIGACIJA

```
Vindex        Bezbednost        Kontakt              [Prijava za testiranje]
```

Bez stavke „Industries": nema sadržaja da je popuni, a prazna strana šteti više nego njeno
odsustvo. Dugoročno proširenje se signalizira **jednom sekcijom na početnoj**, ne navigacijom.

## 11. CTA

**PRIMARNI:** „Prijavite se za zatvoreno testiranje" — jedini iskren: nema prodajnog tima,
nema samouslužne registracije, nema korisnika.
**SEKUNDARNI:** „Preuzmite bezbednosni list".
**ZA ADVOKATE:** isti primarni.
**ZA DRUGE DELATNOSTI:** **preuranjeno.** Zaseban CTA implicirao bi spremnost koja ne postoji;
jedan opšti kontakt je dovoljan.
**IZBEGAVATI:** „Počnite besplatno", „Zakažite demo", „Kontaktirajte prodaju", formular >3 polja.

## 12. SUKOB SA DOKUMENTOM TVRDNJI — jedan, prijavljen a ne rešen izmišljanjem

Šira pozicija *„operativni sloj za profesionalni rad"* je **strateška**, ne funkcionalna
tvrdnja. `VINDEX_AI_PUBLIC_CLAIMS.md` je ne pokriva jer to nije tvrdnja o mogućnosti.

**Predlog rešenja:** dozvoliti je samo ako je jasno označena kao pravac i praćena imenovanjem
advokature kao jedine sadašnje primene. **Odluka pripada vlasniku** — nisam je rešio
dodavanjem nove tvrdnje u obavezujući dokument.

## 13. VIZUELNI PRAVAC

**Nalaz koji menja pretpostavku:** postojeći identitet koristi **Cormorant Garamond** — serif,
editorijalan, ne tehnički monospace kako sam ranije pretpostavio. To je bliže instituciji nego
startapu, što **pogoduje** dugoročnom pozicioniranju prema bankama.

**SEVERNA ZVEZDA:** ozbiljno kao pravni dokument, precizno kao inženjerski alat.
**JEZIK:** Cormorant za naslove, neutralan sans za telo; podloga `#010308`, akcenat `#00d4ff`,
tekst `#e6edf3`; oštri uglovi, mnogo praznog prostora, dijagrami umesto ikonica.
**IZBEGAVATI:** stock fotografije, sjaj, gradijente, mozgove, kola, animirane brojače.

## 14. TEHNIČKA OGRANIČENJA

Postojeći frontend: **vanilla JS/CSS, bez build sistema** — `static/vindex.js` (23.303 linije),
`static/vindex.css` (9.630). FastAPI servira `/static`. Postoji PWA (`sw.js`, `manifest.json`).

| | |
|---|---|
| **REUSE** | paleta, Cormorant, `security.html` i `dpa.html` kao sadržaj |
| **BUILD NEW** | zaseban statički sajt: jedan HTML + jedan CSS, bez okvira |
| **DO NOT TOUCH** | `vindex.js`, `vindex.css`, `sw.js` (keš), pravne strane |
| **NE UVODITI** | React, Tailwind, animacione biblioteke, build korak |

Razlog za „ne uvoditi": aplikacija ima service worker sa keširanjem; uvođenje build sistema
zbog trostranog sajta unosi rizik u proizvod koji radi.

## 15. SEO

`<title>` sa kategorijom, **ne** „AI za pravo" · meta opis ≤155 znakova · canonical ·
OpenGraph + slika · `Organization` structured data · tačno jedan `<h1>` · semantični naslovi.
Ciljni pojmovi: *operativni sloj*, *evidencija predmeta*, *poreklo podatka*, *advokatska
kancelarija*. **Bez blog fabrike.**

## 16. PRISTUPAČNOST

Semantični HTML · kontrast ≥ 4.5:1 — **proveriti `#00d4ff` na `#010308`**, akcenat na tamnoj
podlozi je granični slučaj · vidljiv focus · potpuna tastatura · `prefers-reduced-motion` ·
dodirne mete ≥ 44px · alt tekstovi dijagrama objašnjavaju **sadržaj**, ne izgled.

## 17. PERFORMANSE

≤1.5 s na 4G · bez okvira · font `display=swap`, najviše dve težine · `width`/`height` na svim
slikama radi CLS · SVG dijagrami · **bez animacione biblioteke** — prelazi u CSS-u.

## 18. RED TEAM

| Prigovor | Ozbiljnost | Ispravka |
|---|---|---|
| „Još jedan omotač oko ChatGPT-a" | **VISOKA** | poreklo polja i evidencija **iznad pregiba** |
| „Operativni sistem" zvuči kao naduvavanje | **VISOKA** | ne koristiti u heroju; kategorija je „operativni sloj" |
| Deluje preširoko i nefokusirano | SREDNJA | advokatura u podnaslovu; ostale delatnosti jedan red |
| Advokat misli da nije za njega | SREDNJA | konkretan pravni scenario u „Kako radi" |
| Bankar ne vidi sebe | NISKA | prihvatljivo — banke nisu tržište za lansiranje |
| Kupac sumnja u bezbednost | **VISOKA** | dokumenti dostupni bez formulara |
| **Nema dokaza da proizvod radi** | **VISOKA** | **SCREENSHOT REQUIRED — najveći nedostatak** |
| CTA neprikladan fazi | NISKA | poziv na testiranje odgovara stanju |

## 19. KRITERIJUMI PRIHVATANJA

Sajt je gotov kada: nijedna tvrdnja nije van odobrene liste · izraz „operativni sistem" se ne
pojavljuje kao tehnička tvrdnja · advokatura je imenovana ali ne dominira navigacijom ·
poverenje stoji iznad liste funkcija · postoji tačno jedan primarni CTA · osnovni sadržaj radi
bez JavaScript-a · kontrast i tastatura provereni · **aplikacija netaknuta**.
