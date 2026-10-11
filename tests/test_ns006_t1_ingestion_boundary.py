"""NS006 Task 1 — granica unosa dokumenata posle nadogradnje pypdf 6.15.0 → 6.19.0.

`uploaded_doc/extractor.py::extract_pdf` poziva `pypdf.PdfReader(...).extract_text()`
nad SVAKIM PDF-om koji korisnik otpremi (Smart Intake radnik i upload). Ranjivosti
6.15.0 (PYSEC-2026-3911/4153/4154/4155/4156: XForm, zaglavlja objekata, ToUnicode,
Widths, FlateDecode) su na tom putu dostižne. 6.19.0 je najmanja verzija koja
zatvara svih 11 nalaza pip-audit-a.

Dokazuje:
  • pin u requirements.txt ne sme pasti ispod 6.19.0 (i instalirana verzija u CI
    mora biti ta);
  • digitalni PDF i PDF sa samo vlasničkom lozinkom se čitaju;
  • šifrovan PDF (korisnička lozinka), smeće sa %PDF zaglavljem i odsečen PDF
    podižu izuzetak — nikad izmišljen tekst;
  • izuzetak iz ekstrakcije Smart Intake radnik beleži kao NEUSPEH posla, nikad
    kao `completed`.
"""
import asyncio
import os
import re
from importlib.metadata import version as _verzija
from pathlib import Path

import pytest

KOREN = Path(__file__).resolve().parent.parent
MIN_PYPDF = (6, 19, 0)

fitz = pytest.importorskip("fitz", reason="PyMuPDF (requirements.txt) pravi test PDF-ove")

TEKST = ("Ugovor o radu zakljucen 15.03.2025. izmedju poslodavca i zaposlenog; "
         "zarada se isplacuje do petog u mesecu za prethodni mesec. ") * 3


def _broj(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def _pin() -> str:
    m = re.search(r"(?m)^pypdf==([0-9.]+)\s*$", (KOREN / "requirements.txt").read_text(encoding="utf-8"))
    assert m, "pypdf mora biti zakucan (==) u requirements.txt"
    return m.group(1)


def _pdf(put: Path, **sifra) -> Path:
    doc = fitz.open()
    strana = doc.new_page()
    for i, deo in enumerate(range(0, len(TEKST), 80)):
        strana.insert_text((72, 72 + 18 * i), TEKST[deo:deo + 80])
    if sifra:
        doc.save(str(put), encryption=fitz.PDF_ENCRYPT_AES_256, **sifra)
    else:
        doc.save(str(put))
    return put


def test_pin_zatvara_poznate_nalaze():
    assert _broj(_pin()) >= MIN_PYPDF, f"pypdf=={_pin()} je ispod {MIN_PYPDF} (11 poznatih PYSEC nalaza)"


def test_instalirana_verzija_odgovara_pinu():
    instalirana = _verzija("pypdf")
    if instalirana != _pin() and not os.environ.get("CI"):
        pytest.skip(f"lokalno okruženje nije sinhronizovano (pypdf {instalirana} ≠ pin {_pin()}); CI mora biti")
    assert instalirana == _pin()


def test_digitalni_pdf_se_cita(tmp_path):
    from uploaded_doc.extractor import extract
    tekst, skeniran, ocr, strane, conf = extract(_pdf(tmp_path / "dig.pdf"))
    assert "15.03.2025" in tekst and skeniran is False and ocr is False and conf is None
    assert strane and len(strane) == 1


def test_samo_vlasnicka_lozinka_se_cita(tmp_path):
    from uploaded_doc.extractor import extract
    tekst, skeniran, *_ = extract(_pdf(tmp_path / "own.pdf", owner_pw="vlasnik", user_pw=""))
    assert "15.03.2025" in tekst and skeniran is False


@pytest.mark.parametrize("vrsta", ["sifrovan", "smece", "odsecen"])
def test_necitljiv_pdf_podize_izuzetak_bez_teksta(tmp_path, vrsta):
    from uploaded_doc.extractor import extract
    if vrsta == "sifrovan":
        put = _pdf(tmp_path / "enc.pdf", user_pw="tajna", owner_pw="vlasnik")
    elif vrsta == "smece":
        put = tmp_path / "smece.pdf"
        put.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 16)
    else:
        izvor = _pdf(tmp_path / "ceo.pdf").read_bytes()
        put = tmp_path / "odsecen.pdf"
        put.write_bytes(izvor[: len(izvor) // 2])
    with pytest.raises(Exception) as exc:
        extract(put)
    assert "15.03.2025" not in str(exc.value)


def test_radnik_belezi_neuspeh_a_ne_uspeh(tmp_path, monkeypatch):
    from shared import intake_queue
    from shared.intake_worker import IntakeWorker
    sifrovan = _pdf(tmp_path / "enc.pdf", user_pw="tajna", owner_pw="vlasnik")
    zapis = []

    async def _claim(*_a, **_k):
        return {"id": "posao-1", "attempts": 0, "max_attempts": 5}

    async def _belezi(ime, *a, **_k):
        zapis.append(ime)

    monkeypatch.setattr(intake_queue, "claim_next_job", _claim)
    monkeypatch.setattr(intake_queue, "record_heartbeat", lambda *a, **k: _belezi("heartbeat"))
    monkeypatch.setattr(intake_queue, "mark_job_failed", lambda *a, **k: _belezi("failed"))
    monkeypatch.setattr(intake_queue, "mark_job_completed", lambda *a, **k: _belezi("completed"))
    monkeypatch.setattr(intake_queue, "mark_job_awaiting_review", lambda *a, **k: _belezi("awaiting_review"))
    radnik = IntakeWorker()

    async def _process(job):
        IntakeWorker._extract_text(sifrovan)   # stvarni extractor nad stvarnim šifrovanim PDF-om
        return False

    monkeypatch.setattr(radnik, "_process", _process)
    radnik.reap_every_n_ticks = 10 ** 9
    assert asyncio.run(radnik._tick()) is True
    assert "failed" in zapis and "completed" not in zapis and "awaiting_review" not in zapis
