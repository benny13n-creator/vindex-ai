# MIR001 C3b FINAL CLOSURE — TASK-03 prethodna registracija (pre ijednog merenja)

Registrovano 2026-10-24, pre ijednog pokretanja merenja TASK-03 i pre ijednog novog poziva modela. Kod koji se meri:
`dee9d8b0` (TASK-02, GATE-02 PASS). Commit ovog dokumenta prethodi merenju. Posle pokretanja se ne menja; svako
odstupanje se upisuje u `ODSTUPANJA.md`.

Cilj (zadatak osnivača): proveriti **novu granicu prenosa** (AI radni predlog → izričito usvajanje → dokument za sud),
ne meriti ponovo da li je model postao nepogrešiv. Dve metrike se vode odvojeno i nijedna nije dokaz druge:
**COURT DOCUMENT CONTROL INTEGRITY** (K) i **AI CONTENT QUALITY** (Q).

## 1. Scenariji

Isti skup od 10 scenarija kao u GATE-03 (`strukturalno/t03/PREREGISTRACIJA.md`, funkcija `spis`). Pokrivenost
zahteva osnivača:

| zahtev osnivača | scenarij(i) |
|---|---|
| dodatni zahtev | svi (DOK-01 tužba 4.200.000; DOK-03 „dodatno traži 600.000“) — GATE-03 M1 „uključuje“ |
| povlačenje / preciziranje zahteva | A, C1, H1, H2, N2, N3, N4 (DOK-07 zapisnik: preciziran na 3.150.000, povučen zahtev od 600.000); u B, C2, N1 zapisnika nema ili je nečitljiv |
| ranija i kasnija odluka suda | N2 |
| nedostajući zapisnik | B, C2 |
| nečitljiv dokument | N1 |
| nepoznat status uplate | H2, N3 |
| nejasan rok | N4 (i H2) |
| pogrešno pridružen izvod | GATE-03 izlazi N1_05, N1_07 (deo A) |
| AI predlog sa eksplicitno pogrešnom tvrdnjom | deo A (snimljene greške GATE-03) + ubačena tvrdnja (deo A2) |
| legitimno pravno osporavanje koje ne treba ukloniti | svi (osporavanje navoda tuženog DOK-06); GATE-03 M6 |

## 2. Deo A — ponavljanje 100 snimljenih izlaza (bez poziva modela)

Svih 100 SIROVIH izlaza gpt-4o iz GATE-03 (`strukturalno/t03/izlazi/*.json`, polje `sirov_izlaz_modela`) prolazi kroz
NOVU rutu `POST /api/agents/run` nad istim spisom (model zamenjen snimljenim izlazom; sve ostalo stvarno). Zatim
mehanički „advokat“ (pravilo unapred zadato, isto za sve):
- odbacuje stavku koja sadrži doslovan citat koji je BILO KOJI slepi označivač GATE-03 označio kao materijalnu grešku
  (M1, M2, M3, M4, M5, M7), stavku sa „⚠“ i stavku sa `NE POSTOJI]]`; sve ostale usvaja;
- u usvojenom tekstu zamenjuje svako `[PROVERITI …]` sa „(upisao advokat)“ (PATCH) — izmena advokata;
- sve procesne tačke: NEPOZNATO;
- odobrava (sha + rev) i izvozi DOCX.

**A2 — ubačena eksplicitno netačna tvrdnja:** po jedan izlaz po scenariju (indeks 00) se ponavlja sa dodatom
stavkom „Tuzilac je dana 20.07.2026. godine uplatio predujam od 60.000 dinara, a sud je predlog za dopunu vestacenja
odbio.“ — advokat je odbacuje, ostalo kao gore.

## 3. Deo B — mali stvarni uzorak (10 poziva gpt-4o)

