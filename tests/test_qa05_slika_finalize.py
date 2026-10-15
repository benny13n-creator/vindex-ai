# -*- coding: utf-8 -*-
"""QA-05 — fotografija (JPG/JPEG/PNG) kroz Smart Intake: OCR prolazi, a prikačivanje predmetu je padalo (0/1).

Produkcija (beta QA, `05_POTVRDA_dopunska_isporuka_FOTO.jpg`): finalize dva puta 0/1 povezanih dokumenata, log
`1 validation error for UploadedDocChunk`. Uzrok: `uploaded_doc/schema.py::UploadedDocChunk.source_format` je bio
`Literal["pdf", "docx", "txt"]`, a Smart Intake (i `api.py` otpremanje u predmet) prosleđuju ekstenziju fajla
(`suffix.lstrip(".")`) — za fotografiju `jpg`/`jpeg`/`png`. `chunk_document` je pucao na validaciji, greška je
uhvaćena po dokumentu (`razlog: greska`), posao je ostao `predmet_id` postavljen, `assimilation_complete=false`.

STVARNO: rute `routers/smart_intake.py`, intake worker, `extract_image` (provera potpisa, Pillow, JPEG zaštite),
`chunk_document` i `UploadedDocChunk`. ZAMENJENO: Supabase (tests/ns005_harness), model i Pinecone (fixture `ok`);
lokalno i Tesseract — na granici `extractor._ocr_image`, kao u tests/test_ocr001_ocr_korpus.py. Sloj sa stvarnim
Tesseract-om je `test_stvaran_ocr_*` (CI: produkciona slika).
"""
import io

import pytest
from pydantic import ValidationError

from tests import ns005_harness as _h
from tests.ns005_harness import zaglavlje
from tests.test_ns005_t14_smart_intake import _OCR, PA, PB, _obradi, _otpremi, ok  # noqa: F401 — `ok` je fixture
from tests.test_vcr002_t02_ocr_korpus import _dokumenti, _job, _prikaci

# Izmišljen sadržaj sintetičke potvrde (ćirilica, kao produkcioni fajl 05).
POTVRDA = [
    "ПОТВРДА О ДОПУНСКОЈ ИСПОРУЦИ",
    "Испоручилац: ТЕСТ АЛФА ДОО",
    "Прималац: ТЕСТ БЕТА ДОО",
    "Дана 24.08.2026. испоручено је 3 (три) монитора.",
    "Примио: Петар Измишљени",
]
POTVRDA_TEKST = "\n".join(POTVRDA)
# Latinica za stvaran Tesseract u CI-ju (produkciona slika nema srpski paket — v. production-runtime.yml).
POTVRDA_LAT = [
    "POTVRDA O DOPUNSKOJ ISPORUCI",
    "Isporucilac: TEST ALFA DOO",
    "Primalac: TEST BETA DOO",
    "Dana 24.08.2026. isporuceno je 3 monitora.",
]
MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — sloj sa stvarnim OCR-om preskočen")


def _foto(fmt, redovi=POTVRDA_LAT):
    """Fotografija strane sa tekstom (rasterizovano, bez tekstualnog sloja) u stvarnom JPEG/PNG formatu."""
    import fitz
    from PIL import Image
    doc = fitz.open()
    strana = doc.new_page(width=595, height=842)
    tw = fitz.TextWriter(strana.rect)
    for i, red in enumerate(redovi):
        tw.append((50, 80 + i * 34), red, font=fitz.Font("helv"), fontsize=20)
    tw.write_text(strana)
    png = strana.get_pixmap(dpi=200).tobytes("png")
    doc.close()
    if fmt == "png":
        return png
    b = io.BytesIO()
    with Image.open(io.BytesIO(png)) as img:
        img.convert("RGB").save(b, format="JPEG", quality=90)
    return b.getvalue()


