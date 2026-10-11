# VCR001 — knjiga zadataka

Program na grani `program/vcr001` (worktree `C:/vindex-vcr001`), počev od `main` = produkcija `6ad0b13a`. Nivoi dokaza:

| Oznaka | Nivo |
|---|---|
| LU | lokalno, unit |
| LI | lokalno, integraciono (stvarne rute, fake baza) |
| BM | pregledač + mock provajder |
| BR | pregledač + pravi backend (fake baza) |
| CI | GitHub Actions / Docker slika |
| LIVE | produkcija |

---

## T00 — osnovica sposobnosti i prava pristupa — `PASS_IMPLEMENTED` (analiza)
- **Izvor zahteva:** direktiva VCR001 T00; `docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md`; A018 (kopija u `docs/product/A018_BOJAN_REQUIREMENTS_REALITY_MATRIX.md`).
- **Početni SHA:** `6ad0b13a`.
- **Fajlovi:**
  - `docs/v2-execution/VINDEX_V2_FOUNDER_EXECUTION_DIRECTION.md`;
  - `VCR001_CAPABILITY_PARITY_MATRIX.md`, `VCR001_REQUIREMENTS_MATRIX.csv`, `VCR001_CHECKPOINT.json`, ovaj fajl;
  - kopija A018.
- **Nalazi (P, statički inventar i kod):**
  1. Osnivač prolazi tarifne provere (`shared/permissions.py`), pa „vidi malo funkcija“ znači **da V2 nema ulaz**, ne da mu je pristup ograničen.
  2. V2 poziva 37 ruta iz 15 modula; stari UI 226.
  3. Bez V2 ulaza su: prijem „problem prvo“, nov predmet iz dokumenta, multi-agent, šabloni, strategija, prediktor, zastarelost, zadaci, ručni unos dokaza i podsetnici.
  4. Istorijski kvar `predmet_klijenti.user_id` u `routers/intake.py` **više ne postoji** (umetanja ne šalju `user_id`).
  5. Miroslavljev izvor zahteva nije pronađen: `REQUIREMENT_SOURCE_UNAVAILABLE`.
- **Van obima:** redizajn navigacije; nadogradnja naloga.
- **Testovi:** nema (analiza).
- **Produkcija:** prijavljeni tok **nije proveren** (nema test naloga).
- **Završni SHA:** v. commit „docs(vcr001): T00 …“.