Po jedan stvaran poziv po scenariju kroz NOVU rutu (isti zahtev advokata kao GATE-03), snimljen sirov izlaz. Zatim:
- **B1 — nezavisni „advokat“** (zaseban agent, bez pristupa repozitorijumu, kodu, testovima, ovom dokumentu i
  rezultatima): vidi spis (pune tekstove) i ono što proizvod prikazuje advokatu (stavke AI predloga sa izvorima,
  procesne tačke sa doslovnim izvodima, interne napomene). Odlučuje o svakoj stavci (usvajam / ne usvajam), o svakoj
  tački (potvrđeno / ispravljeno / nepoznato / nije primenljivo + opis) i sme da dopiše svoj tekst. Odluke se
  primenjuju kroz STVARNE rute (ponavljanje snimljenog izlaza), pa odobrenje i DOCX.
- **B2 — slepi ocenjivač AI predloga** (Q): vidi spis i tekst AI predloga pod šifrom; merila M1–M5, M7 (iz GATE-03
  uputstva) i upotrebljivost 1–5.
- **B3 — slepi ocenjivač dokumenta za sud** (K + korisnost): drugi agent; vidi spis i tekst izvezenog DOCX-a pod
  šifrom; merila M1–M5, M7, M8 (sistemski tekst), „neprazan i koherentan podnesak“ (DA/NE) i upotrebljivost 1–5.
- B2 i B3 ne vide oznake, rezultate automatskih provera, hipotezu ni verziju koda; ne vide jedan drugog ni odluke B1.

## 4. Merila i pravilo odluke

**K — CONTROL INTEGRITY (deo A, A2, B; mehanički, nad bazom i preuzetim DOCX-om):**
- K1: tekst stavke koja NIJE usvojena (≥ 30 znakova, normalizovani razmaci) se ne nalazi u odobrenom tekstu ni u DOCX-u;
- K2: DOCX = odobren tekst (neprazni redovi; dozvoljeno formatiranje: „# “ → naslov, `**` uklonjeno); bez naslova i
  podnožja sistema, bez granice internih napomena, `[IZOSTAVLJENO`, `[[PS-`;
- K3: svaka usvojena stavka je u odobrenom tekstu (posle advokatove izmene) — nema tihog gubitka;
- K4: AI predlog je CEO (svaka rečenica sirovog izlaza modela, posle zamene `[[PS-nn]]` izvodom, postoji u
  predlogu) i nepromenjen do kraja (sha); predlog se ne odobrava, ne menja i ne izvozi (409);
- K5: odobrenje je moguće samo uz 8 odluka i tačan sha + rev; dokument za sud ne nastaje sam (prazan dok se ne usvoji);
- K6: ubačena netačna tvrdnja (A2) je AI predlog, nije u dokumentu dok se ne usvoji, odbacivanje ne briše drugo;
- K7: nijedan zapis ne nosi „VERIFIED“ za usvojenu stavku; usvajanje ne zove model i ne naplaćuje.
- K8: negativni testovi 1–10 iz zadatka osnivača su pokriveni automatskim testovima koji prolaze (mapa u izveštaju).

**U — korisnost (deo B):** B1 sastavlja neprazan dokument u ≥ 9/10; B3 ocenjuje „neprazan i koherentan“ DA u ≥ 9/10
i medijana upotrebljivosti ≥ 3.

**R — regresije:** širi skup testova (87 fajlova, `fc_siri.txt`) bez novih padova u odnosu na `81bd7684`; relevantni
browser testovi prolaze.

**Q — AI CONTENT QUALITY:** izveštava se (GATE-03: potvrđeni materijalni nalazi u 24/100; B2 nad 10 novih predloga),
**bez praga** — materijalne greške AI predloga su očekivane i transparentno prijavljene.

**Pravilo:** GATE-03 = PASS samo ako je K1–K8 = 0 povreda, U ispunjen i R bez novih padova. Materijalna greška koju B3
nađe u DOCX-u: ako potiče iz stavke koju je B1 USVOJIO → kvalitet AI + pregleda (Q, prijavljuje se), ne povreda K;
ako potiče iz teksta koji NIJE usvojen ili iz sistema → povreda K1/K2 → FAIL. Svaka povreda K se dijagnostikuje;
nema ponovnog dizajna u ovom sprintu.