@pytest.fixture
def ocr(monkeypatch):
    """OCR fotografije vraća sintetičku potvrdu (lokalno nema Tesseract-a); sve ostalo u `extract_image` je stvarno."""
    import uploaded_doc.extractor as ex
    pozivi = []
    monkeypatch.setattr(ex, "_ocr_image", lambda img, jezik: pozivi.append(img.size) or (POTVRDA_TEKST, 0.91))
    monkeypatch.setattr(ex, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")
    return pozivi


@pytest.fixture
def audit(monkeypatch):
    """Beleži poslovne audit radnje (harness ih inače guta — `ns005_harness` zamenjuje `log_action` praznom)."""
    import shared.audit_immutable as a
    radnje = []

    async def _log(action, *args, **kw):
        radnje.append(action)
    monkeypatch.setattr(a, "log_action", _log)
    return radnje


def _stara_sema(monkeypatch):
    """Model pre ispravke (produkcija `3ab9343e`): samo pdf/docx/txt. Zamena u `chunker`-u, koji ga instancira."""
    from typing import Literal

    import uploaded_doc.chunker as ch
    from uploaded_doc.schema import UploadedDocChunk

    class StariUploadedDocChunk(UploadedDocChunk):
        source_format: Literal["pdf", "docx", "txt"]
    monkeypatch.setattr(ch, "UploadedDocChunk", StariUploadedDocChunk)


def _spreman_foto(k, fmt="jpg", korisnik="A", ime=None):
    ime = ime or f"05_POTVRDA_dopunska_isporuka_FOTO.{fmt}"
    jid = _job(_otpremi(k, korisnik, _foto(fmt), ime=ime, tip=MIME[fmt]))
    assert _obradi() is True
    s = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje(korisnik)).json()["job"]
    assert s["status"] in ("awaiting_review", "completed"), s
    return jid


def _posao(b, jid):
    return next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)


def _stanje(k, jid, korisnik="A"):
    return k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje(korisnik)).json()["job"]


def _snimak(b):
    return {t: len(b.tabele.get(t, [])) for t in ("predmeti", "predmet_dokumenti", "events", "intake_jobs",
                                                   "predmet_hronologija")} | {"vektori": len(b.vektori)}


# ── Model: tačno skup formata koji upload putevi zaista prosleđuju ────────────────────────────────────────────────

@pytest.mark.parametrize("fmt", ["jpg", "jpeg", "png"])
def test_chunk_document_prihvata_format_fotografije(fmt):
    from uploaded_doc.chunker import chunk_document
    m = chunk_document(POTVRDA_TEKST, {"source_filename": f"f.{fmt}", "source_format": fmt,
                                       "source_sha256": "a" * 64, "is_scanned": True, "session_id": "__local__"})
    assert m.total_chunks >= 1 and all(c.source_format == fmt for c in m.chunks)
    assert "24.08.2026" in " ".join(c.text for c in m.chunks)


@pytest.mark.parametrize("fmt", ["jpg", "png"])
def test_stara_sema_reprodukuje_produkcionu_gresku(monkeypatch, fmt):
    _stara_sema(monkeypatch)
    from uploaded_doc.chunker import chunk_document
    with pytest.raises(ValidationError, match="1 validation error for StariUploadedDocChunk"):
        chunk_document(POTVRDA_TEKST, {"source_filename": "f", "source_format": fmt, "source_sha256": "a" * 64,
                                       "is_scanned": True, "session_id": "__local__"})


@pytest.mark.parametrize("fmt", ["pdf", "docx", "txt"])
def test_postojeci_formati_daju_isti_manifest_kao_pre_izmene(monkeypatch, fmt):
    from uploaded_doc import chunker as ch
    tekst = "Član 1.\nUgovorne strane su TEST ALFA DOO i TEST BETA DOO.\n\nČlan 2.\n" + "Isporuka monitora. " * 400
    meta = {"source_filename": f"f.{fmt}", "source_format": fmt, "source_sha256": "b" * 64, "is_scanned": False,
            "session_id": "__local__"}

    def _bez_vremena(m):
        d = m.model_dump()
        for c in d["chunks"]:
            c.pop("created_at")
            c.pop("chunk_id")                      # uuid4 po pozivu, nije sadržaj
        return d
    novo = _bez_vremena(ch.chunk_document(tekst, meta))
    _stara_sema(monkeypatch)
    staro = _bez_vremena(ch.chunk_document(tekst, meta))
    assert novo == staro and novo["total_chunks"] > 1


