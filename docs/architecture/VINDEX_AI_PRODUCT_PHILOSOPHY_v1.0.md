# Vindex AI — Product Philosophy v1.0

Ovo nije roadmap. Nije arhitektura. Nije plan izvršenja. To su već
`VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md` (šta jeste sistem), `VINDEX_AI_90_DAY_
EXECUTION_PLAN_2026-07-18.md` (šta se radi sledeće) i
`VINDEX_AI_PILOT_SUCCESS_FRAMEWORK_v1.0.md` (kako se odlučuje tokom pilota).

Ovo je četvrti i poslednji nivo — identitet. Dokument na koji se vraćaš kad
biraš između deset dobrih ideja, ne po osećaju nego proverom da li se
uklapaju u ono što Vindex AI jeste.

**Metodološka napomena, važna za poverenje u ovaj dokument:** delovi ispod
su ili (a) direktan citat/rezime odluka koje su već eksplicitno donete u
ovom projektu — obeleženo, sa izvorom — ili (b) moja sinteza iz mnogo malih
odluka u opšti princip — obeleženo kao sinteza. Deo 7 na kraju je lista
pitanja gde sinteza nije dovoljna — tamo treba tvoja eksplicitna potvrda,
ne moja pretpostavka. Ne izmišljam vrednosti koje nisi izrazio.

---

## 1. Šta Vindex AI nikada neće postati

**Direktno potvrđeno, ne sinteza:**

- **Ne generic Web3 portfolio tracker, trading platforma, ili DeFi alat.**
  Digitalna imovina modul je eksplicitno omeđen na Compliance & Due
  Diligence (MiCA/CARF/DAC8/AML/Wallet Risk/Source of Funds) — ako neki
  predlog liči na trading/portfolio funkciju, van je granice bez obzira
  koliko tehnički zanimljiv (`feedback_web3_scope_boundary`).
- **Ne lista od 60 AI funkcija.** Pozicioniranje je "7 stubova", narativ
  koji se pamti, ne enumeracija feature-a
  (`project_business_groups_pricing`, 2026-07-15).
- **Ne proizvod čiji razvoj vodi hype ili impresioniranje investitora.**
  Eksplicitno u Pilot Success Framework: "Šta NIJE cilj pilota —
  impresioniranje investitora demonstracijama, dokazivanje da AI može sve."
- **Ne sistem koji gradi pravni graf ili reasoning engine bez pouzdanog
  korpusa.** Eksplicitno odbijeno dvaput u istoj sesiji (Case Genome Level 5
  alignment i Legal Citation Verification v2): "Do not build a graph
  database. Do not create a new legal reasoning engine."
- **Ne generic-SaaS izgled.** Bloomberg Terminal/Palantir Foundry
  referenca, ne Linear/Stripe — oštri uglovi, bez glow-a, monospace, bez
  generičkih emoji ikonica. Ovo pravilo je ispravljano 3+ puta nakon
  regresija, tretira se kao tvrdo, ne kao preporuka
  (`feedback_no_generic_ui_bloomberg_style`, `feedback_no_generic_icons`).

**Sinteza iz ponovljenih odluka:**

- Vindex AI teži da bude **"najpouzdaniji operativni sistem pravne
  kancelarije"**, ne **"najpametniji AI za advokate"**. Ova razlika je
  eksplicitno izgovorena tokom diskusije o Case Genome arhitekturi i od
  tada se dosledno ponavlja u svakoj narednoj odluci (Reliability Patch
  pre Faze 2, Evidence-gejtovanje pre nove funkcionalnosti, odbijanje da
  se pravni graf gradi bez dokaza). Pametnoća pojedinačnog odgovora nije
  cilj — pouzdanost celog sistema kroz vreme jeste.

---

## 2. Koje probleme rešava bolje od svih (stvaran moat)

Iz Architecture Bible Deo II, eksplicitno razdvojeno na tri nivoa da se ne
mešaju (ponovljeno ovde jer je centralno za identitet):

| Nivo | Primer | Da li je lako kopirati |
|---|---|---|
| Feature | Case Genome JSON ekstrakcija, evidence ranking | Da — bilo koji konkurent sa GPT-4o pristupom |
| Arhitektonska prednost | Event-driven pipeline, verification layer, versioning | Delimično — sporije se kopira, zahteva inženjerski rad |
| **Stvaran moat** | **Akumulirano znanje kancelarije kroz vreme (Firm DNA), dokazana tačnost merena javno (LEC/Hall of Shame/Dashboard), trošak zamene kad je predmet firme već godinama unutra** | **Ne — raste samo sa vremenom i stvarnom upotrebom** |

Regionalni fokus je deo istog moat-a: srpsko/regionalno pravo, ne
generički globalni legal AI, i G7 (Digitalna imovina) kao regionalni
diferencijator — retko koja platforma u regionu ima
MiCA/CARF/DAC8/AML/Wallet Risk pod jednim krovom
(`project_business_groups_pricing`).

