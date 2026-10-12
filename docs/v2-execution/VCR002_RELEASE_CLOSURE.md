# VCR002 — zatvaranje izdanja: tri ciljane ispravke pre spajanja PR #20

**Polazište:** `e6584030` (kod `38ac5fcd`). **Osnovica za regresiju:** `main` = produkcija `b36235a3`.

Ništa nije spojeno, pušteno ni primenjeno na produkciju. Migracija 137 postoji samo u repo-u i testirana je nad izolovanim lokalnim PostgreSQL-om 17. Tajne, cene, Cron i autonomija nisu dirani. PR #20 ostaje Draft.

## FIX 1 — integritet brisanja dokumenta (P0) — `80dc114e`

**Kvar (reprodukovan na `38ac5fcd`; 7 od 8 novih testova pada):**
- greška pri čitanju AI tvrdnji je progutana, pa je API vraćao `success: true`, a tvrdnje su ostajale aktivne;
- greška pri povlačenju tvrdnji je davala `success: true, tvrdnje_povucene: -1`;
- pad procesa posle brisanja reda, a pre povlačenja, ostavljao je tvrdnje aktivne. Pošto je FK `predmet_dokazi.dokument_id` `ON DELETE SET NULL`, veza sa izvorom je već bila obrisana, pa ih ni ponovni pokušaj (404) ni bilo koji kasniji posao više nisu mogli naći. To je trajan kvar, ne prolazan.

**Najmanja ispravna granica transakcije:** jedna PostgreSQL funkcija.

- **Migracija 137** (`invalidate_dokument_and_ai_claims_and_emit_event`, novo ime, stara funkcija netaknuta). U jednoj transakciji:
  1. zaključava red dokumenta (`FOR UPDATE`, pa konkurentan upis tvrdnje ne promakne);
  2. meko briše AI tvrdnje tog dokumenta (isti predikat kao FIX-T03-1);
  3. briše red;
  4. upisuje `SourceInvalidated`.

  Sve ili ništa. `SECURITY DEFINER`, `search_path = ''`, vlasništvo se proverava unutar funkcije, `EXECUTE` ima samo `service_role`.
- **`api.py`:** atomski put. **Dok 137 nije primenjena na produkciju**, samo za PGRST202/42883, važi put sa kompenzacijom:
  - tvrdnje se povlače PRE brisanja reda;
  - ako brisanje ne uspe, povlačenje se vraća, i to samo za redove koje je povukao ovaj zahtev;
  - ako ni vraćanje ne uspe, odgovor to izričito kaže.

  Uspeh se prijavljuje samo kad su oba koraka potvrđena. Advokatove tvrdnje, istorija izvora i nepromenljiv audit su očuvani.
- **Preostali prozor bez 137:** pad radnika tačno između povlačenja i brisanja reda. Tada su tvrdnje povučene, a dokument je u listi. Vektori su već uklonjeni, a uspeh nije prijavljen. Ponovni pokušaj završava brisanje (dokazano testom). Migracija 137 zatvara i ovaj prozor.

**Dokazi:**

| Šta | Rezultat | Nivo |
|---|---|---|
| `tests/test_vcr002_rc_fix1_brisanje_dokumenta.py`, kroz stvarnu rutu | 9 passed: greška čitanja, greška povlačenja, pad posle brisanja, pad između povlačenja i brisanja, kompenzacija, greška atomske funkcije, atomski put sa tuđim korisnikom, nikad `-1`, trka dva brisanja | ISOLATED |
| `tests/test_vcr002_rc_fix1_migracija137_pg.py`, **pravi PostgreSQL 17** | 5 passed:<br>• jedna transakcija, tačan skup povučenih tvrdnji;<br>• rollback pri grešci, pa uspešan ponovni pokušaj;<br>• tuđ korisnik ništa ne dira, a ponovni poziv je bez izmena;<br>• `EXECUTE` samo `service_role`;<br>• konkurentan nepotvrđen upis tvrdnje čeka i povlači se | ISOLATED (pravi PG) |
| Mutacije | 7/7 uhvaćeno: atomska greška tretirana kao „nema funkcije“, bez kompenzacije, progutana greška čitanja, SQL bez `FOR UPDATE`, SQL povlači i advokatove, SQL briše pre povlačenja, uspeh iako funkcija vrati `false` | — |
| Postojeći testovi brisanja (T03, NS001, Wave 2 2D, migracije 132/133) | 65 passed. Lažne baze NS001 i T03 dobile su model nove funkcije (isti predikat vlasništva). | ISOLATED |

