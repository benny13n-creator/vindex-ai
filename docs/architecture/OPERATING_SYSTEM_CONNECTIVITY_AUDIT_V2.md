# Vindex AI — Operating System Connectivity Audit V2 (2026-07-19)

Treći prolaz kroz istu suštinsku analizu (nastavak
`OPERATING_SYSTEM_CONNECTIVITY_AUDIT.md` i `OPERATING_SYSTEM_ROADMAP.md`),
strukturiran po tačno traženih 8 faza. Gde se nalaz preklapa sa
prethodna dva dokumenta, citiran je bez ponovnog izvođenja dokaza —
ovaj dokument dodaje dve stvari koje prethodna dva NISU imala: (a)
granularnost po tipu dokumenta (7 traženih tipova, ne opšta kategorija),
(b) eksplicitan Operating System Score po 4 faze lanca. Analiza, ne
implementacija — nijedna linija koda nije menjana.

**Pitanje na koje ovaj dokument odgovara:** *"Koliko je Vindex AI danas
udaljen od vizije da advokat samo donosi odluke, a sistem vodi
predmet?"* Odgovor je u poslednjoj sekciji, zasnovan isključivo na
nalazima ispod.

---

# FAZA 1 — Event Flow Audit

| Event | Postoji (definicija)? | Ko emituje? | Ko sluša? | Aktivira se ikad? | Šta bi trebalo da pokrene |
|---|---|---|---|---|---|
| Predmet kreiran | DA, `EventType.PREDMET_KREIRAN` | **Niko u produkcijskom kodu** (0 pogodaka van test fajlova) | `on_predmet_kreiran` (registrovan, `event_bus.py:98-107`) | **NE** | `run_case_pipeline()` — rokovi, mini-strategija, HCC briefing, risk snapshot. Kod POSTOJI i radi za "iz šablona" put. |
| Dokument uploadovan | DA, `EventType.DOKUMENT_UPLOADOVAN` | Niko | `on_dokument_uploadovan` (registrovan) | **NE** | Upisuje `decision_log` — ALI Evidence klasifikacija i Genome refresh SE DEŠAVAJU već (kroz direktan fire-and-forget poziv u `api.py`, zaobilazeći event bus potpuno). Funkcionalnost postoji, samo nije POVEZANA kroz event arhitekturu. |
| Novi dokument klasifikovan | **NE POSTOJI** nijedan odgovarajući EventType u enum-u | N/A | N/A | N/A | Trebalo bi da postoji i da trigeruje deadline-suggestion logiku (Faza 3). |
| Promena statusa predmeta (Kanban) | **NE POSTOJI** | N/A | N/A | N/A | `update_kanban_faza()` (`api.py:3187-3200`) je čist single-column UPDATE, bez ikakvog eventa. |
| Promena klijenta | **NE POSTOJI** | N/A | N/A | N/A | — |
| AI analiza završena (opšte) | Zavisi koja — nema jedinstven event | — | — | — | Samo Genome ima svoj event; Strategy/Drafting/Research nemaju. |
| Genome updated | DA, `EventType.GENOME_UPDATED` | **DA** — `routers/case_dna.py:378` | `on_genome_updated` (`event_bus.py:149-178`) | **DA — jedini potpuno funkcionalan event u celom sistemu** | Radi ispravno (upisuje `audit_immutable`). |
| Rok kreiran | DA, `EventType.ROK_DODAN` | Niko | Nema registrovan handler | **NE**, potpuno mrtav | — |
| Rok istekao | DA, `EventType.ROK_KRITICAN` | Niko | `on_rok_kritican` (registrovan, kreira `proactive_alerts`) | **NE** | Alerti za rokove koji ističu — kod POSTOJI, samo ne prima signal. |

**Zaključak Faze 1:** od 9 traženih tipova, 2 nemaju uopšte definiciju
u sistemu (klasifikovan dokument, promena statusa). Od preostalih 7
definisanih, samo 1 (Genome) je živ. 2 imaju izgrađene handlere koji
čekaju signal koji nikad ne stiže (Predmet kreiran, Rok istekao) — ovo
su "mrtve žice" sa najvećom vrednošću ako se ožive, jer je posao na
strani handlera već završen.