**Nikad ne tvrditi da je sama multi-agent arhitektura ili broj AI funkcija
moat.** Dobar konkurent sa dovoljno vremena može da kopira bilo koju
pojedinačnu funkciju. Ne može da kopira tri godine akumuliranog znanja
jedne kancelarije, niti dokazanu tačnost izmerenu na stvarnim predmetima.

---

## 3. Šta odbijamo da gradimo čak i ako korisnik traži

**Direktno potvrđeno:**

- Funkcionalnost bez dokaza iz Evidence Matrix-a (< 2 boda), osim
  Emergency Rule slučaja (`project_pilot_success_framework`).
- Pravni graf/korpus-backed reasoning engine dok ne postoji pouzdan korpus
  (aktivan, dokumentovano nestabilan — Pinecone write-cap, većina izvora
  neuspešno ingestovano, `CASE_GENOME_GAP_ANALYSIS_2026-07-18.md`).
- Potpuno autonoman sistem koji snima Genome bez mogućnosti ljudskog
  pregleda — `require_review` je status na sačuvanom Genome-u, NIKAD
  blokada snimanja. Ovo je eksplicitna arhitektonska odluka, ne privremeno
  ograničenje (Faza 1.3 design note, ponovljeno u svakoj narednoj fazi).
- Nova arhitektura/ADR serija bez konkretnog nalaza koji je opravdava —
  "Evidence faza" eksplicitno zatvorena 2026-07-15, važi i danas.

**Sinteza:** obrazac koji se ponavlja — kad god je predložena veća
funkcionalnost bez dokaza (Case Genome Level 5 master prompt, novi
arhitektonske revizije), odgovor nije bio "ne, nikad", nego "ne sada, ne
bez dokaza, mapiraj na postojeće umesto novog rada". Vindex AI ne odbija
ambiciozne ideje — odbija da ih gradi PRE dokaza da su potrebne.

---

## 4. "AI koji pomaže advokatu" vs "AI koji odlučuje umesto advokata"

Ovo je najvažnije pitanje u dokumentu i ono gde je razlika između sinteze i
tvoje eksplicitne potvrde najbitnija — vidi i Deo 7.

**Ono što JE potvrđeno kroz stvarne odluke:**

- **AI predlaže činjenice i procene. Backend računa izvedene brojeve.
  Advokat donosi pravnu/strateešku odluku.** Ovo je Track 3
  "Deterministic Intelligence Framework" princip, direktno formulisan
  posle Genome Strength Calibration patch-a: "LLM više ne treba da bude
  generator konačnih vrednosti, nego generator činjenica i procena."
  Backend "odlučuje" ovde znači računa aritmetiku (score, confidence,
  completeness) iz LLM-ovih strukturiranih izlaza — NE da sistem donosi
  pravnu odluku umesto advokata.
- **Nijedan AI zaključak se ne prikazuje bez dokaza.** Explainability je
  ugrađen zahtev, ne naknadna dekoracija — `snaga_faktori`,
  `dokazi_rang.razlog`, `najslabija_tacka.preporuka` su svi obavezni polja
  sa "zašto", ne samo "šta".
  - **Verifikacija je savetodavna, ne blokirajuća.** Genome Verification
  Layer eksplicitno NE blokira snimanje ni u jednoj fazi razvijenoj do
  sada — čak i "require_review" ostavlja odluku advokatu, samo mu
  signalizira da obrati pažnju.

**Radna definicija (sinteza, predlažem kao polaznu tačku):**

> "AI pomaže advokatu" znači: AI izvlači, procenjuje, računa, flaguje,
> predlaže — uvek ostavljajući konačnu pravnu/stratešku odluku advokatu, uz
> punu mogućnost da advokat proveri svaki zaključak do izvora.
>
> "AI odlučuje umesto advokata" bi značilo: autonomna akcija sa stvarnom
> pravnom/finansijskom posledicom preduzeta bez ljudskog pregleda (npr.
> automatsko podnošenje podneska, automatsko prihvatanje poravnanja,
> automatsko zatvaranje predmeta). Ovo Vindex AI danas ne radi nigde u
> sistemu, i nijedna trenutna arhitektonska odluka ne planira to bez znatno
> jačeg dokaza pouzdanosti nego što danas postoji.

Ovo JE granica koju bih preporučio da bude nepromenljiva — ali je pišem
kao predlog za tvoju potvrdu, ne kao već izgovorenu odluku u tim tačnim
rečima.

---

## 5. Nepromenljivi principi

Sinteza iz dosledno ponovljenih odluka kroz ceo projekat — svaki od ovih
je viđen da pobeđuje u sukobu sa drugim prioritetima (brzinom, ambicijom,
"zvuči impresivno") više puta, ne samo jednom:

1. **Proverljivost.** Svaki zaključak mora imati putanju nazad do izvora
   (dokument, zakon, presuda). Nikad "veruj mi".
