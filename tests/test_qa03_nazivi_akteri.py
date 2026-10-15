# -*- coding: utf-8 -*-
"""QA-03 (PR #36) — svaki backend potpis `predmet_hronologija.akter` poređen sa rečnikom prikaza
(`frontend-v2-ng/src/nazivi.js::AKTERI`), umesto oslanjanja na broj mapiranja iz izveštaja.

Pravila semantike izvora (beta QA ugovor):
  * interni naziv procesa (engleski / „(AI)“) ne sme da stigne do advokata neprevedeno → mora biti u rečniku;
  * naziv ne sme da tvrdi potvrdu advokata (stanje odluke ide iz lanca odluka, ne iz imena aktera);
  * AI proizvođač ostaje vidljiv kao AI; statički šablon se NE naziva AI-jem;
  * ljudski/sudski akter (srpski tekst) ostaje doslovno — rečnik ga ne sme preslikati.
"""
import re
from pathlib import Path

KOREN = Path(__file__).resolve().parents[1]
NAZIVI = (KOREN / "frontend-v2-ng" / "src" / "nazivi.js").read_text(encoding="utf-8")


def _akteri_recnika() -> dict:
    blok = re.search(r"var AKTERI = \{(.*?)\n  \};", NAZIVI, re.S).group(1)
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', blok))


def _backend_potpisi() -> dict:
    """{doslovan potpis: [fajl:linija]} za svaki `"akter": "<literal>"` / f-string prefiks u backend kodu."""
    nadjeno: dict = {}
    for p in [KOREN / "api.py", *sorted((KOREN / "routers").glob("*.py")), *sorted((KOREN / "services").glob("*.py")),
              *sorted((KOREN / "shared").glob("*.py"))]:
        for i, red in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if red.lstrip().startswith("#"):
                continue
            m = re.search(r'["\']akter["\']\s*:\s*f?"([^"{]+)', red) or re.search(r'hron_akter\s*=\s*"([^"]+)"', red)
            if m:
                nadjeno.setdefault(m.group(1).strip(), []).append(f"{p.relative_to(KOREN)}:{i}")
    return nadjeno


INTERNI = re.compile(r"\(AI\)|Engine|Intake|Pipeline|Template|Copilot|Genome|Auto-detect|Wizard")
# Potpisi koji su već srpski i ljudski čitljivi — prikazuju se doslovno (api.py:5667 je opis polja u promptu, ne akter).
SRPSKI_DOSLOVNO = {"Advokat", "Advokat (ručno zatvaranje)", "Automatski — ZPP lanac |", "Demo predmet",
                   "Ko je preduzeo radnju (osoba, firma, sud...)"}


def test_svaki_interni_potpis_ima_srpski_naziv():
    recnik = _akteri_recnika()
    potpisi = _backend_potpisi()
    assert len(potpisi) >= 12, potpisi
    nepokriveni = {k: v for k, v in potpisi.items() if INTERNI.search(k) and k not in recnik}
    assert not nepokriveni, f"interni naziv procesa bez srpskog naziva: {nepokriveni}"
    nepoznati = {k: v for k, v in potpisi.items() if not INTERNI.search(k) and k not in SRPSKI_DOSLOVNO}
    assert not nepoznati, f"nov potpis aktera — odlučiti: prevod u nazivi.js ili doslovno: {nepoznati}"


def test_recnik_nema_mrtvih_ni_izmisljenih_potpisa():
    """Svaki ključ rečnika je stvaran backend potpis (inače bi rečnik prevodio nešto što niko ne upisuje)."""
    potpisi = _backend_potpisi()
    assert set(_akteri_recnika()) <= set(potpisi), set(_akteri_recnika()) - set(potpisi)


def test_nijedan_naziv_ne_tvrdi_potvrdu():
    for k, v in _akteri_recnika().items():
        assert not re.search(r"potvr|odobr|overi", v, re.I), (k, v)


def test_ai_poreklo_ostaje_vidljivo_a_sablon_nije_ai():
    recnik = _akteri_recnika()
    for k, v in recnik.items():
        ai = "(AI)" in k and not k.startswith("Template") or k == "Smart Intake"
        if ai:
            assert "AI" in v, (k, v)
        if k.startswith("Template") or "šablon" in k:
            assert "AI" not in v and "Šablon" in v, (k, v)
        if k in ("Case Evolution Engine", "Learning Engine"):
            assert v.startswith("Sistem"), (k, v)


def test_ljudski_akter_nije_u_recniku():
    recnik = _akteri_recnika()
    for k in SRPSKI_DOSLOVNO:
        assert k.strip() not in recnik


def _vrste_predmeta() -> dict:
    blok = re.search(r"var VRSTE_PREDMETA = \{(.*?)\n  \};", NAZIVI, re.S).group(1)
    return {k.strip(): v for k, v in re.findall(r'"?([a-z][a-z_ ]*)"?:\s*"([^"]+)"', blok)}


def test_vrsta_predmeta_iz_v2_unosa_vraca_isti_naziv_koji_je_advokat_izabrao():
    """nov-predmet.js::KLJUC (naziv → šifra) i nazivi.js::VRSTE_PREDMETA (šifra → naziv) su dve strane istog ugovora:
    šifra mora da se prikaže kao izabran naziv (veliko početno slovo), inače bi „radni_spor“ mogao postati „Krivični“."""
    src = (KOREN / "frontend-v2-ng" / "src" / "nov-predmet.js").read_text(encoding="utf-8")
    kljuc = dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', re.search(r"var KLJUC = \{(.*?)\};", src, re.S).group(1)))
    vrste = _vrste_predmeta()
    assert len(kljuc) >= 14
    for naziv, sifra in kljuc.items():
        if sifra[:1].isupper():          # „Parnica“: čuva se sam naziv, prikazuje se doslovno
            continue
        assert vrste.get(sifra) == naziv[:1].upper() + naziv[1:], (naziv, sifra, vrste.get(sifra))


def test_programske_sifre_vrste_predmeta_imaju_naziv():
    """Šifre koje backend upisuje u `predmeti.tip` kao literal: Smart Intake (`opsti`), šabloni prijema
    (`gradjansko`, `izvrsenje`), uvoz (`clio_import`). Svaka postoji u kodu i ima srpski naziv."""
    vrste = _vrste_predmeta()
    izvori = {"opsti": "smart_intake.py", "gradjansko": "intake.py", "izvrsenje": "intake.py", "clio_import": "integracije.py"}
    for sifra, fajl in izvori.items():
        assert f'"tip":     "{sifra}"' in (KOREN / "routers" / fajl).read_text(encoding="utf-8") or             f'"tip":   "{sifra}"' in (KOREN / "routers" / fajl).read_text(encoding="utf-8"), (fajl, sifra)
        assert sifra in vrste, sifra