---

# FAZA 2 — Document → Action Audit

Kad korisnik otpremi dokument, da li sistem automatski:

```
☑ prepoznaje tip dokumenta        — DA (Evidence Vault, automatski)
☑ izvlači bitne činjenice          — DA (dva paralelna sistema: Evidence
                                      Vault kljucne_cinjenice + Genome
                                      ekstrakcija — ne ukršteni, vidi
                                      prethodni audit)
☑ povezuje dokument sa predmetom   — DA (trivijalno, upload je već u
                                      kontekstu predmeta)
☐ generiše rokove                  — NE, nijedan mehanizam
☐ generiše zadatke                 — NE, potvrđeno 0 nalaza (prethodna
                                      runda)
☒ menja stanje predmeta            — DELIMIČNO (Genome procena da,
                                      Kanban faza ne)
☒ upozorava korisnika              — DELIMIČNO (samo ako je Genome
                                      delta značajna — proactive_alerts)
☒ pokreće relevantne AI module     — DELIMIČNO (Genome+Evidence da,
                                      Strategy/Drafting ne — ispravno,
                                      ti zahtevaju nameru)
```

## AUTOMATIZOVANO

Klasifikacija tipa dokumenta, ekstrakcija ključnih činjenica (dva
odvojena sistema), povezivanje dokument↔predmet, Genome regeneracija,
Genome delta-alert (kad je značajna).

## NIJE AUTOMATIZOVANO A TREBALO BI

Generisanje roka iz klasifikovanog dokumenta, generisanje zadatka iz
Genome nalaza (npr. "nedostaje"), promena Kanban faze na osnovu
sadržaja dokumenta (npr. klasifikovana `sudska_odluka` bi razumno
mogla predložiti prelazak u "Čeka odluku" fazu), upozorenje za SVAKI
značajan pojedinačni nalaz — ne samo agregatnu Genome deltu.

---

# FAZA 3 — Legal Deadline Automation Audit (po tipu dokumenta)

**Ključan preduslov-nalaz pre tabele:** Evidence Vault klasifikator
(`routers/evidence.py`, `_CLASSIFY_SYSTEM`) ima **8 kategorija**, ne
7 traženih tipova — i grupiše ih grublje nego što bi rok-trigering
logika zahtevala:
- `sudska_odluka` = presuda **I** rešenje **I** zaključak suda, sve u
  istoj kategoriji.
- `podnesak` = tužba **I** žalba **I** prigovor **I** zahtev stranke,
  sve u istoj kategoriji.

Ovo znači: čak i kad bi se klasifikacija povezala sa rok-kalkulacijom,
sistem danas **ne bi mogao da razlikuje da li je "podnesak" tužba (koja
pokreće rok za odgovor kod PROTIVNE strane) ili žalba (koja pokreće
drugačiji rok) ili odgovor na tužbu (koji obično ne pokreće nov rok
sam po sebi)** — sva tri se klasifikuju identično. Ovo mora biti rešeno
PRE nego što se rok-trigering iz Faze 3 predloga (prethodni dokument)
implementira, ne posle.