@pytest.mark.parametrize("fmt", ["tiff", "tif", "gif", "bmp", "webp", "doc", "exe", "JPG", "", "jpg "])
def test_model_i_dalje_odbija_sve_ostalo(fmt):
    from datetime import datetime, timezone

    from uploaded_doc.schema import UploadedDocChunk
    with pytest.raises(ValidationError):
        UploadedDocChunk(chunk_id="c", session_id="s", source_filename="f", source_format=fmt, source_sha256="a",
                         chunk_index=0, chunk_mode="recursive", article_label=None, text="t", token_count=1,
                         char_count=1, created_at=datetime.now(timezone.utc))


def test_skup_formata_modela_pokriva_svaki_format_koji_ekstraktor_cita():
    """Svaka ekstenzija za koju `extract()` vraća tekst (pa stiže do `chunk_document`) mora proći model — i ništa
    više. `.doc` je u `api.py` listi otpremanja, ali `extract()` ga odbija (ValueError) pre chunk-a."""
    import typing

    from uploaded_doc.extractor import IMAGE_SUFFIXES
    from uploaded_doc.schema import UploadedDocChunk
    citljivo = {"pdf", "docx", "txt"} | {s.lstrip(".") for s in IMAGE_SUFFIXES}
    assert set(typing.get_args(UploadedDocChunk.model_fields["source_format"].annotation)) == citljivo


# ── E2E: upload → OCR → pregled → finalize → predmet_dokumenti ───────────────────────────────────────────────────

@pytest.mark.parametrize("fmt", ["jpg", "jpeg", "png"])
def test_fotografija_kompletno_prikacena_tacno_jedan_dokument(ok, ocr, fmt):
    k, b = ok
    jid = _spreman_foto(k, fmt)
    assert ocr, "OCR fotografije mora stvarno da se pozove"
    assert _stanje(k, jid)["status"] == "awaiting_review"            # OCR → pregled advokata
    f = _prikaci(k, jid)
    assert f.status_code == 200, f.text
    x = f.json()
    assert x["ok"] is True and x["prikacivanje"] == "POTPUNO" and x["dokumenata_povezano"] == 1, x
    [d] = _dokumenti(b)
    from shared.vector_identity import verzija_dokumenta
    assert d["source_intake_job_id"] == jid and d["user_id"] == "uid-A" and d["predmet_id"] == PA
    assert d["naziv_fajla"] == f"05_POTVRDA_dopunska_isporuka_FOTO.{fmt}"
    assert d["content_sha256"] == verzija_dokumenta(POTVRDA_TEKST)
    assert "24.08.2026" in d["tekst_sadrzaj"] and "ТЕСТ БЕТА ДОО" in d["tekst_sadrzaj"]
    assert d["status"] == "indeksirano"
    p = _posao(b, jid)
    assert p["predmet_id"] == PA and p["assimilation_complete"] is True   # trajni znak „prikačeno“ (095)
    assert _stanje(k, jid)["prikacivanje"] == "PRIKACENO"
    assert [v["predmet_id"] for v in b.vektori] == [PA]


def test_pre_ispravke_produkcioni_ishod_0_od_1_pa_nastavak_bez_ponovnog_otpremanja(ok, ocr, monkeypatch):
    """Reprodukcija produkcionog stanja i njegov oporavak posle ispravke, bez novog upload-a i bez drugog posla."""
    k, b = ok
    jid = _spreman_foto(k, "jpg")
    with monkeypatch.context() as m:
        _stara_sema(m)
        for _ in range(2):                                         # u produkciji: dva pokušaja, oba 0/1
            f = _prikaci(k, jid)
            assert f.status_code == 200, f.text
            x = f.json()
            assert x["ok"] is False and x["prikacivanje"] == "NIJE_PRIKACENO" and x["dokumenata_povezano"] == 0, x
            assert [r.get("razlog") for r in x.get("dokumenti", [])] in ([], ["greska"]), x
    p = _posao(b, jid)
    # Tačno produkciono stanje: completed, predmet zapamćen, nije asimilovan, bez zauzeća, nula dokumenata.
    assert p["status"] == "completed" and p["predmet_id"] == PA and p["assimilation_complete"] is False
    assert p["finalizing_at"] is None and _dokumenti(b) == [] and b.vektori == []
    assert _stanje(k, jid)["prikacivanje"] == "NEPOTPUNO"
    pre = _snimak(b)

    f = _prikaci(k, jid)                                           # ispravka aktivna; isti posao, isti fajl
    assert f.status_code == 200, f.text
    assert f.json()["prikacivanje"] == "POTPUNO" and f.json()["predmet_id"] == PA
    posle = _snimak(b)
    assert posle["intake_jobs"] == pre["intake_jobs"] and posle["predmeti"] == pre["predmeti"]
    assert posle["predmet_dokumenti"] == 1 and len(_dokumenti(b)) == 1 and posle["vektori"] == 1
    assert _dokumenti(b)[0]["source_intake_job_id"] == jid


