# VINDEX AI — WEBSITE DISCOVERY & FORENSIC PRODUCT ANALYSIS

Stanje repozitorijuma: `b29ffb6f` · Analiza se oslanja na 20+ forenzičkih prolaza (V33–V58) nad ovim kodom.
**Ništa nije implementirano niti menjano u ovoj misiji.**

---

## 1. EXECUTIVE SUMMARY

Vindex AI **nije AI asistent za pravo.** To je pogrešan opis i vodi ka pogrešnom sajtu.

Vindex je **sistem evidencije za predmet** — održava strukturisan, proverljiv prikaz jednog predmeta i taj prikaz stavlja na raspolaganje AI modelima. Vrednost nije u modelu; vrednost je u tome što svako polje konteksta nosi oznaku porekla, a svaka radnja ostavlja nepromenljiv trag.

**Tri nalaza koja moraju oblikovati sajt:**

1. **Najjača strana proizvoda je ono što se najteže prodaje** — provenance i nepromenljiva evidencija. To nije funkcija koju kupac traži; to je razlog zašto će rezultatu verovati.
2. **Najslabija tačka nije kod nego dokaz** — nijedan izlaz modela nije ocenjen nad stvarnim predmetom. Sajt zato **ne sme** da tvrdi bilo šta o kvalitetu AI rezultata.
3. **Ne postoji marketinška ulazna strana.** `static/` sadrži samo pravno-usklađenosne strane. Sajt se gradi od nule, a ne redizajnira.

---

## 2. ŠTA VINDEX ZAPRAVO JESTE

**111 rutera**, 582 registrovane rute, 3893 automatizovana testa.

Stvarna arhitektura, izvedena iz koda (ne iz dokumentacije):

```
DOKUMENTI            intake/smart_intake → OCR → klasifikacija → predmet_dokumenti
      ↓
KONTEKST PREDMETA    shared/case_context.py :: context_field(value, source, owner, refresh)
      ↓              ← ovo je srce proizvoda; koristi ga 12 modula
AI SLOJ              99 poziva, jedan dobavljač; provenance kroz SDK-level presretanje
      ↓
ANALIZA              rokovi, protivrečnosti, rizik, Case Genome
      ↓
AKCIJA               nacrti (drafting), zadaci, rokovi
      ↓
TRAG                 audit_immutable — hash-lanac, 71 vrsta radnje, DB triger
```

Lanac **jeste** onakav kakav bi trebalo da bude. Nije fasada.

**Ali:** grana `AI SLOJ` nije apstrahovana u produkciji. `shared/ai_fabric.py` postoji sa tri priključka i governance kapijom, ali **nijedna funkcija ne ide kroz njega** (mereno: 0 poziva).

---

## 3. CORE PRODUCT THESIS

**Vindex poseduje kontekst, ne model.**

Svaki AI alat može da odgovori na pitanje o dokumentu koji mu zalepiš. Vindex održava uređen prikaz celog predmeta — činjenice, rokove, dokaze, stranke — u kome svako polje zna iz kog dokumenta potiče, ko ga je uneo i kada se osvežava. Taj prikaz je provider-agnostičan (običan `dict`), pa preživljava promenu modela. Model se menja svakih šest meseci; uređen kontekst i proverljiv trag ostaju.

**JEDNA REČENICA (23 reči):**
> Vindex održava proverljiv prikaz pravnog predmeta — sa poreklom svakog podatka — i taj prikaz stavlja na raspolaganje AI modelima.

**10 SEKUNDI:**
> Umesto da advokat lepi dokumente u ćaskanje sa AI-jem, Vindex drži uređen predmet i sam prosleđuje modelu ono što je bitno — uz trag odakle je svaki podatak došao.

**30 SEKUNDI:**
> Advokat unese dokumente. Vindex ih prepozna, poveže sa predmetom i iz njih izvuče činjenice, rokove i dokaze. Kad kasnije pita bilo šta o predmetu, model ne dobija sirov tekst nego uređen prikaz — pa se svaka tvrdnja može vratiti na dokument iz kog potiče. Svaka radnja ostaje zabeležena u evidenciji koja se ne može naknadno izmeniti.

**TEHNIČKI:**
> Kanonski context fabric (`context_field(source, owner, refresh)`) + hash-ulančana nepromenljiva evidencija + governance kapija pre poziva modela. Provider fabric sa tri adaptera je implementiran ali još nije u produkcionom toku.

---

## 4. MATRICA MOGUĆNOSTI