## FIX 2 — oporavak plaćenog niza savetnika (P0) — `a1468152`

**Reprodukcija** (stvarna ruta, stvaran trajni middleware, radnik umire posle prvog plaćenog koraka):
- red idempotencije ostaje `IN_PROGRESS`, pa nema lažnog „završeno“, a isti ključ dobija iskren 409 „ishod nepoznat“;
- **izlaz plaćenog koraka nije upisan ni u jednu tabelu**;
- naplata je red u `feature_usage_log` bez veze sa zahtevom ili korakom;
- nova radnja advokata **ponovo plaća isti korak**.

**Presuda:** postojeća trajna infrastruktura **ne može** bezbedno da uskladi plaćen rad. Za to je potrebna nova evidencija koraka (nova šema, posebno odobrenje). Keš procesa nije trajna garancija i nije korišćen.

**Ispravka:**
- V2 ulaz „Od istraživanja do nacrta“ je **isključen**: HTML `disabled`, a katalog savetnika ga ne može ponovo uključiti. Nasilan izbor ne šalje zahtev i kaže da način rada nije dostupan.
- „Jedan savetnik“ i „Tri pogleda istovremeno“ rade kao i pre.
- Backend `/api/agents/pipeline` nije menjan. Niko drugi ga ne poziva (proveren repo).

| Šta | Rezultat |
|---|---|
| `tests/test_vcr002_rc_fix2_niz_oporavak.py` | 4 passed: 3 reprodukcije koje su dokaz odluke (padaju ako se ponašanje promeni) i čuvar V2 ulaza |
| Mutacije | 2/2 (katalog ponovo uključuje niz; HTML nudi niz) |
| Browser | vidi „Zajednička kapija“ |

## FIX 3 — AI tvrdnje i protivrečnosti u kontekstu pravnog pitanja (P0) — `056a48e6`

**Kvar (reprodukovan; 7 od 8 novih testova pada):**
- `/api/pitanje` je modelu slao „Utvrđene činjenice u predmetu: … (cinjenica, snaga=jaka)“ za AI tvrdnje;
- `snaga` je bila podrazumevana vrednost kolone ili DC-005 „pronađeno“, ne procena;
- dve tvrdnje u **trajnoj V2 protivrečnosti** (17.03. naspram 25.03.2025, stvarno upisanoj kroz T03 tok) išle su bez oznake.

**Ispravka** (`shared/genome_contract.kontekst_tvrdnji`, uz kanonski `poreklo_tvrdnje`):

| Poreklo (kanonsko) | Oznaka u kontekstu |
|---|---|
| advokat | „uneo advokat“ (+ „procena advokata: X“ samo kad je `izvor_snage = covek`) |
| tvrdnja pronađena u tekstu svog dokumenta | „navod iz dokumenta, pronađen u tekstu (AI izdvojio \| autor nije zabeležen)“ |
| AI, nije pronađena | „AI izdvojio, u tekstu dokumenta nije pronađen — neproveren“ |
| nepoznato | „poreklo nije zabeleženo — neproveren“ |

- Naslov: „Tvrdnje u predmetu (nijedna nije sudski utvrđena činjenica; uz svaku je navedeno poreklo)“.
- **SPORNO** stoji samo uz članove trajnih V2 protivrečnosti u stanju aktivna ili za pregled, uz odeljak „Sporne tačke“. Čitanje je ograničeno na predmet I korisnika; razrešena protivrečnost nije sporna.
- Pad čitanja protivrečnosti se izričito kaže.
- Nema klasifikatora protivrečnosti ni nove ocene sigurnosti. Sve ostaje u granici poverenja (`VINDEX_NEPOVERLJIVO`).