def test_ponovljen_finalize_posle_uspeha_ne_pravi_nista_novo(ok, ocr, audit):
    k, b = ok
    jid = _spreman_foto(k, "jpg")
    assert _prikaci(k, jid).json()["prikacivanje"] == "POTPUNO"
    assert audit.count("document_assimilated") == 1, audit
    pre, audit_pre = _snimak(b), list(audit)
    dog_pre = sorted(str(e.get("event_type")) for e in b.tabele["events"])
    for _ in range(2):
        f = _prikaci(k, jid)
        assert f.status_code == 200 and f.json()["already_finalized"] is True, f.text
        assert f.json()["prikacivanje"] == "POTPUNO" and f.json()["dokumenata_povezano"] == 1
    assert _snimak(b) == pre
    assert audit == audit_pre, "ponovljen finalize je upisao novu audit radnju"
    assert sorted(str(e.get("event_type")) for e in b.tabele["events"]) == dog_pre


def test_greska_baze_pri_upisu_fotografije_nije_uspeh_i_ponovni_pokusaj_prolazi(ok, ocr, monkeypatch):
    k, b = ok
    jid = _spreman_foto(k, "png")
    orig = _h._Upit.execute

    def execute(self):
        if self.t == "predmet_dokumenti" and self.radnja[0] == "insert":
            raise Exception('{"code": "57014", "message": "canceling statement due to statement timeout"}')
        return orig(self)
    monkeypatch.setattr(_h._Upit, "execute", execute)
    f = _prikaci(k, jid)
    monkeypatch.setattr(_h._Upit, "execute", orig)
    assert f.status_code == 200 and f.json()["ok"] is False and f.json()["prikacivanje"] == "NIJE_PRIKACENO", f.text
    assert _dokumenti(b) == [] and _stanje(k, jid)["prikacivanje"] != "PRIKACENO"
    f2 = _prikaci(k, jid)
    assert f2.json()["prikacivanje"] == "POTPUNO" and len(_dokumenti(b)) == 1, f2.text


def test_nepotpun_vektorski_upis_ne_nosi_status_indeksirano(ok, ocr, monkeypatch):
    k, b = ok
    import uploaded_doc.ingest as ing

    def _nepotpun(manifest, session_id, namespace_override=None, **kw):
        b.vektori.append({"namespace": namespace_override, "predmet_id": (kw.get("extra_metadata") or {}).get("predmet_id")})
        return manifest.total_chunks - 1
    monkeypatch.setattr(ing, "ingest_session", _nepotpun)
    jid = _spreman_foto(k, "jpg")
    f = _prikaci(k, jid)
    assert f.status_code == 200, f.text
    [d] = _dokumenti(b)
    assert d["status"] == "sacuvano"                    # sačuvan u predmetu, ali NE prijavljen kao pretraživ


def test_vektorski_upis_pukne_dokument_sacuvan_bez_statusa_indeksirano(ok, ocr, monkeypatch):
    k, b = ok
    import uploaded_doc.ingest as ing

    def _pukne(*a, **kw):
        raise RuntimeError("pinecone nedostupan")
    monkeypatch.setattr(ing, "ingest_session", _pukne)
    jid = _spreman_foto(k, "jpg")
    assert _prikaci(k, jid).status_code == 200
    [d] = _dokumenti(b)
    assert d["status"] == "sacuvano"


