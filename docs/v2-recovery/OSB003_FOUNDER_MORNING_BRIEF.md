# OSB003 — jutarnji brif za osnivača

**Preporuka: USLOVNI GO.** Noćas sam pokušao da oborim kandidata i našao 5 stvarnih kvarova; svih 5 je ispravljeno
uz test koji pada bez ispravke. Ostaju vaše odluke i spajanje tri PR-a redom. Ništa nije spojeno ni deployovano.

Oznake: **P** izmereno · **I** zaključeno · **U** nepoznato.

## Šta je nađeno i ispravljeno
| # | Kvar | Šta bi korisnik doživeo | Ispravka |
|---|---|---|---|
| 1 | Prolazna greška baze trajno gubi tvrdnje iz dokumenta | dokument bez dokaza, tiho | `db5255d2` |
| 2 | Čuvar citata ne vidi „članu 9999“, „čl. 9999“ | izmišljen član u odgovoru bez blokade | `1c188ea3` |
| 3 | Nov korisnik bez predmeta vidi „Vindex je pripremio“ | reklama za isključenu autonomiju na prvom ekranu | `9994b976` |
| 4 | JWKS ključ bez `alg` → 500 umesto 401 | greška umesto odbijanja (bez pristupa) | `0709728d` |
| 5 | CI secret-scan crven zbog stare verzije alata | prava nova tajna bi se izgubila u šumu | `b8ac7935` |

## Ispravljena moja ranija greška
OSB002 je tvrdio da produkciona slika nema srpski OCR paket. **Netačno.** Slika ima srpsku ćirilicu i latinicu (P), a
skenirana ćirilica se čita 21/21 reči sa pouzdanošću 0.95 (P). Pogrešno sam pročitao drugi CI posao.

## Stanje kandidata
| Oblast | Stanje |
|---|---|
| Solo tok u pravom pregledaču (predmet → klijent → dokument → dokazi → Genome → akcije → pitanje → nacrt) | P: 23/23 |
| Srpski OCR (latinica i ćirilica) u produkcionoj slici | P |
| Autonomija isključena (i za novog korisnika bez predmeta) | P |
| JWT: falsifikati | P: 0 prihvaćeno u 4 varijante JWKS-a |
| Tajne | P: 0 nalaza u istoriji posle ispravke alata; nova tajna se hvata |
| Curenje između korisnika / timske rute | P: nema |
| CI u odnosu na polaznu granu (Test Suite 3.11/3.13, produkcioni Python, Docker, V2 NG, Security) | P: **0 novih padova**; secret-scan prvi put zelen |
| Živi OCR u produkciji, tačnost na stvarnom korpusu | U |
| Da li Render radi iz Docker slike | I (pid 7, 1 worker); potvrda u dashboard-u |

## Otvoreno, ali nije blokada za solo betu
- **BETA-DEF-004:** ako baza padne baš između upisa dokumenta i upisa događaja, taj dokument ostaje bez tvrdnji. Retko;
  ispravka traži promenu ugovora — predlog u `defects/BETA-DEF-004_*.md`.
- **BETA-DEF-003:** odbijeno prikačivanje zaključava posao 120 s.
- Čuvar citata ne poredi naziv zakona (isti broj člana iz drugog zakona prolazi).
- Tajna upisana u `data/sudska_praksa/raw/` ne bi bila otkrivena (postojeća allowlist javnog HTML-a).

## Vaše odluke
1. **JWT izuzetak (obavezno).** Preporuka: odobriti CVE-2026-85394 (python-jose 3.5.0) na **90 dana**, samo dok svaki
   `jwt.decode` ima tačno jedan algoritam i produkcioni JWKS ima samo ES256 ključ sa `alg`. Ponovni pregled odmah ako:
   izađe ispravljena verzija, promeni se JWKS, ili se doda nova ruta koja čita JWT. Bez odobrenja: NO-GO.
2. **Spajanje redom:** PR #12 → PR #13 → PR #14 u `release/v2-rc1`, pa RC1 → `main`. Preporuka: da, posle pregleda.
3. **Produkcioni smoke test** (posle deploy-a, jedan vaš test nalog, troši OCR/AI kredite): prijava → nov predmet →
   jedan digitalni i jedan skenirani ćirilični PDF → posle 1–2 min proveriti „Dokazi“ → jedno pitanje → `/health` novi
   SHA → Danas bez „Vindex je pripremio“. Preporuka: odobriti.

## Bezbednost
Bez spajanja, deploy-a, migracija, Cron-a, produkcionih upisa ili brisanja audit istorije. U produkciji samo read-only
čitanje `/health` i javnog JWKS-a.