| Mogućnost | Dokaz | Status | Pouzdanost | Na sajt? |
|---|---|---|---|---|
| Kanonski kontekst sa poreklom po polju | `shared/case_context.py`, 12 modula | PRODUCTION | HIGH | **DA — vodeća poruka** |
| Nepromenljiva evidencija (hash-lanac) | `audit_immutable`, 71 akcija, DB triger, DDL potvrđen | PRODUCTION | HIGH | **DA** |
| Razdvajanje podataka po vlasniku | vlasnički predikat u samoj DB operaciji; V49–V58 bez nalaza | PRODUCTION | HIGH | **DA** |
| Poreklo AI odgovora | `shared/ai_provenance.py`, `ai_forensics` | PRODUCTION | HIGH | **DA** |
| Unos više dokumenata + klasifikacija | `routers/intake.py`, `smart_intake.py`, `evidence.py` | PRODUCTION | HIGH | DA |
| Semantička pretraga | Pinecone, `app/services/retrieve.py` | PRODUCTION | MEDIUM | DA |
| Rokovi / obaveze | `_step_ekstrakcija_rokova`, `rokovi_lanac` | PRODUCTION | MEDIUM | DA |
| Protivrečnosti / rizik | `_step_risk_snapshot`, case intelligence | IMPLEMENTED / NOT PROVEN | MEDIUM | OGRANIČENO |
| Nacrti podnesaka | `routers/drafting.py`, `drafting_grounding.py` | IMPLEMENTED / NOT PROVEN | **LOW** | **OGRANIČENO** |
| OCR kvalitet | postoji, `awaiting_review` grana | IMPLEMENTED / NOT PROVEN | **LOW** | **NE** |
| Uloge u kancelariji | `_require_firma_admin` → 403 | PRODUCTION | HIGH | DA |
| Provider fabric (3 dobavljača) | `shared/ai_fabric.py`, 31 test | IMPLEMENTED, **0 produkcijskih poziva** | HIGH | **OGRANIČENO — samo kao arhitektura** |
| Unakrsna provera modela | samo ugovor, bez implementacije | PLANNED | — | **NE** |
| Naplatni sloj | 59 testova **preskočeno** (nema baze) | NOT PROVEN | **LOW** | **NE** |
| Glasovni unos | `routers/voice.py` postoji | NOT VERIFIED | LOW | NE |

---

## 5. STVARNI PROBLEMI KORISNIKA

| Problem | Sadašnji tok | Vindex | Dokaz |
|---|---|---|---|
| Gubitak konteksta posle pauze | ponovo čita ceo spis | uređen prikaz predmeta uvek dostupan | `case_context.py` |
| Rokovi skriveni u tekstu | ručno prepisuje u kalendar | ekstrakcija rokova iz dokumenata | `_step_ekstrakcija_rokova` |
| „Odakle ovo?" pri proveri AI odgovora | nema odgovor | `source` na svakom polju | `context_field` |
| Ko je šta menjao u predmetu | nepouzdano | hash-ulančana evidencija | `audit_immutable` |
| Pretraga po značenju | Ctrl+F po ključnoj reči | semantička pretraga | Pinecone |
| Podaci klijenata međusobno odvojeni | poverenje u alat | vlasnički predikat u svakoj operaciji | V49–V58 |

---

## 6–7. TRŽIŠTE I KUPAC

**PRIORITET**

| Tržište | Uklapanje problema | Zrelost proizvoda | Validacija |
|---|---|---|---|
| **Advokatske kancelarije (male/srednje)** | VISOKO | VISOKA | razgovori u toku |
| Korporativni pravni poslovi | VISOKO | SREDNJA | nema |
| Notarijat | SREDNJE | SREDNJA | nema |
| Osiguranje / banke | SREDNJE | NISKA (traži integracije) | nema |
| Konsalting / revizija | SREDNJE | NISKA | nema |

**KO ODLUČUJE — ključni nalaz za sajt**

U maloj kancelariji **korisnik, kupac i odlučilac su ista osoba**: advokat vlasnik. Nema nabavnog procesa, nema IT odeljenja, nema pravnog odeljenja koje odobrava.

**Posledica:** sajt se obraća **jednoj osobi koja plaća iz svog džepa i sama snosi rizik**. Ne korporativnom kupcu. To znači: bez „enterprise" jezika, bez „zakažite demo sa našim timom", bez formulara od 9 polja.

**Blokator:** poverenje u tajnost podataka i strah od greške AI-ja u pravnom radu. Sajt mora da odgovori na to **pre** nego što traži bilo šta.

---