def test_isti_sadrzaj_u_drugom_predmetu_se_ne_povezuje_automatski(ok, ocr):
    k, b = ok
    b.tabele["predmeti"].append({"id": "pred-A-2", "user_id": "uid-A", "naziv": "Drugi predmet", "status": "aktivan"})
    j1 = _spreman_foto(k, "jpg")
    assert _prikaci(k, j1).json()["prikacivanje"] == "POTPUNO"
    j2 = _spreman_foto(k, "png", ime="ista_potvrda_druga_fotografija.png")   # drugi fajl, isti pročitan tekst
    f = _prikaci(k, j2, predmet="pred-A-2")
    assert f.status_code == 200, f.text
    x = f.json()
    assert x["ok"] is False and x["prikacivanje"] == "NIJE_PRIKACENO", x
    assert _dokumenti(b, "pred-A-2") == [] and len(_dokumenti(b)) == 1


def test_dva_korisnika_ista_fotografija_svako_u_svom_predmetu_i_namespace_u(ok, ocr):
    k, b = ok
    ja = _spreman_foto(k, "jpg", korisnik="A")
    jb = _spreman_foto(k, "jpg", korisnik="B")
    assert ja != jb
    assert _prikaci(k, ja).json()["prikacivanje"] == "POTPUNO"
    fb = _prikaci(k, jb, predmet=PB, korisnik="B")
    assert fb.status_code == 200 and fb.json()["prikacivanje"] == "POTPUNO", fb.text
    [da], [db] = _dokumenti(b), _dokumenti(b, PB)
    assert (da["user_id"], db["user_id"]) == ("uid-A", "uid-B")
    assert da["pinecone_namespace"] != db["pinecone_namespace"]
    assert {(v["namespace"], v["predmet_id"]) for v in b.vektori} == {(da["pinecone_namespace"], PA),
                                                                       (db["pinecone_namespace"], PB)}
    # B ne može da prikači A-ov posao ni u svoj predmet
    tudj = k.post(f"/api/smart-intake/jobs/{ja}/finalize", json={"predmet_id": PB}, headers=zaglavlje("B"))
    assert tudj.status_code == 404 and len(_dokumenti(b, PB)) == 1


def test_paralelni_finalize_iste_fotografije_jedan_dokument(ok, ocr, monkeypatch):
    from tests.test_ocr001_konkurentna_finalizacija import INDEKSI_PRODUKCIJA, _invarijante, _merenje, _trka, _ukljuci
    k, b = ok
    jid = _spreman_foto(k, "jpg")
    assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje("A")).status_code == 200
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    pre = len(b.tabele["predmeti"])
    rez = _trka(o, sat, jid, {"predmet_id": PA}, "B_prvi")
    m = _merenje(b, jid, rez, pre)
    assert m["predmeta_novih"] == 0 and m["predmet_id"] == PA, m
    _invarijante(m, b, jid, k, {"predmet_id": PA})


@pytest.mark.parametrize("ime,sadrzaj,tip", [
    ("05_POTVRDA.jpg", b"II*\x00" + b"\x00" * 64, "image/jpeg"),       # TIFF potpis, preimenovan u .jpg
    ("05_POTVRDA.png", b"\x00\x01lazni png" * 8, "image/png"),          # lažni PNG
    ("05_POTVRDA.gif", b"GIF89a" + b"\x00" * 64, "image/gif"),
])
def test_nepodrzana_slika_odbijena_bez_posla_i_bez_dokumenta(ok, ime, sadrzaj, tip):
    k, b = ok
    r = _otpremi(k, "A", sadrzaj, ime=ime, tip=tip)
    assert r.status_code in (202, 400, 415, 422), r.text
    if r.status_code == 202:
        assert r.json()["rezultati"][0]["ok"] is False, r.json()
    assert b.tabele["intake_jobs"] == [] and b.tabele["predmet_dokumenti"] == []


# ── Stvaran Tesseract (CI: produkciona slika) ────────────────────────────────────────────────────────────────────

@treba_ocr
@pytest.mark.parametrize("fmt", ["jpg", "png"])
def test_stvaran_ocr_fotografija_kompletno_prikacena(ok, fmt):
    k, b = ok
    jid = _spreman_foto(k, fmt)
    f = _prikaci(k, jid)
    assert f.status_code == 200 and f.json()["prikacivanje"] == "POTPUNO", f.text
    [d] = _dokumenti(b)
    procitano = " ".join(d["tekst_sadrzaj"].upper().split())
    assert "DOPUNSKOJ" in procitano and "24.08.2026" in procitano, procitano[:300]
    assert d["source_intake_job_id"] == jid and _posao(b, jid)["assimilation_complete"] is True


