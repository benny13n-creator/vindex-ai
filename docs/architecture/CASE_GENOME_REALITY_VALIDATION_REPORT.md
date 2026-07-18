# Case Genome — Reality Validation Report

Status (2026-07-18): **Deo 1 (sintetička kalibracija) završen.** Deo 2 (5-10
stvarnih anonimizovanih predmeta) čeka founder-a da obezbedi dokumenta —
okvir za to je izgrađen i spreman (`scripts/genome_case_dna_evaluate.py`),
nije pokrenut.

Ovaj izveštaj NE tvrdi da je Genome spreman za produkciju na osnovu
sintetičkih rezultata. Sintetički batch postoji da (1) proveri da pipeline
stvarno radi kroz prave API endpoint-e, (2) izmeri da li Verification Layer
(Faza 1.3) ima razuman odnos lažnih pozitiva/negativa, (3) uspostavi
mernu metodologiju pre nego što se primeni na stvarne predmete.

---

## Deo 1 — Sintetička kalibracija

### Dataset opis

6 konstruisanih srpskih pravnih slučajeva, svaki sa namernim ground truth-om
i namernom kompleksnošću (sukobljene činjenice, nepotpuni dokazi, vremenska
neusaglašenost, mešavina jakih/slabih dokaza — svi zahtevani tipovi
pokriveni bar jednom):

| Oznaka | Tip | Namerna kompleksnost |
|---|---|---|
| CASE-A | Radni spor (otkaz) | Sukobljeni razlozi otkaza (disciplinski vs. ekonomski) — interna beleška protivreči zvaničnom rešenju |
| CASE-B | Ugovorni spor | Kompletan dosije, ali veštačenje namerno slabo/neodlučno |
| CASE-C | Naknada štete | Vremenska neusaglašenost — dva svedoka daju različite datume nezgode |
| CASE-D | Nasledstvo | Jak pisani dokaz (overen testament) naspram slabe, nepotkrepljene usmene tvrdnje |
| CASE-E | Potrošački spor | Namerno oskudan dosije — samo 1 dokument |
| CASE-F | Radni spor (mobing) | Sve četiri vrste složenosti kombinovane: interna kontradikcija u imejl prepisci, jak medicinski dokaz, slab/prazan HR sažetak |

Ovo NISU stvarni predmeti — sadržaj je fiktivan, konstruisan sa poznatim
odgovorom unapred, da bi ocena tačnosti bila objektivna (isti princip kao
LEC anotacija, samo mali kontrolisan uzorak umesto 150-200 stvarnih
dokumenata).

### Metodologija

Svih 6 slučajeva prošlo je kroz **stvarne API endpoint-e**, ne kroz direktan
upis u bazu:

```
POST /api/predmeti                    (kreiranje predmeta)
POST /api/predmeti/{id}/upload  × N    (stvarni .docx fajlovi, stvarna OCR/
                                         parse putanja, stvarna Genome
                                         pozadinska ekstrakcija)
```

Jedino što nije "pravo" u ovom harnessu: autentifikacija. Nema browser
automatizacije dostupne u ovom okruženju, pa je `api._require_auth` patch-ovan
da vrati fiksnog, STVARNOG, već postojećeg korisnika (founder-ov nalog) za
trajanje testa — svako telo endpoint-a, DB upis, pozadinski zadatak i
poslovno pravilo posle te tačke izvršava se potpuno nepromenjeno.
`services.event_bus.dispatch_pending_events()` pozvan je direktno (ne kroz
živi DispatchLoop, koji ne radi van glavnog app procesa) da deterministički
obradi outbox — ista funkcija koju produkcioni loop poziva na svaka 3s.

**Dva bug-a nadjena i ispravljena u samom harness-u tokom ovog batch-a**
(transparentno prijavljeno, ne sakriveno):
1. Polling `GET /case-dna` je prolazio kroz drugi auth mehanizam
   (`shared.deps.get_current_user`) od onog patch-ovanog
   (`api._require_auth`) — svaki poll je vraćao 401. Ispravljeno: polling
   sada čita `predmeti.case_dna` direktno (read-only), pipeline sam ostaje
   nepromenjen.