| Šta | Rezultat |
|---|---|
| `tests/test_vcr002_rc_fix3_kontekst_pitanja.py` (tačan tekst ka modelu, stvaran predmet sa tri dokumenta) | 8 passed |
| Mutacije | 7/7 (vraćen naslov, razrešena kao sporna, DC-005 snaga kao procena, čitanje bez granice korisnika, pad čitanja prećutan, AI bez „neproveren“, izvor bez oznake AI) |
| Regresija: svi testovi koji šalju `/api/pitanje` sa predmetom + brisanje + savetnici (21 fajl; `test_beta_gate_upload_refund.py` se izdvojeno ne prikuplja bez OpenAI ključa, pa je pokriven punim paketom) | 372 passed, 9 skipped, 0 failed |

## Zajednička kapija

**Poređenje identiteta palih testova sa istom osnovicom:** `main` `b36235a3`.

| Provera | Rezultat | Novo |
|---|---|---|
| Lokalni pun Python paket, `056a48e6` (sva tri fixa) | 19 failed, 9323 passed (osnovica 22 failed) | **0** |
| Lokalni pun Python paket, `80dc114e` (samo FIX 1) | 21 failed, 9310 passed; 2 razlike, obe nisu do koda | **0** posle provere |
| CI Test Suite 3.11 / 3.13 (38249352253) | 174 / 174, 8787 passed | **0** |
| CI Production Runtime Parity (38249352357) | 196; Docker build + boot success; OCR u produkcionoj slici 32 passed | **0** |
| CI Security Checks (38249352222) | success | — |
| CI V2 NG (38249372047) | success; prvi pokušaj je pao na nasleđenom `FLAKY-DEMO-PIKSEL` (HEAD naspram HEAD-a, 15 piksela po jednu nijansu). Pokrenut je ponovo samo taj posao, prag nije menjan. | — |
| Lokalno svih 45 V2 frontend paketa (`verify*` + `e2e:*`) | **45/45 PASS**; `verify:live-agenti` 38/38, `e2e:savetnici` 16/16 | — |

**Dve razlike u pokretanju FIX 1, obe objašnjene:**
- `test_b4_authority_playwright.py::test_b4_ui_oznaka_se_vidi_i_bez_ijednog_izvora`: pokrenut sam prolazi. To je ista klasa legacy V1 Playwright nestabilnosti pod opterećenjem kao u VCR002.
- `test_wave10_test_db_bootstrap.py::test_deljeni_klasteri_i_dalje_rade`: test se preskače kad nijedan lokalni klaster ne radi, a pada kad radi samo jedan. Tokom tog pokretanja radio je izolovani PG na 55432 za dokaz migracije 137. Posle gašenja klastera, u završnom pokretanju je preskočen kao u osnovici.

**Pravi PostgreSQL:** izolovan lokalni klaster PG 17 (127.0.0.1:55432). Ugašen je posle dokaza.

## Preostale blokade (ovlašćenje, ne kod)

1. Odobrenje spajanja tačno kandidata `056a48e6` (PR #20 ostaje Draft).
2. Migracija 137, posle spajanja; zatvara `LIM-RC-1`.
3. QA nalog za prijavljenu proveru produkcije.
4. `CRON_SECRET` / `CRON_TOKEN` i test primalac za podsetnike; odluka o SMS cron-u.
5. Migracija 136 i autonomija.
6. Pilot predmet.
7. Miroslavljev izvorni dokument.
8. Trajna evidencija koraka niza savetnika, ako želite da se niz ponovo uključi.

## Presuda

**GO** za spajanje kandidata `056a48e6`, uz vaše odobrenje tačno tog kandidata. Nijedan od tri rizika više ne blokira spajanje. Gornje blokade ograničavaju samo tvrdnju „radi u produkciji za prijavljenog advokata“.