2. **Audit.** Svaka promena Case Genome-a ostavlja trag — ko, kada, zašto,
   koji agent, pre/posle (`audit_immutable`, hash-chain, GDPR čl. 32
   referenca u samom kodu).
3. **Ljudska kontrola nad konačnim odlukama.** Sistem flaguje, upozorava,
   predlaže — nikad ne izvršava nešto sa pravnom/finansijskom posledicom
   bez advokata.
4. **Dokaz pre arhitekture.** Rule A/Evidence Matrix — ideja koliko god
   dobra ne postaje kod dok ne postoji dokaz da je potrebna.
5. **Merljivost.** Rule C — ništa nije završeno dok se ne izmeri pre i
   posle. "Popravili smo X" bez brojke nije završen posao.
6. **Pouzdanost pre količine.** Posle #73, eksplicitan signal da sledeći
   sat rada vredi više uložen u pouzdanost postojećeg nego u novi modul.
7. **Regionalni, ne generički identitet.** Srpski jezik (ekavica
   obligatorna), srpsko/regionalno pravo, Bloomberg-stil vizuelni jezik —
   Vindex AI ne izgleda niti zvuči kao prevod globalnog proizvoda.

---

## 6. Kako procenjujemo da li nova funkcionalnost doprinosi ili narušava identitet

Praktična provera, kombinuje sve prethodne delove u jedan filter za bilo
koji budući predlog:

1. **Evidence Matrix skor ≥2, ili Emergency Rule?** Ako ne — stoji na
   "Future Ideas", razgovor se ne nastavlja dok se ne pojavi dokaz.
2. **Da li jača stvaran moat (akumulirano znanje / dokazana tačnost /
   switching cost), ili je samo još jedna kopirljiva funkcija?** Oboje
   može biti vredno graditi — ali kopirljiva funkcija ne dobija prioritet
   nad nečim što jača moat, pri jednakom Evidence skoru.
3. **Da li ostavlja konačnu odluku advokatu?** Ako predlog uključuje
   autonomnu akciju sa pravnom/finansijskom posledicom bez ljudskog
   pregleda — stoji, čeka posebnu odluku (videti Deo 4/7), ne ide u
   normalan razvoj tok.
4. **Da li dolazi sa objašnjivošću i audit tragom ugrađenim od početka,
   ili se to planira "kasnije"?** Explainability/audit "kasnije" istorijski
   znači "nikad" — ugrađuje se od prve verzije ili se ne gradi.
5. **Da li se uklapa u Bloomberg/regionalni vizuelni i jezički identitet?**
   Generic-SaaS izgled ili ne-ekavica tekst se odbija bez obzira na
   funkcionalnu vrednost ispod.

Ako predlog prođe sva pet — ide u normalan razvojni tok (Idea → Dokaz →
Plan → Implementacija → Instrumentacija → Validacija → Merenje → Odluka).
Ako ne prođe bilo koju — ne ide u razvoj dok se ta konkretna tačka ne
reši, ne generalno "razmotrićemo kasnije".

---

## 7. Otvorena pitanja — traže tvoju potvrdu, ne moju pretpostavku

Ovo nije formalnost. Sledeći delovi su moja najbolja sinteza iz onoga što
je do sada rečeno, ali NISU citat tvoje eksplicitne odluke u tim tačnim
rečima — trebalo bi da ih potvrdiš, izmeniš, ili odbaciš pre nego što ovaj
dokument postane v1.0 u punom smislu ("konačan", ne "nacrt"):

1. **Deo 4 radna definicija** ("AI pomaže" vs "AI odlučuje") — da li se
   slažeš sa ovom tačnom granicom, ili bi je drugačije povukao? Ovo je
   verovatno najvažnije pojedinačno pitanje u celom dokumentu, jer
   direktno određuje šta se sme automatizovati u budućnosti (npr. da li
   auto-finalize iz Smart Intake-a, ako telemetrija to opravda, ikad sme
   da postane potpuno autonoman, ili uvek mora zadržati klik potvrde).
2. **Deo 1** — postoji li neka kategorija proizvoda/funkcije koju bi
   eksplicitno želeo da dodaš na "nikad" listu, a koja još nije pomenuta
   nijednom u dosadašnjem radu (pa je nemam odakle da izvedem)?
3. **Deo 5, princip 6** ("pouzdanost pre količine") — da li ovo ostaje
   važeće i posle Faze 2 otključavanja, ili se pomera nazad ka
   ravnotežnijem razvoju sada kad je pilot blizu?
4. **Format/dužina** — ovaj nacrt je disciplinovano kratak (prati princip
   "svaka rečenica mora nešto da objasni ili se briše" iz Bible-a) umesto
   doslovno 10-15 strana proze. Ako želiš doslovno tu dužinu sa više
   primera/objašnjenja po tački, reci — trenutna verzija je optimizovana za
   preciznost, ne za obim.