2. Poll petlja je prekidala čekanje na PRVOJ validnoj verziji genoma
   (`verzija >= 1`), ne na FINALNOJ. Kod uzastopnih upload-a, svaki upload
   pokreće SOPSTVENI nezavisni pozadinski refresh — kod CASE-C (4 dokumenta)
   ovo je uhvatilo verziju 3 (3 dokumenta) dok je verzija 4 (sva 4 dokumenta)
   još bila u toku. Uživo stanje baze je ispravno stiglo do v4 par sekundi
   kasnije — ovo NIJE bio defekt proizvoda, bio je defekt merenja. Ispravljeno:
   petlja sada čeka na `verzija >= broj_uspesno_uploadovanih_dokumenata`.
   Podaci ispod za CASE-C koriste ispravljenu (v4) verziju.

### Rezultati po dimenziji

**1. Faktička tačnost — VISOKA u svih 6 slučajeva.** Nijedna izmišljena
činjenica van kategorije zakonskih citata (ispod). Datumi, uloge stranaka,
sadržaj dokumenata dosledno tačno preneti. Polja koja dokumenti ne
specificiraju (JMBG, adrese, iznosi) dosledno označena kao "nepoznato", ne
izmišljena — dobar znak protiv halucinacije.

**2. Stopa nepodržanih tvrdnji — 6/6 slučajeva (100%) sadrži bar jedan
zakonski citat sa brojem člana koji NIJE doslovno prisutan ni u jednom
uploadovanom dokumentu** (npr. CASE-A: "Zakon o radu čl. 179" — nijedan
dokument ne pominje broj člana). Ovo je najjasniji, najmerljiviji nalaz
celog vežbanja. Validator (Faza 1.3) hvata 5/6 ovih slučajeva kroz
"unverified_law_ref" — ali CASE-A prolazi neopaženo jer se PROVERAVA SAMO
NAZIV ZAKONA (koji je prepoznat — "Zakon o radu" jeste poznat zakon), ne
BROJ ČLANA. Ovo je tačno ograničenje već navedeno u Faza 1.3 design note-u
("argumenti_za/protiv provenance nije proveravana") — sada empirijski
potvrđeno na stvarnom primeru, ne hipotetički.

*Napomena o reprezentativnosti:* nijedan od 6 sintetičkih dokumenata ne
sadrži zakonski citat u samom tekstu — stvaran podnesak advokata često
citira konkretne članove. Ovo je mogao veštački podići stopu "nepodržanih"
citata; stvaran batch može pokazati nižu stopu ako se citati zaista nalaze
u izvornim dokumentima.

**3. Kvalitet rangiranja dokaza — JAK, 6/6.** Svaki namerno postavljen
par jak/slab dokaz ispravno je prepoznat i rangiran po redosledu: CASE-B
(veštačenje ispravno najniže rangirano zbog neodlučnosti), CASE-C v4
(drugi svedok ispravno najniže rangiran zbog datumske nesigurnosti — sa
razlogom koji EKSPLICITNO navodi tu nesigurnost), CASE-D (usmena tvrdnja
ispravno najniže rangirana), CASE-F (HR sažetak ispravno nisko rangiran).

**4. Korisnost procene rizika — MEŠOVITO, važan nalaz.** Narativni deo
(najslabija_tacka, snaga_faktori, kontradikcije) je dosledno specifičan i
koristan u svih 6 slučajeva — ispravno identifikuje tačno onu slabost koju
sam namerno ugradio u svaki predmet. **Ali brojčani/kategorijski sažetak
NE razlikuje slučajeve uopšte: svih 6 slučajeva ima IDENTIČNIH 65%
(`snaga_predmeta_procent`) i IDENTIČNU ocenu "srednja" (`snaga_predmeta`)**
— uključujući CASE-E, jedan oskudan dokument sa `genome_kompletnost: "niska"`,
naspram CASE-D, kompletan dosije sa overenim testamentom kao dominantnim
dokazom. Ovo je najveći pojedinačni nalaz iz cele vežbe: **glavni brojčani
indikator snage predmeta trenutno ne nosi merljiv signal**, čak i kada je
narativno obrazloženje ispod njega jasno različito po slučaju. Faza 1.3
validator je ovo posredno i potvrdio: u 2/6 slučajeva (B, D) je uhvatio da
sam GPT-ov navedeni procenat (65%, "visok") logički protivreči sopstvenom
zbiru `snaga_faktori` (neto negativan) — čak ni sam model nije interno
konzistentan oko ovog broja.

