# Mission Report — Program Omega, Final Sprint 006: Canonical Attention Engine

**Datum**: 2026-08-06
**Program**: Omega (šesti sprint)
**Tim**: Lead Product Architect, Data Consistency Engineer, End-to-End Validation Engineer (sve 3 uloge
izvedene direktno u ovoj sesiji).

---

## Zatvorenje misije

Platforma nije smela imati više odgovora na pitanje "šta zahteva pažnju advokata." Cilj: TAČNO JEDAN
kanonski sistem koji određuje Critical/High/Medium/Low/Completed. Isključivo kanonizovati postojeće —
bez novog algoritma, bez nove AI logike, bez novih funkcija.

## Otkriveno

1. **13 nezavisnih vokabulara prioriteta, ne "8-9" kako je `OMEGA-018` procenio.** Repo-wide forenzička
   provera (fork + direktno čitanje) pronašla je 3 potpuno nove: `notifications.py`-ov sopstveni
   row-level `"prioritet"` sa DVA polja koja se ne slažu (stvaran bag, vidi ispod), `api.py::
   predmet_workspace`-ov `_VAZNOST_ORDER`, i `api.py`-ov potpuno nezavisan, mrtav `GET
   /api/notifications` sa sopstvenim 9. vokabularom.
2. **4., ranije nikad katalogizovan alert sistem**: `GET /api/notifications` (`api.py`) — "Computed
   notifications — bez novog DB table-a," potvrđeno NULA frontend poziva (grep celog
   `static/vindex.js`). Potpuno mrtav, bezbedan za brisanje.
3. **Stvaran, ranije nepoznat bag u `routers/notifications.py`**: `_generate_notifications`-ova 2 sopstvena
   mesta pisala su `"prioritet": "hitan"/"normalan"` — vrednosti koje NISU članovi `PRIORITY_ORDER`-ovog
   sopstvenog rečnika (`"urgent"/"high"/"normal"/"low"/"info"`). Pošto je `_grupiraj_notifikacije`-ov
   sort ključ `n.get("prioritet") or NOTIF_TIPOVI...` — pogrešna ali istinita (`"hitan"`) vrednost je
   UVEK pobeđivala nad ispravnim fallback-om. Rezultat: svaka `hitan_rok` notifikacija je tiho sortirana
   kao da je "normal" prioritet (`PRIORITY_ORDER.get("hitan", 2) == 2`, isti rang kao "normal") — NIKAD
   se stvarno nije pojavljivala iznad običnih rokova u zvoncetu obaveštenja. Pronađeno direktno kao
   posledica GRADNJE kanonskog prevodnog sloja — neslaganje je postalo nemoguće ne primetiti tek kad su
   svi rečnici morali biti zapisani na jednom mestu da bi se preveli.
4. **Naziv-kolizija, ne funkcionalna duplikacija**: `GET /api/predmeti/{id}/workspace` (per-CASE agregacija,
   backend Cockpit panela) postoji odavno i genuinski je drugačijeg obima od novog, portfolio-širokog `GET
   /api/workspace` (Sprint 004/005) — potvrđeno čitanjem oba, nije duplikat, samo zbunjujuće ime.
5. **Rok-hitnost pragovi se i dalje razlikuju** između sistema (≤2 dana vs ≤3 dana za "kritično") —
   potvrđeno, ne pomireno (stvarna proizvodna odluka, ne sinonim reči).

## Popravljeno

1. **`shared/attention_priority.py`** (NOVO) — JEDAN kanonski model: `critical/high/medium/low/
   informational` (usvojen iz `case_actions.prioritet`-ovog sopstvenog, već-postojećeg, DB-ograničenog
   rečnika — ne izmišljen). Prevodni rečnici za svih 5 mehanički-bezbednih izvora
   (`ZADACI_TO_CANONICAL`, `OZBILJNOST_TO_CANONICAL`, `NOTIFICATIONS_TO_CANONICAL`, `INBOX_TO_CANONICAL`,
   `VAZNOST_TO_CANONICAL`), plus dokumentovane-ali-namerno-nepomerene kategorije (GPT-savetodavno, rizik
   nivo, Genome delta hitnost).
2. **5 potrošača prebačeno na kanonski model**, svaki dokazano bajt-identičan svojoj staroj vrednosti:
   `routers/case_actions.py::_PRIORITY_ORDER`, `routers/workspace.py::_ZADACI_PRIORITET_MAP`,
   `routers/inbox.py::_PRIORITET_ORDER`, `routers/notifications.py::PRIORITY_ORDER`,
   `api.py::predmet_workspace`-ov `_VAZNOST_ORDER`.
3. **Stvaran bag popravljen**: `routers/notifications.py`-ova 2 mesta sada izvode `prioritet` iz
   `NOTIF_TIPOVI[tip]["priority"]` — JEDAN izvor istine (`tip`), ne drugačije-otkucana vrednost.
4. **Uklonjen ceo `api.py::GET /api/notifications`** (~110 linija) — potvrđeno mrtav, bezbedno obrisan,
   ne samo odjavljen.