| Dokument tip | Trenutno stanje | Željeno stanje | Potrebne izmene | Rizik |
|---|---|---|---|---|
| **Tužba** | Klasifikovana kao `podnesak`, nerazlikovano od žalbe/odgovora. Nema rok trigera. | Ako je primljena OD protivne strane, trigeruje rok za odgovor. | Precizirati klasifikator (razdvojiti tužba/žalba/odgovor unutar `podnesak`) + determinističko mapiranje + potvrda UI. | Srednji |
| **Presuda** | Klasifikovana kao `sudska_odluka`, nerazlikovano od rešenja. Nema rok trigera, iako ZPP katalog za "dostava_presude_prvostepene" VEĆ POSTOJI (`rokovi_lanac.py`). | Rok za žalbu automatski predložen. | Precizirati klasifikator + mapirati na postojeći ZPP ključ + potvrda UI. | **Nizak-srednji — kalkulacija već postoji, samo triger nedostaje.** |
| **Rešenje** | Ista kategorija kao presuda, nerazlikovano. | Verovatno drugačiji rok tip od presude. | Ista potreba za precizacijom klasifikatora. | Srednji |
| **Poziv suda** | Verovatno pada u `dopis` ili `ostalo` — nije jasno klasifikovano kao poseban tip. | Prepoznat datum ročišta, kalendarski unos. | Nova/precizirana kategorija u klasifikatoru. | Nizak |
| **Žalba** | `podnesak`, nerazlikovano od tužbe. | Rok za odgovor na žalbu (ako protivnik uloži). | Ista potreba kao tužba. | Srednji |
| **Odgovor na tužbu** | `podnesak`, nerazlikovano. | Obično NE generiše nov rok sam po sebi (zavisi od sadržaja, ne od tipa) — ovo je suštinski složenije od ostalih. | Sadržaj-zavisna logika, ne čisto tip-zavisna — van dometa jednostavnog mapiranja. | **Viši — teže rešiti deterministički.** |
| **Dostavnica** | Verovatno `dopis`/`ostalo`, nema posebnu obradu. **Datum dostave se ne hvata pouzdano nigde u pipeline-u.** | Pouzdano hvatanje datuma dostave — ovo je POČETNA TAČKA za skoro sve ZPP rokove ("15 dana OD DANA DOSTAVE presude"). | Bez ovoga, čak i savršena klasifikacija ostalih tipova ne pomaže — nema pouzdan datum od kog se računa. | **VISOK — ovo je temeljni blok. Prioritetnije od preciziranja ostalih kategorija.** |

---

# FAZA 4 — Duplicirani unosi

**Primer iz zahteva, proveren protiv koda:** advokat unese/otpremi
dokument iz kog se vidi "presuda dostavljena 01.07."

- Da li sistem automatski zna rok žalbe? **NE** — mora ručno otvoriti
  ZPP "Lanac rokova", izabrati tip akta, uneti isti datum ponovo.
- Da li sistem automatski zna status predmeta? **NE** — Kanban faza se
  ne menja dok se ručno ne prevuče.
- Da li sistem automatski zna sledeću akciju? **DELIMIČNO** — ako je
  datum deo uploadovanog teksta, Genome MOŽE ga ekstrahovati u
  `datumi_kljucni`/`rokovi_kriticni`, ali ostaje zarobljeno u JSON
  koloni, ne postaje actionable rok (potvrđeno u prethodnom auditu).

## Lista duplih operacija

1. **Datum ključnog događaja** — unosi se (a) implicitno kroz upload
   teksta (Genome ga ekstrahuje ako je pomenut), (b) ponovo RUČNO u ZPP
   lanac formu za stvarnu kalkulaciju.
2. **Tip procesnog akta** — Evidence Vault ga klasifikuje automatski
   (sa gore opisanim granularnim ograničenjem), ALI advokat mora
   ponovo RUČNO da izabere "tip procesnog akta" u ZPP lanac formi —
   potpuno odvojen dropdown, ne preuzima Evidence Vault rezultat.