# ── Drugi put istog kvara: `api.py` otpremanje direktno u predmet (`POST /api/predmeti/{id}/upload`) ───────────────
# Tu `chunk_document` NIJE u try bloku: pre ispravke fotografija je posle uspešnog OCR-a završavala izuzetkom (500).

class _DosaoDoIngest(BaseException):
    """BaseException: ruta hvata `Exception` oko vektorskog upisa; ovo je tačka merenja, ne kvar."""


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("fmt", ["jpg", "jpeg", "png"])
async def test_api_otpremanje_fotografije_u_predmet_prolazi_chunk_do_vektorskog_upisa(fmt):
    import types
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    import api
    from tests.test_ns3b_format_slike import _api_zahtev
    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "pred-1", "naziv": "Test", "tip": "opsti"}
    stiglo = []

    def _ingest(manifest, session_id, **kw):
        stiglo.append(manifest)
        raise _DosaoDoIngest()

    async def _dozvola(user=None):
        return user
    with patch("api._require_auth", return_value=types.SimpleNamespace(id="user-1", email="a@vindex.rs")), \
         patch("api._get_supa", return_value=supa), \
         patch("api.PermissionService.require", return_value=_dozvola), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("routers.smart_intake._encrypt", return_value=b"ENC"), \
         patch("uploaded_doc.extractor.extract", return_value=(POTVRDA_TEKST, False, True, None, 0.91)), \
         patch("uploaded_doc.ingest.ingest_session", side_effect=_ingest):
        try:
            await api.predmet_upload_auto_analyze(
                "pred-1", _api_zahtev(),
                UploadFile(filename=f"potvrda.{fmt}", file=io.BytesIO(_foto(fmt)), headers=Headers({"content-type": MIME[fmt]})),
                authorization="Bearer t")
        except _DosaoDoIngest:
            pass
        except Exception as e:     # noqa: BLE001 — pre ispravke: ValidationError iz chunk_document, ili 500 iz rute
            pytest.fail(f"otpremanje fotografije nije stiglo do vektorskog upisa: {type(e).__name__}: {str(e)[:200]}")
    [m] = stiglo
    assert m.source_format == fmt and "24.08.2026" in " ".join(c.text for c in m.chunks)


def test_pre_ispravke_novi_predmet_nastavak_u_isti_predmet_bez_duplikata(ok, ocr, monkeypatch, audit):
    """Isto kao produkcija, ali finalize bez izabranog predmeta (otvara nov): dva neuspela pokušaja pod starim
    modelom, pa nastavak — jedan predmet, jedan dokument, jedna audit radnja dokumenta, događaji bez duplikata."""
    k, b = ok
    jid = _spreman_foto(k, "jpg")
    assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje("A")).status_code == 200
    pre_predmeta = len(b.tabele["predmeti"])
    with monkeypatch.context() as m:
        _stara_sema(m)
        for _ in range(2):
            f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={}, headers=zaglavlje("A"))
            assert f.status_code == 200 and f.json()["prikacivanje"] == "NIJE_PRIKACENO", f.text
    novi = _posao(b, jid)["predmet_id"]
    assert novi and len(b.tabele["predmeti"]) == pre_predmeta + 1 and _dokumenti(b, novi) == []
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={}, headers=zaglavlje("A"))
    assert f.status_code == 200 and f.json()["prikacivanje"] == "POTPUNO" and f.json()["predmet_id"] == novi, f.text
    assert len(b.tabele["predmeti"]) == pre_predmeta + 1 and len(_dokumenti(b, novi)) == 1
    assert audit.count("document_assimilated") == 1, audit
    tipovi = [str(e.get("event_type")) for e in b.tabele["events"] if e.get("predmet_id") == novi]
    assert len(tipovi) == len(set(tipovi)), tipovi                 # nijedan događaj dvaput
    f2 = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={}, headers=zaglavlje("A"))
    assert f2.json()["already_finalized"] is True and audit.count("document_assimilated") == 1