## 8–9. POZICIONIRANJE I STVARNI DIFERENCIJATORI

| Alternativa | Vindex je jači | Vindex je slabiji |
|---|---|---|
| ChatGPT/Claude direktno | uređen kontekst, trag, razdvajanje podataka | sirova snaga modela, cena, brzina |
| Pravni AI alati (strani) | srpski pravni kontekst, provenance | zrelost, reference, obim korpusa |
| Sistemi za upravljanje dokumentima | razumevanje sadržaja | zrelost, integracije |
| Softver za vođenje kancelarije | AI sloj | računovodstvo, fakturisanje, kalendari |

**GENUINE DIFERENCIJATORI (posle brutalne provere)**

1. **Poreklo po polju konteksta** — implementirano, dokazivo, objašnjivo u jednoj rečenici. **Ovo je jedini pravi diferencijator.**
2. **Nepromenljiva evidencija sa hash-lancem** — implementirano i DB-potvrđeno. Retko van finansijskih sistema.
3. **Srpski pravni kontekst** — korpus propisa i prakse. Nije tehnički diferencijator, ali jeste tržišni.

**NIJE DIFERENCIJATOR (roba široke potrošnje):** OCR, semantička pretraga, sažimanje, izrada nacrta, ćaskanje o dokumentu. Sve to danas ima svako. **Ne graditi sajt oko toga.**

**Provider fabric NIJE diferencijator dok kroz njega ne prođe nijedan poziv.**

---

## 10. BEZBEDNOST — tri kategorije

**BEZBEDNO ZA SAJT:** razdvajanje podataka po vlasniku · nepromenljiva evidencija radnji · poreklo AI odgovora · uloge i ovlašćenja · sadržaj upita se ne upisuje u evidenciju · postojeći dokumenti (DPA, bezbednosni list, AI disclosure).

**UZ PAŽLJIVU FORMULACIJU:** „provera ulaznog sadržaja pre slanja modelu" (ne zvati to zaštitom od napada) · „više nezavisnih unutrašnjih provera" (ne zvati to auditom treće strane).

**SAMO INTERNO:** imena tabela, ruta i modula · to da aplikacija koristi service-role ključ · struktura migracija · rezultati forenzičkih sprintova · ime dobavljača modela.

**NIKAD:** „potpuno bezbedno" · „GDPR usklađeno" (postoje mehanizmi, nema nezavisne potvrde) · „vaši podaci se ne koriste za treniranje" — dok se ne proveri ugovorom sa dobavljačem.

---

## 11. AI POZICIONIRANJE

**JAVNO:** „Vindex je platforma; AI model je komponenta koju ona koristi za pojedinačan zadatak."

**TEHNIČKI:** kanonski kontekst je provider-agnostičan; sloj za više dobavljača je implementiran sa tri adaptera i governance kapijom, ali još nije u produkcionom toku.

**ZABRANJENO:**
- „Vindex ima sopstveni AI model" — **netačno**
- „Vindex automatski bira najbolji model" — **nije implementirano**
- „Koristimo GPT, Claude i Gemini" — adapteri postoje, **produkcija koristi jednog dobavljača**
- bilo koji procenat tačnosti — **nikad izmeren**

---

## 12. INVENTAR DOKAZA

**PROVERENO O PROIZVODU:** kanonski kontekst · nepromenljiva evidencija · razdvajanje podataka · uloge · provenance AI-ja.
**INŽENJERSKI DOKAZ (ne stavljati na sajt kao prodajni argument):** 3893 testa · 20+ forenzičkih prolaza.
**TRŽIŠNA VALIDACIJA:** razgovori sa više advokata; kontakt sa Stefanom Gojkovićem, sudijskim pomoćnikom. **Nisu korisnici ni partneri.**
**NEDOKAZANO:** kvalitet AI izlaza · upotrebljivost nacrta · OCR · brzina · naplata.

---

## 13–15. SADRŽAJ I ARHITEKTURA SAJTA

**Preporučeni redosled odstupa od zadatog — i evo zašto:** kupac je pojedinac koji se plaši greške AI-ja. Poverenje mora doći **pre** nabrajanja funkcija, ne posle.

```
1. HERO            — šta je Vindex, u jednoj rečenici
2. PROBLEM         — gubitak konteksta, rokovi u tekstu
3. KAKO RADI       — 4 koraka, konkretno
4. ZAŠTO VERUJETI  ← POMERENO NAPRED (poreklo + evidencija)
5. ŠTA RADI DANAS  — grupisano, bez liste od 40 stavki
6. ZA KOGA         — advokatura prvo
7. STANJE          — pošteno: pred zatvoreno testiranje
8. CTA
```