3. **Kontekst predmeta za Strategy module** — **PRIMER VEĆ REŠENOG
   DUPLIRANJA** (Trust Layer runda, ranije ove sesije): ranije je
   advokat morao ručno da opisuje predmet za svaki Strategy modul iako
   je sistem već imao sve podatke; sada se auto-popunjava. Naveden ovde
   kao dokaz da se ovaj tip problema MOŽE rešiti brzo kad se
   prioritetizuje — isti obrazac treba primeniti na ZPP lanac (stavka
   #2 iznad).
4. **"Sledeći koraci"** — 4 nezavisna sistema (Genome sinteza,
   `matter_intel.py`, `case_intelligence.py`, `workflow.py`, svi
   potvrđeni u prethodnom auditu) — svaki potencijalno zahteva
   sopstveni kontekst/unos, nijedan ne deli rad sa ostalima.

---

# FAZA 5 — AI Output → System Action Audit

| Modul | Kad završi posao, šta se AUTOMATSKI dešava dalje? |
|---|---|
| **Case Genome** | Upisuje `case_dna`, emituje `GenomeUpdated` (radi), kreira `proactive_alert` **samo ako je delta značajna**. Polje `nedostaje` (npr. "nedostaje odgovor tužene strane") se **PRIKAZUJE u panelu, ne kreira task niti posebno upozorenje** za tu konkretnu stavku. |
| **Strategy** | Vraća tekst korisniku. **Ništa se ne upisuje u predmet** (nema save-to-predmet mehanizam), ne kreira task, ne menja prioritet. Čista prezentacija. |
| **Evidence Vault** | Upisuje `tip_dokaza`/`pravni_elementi`/`predmet_dokazi` redove, **trigeruje Genome refresh** (jedina automatska posledica van sopstvenog upisa). |
| **Smart Intake** | Nije live na main grani (feature branch, van obima ovog audita). |
| **OCR** | Tekst ide dalje u Evidence/Genome pipeline (deo iste sekvence — funkcioniše). `ocr_used`/kvalitet metadata se upisuje u Pinecone tag, **nikad se ne čita nazad nigde** (potvrđeno u prethodnoj rundi). |
| **Research** (`/api/pitanje`, `api.py:2587`) | Vraća tekst odgovora. **Ništa se ne čuva/povezuje sa predmetom automatski** — ako advokat želi da sačuva odgovor, mora ručno da kopira. |
| **Drafting** (`/api/podnesak`, `/api/nacrt`, `routers/drafting.py:236,372`) | Vraća generisani nacrt teksta (`return {"status":"success","odgovor":nacrt,...}`, `routers/drafting.py:493-497`, **potvrđeno čitanjem koda do kraja funkcije**). **Nije automatski sačuvan kao dokument predmeta, ne kreira task za pregled/podnošenje.** Advokat mora ručno da izveze/sačuva/poveže sa predmetom. |

**Primer iz zahteva, direktno proveren:** "AI pronašao: nedostaje
odgovor tužene strane" (Genome `nedostaje[]` polje).
- Kreira task? **NE.**
- Upozori advokata? **Samo pasivno** — vidljivo kad advokat SAM otvori
  Genome panel. Nema push/proaktivno obaveštenje za ovu specifičnu
  stavku (razlikuje se od "delta" alerta koji je agregatan, ne
  po-stavci).
- Menja prioritet? **NE** — ne postoji koncept "prioritet predmeta" koji
  bi se automatski menjao na osnovu ovoga; Kanban faza ostaje ručna.

---

# FAZA 6 — User Promise Gap Analysis

| Tekst na UI | Realno ponašanje | Status |
|---|---|---|
| Landing: "Sistem prati rokove umesto vas — automatska obaveštenja 7, 2 i 1 dan" (`index.html:4067`) | Kod postoji (`email_notif.py`), ali zahteva eksterni cron koji `Procfile` ne definiše — isporuka neizvesna | 🔴 **RED** |
| 3 "unlock" modal poruke (Knowledge Transfer/Firm DNA/Intelligence Engine, `vindex.js:9845-9853`) | Nijedna nije mapirana na stvaran UI pane — nema potvrđeno odredište | 🔴 **RED** |
| Onboarding: "ZPP rokovi se računaju automatski" | Kalkulacija JESTE automatska (deterministička), triger je RUČAN | 🟡 **YELLOW** |
| Playbook interno: "Vindex će automatski koristiti presedane pri generisanju nacrta" (`index.html:2942`) | Neprovereno da li Playbook upload stvarno ulazi u RAG kontekst `/api/podnesak` poziva | 🟡 **YELLOW** |
| "Automatsko pisanje tužbi/žalbi" (PRO modal) | Tačno — AI generiše nacrt po eksplicitnom kliku, razumno tumačenje reči "automatsko" | 🟢 **GREEN** |
| "Analiza dokumenta — automatski izvlači ključne klauzule" (kc-ai-card) | Tačno, po uploadu + kliku | 🟢 **GREEN** |
| "Jedan klik pokreće svih 6 modula u automatskom redosledu" (Kompletna analiza) | Tačno, orkestrator potvrđen da radi | 🟢 **GREEN** |
| Onboarding: "Sistem će automatski analizirati dokument i izvući ključne informacije" | Tačno — Evidence Vault + Genome auto-obrada posle uploada | 🟢 **GREEN** |
| Strategija pod-tab: "Alati rade u kontekstu ovog predmeta — čitaju vaše dokumente automatski" | Tačno **POSLE POPRAVKE** ove sesije (auto-context sada radi za sve module) | 🟢 **GREEN** (bilo RED, sada popravljeno) |

**Rezime:** 2 RED (oba ozbiljna — jedan javan, pre-registracija), 2
YELLOW (nijanse ili neproverenost, ne aktivna netačnost), 5 GREEN.

---

# FAZA 7 — Operating System Score

| Faza lanca | Ocena (0-10) | Obrazloženje |
|---|---|---|
| 1. Dokument → razumevanje | **8/10** | OCR, klasifikacija, Genome ekstrakcija — sve automatski, dobro pokriveno. Minus poeni: klasifikator granularnost (Faza 3 nalaz), dostavnica datum nepouzdan. |
| 2. Razumevanje → akcija | **3/10** | **Najveći prekid u celom lancu.** Genome zna mnogo (najslabija tačka, nedostaje, rokovi_kriticni), ali retko šta se automatski PRETVARA u konkretnu akciju (rok, task, status promena). `run_case_pipeline()` postoji i radi — diskonektovan od standardnog puta. |
| 3. Akcija → obaveštenje | **2/10** | Čak i kad se nešto DESI (retko — Genome delta), isporuka obaveštenja je neizvesna (cron problem, Faza 6). Deadline Guardian potpuno nedostupan iz UI-ja. |
| 4. Obaveštenje → odluka advokata | **7/10** | Kad advokat STVARNO vidi nešto (ručno otvori ekran), format je dobar — Trust Layer runda (Zaključak/Osnov/Sigurnost) daje jasnu, proverljivu preporuku. **Ovo je jedini deo lanca koji je stvarno dobro rešen** — problem je što retko šta stigne dovde bez ručne akcije da se prvo otvori ekran. |

**Napomena o čitanju ove tabele:** prost prosek (8+3+2+7)/4 = 5.0 bi
prikrio pravu sliku. Lanac je jak koliko najslabija karika — kad Faza 2
padne na 3/10, sve što dolazi POSLE nje (Faza 3, čak i Faza 4 kvalitet)
postaje irelevantno ZA AUTOMATSKI tok, iako ostaje korisno kad advokat
ručno pokrene svaki korak sam. **Efektivna automatizacija end-to-end
lanca je bliža 2-3/10, ne 5/10** — sistem "razume" odlično, ali retko
kad "deluje" na osnovu tog razumevanja bez ljudske ruke na svakom
koraku.

---

# FAZA 8 — Top 5 Connectivity Gaps

### 1. `PREDMET_KREIRAN` se nikad ne emituje

- **Zašto kritično:** jedina karika koja bi odjednom povezala rokove +
  mini-strategiju + risk snapshot + HCC briefing za SVAKI nov predmet,
  ne samo "iz šablona" put. Sav taj kod već postoji i radi.
- **Koliko rada zahteva:** Nizak — jedan `emit()`/outbox insert poziv u
  `routers/intake.py` posle uspešnog kreiranja predmeta.
- **Poslovni efekat:** Visok — aktivira 4 već izgrađene mogućnosti
  jednim potezom.
- **Rizik implementacije:** Nizak-srednji — proveriti da pipeline radi
  i za predmete bez dokumenata, meriti trošak dodatnih GPT poziva pre
  širokog puštanja.

### 2. Notification cron neizvesnost (Faza 6, RED #1)

- **Zašto kritično:** javno obećanje na landing stranici, pre
  registracije — najveći reputacioni rizik u celom audit-u ako se
  potvrdi da ne radi.
- **Koliko rada zahteva:** Nepoznato dok se ne proveri hosting
  dashboard — možda samo konfiguracija (nizak), možda treba novi
  infrastructure setup (srednji).
- **Poslovni efekat:** Kritičan — ako prospekt/klijent otkrije da
  obećanje ne važi, poverenje se ruši trenutno, ne postepeno.
- **Rizik implementacije:** Nizak — ovo je infrastruktura/konfiguracija,
  ne novi kod.

### 3. Deadline Guardian nema UI vezu

- **Zašto kritično:** direktno bi popravio Fazu 7 "Akcija→obaveštenje"
  (danas 2/10) sa POTPUNO POSTOJEĆIM backend kodom.
- **Koliko rada zahteva:** Nizak-srednji — čist frontend rad, backend
  gotov (`routers/zastarelost.py`).
- **Poslovni efekat:** Visok.
- **Rizik implementacije:** Nizak.

### 4. Dokument-klasifikacija → rok-trigering veza (uključujući granularnost, Faza 3)

- **Zašto kritično:** ovo je srž samog obećanja iz prompt-a ("advokat
  ne treba ručno da računa posledice procesnih događaja").
- **Koliko rada zahteva:** Srednji — precizirati klasifikator
  (razdvojiti tužba/žalba/odgovor, presuda/rešenje), rešiti dostavnica-
  datum problem, mapirati na postojeći ZPP katalog, dodati obavezan
  potvrda-UI korak.
- **Poslovni efekat:** Visok, ali sporiji da se oseti nego #1-3 jer
  zahteva više koraka pre nego što je vidljivo korisniku.
- **Rizik implementacije:** Srednji — klasifikacija mora biti dovoljno
  pouzdana pre nego što se poveže sa deterministic kalkulacijom, inače
  se šalje uverljivo pogrešan predlog (isti rizik profil kao P1.3 iz
  Trust Layer runde).

### 5. AI Output → System Action gap (Genome/Strategy/Drafting ne kreiraju task niti se auto-čuvaju)

- **Zašto kritično:** ovo je tačno mesto gde AI "završi posao" ali
  advokat mora sve ručno da prenese dalje — direktno suprotno obećanju
  "advokat samo potvrđuje/ispravlja/odbija".
- **Koliko rada zahteva:** Srednji — dizajnirati task-kreiranje sa
  obaveznom advokatovom potvrdom, opcionu auto-save funkciju za
  Drafting nacrte.
- **Poslovni efekat:** Srednje-visok — smanjuje osećaj "duplog unosa"
  (Faza 4) na dnevnoj bazi rada.
- **Rizik implementacije:** Nizak-srednji — bezbedno ako je
  advokat-potvrđeno, ne auto-izvršeno (ista granica kao svuda drugde u
  ovom projektu).

---

# Odgovor na centralno pitanje

**"Koliko je Vindex AI danas udaljen od vizije da advokat samo donosi
odluke, a sistem vodi predmet?"**

Ne meri se u mesecima razvoja — meri se u **broju postojećih, već
napisanih funkcija koje čekaju jedan poziv da ih aktivira.** Faza 7
Score pokazuje tačno gde je razmak: sistem RAZUME dokument gotovo
odlično (8/10) i, kad advokat ručno stigne do rezultata, PREZENTUJE ga
na način kome se može verovati (7/10) — oba kraja lanca su jaka. Sredina
lanca (razumevanje→akcija→obaveštenje, 3/10 i 2/10) je mesto gde
"operativni sistem" trenutno postoji samo kao kod, ne kao iskustvo.

Top 5 gap lista pokazuje da 4 od 5 najkritičnijih problema imaju NIZAK
do SREDNJI trošak popravke, jer je posao (pipeline, guardian, event
handleri) već napisan — nedostaje samo poziv koji ih aktivira. Peti
(notifikacioni cron) nije čak ni pitanje koda. **Vindex AI nije daleko
od ove vizije u smislu rada koji ostaje — daleko je u smislu odluka
koje čekaju da se donesu o tome ŠTA prvo povezati, i u kom redosledu,
sa merenjem posle svake veze — ista disciplina koja je već primenjena
na svaki drugi deo ovog proizvoda ove sesije.**