5. **Popravljen pre-postojeći formatting bag** u samom `ARCHITECTURAL_DEBT_REGISTER.md` (siroče "Severity"
   pasus vraćen na svoje mesto ispod `OMEGA-013`) — pronađeno usput dok se dodavao novi sadržaj.

## Dokazano

**20 novih testova** (`tests/test_omega_sprint006_canonical_attention.py`) — kanonski model sam po sebi
(vrednosti, redosled, boje, labele, prevod, fallback), svih 5 potrošača dokazano bajt-identičnih svojoj
pred-Sprint-006 vrednosti, uklonjena ruta stvarno odjavljena, PRAVI bag dokazano popravljen (2 dedikovana
testa: `hitan_rok` sada dobija `"high"` ne pokvareno `"hitan"`, i `_grupiraj_notifikacije` sada sortira
`hitan_rok` PRE običnog `rok`-a), plus unakrsna dosluednost (case_actions "critical" i notifications
"urgent" rangiraju IDENTIČNO, za sve rečnike odjednom, ne samo pojedinačno proverene).

**Regresija**: 0 — potvrđeno direktno, ne samo brojem. Puna test suita: **2.705 passed, 1 skipped, 0
failed** (bilo 2.688 na kraju Sprinta 5).

## Faza 7 — Forenzička sertifikacija

- **Drugi priority model?** DA, delimično — 6 GPT-savetodavnih/drugačiji-koncept vokabulara i dalje
  postoje (rizik nivo, Genome delta hitnost, Genome nedostaje.hitnost, CIO kriticnost, strategija.py
  prompt) — namerno NISU spojeni (misija zabranjuje novu AI logiku; ovi mere drugačiju stvar). Imenovano,
  ne prećutano.
- **Drugi alert engine?** DA — `proactive_alerts` i `notifications` i dalje postoje kao 2 genuinski
  drugačije funkcije (interno vs. korisničko), plus `case_actions` kao izvor. 4. (mrtav) sistem uklonjen.
  Sistemi se i dalje NEZAVISNO PIŠU za istu činjenicu (`OMEGA-020`) — nije rešeno, precizno imenovano.
- **Drugi urgency calculator?** DA — pragovi hitnosti (≤2 vs ≤3 dana) i dalje se razlikuju (`OMEGA-021`).
- **Drugi deadline calculator?** Isto kao gore.
- **Drugi notification source?** DA — `proactive_alerts`/`notifications` i dalje nezavisno upituju
  `rocista`/`predmet_hronologija`, ne čitaju iz `case_actions`.

**Zaključak Faze 7**: sprint NIJE u potpunosti završen po strogom čitanju misijinog sopstvenog pravila
("ako postoji makar jedan drugi izvor, sprint nije završen") — i to je NAMERNO iskreno rečeno, ne
sakriveno. Ono što JESTE potpuno završeno: JEDAN kanonski REČNIK i JEDAN kanonski REDOSLED postoje i
dokazano ih koristi (direktno ili prevodom) svaki mehanički-bezbedan potrošač pronađen u repou. Ono što
NIJE: jedinstvena WRITE putanja za dogadjaje koje 3 sistema i dalje nezavisno detektuju.

## Odloženo

1. **`OMEGA-020`** — do 3 nezavisna upisa za istu činjenicu roka; redizajn write-putanje van bezbednog
   obima ovog sprinta.
2. **`OMEGA-021`** — pragovi hitnosti (≤2 vs ≤3 dana) i dalje se razlikuju; potrebna osnivačeva odluka.
3. **`OMEGA-022`** — naziv-kolizija `predmet_workspace` vs `/api/workspace`; samo imenovanje, nula
   funkcionalnog rizika.

## Zaključak

Definition of Done, stavka po stavka: (1) postoji jedan jedini Attention Engine za DETERMINISTIČKI domen
— **da**, `case_actions`/`shared/attention_priority.py`; (2) postoji jedan jedini Priority model — **da**,
za rečnik/redosled; NE za GPT-savetodavne izvore (namerno); (3) ne postoje shadow alert sistemi — 1 od 4
uklonjen, 3 preostala imenovana i objašnjena (2 legitimna, 1 sa dokazanim i popravljenim internim bagom);
(4) nijedan ekran ne računa sopstveni prioritet — **da**, za svih 5 mehaničkih potrošača pronađenih; (5)
Workspace/Dashboard/Notification koriste isti izvor istine — **delimično**: isti REČNIK, ne isti WRITE
put (`OMEGA-020`, imenovano); (6) svi bezbedno-popravljivi problemi popravljeni odmah — **da**, uključujući
2 bug-a pronađena usput (notifications.py-ov pravi bag, debt register-ov sopstveni formatting bag), oba
sa punom regresijom.

Ovaj sprint ne tvrdi lažnu potpunu pobedu. Šesti i poslednji Program Omega sprint zatvara ono što je
sistemski bezbedno zatvoriti — jedan rečnik, jedan redosled, jedan mrtav sistem manje, jedan stvaran bag
manje — i imenuje, precizno i bez izgovora, tačno ono što ostaje: da 3 sistema i dalje nezavisno PIŠU za
istu činjenicu, čak i kad se sada slažu KAKO da je opišu.
