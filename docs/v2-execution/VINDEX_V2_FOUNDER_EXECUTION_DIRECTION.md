# Vindex V2 — izvršni pravac osnivača (VCR001)

**Status:** dodatna izvršna odluka. Podređena je dokumentima *VINDEX — CANONICAL OPERATING RULES* i `docs/v2/VINDEX_V2_PRODUCT_ARCHITECTURE_DECISION_PAD_001.md` (zaključan, nije menjan). Ne zamenjuje nijedan njihov zahtev o bezbednosti, pravnoj pouzdanosti i očuvanju sposobnosti.
**Izvor:** direktiva osnivača „VINDEX AI — MASTER EXECUTION DIRECTIVE / VCR001“, data u radnoj sesiji 2026-10-11. Bez potpisa; ovo je zapis instrukcije, ne potpisan dokument.

## Odobren pravac (citat)
> PRESERVE → CONSOLIDATE → HARDEN → RECONNECT → VERIFY → RELEASE.
> Vindex is a Legal Operating System. … Existing capabilities are assets. Do not remove them because their existing frontend is old, incomplete or complicated.

**Cilj proizvoda:** postojeći V2 učiniti profesionalno upotrebljivim pravnim operativnim sistemom. To znači:
- ponovo povezati postojeće V1 sposobnosti;
- završiti radne tokove sa izvorom (Bojan);
- omogućiti postojeće multi-agentske sposobnosti na zahtev;
- pripremiti kontrolisanu A2/A3 autonomiju.

**Jedinica uspeha:** radni tok koji advokat zaista završi.

## Prekretnice
| | Obuhvat | Zadaci |
|---|---|---|
| **R1** | kompletan prijem: osnovica, OCR, V2 čarobnjak za prijem, organizacija predmeta | T00–T03 |
| **R2** | kompletan pravni rad: Genome i istraživanje, nacrti sa ljudskim pregledom, agenti na zahtev, V1 sposobnosti | T04–T07 |
| **R3** | autonomija A2/A3 (aktivacija traži zasebnu odluku) i zatvaranje zahteva Bojana i Miroslava | T08–T09 |

## Redosled
T00 → T01 → … → T09, strogo redom. Svaki zadatak prolazi kroz: problem → dokaz → ugovor → implementacija → ciljani test → negativna kontrola → E2E → bezbednost → zapis → zatvaranje.

## Očuvanje
- Postojeći ugovori podataka, API-ji, dozvole, istorija i integracije.
- RH001/RH002.
- JWT izuzetak samo pod uslovima iz `JWT_CVE_2026_85394_RISK_ACCEPTANCE.md`.
- Vizuelni identitet (grafit, cijan, Source Serif 4, Source Sans 3, JetBrains Mono).
- Timske funkcije.

## Definicija završenog
Sposobnost je završena kada je svi uslovi ispunjeni:
- advokat je nalazi, ima dozvolu i šalje unos kroz pravi UI;
- backend radi; rezultat je vidljiv i ostaje sačuvan; sledeći korak toka koristi rezultat;
- greške su istinite; naplata prati postojeći ugovor; neovlašćen pristup je odbijen;
- postoji test celog toka u pregledaču; dobijena je produkciona potvrda gde je primenljivo.

Sam endpoint, mock test u pregledaču ili stari snimak ekrana ne računaju se kao završetak.

## Kapije dokaza
Ugovor → dokaz pre ispravke → minimalna izmena → ciljani testovi → negativna kontrola → adversarijalni slučajevi → E2E u pregledaču → sačuvano stanje → zapis → zatvaranje sa SHA. Nivoi dokaza se odvajaju: lokalno, izolovana baza, pregledač sa mock-om, pregledač sa pravim backendom, produkcija.

## Granice ovlašćenja
- **Odobreno ovom direktivom:** izmene koda, testovi, commit-ovi na programskoj grani, Draft PR-ovi.
- **Traži zasebnu izričitu odluku:**
  - merge i deploy u produkciju za konkretan kandidat;
  - produkcione migracije (uključujući 136);
  - Render Cron i budžet autonomije;
  - izmene naplate i tarifa;
  - spoljne pravne radnje (A5);
  - nadogradnja naloga ili upis kredita.