**5. Korisnost narednih koraka (`nedostaje`) — DOBRO u 5/6.** CASE-B
("Dokumentacija prevoznika" — tačno ono što je veštak eksplicitno naveo kao
potrebno), CASE-E ("Tehnički pregled veš mašine"), CASE-A, CASE-C, CASE-D
svi su proizveli specifične, izvršive stavke koje se poklapaju sa namerno
ugrađenim prazninama. **CASE-F je propust: `nedostaje` je prazna lista**
uprkos očigledno oskudnom `hr_sazetak.docx` ("Primljena je prijava
zaposlene. Predmet je prosleđen na dalje postupanje." — ništa suštinsko) —
razuman "nedostaje" unos (npr. rezultat internog HR istražnog postupka) nije
prepoznat. Mali uzorak (n=1 promašaj od 6), ne generalizuje se dalje ovde.

**6. Vreme ljudskog pregleda — NIJE MERLJIVO u ovom batch-u.** Ovo iskreno
zahteva stvarnog advokata koji ne zna unapred odgovor, pod realnim
vremenskim pritiskom. Moj sopstveni pregled (sa unapred poznatim ground
truth-om) nije validan proxy — ne prijavljujem izmišljen broj. Ova dimenzija
čeka Deo 2.

### Stopa lažnih pozitiva (validator)

**0/8 (0%)** — od ukupno 8 zastavica (2 hard + 6 soft) podignutih preko
svih 6 slučajeva, nijedna nije bila pogrešan alarm. Oba hard flag-a
(CASE-B, CASE-D) su stvarna interna neslaganja koje sam ručno proverio
aritmetički. Svih 6 soft flag-ova su zakonski citati koji zaista nisu u
izvornim dokumentima. Isti caveat o reprezentativnosti kao iznad — proverava
se ponovo na stvarnim predmetima.

### Nalazi lažnih negativa

- Faza 1.3 ne proverava broj člana zakona, samo naziv (CASE-A propust,
  detaljno gore) — konkretno, novo, akcionabilno ograničenje.
- `snaga_predmeta_procent`/`snaga_predmeta` non-diferencijacija nije nešto
  što validator uopšte pokušava da proveri (nije u obimu Faze 1.3) — ali je
  sada dokumentovan realan problem koji zaslužuje sopstvenu odluku.
- CASE-F prazna `nedostaje` lista — van obima validatora (next-action
  kvalitet nikad nije bio deo Faze 1.3), ali vredno pomena.

### Kritičan nalaz — otkriven i ODMAH ispravljen (mali, siguran fix)

**`proactive_alerts` insert je bio 100% neuspešan na SVIH 6 slučajeva** —
ne regresija, potpuno neispravna funkcija otkad je napisana. Kod je koristio
pogrešna imena kolona (`tekst_alerta`/`tip_alerta`/`hitnost`) i pogrešne
vrednosti (`"hitan"/"normalan"`, maskulin) naspram stvarne žive šeme
(`naslov`/`opis`/`tip`/`urgentnost`, sa CHECK ograničenjem koje dozvoljava
samo `'normalna'|'visoka'|'hitna'`, feminin — migracija `036_decision_log.sql`).
Ovo pogađa "Genome Intelligence Delta" — proaktivne alertove koji upozoravaju
advokata kad se snaga predmeta značajno promeni.

**Ispravka:** `routers/case_dna.py`, oba mesta koja upisuju u
`proactive_alerts` (u `_run_genome_background` i `refresh_case_dna`) —
tačna imena kolona i vrednosti usklađene sa živom šemom i sa postojećim
`services/event_bus.py` alert insert-ima (ista tabela, isti obrazac). Nema
migracije — sve kolone već postoje. Verifikovano direktnim insert/delete
testom protiv žive baze pre i posle. Puna test suita (1621 test) ostaje
zelena.

Ovo kvalifikuje kao "kritičan nalaz" po instrukciji ("fix only if critical")
jer: (1) pogađa realnu, korisnički vidljivu funkciju, (2) uzrok je tačno
utvrđen, ne nagađan, (3) ispravka je mala, ne dira šemu, ne dira Genome
JSON, ne dira arhitekturu — samo ispravlja imena polja da odgovaraju već
postojećoj tabeli.

### Manji nalazi (ne zahtevaju akciju sada)

- Rapidni uzastopni upload-i (3-4 dokumenta u nizu) proizvode više
  prolaznih verzija Genome-a (v1→v2→v3→v4) pre nego što se stabilizuju —
  advokat koji posmatra u realnom vremenu bi video Genome kako "treperi"
  kroz nepotpuna stanja. Nije bug, ali je direktno relevantno za "Impact
  Propagation" prazninu već dokumentovanu u Architecture Bible Deo III —
  vredno pomena za budući razgovor, ne akcija sada.
- Pinecone 429 (mesečni limit) pogođen ponovo tokom ovog batch-a — kod se
  ispravno gracefully degradira (dokument se čuva bez RAG indeksiranja),
  potvrđuje da je taj deo koda robustan. Konzistentno sa već dokumentovanim
  nalazom u Architecture Bible Deo VI — nije nov problem.
- `predmet_dokumenti.ai_tags` kolona nedostaje (Evidence Vault
  auto-klasifikacija) — konzistentno sa već poznatim STATE_AUDIT.md nalazom
  (migracija 016 nikad kompletno primenjena) — nije nov problem, nije
  dirano ovde.

### Housekeeping

Ovaj batch je kreirao **7 test predmeta** u produkciji (6 iz batch-a + 1 iz
ranijeg debug testa istog dana), sva jasno označena `[KALIBRACIJA]` u
nazivu radi lake identifikacije. Produkciona `predmeti` tabela je time
narasla sa 1 na 8 redova. Nisu obrisani — brisanje bez eksplicitnog
odobrenja bi bila destruktivna akcija van obima ovog zadatka. Predlažem da
se zadrže dok se ne odluči da li služe kao referentni regresioni skup za
buduće bootstrap runove, ili da se obrišu.

---

## Deo 2 — Validacija na stvarnim anonimizovanim predmetima (PENDING)

Nije pokrenuto. `scripts/genome_case_dna_evaluate.py` (harness) je gotov i
reusable — prima listu definicija predmeta identičnog oblika kao sintetički
batch (`{label, naziv, opis, tip, documents: [{filename, paragraphs}]}`) i
prolazi kroz identičan proces (stvarni API → stvarna ekstrakcija → stvarna
verifikacija → stvarni event → stvarni audit). Jedino što nedostaje: 5-10
stvarnih anonimizovanih dokumenata od founder-a. Kad stignu, isti harness
(sa oba bug-a već ispravljena) se pokreće bez izmena.

Vreme ljudskog pregleda (dimenzija 6) posebno zahteva da Deo 2 uključi
stvarnog advokata-recenzenta (idealno founder-a ili pilot advokata), ne
Claude Code kao recenzenta — ovo je jedina dimenzija koju sintetički batch
strukturno ne može da izmeri.

---

## Odluka (posle izveštaja)

Tri opcije, kao što je traženo:

1. **Popraviti pouzdanost** — jedini identifikovan kritičan bug je već
   popravljen (proactive_alerts). Preostali nalazi (non-diferencijacija
   snaga_predmeta_procent, article-number grounding gap) nisu "kritični" u
   smislu da nešto ne radi — Genome i dalje radi, samo jedan broj i jedna
   klasa citata nisu onoliko pouzdani koliko izgledaju. Ovo bi bio kandidat
   za Rule A (dokazano od strane ovog izveštaja) da se popravi pre ili
   paralelno sa Fazom 2 — ali obim popravke (npr. da li menjati sam
   ekstrakcioni prompt, ili proširiti Verification Layer da proverava broj
   člana, ili oboje) je dizajnerska odluka koju ne donosim ovde.
2. **Nastaviti sa Fazom 2** — moguće, pošto je pipeline dokazano funkcionalan
   end-to-end i kritičan bug je otklonjen. Rizik: Faza 2 (Smart Intake
   instrumentacija) ne zavisi od ovih nalaza, pa nastavak ne bi bio
   neodgovoran — ali bi ostavio poznat, sada dokumentovan kvalitetni
   problem nerešen dok se gradi dalje na istom temelju.
3. **Prilagoditi arhitekturu** — najveći zahvat, verovatno preuranjen za
   samo 6 sintetičkih slučajeva. Sačekati Deo 2 (stvarni predmeti) pre bilo
   kakve prompt/šema izmene bi bio disciplinovaniji potez, dosledan Rule A.

**Moja preporuka, ne odluka:** popraviti već popravljeno (urađeno), zatim
sačekati Deo 2 pre bilo kakve dalje izmene ekstrakcionog prompta ili
proširenja Verification Layer-a — 6 sintetičkih slučajeva je dovoljno da se
otkrije PROBLEM (uspešno je), nije dovoljno da se opravda KAKO ga rešiti.
Faza 2 (Smart Intake instrumentacija) je nezavisna od ovih nalaza i može
teći paralelno bez rizika. Odluka je founder-ova.