**MINIMALNI SAJT (P0):** `Početna` (sve gore, jedna strana) · `Bezbednost` (postoji sadržaj) · `Kontakt`.
**P1:** `Kako radi` (razrada) · `Za advokate`.
**P2 — NE PRAVITI SADA:** Industrije, Blog, Dokumentacija, FAQ, O nama, Cenovnik.

Trostrani sajt je **prednost** u ovoj fazi: manje površine za neproverene tvrdnje.

---

## 16. KONVERZIJA

**PRIMARNI CTA: „Prijavite se za zatvoreno testiranje"**

Obrazloženje: proizvod **nema** korisnike i **nije** spreman za samouslužnu registraciju. „Zatražite demo" implicira prodajni tim koji ne postoji. „Probajte besplatno" implicira spreman proizvod. Poziv na zatvoreno testiranje je **jedini iskren**, a usput deluje kao kvalifikacija — što povećava vrednost umesto da je smanjuje.

**SEKUNDARNI:** „Preuzmite bezbednosni list" (dokument već postoji — daje opreznom advokatu nešto konkretno bez razgovora).

**IZBEGAVATI:** „Počnite besplatno" · „Zakažite demo" · „Kontaktirajte prodaju" · bilo koji formular duži od 3 polja.

---

## 17. VIZUELNI IDENTITET

**Nalaz:** marketinška ulazna strana **ne postoji**. `static/` ima samo pravne strane. Postoji vizuelni jezik same aplikacije: `#010308` podloga, `#00d4ff` akcenat, `#e6edf3` tekst, oštri uglovi, monospace elementi.

**ZADRŽATI:** tamnu paletu i oštre uglove — deluju kao alat, ne kao brošura. Konzistentnost sa aplikacijom gradi poverenje.
**IZBEGAVATI:** stock fotografije advokata, sjaj, gradijente, ikonice mozga i kola. Memorija projekta to već zabranjuje.
**NAPRAVITI:** dijagram toka predmeta i prikaz polja sa oznakom porekla — to je jedina slika koja objašnjava proizvod.

---

## 18. UX PRINCIPI

1. Objasni pre nego što prodaješ.
2. Razdvoj *danas* od *planirano* — vidljivo, ne u fusnoti.
3. Nijedan broj bez merenja.
4. Poverenje pre konverzije.
5. Pokaži proizvod, ne apstrakciju.
6. Jedan CTA po strani.
7. Tehnička uverljivost bez žargona.
8. Bez tamnih obrazaca — nema lažne hitnosti ni izmišljenih brojača.

---

## 19. RED TEAM — šta bi srušilo poverenje

| Prigovor | Odgovor koji sajt mora imati |
|---|---|
| „Još jedan omotač oko ChatGPT-a" | prikazati poreklo polja i evidenciju — to omotač nema |
| „Gde su moji podaci?" | bezbednosni list i DPA odmah dostupni, bez formulara |
| „Ko ovo već koristi?" | **priznati da niko** — pozvati na zatvoreno testiranje |
| „Koliko je tačan?" | **ne odgovarati brojem.** Reći da svaka tvrdnja ima izvor koji advokat proverava |
| „Deluje kao hobi projekat" | tri strane bez greške bolje od deset praznih |
| Poslovni strateg: „gde je odbrana?" | kontekst i trag, ne model |

**ŠTA NEDOSTAJE:** jedan stvarni predmet proveden kroz sistem · ekranski prikazi · kontakt podaci firme · odluka o ceni.

---

## 20–21. TVRDNJE

Vidi `VINDEX_AI_PUBLIC_CLAIMS.md`.

**PREPORUČENI PRAVAC:** tri strane, tamna tehnička estetika dosledna aplikaciji, poverenje pre funkcija, poziv na zatvoreno testiranje. Sadržaj isključivo iz odobrene liste tvrdnji.

---

## 22. OTVORENA PITANJA

1. **Ekranski prikazi** — bez njih sajt ostaje tekstualan. Ko ih pravi?
2. **Kontakt i pravni podaci firme** — nisu u repozitorijumu.
3. **Cena** — u repozitorijumu postoji više neusaglašenih varijanti; sajt ne sme da je pominje dok se ne odluči.
4. **Ugovor sa dobavljačem modela** — bez njega se ne sme tvrditi ništa o korišćenju podataka za treniranje.
5. **Jedan proveden predmet** — jedini način da se bilo šta kaže o kvalitetu rezultata.
