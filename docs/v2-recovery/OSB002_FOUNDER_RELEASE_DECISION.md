# OSB002 — odluka o izdanju solo bete (za jutarnji pregled)

**Preporuka: uslovni GO.** Osnovni solo tok radi od početka do kraja. Noćas je nađen i ispravljen jedan stvaran
kvar koji bi pogodio prvog advokata: dokumenti otpremljeni kroz V2 nisu dobijali tvrdnje u dokazima. Do izdanja
nedostaju vaše dve odluke i spajanje PR-ova; ništa nije spojeno ni deployovano.

Oznake: **P** izmereno · **I** zaključeno iz koda · **A** pretpostavka · **U** nepoznato.

## Šta je noćas zatvoreno
| Oblast | Stanje |
|---|---|
| Solo tok (klijent → predmet → dokument → dokazi → Genome → akcije → pitanje → Law Brain → nacrt) | **radi** posle ispravke (P, lokalno, modeli simulirani) |
| Isključena autonomija (bez migracije 136) | **dokazano** ponovljivim browser testom u repou, sa kontrolom koja mora da padne (P) |
| Granica solo / tim | **bez curenja** kroz svih 58 timskih ruta; solo ne može da delegira (P) |
| JWT ranjivost biblioteke | **nije dostižna** u Vindex kodu; ispravljena verzija ne postoji (P/I) |
| Tajne u kodu | **nijedna nova** u 94 commita od produkcije (P) |
| OCR otkazi (prazan, oštećen, prekinut) | **nikad lažno „završeno“** (P) |
| CI (Test Suite 3.11/3.13, produkcioni Python, Docker, V2 NG, OCR korak) | **0 novih padova** naspram polazne grane (P) |
| Živi OCR u produkciji, tačnost na stvarnom korpusu | **U**. Produkcioni image nema srpski OCR paket (samo engleski), pa su dijakritici i ćirilica rizik |

## Ispravka
`c148d342`: jedna linija u `routers/smart_intake.py`. Smart Intake je dokument unapred označavao kao
„klasifikovan“, pa sistem nikad nije izvlačio tvrdnje iz dokumenata otpremljenih kroz V2. Bez ispravke Living Matter
bi za te dokumente imao prazne dokaze i ne bi nalazio kontradikcije. Testovi: 53 povezana fajla bez ijednog novog pada.

## Oborena uverenja
- „Browser dokaz 17/17 potvrđuje da nema autonomnih akcija“: ta provera je bila slepa (tražila je „prihvati“, a dugme
  glasi „Prihvatam“). Nova provera to hvata.
- „Gitleaks pada zbog 876 starih nalaza“: tačan uzrok je zastarela verzija gitleaks-a u CI-ju koja ne čita allowlist.
- „Nema API-ja za delegaciju“: API postoji (`/api/enterprise/predmet/delegiraj`), samo bez dugmeta; solo dobija 404.

## Blokade za solo betu
Nijedna tehnička. Ostaju vaše odluke ispod.

## Vaše odluke (najviše tri)
1. **JWT izuzetak (obavezno pre izdanja).** Preporuka: **odobriti** privremeni izuzetak za CVE-2026-85394 u
   python-jose 3.5.0, sa obavezom da se zameni bibliotekom kada izađe ispravka ili najkasnije za 90 dana.
   Obim odobrenja: samo ovaj CVE, samo dok svaki `jwt.decode` ima tačno jedan algoritam i dok produkcioni JWKS
   ima samo ES256 ključ. Okidač za ponovni pregled: nova verzija python-jose, promena JWKS-a ili nova ruta koja
   čita JWT. Bez ovog odobrenja odgovor je NO-GO.
2. **Stari UI i timske funkcije.** Na `/app-legacy` i dalje postoje pravljenje kancelarije i pozivi kolega
   (pozivi sa ulogom „saradnik“ padaju, BETA-DEF-001). Preporuka: **ostaviti kako jeste** i u beta poruci reći
   da saradnja nije podržana. Skrivanje bi bila nova izmena UI-ja koju niste odobrili.
3. **Crven `secret-scan` u CI-ju.** Preporuka: odobriti zaseban mali PR koji (a) fiksira noviju verziju gitleaks-a
   u `security.yml` i (b) dodaje testnu vrednost iz `tests/test_wave10_rate_limiter_isolation.py:35` u
   `.gitleaksignore` sa obrazloženjem. Bez toga RC1→main PR ne može da dobije zelen secret-scan.

## Predlog produkcionog smoke testa (NIJE izveden — čeka vaše odobrenje)
Posle deploy-a, sa jednim vašim test nalogom: prijava → nov klijent → nov predmet → otpremanje jednog
digitalnog i jednog skeniranog PDF-a kroz V2 → pregled i prikačivanje → posle 1–2 minuta proveriti da dokument
ima tvrdnje u „Dokazi“ → jedno pravno pitanje u predmetu → `/health` vraća novi SHA → Danas ne prikazuje
„Vindex je pripremio“. Troši OCR i AI kredite i upisuje podatke, zato traži vašu dozvolu.

## Sledeći korak
Potpišite odluku 1, zatim pregledajte i spojite PR #12, pa PR #13 u `release/v2-rc1`.

## Bezbednost
Bez spajanja u `main` ili RC1, bez deploy-a, migracija, Cron-a, izmena produkcionih podataka ili brisanja audit
istorije. U produkciji su izvedena samo read-only brojanja (`predmeti.case_dna`, dokumenti/tvrdnje) i čitanje
javnog JWKS-a.
