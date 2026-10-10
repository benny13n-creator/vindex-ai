# V2 NS007 — While You Sleep / Autonomous Work

> **STACKED ON NS006 PR #9 · DO NOT MERGE TO MAIN DIRECTLY · DO NOT DEPLOY · REQUIRES NS006 MERGE FIRST**
>
> Base: `feature/vindex-v2-ns006-living-matter` (`dac1f6dd`, zamrznut) · Head: `feature/vindex-v2-ns007-while-you-sleep`
> PR nije otvoren automatski (u okruženju nema `gh`) — tekst je spreman za lepljenje, base MORA biti NS006 grana.
> Dokazi po zadatku: `docs/v2-recovery/NS007_OVERNIGHT_EVIDENCE.md` · Raspoređivač: `docs/v2-recovery/NS007_RENDER_CRON_PLAN.md`

## Šta advokat dobija

**„Vindex je radio pre nego što sam mu rekao da radi."** Noću, bez ikakvog zahteva:
- **Priprema za ročište** (stvarno ročište danas/sutra): ročište iz evidencije, ključne činjenice iz spisa sa izvorom,
  protivrečnosti, otvorene radnje, šta nedostaje, AI pitanja i beleške — označeni kao analiza, ne činjenica.
- **Analiza uticaja nove prakse** (samo odluka PROVERENA u bazi odluka): šta odluka potencijalno menja u OVOM predmetu,
  svaki uticaj uz doslovan izvod iz odluke.
- Danas: „Vindex je pripremio" na vrhu; Pregled predmeta: pripremljen rad tog predmeta; pregled sa „Prihvatam / Odbacujem".
- **Ništa ne izlazi napolje bez advokata**: prihvatanje je samo odluka o pregledu (nema mejla, podneska, poruke, izmene
  predmeta, promocije u memoriju znanja).

## Šema (migracija `136_autonomy_work_items.sql` — KREIRANA, NIJE primenjena)

`autonomy_cycles` (atomsko zauzimanje prozora: INSERT + UNIQUE) · `autonomy_work_items` (jedan okidač = jedan red;
QUEUED → RUNNING → READY_FOR_REVIEW → ACCEPTED/REJECTED; FAILED; DEAD_LETTER; SUPERSEDED) ·
`autonomy_claim_work_item()` (zakup + rezervacija budžeta u jednoj transakciji, pod bravom po organizaciji). RLS:
korisnik vidi samo svoje; upis samo server.

## Ugovor ciklusa

`POST /api/cron/autonomy` (posebna tajna `AUTONOMY_CRON_SECRET`, isti 401) → UTC-sat prozor → kanonski radnik
`workers/background_agents.run_autonomy_cycle` (jedan registar modula) → plan (0 poziva modela) → zauzimanje → izvršilac
→ rezultat samo za vlasnika zakupa. `scripts/trigger_autonomy_cycle.py` = jedini okidač (stdlib, bez tajni baze/modela).
Dnevni cron NEPROMENJEN i odvojen.

## Rezultati (sve PROVEN, detalji u dokazima)

| | |
|---|---|
| Atomičnost (pravi PostgreSQL 17) | 20 istovremenih zauzimanja prozora → 1; 20 istog posla → 1 |
| Trošak | budžet 3 od 10 istovremenih → 3; baza budžeta nedostupna → 0; **100 aktivnih predmeta, 2 ročišta, 1 odluka → tačno 3 poziva**; čitanje/pregled/ponavljanje → 0 |
| Zakupci | B ne vidi / ne zaključuje / ne prihvata / ne pokreće ništa od A; podmetnuto ročište/preporuka odbijeni |
| Haos | pad pre/tokom/posle modela; najviše 2 izvršenja pa DEAD_LETTER; gotov rezultat se ne generiše ponovo |
| Izvori | izmišljena odluka nikad; uticaj samo uz doslovan izvod; poslušan prompt-injection izlaz odbačen |
| UI | `live-pripremljeno` 51/51; ceo NG paket zelen (v. dokaze); sudar ID-jeva sa „Pravnim pitanjem" pronađen i ispravljen |
| Mutacije | svaka kapija sa mutacijom koja je ubijena (preživele uz razlog dokumentovane) |

## Poznat dug (za odluku foundera)

Migracija 136 nije primenjena · kadenca raspoređivača nije odlučena · nema roka čuvanja radnih proizvoda · legacy dnevni
cron (ne-atomski heartbeat, fail-open budžet, radar zove model za sve predmete) nije menjan · Docker slika nije građena
(nema Docker-a lokalno) · PG testovi traže `VX_TEST_PG_DSN` (CI ih trenutno preskače) · „danas" = datum servera (UTC).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
