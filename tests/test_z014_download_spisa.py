# -*- coding: utf-8 -*-
"""
Z014 R1 — PREUZIMANJE ORIGINALNOG SPISA.

Original JESTE cuvan (`predmet_dokumenti.storage_path`, bucket
`intake-dokumenti`, AES-GCM sifrat), ali do ovog sprinta nijedna ruta ga
nije vracala: `preview` daje samo izdvojen tekst. Advokat nije mogao da
preuzme sopstveni spis.

ZASTO SE OVDE NE MOCKUJE ODLUKA KOJU TEST DOKAZUJE

Testovi NE mockuju provered vlasnistva. Mockuju samo bazu i tvrde da
lanac upita nosi sva tri ogranicenja (`id`, `predmet_id`, `user_id`).
Mock koji bi vratio red bez obzira na filtere dokazivao bi sopstvenu
postavku, ne kod. Mutacije M1/M2 (uklanjanje `user_id`, odnosno
`predmet_id` iz lanca) obaraju bas ove testove.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
import api  # noqa: E402

KORISNIK = {"user_id": "u1", "email": "a@b.com"}


def _req():
    from starlette.requests import Request as StarletteRequest

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return StarletteRequest(
        scope={"type": "http", "method": "GET", "path": "/x", "headers": [],
               "query_string": b"", "app": MagicMock(), "state": MagicMock(),
               "client": ("127.0.0.1", 1234)},
        receive=receive,
    )


def _lanac(execute_return):
    m = MagicMock()
    for metod in ("select", "eq", "neq", "order", "range", "ilike", "maybe_single", "single"):
        setattr(m, metod, MagicMock(return_value=m))
    m.execute = MagicMock(return_value=execute_return)
    return m


def _pozovi(pred_data, dok_data=None, storage_bytes=b"neVazno"):
    pred = _lanac(MagicMock(data=pred_data))
    dok = _lanac(MagicMock(data=dok_data))
    supa = MagicMock()
    supa.table.side_effect = lambda t: pred if t == "predmeti" else dok
    supa.storage.from_.return_value.download.return_value = storage_bytes
    return pred, dok, supa


class TestRutaPostoji:
    def test_download_ruta_registrovana(self):
        putanje = {r.path for r in api.app.routes if hasattr(r, "path")}
        assert "/api/predmeti/{predmet_id}/dokumenti/{dok_id}/download" in putanje


class TestAutorizacija:

    def test_upit_dokumenta_ogranicen_na_sva_tri_kljuca(self):
        """Poznat dok_id sam po sebi ne sme nista otvoriti."""
        pred, dok, supa = _pozovi(
            {"id": "p1", "brisanje_zapoceto": None},
            {"id": "d1", "naziv_fajla": "a.pdf", "storage_path": "u/p/x.pdf", "velicina_kb": 10},
        )
        with patch.object(api, "_get_supa", return_value=supa):
            with pytest.raises(Exception):
                # desifrovanje pada (nije pravi sifrat); upiti su do tada
                # vec izvrseni i bas njih ovaj test tvrdi
                asyncio.run(api.predmet_dokument_download("p1", "d1", _req(), user=KORISNIK))

        eq_pozivi = {c.args for c in dok.eq.call_args_list}
        assert ("id", "d1") in eq_pozivi
        assert ("predmet_id", "p1") in eq_pozivi
        assert ("user_id", "u1") in eq_pozivi

    def test_predmet_se_proverava_pre_dokumenta(self):
        """Tudji predmet -> 404 pre nego sto se dokument uopste trazi."""
        from fastapi import HTTPException
        pred, dok, supa = _pozovi(None, {"id": "d1"})
        with patch.object(api, "_get_supa", return_value=supa):
            with pytest.raises(HTTPException) as e:
                asyncio.run(api.predmet_dokument_download("p1", "d1", _req(), user=KORISNIK))
        assert e.value.status_code == 404
        assert dok.execute.call_count == 0, "dokument se trazio iako predmet nije nas"

    def test_predmet_ogranicen_na_korisnika(self):
        pred, dok, supa = _pozovi(
            {"id": "p1", "brisanje_zapoceto": None},
            {"id": "d1", "naziv_fajla": "a.pdf", "storage_path": None, "velicina_kb": 1},
        )
        with patch.object(api, "_get_supa", return_value=supa):
            with pytest.raises(Exception):
                asyncio.run(api.predmet_dokument_download("p1", "d1", _req(), user=KORISNIK))
        eq_pozivi = {c.args for c in pred.eq.call_args_list}
        assert ("id", "p1") in eq_pozivi
        assert ("user_id", "u1") in eq_pozivi

    def test_tombstonovan_predmet_je_404(self):
        from fastapi import HTTPException
        pred, dok, supa = _pozovi({"id": "p1", "brisanje_zapoceto": "2026-01-01"})
        with patch.object(api, "_get_supa", return_value=supa):
            with pytest.raises(HTTPException) as e:
                asyncio.run(api.predmet_dokument_download("p1", "d1", _req(), user=KORISNIK))
        assert e.value.status_code == 404

    def test_poruke_ne_razlikuju_tudje_od_nepostojeceg(self):
        """Isti tekst za 'nije tvoje' i 'ne postoji' — bez curenja postojanja."""
        from fastapi import HTTPException
        poruke = []
        for _ in range(2):
            pred, dok, supa = _pozovi(None)
            with patch.object(api, "_get_supa", return_value=supa):
                with pytest.raises(HTTPException) as e:
                    asyncio.run(api.predmet_dokument_download("p1", "d1", _req(), user=KORISNIK))
                poruke.append(e.value.detail)
        assert poruke[0] == poruke[1] == "Predmet nije pronađen"


class TestNedostajuciOriginal:

    def test_bez_originala_je_404_sa_imenovanim_razlogom(self):
        """Vlastiti spis bez sacuvanog originala — razlog se imenuje, ne cuti."""
        from fastapi import HTTPException
        pred, dok, supa = _pozovi(
            {"id": "p1", "brisanje_zapoceto": None},
            {"id": "d1", "naziv_fajla": "a.pdf", "storage_path": None, "velicina_kb": 10},
        )
        with patch.object(api, "_get_supa", return_value=supa):
            with pytest.raises(HTTPException) as e:
                asyncio.run(api.predmet_dokument_download("p1", "d1", _req(), user=KORISNIK))
        assert e.value.status_code == 404
        assert "original" in e.value.detail.lower()

    def test_prazan_storage_path_isto_kao_none(self):
        from fastapi import HTTPException
        pred, dok, supa = _pozovi(
            {"id": "p1", "brisanje_zapoceto": None},
            {"id": "d1", "naziv_fajla": "a.pdf", "storage_path": "   ", "velicina_kb": 10},
        )
        with patch.object(api, "_get_supa", return_value=supa):
            with pytest.raises(HTTPException) as e:
                asyncio.run(api.predmet_dokument_download("p1", "d1", _req(), user=KORISNIK))
        assert e.value.status_code == 404


class TestNeCuriInterno:

    def test_odgovor_ne_sadrzi_storage_path_ni_bucket(self):
        """Ni u jednoj poruci greske ne sme biti unutrasnjih detalja."""
        from fastapi import HTTPException
        pred, dok, supa = _pozovi(
            {"id": "p1", "brisanje_zapoceto": None},
            {"id": "d1", "naziv_fajla": "a.pdf", "storage_path": "u1/p1/tajna.pdf", "velicina_kb": 10},
        )
        supa.storage.from_.return_value.download.side_effect = RuntimeError("bucket eksplodirao")
        with patch.object(api, "_get_supa", return_value=supa):
            with pytest.raises(HTTPException) as e:
                asyncio.run(api.predmet_dokument_download("p1", "d1", _req(), user=KORISNIK))
        assert e.value.status_code == 500
        assert "tajna.pdf" not in e.value.detail
        assert "bucket" not in e.value.detail.lower()
        assert "intake-dokumenti" not in e.value.detail
