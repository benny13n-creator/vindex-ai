# -*- coding: utf-8 -*-
"""TENFRONTS-M05 (PHOENIX-004) — vektori upload-a čiji `predmet_dokumenti` upis nije uspeo.

`api.py::predmet_upload_auto_analyze` upisuje vektore PRE reda u bazi. Ako upis reda padne, ruta vraća 500,
a vektori su ostajali u deljenom namespace-u vlasnika i bili dostupni pretrazi (RAG filtrira po predmet_id).

Identitet vektora je deterministički: `prefiks_dokumenta(predmet_id, verzija sadržaja)`. Zato ISTI sadržaj
u ISTOM predmetu deli iste ID-eve — ako takav dokument već postoji u bazi, njegovi vektori se NE smeju
dirati. Nijedan Pinecone indeks se ne poziva stvarno; lažni indeks drži vektore u memoriji."""
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api
from shared.vector_deletion import Ishod, obrisi_vektore_neupisanog_dokumenta
from shared.vector_identity import canonical_vector_id, prefiks_dokumenta, verzija_dokumenta
from tests._schema_fake import napravi_supa
from tests.test_intake_original_file_storage import (
    _fake_openai_client, _fake_permission_dependency, _fake_request, _fake_user, _upload_file)

UID, PID = "user-42", "pred-1"
TEKST = "Sadržaj dokumenta."
VER = verzija_dokumenta(TEKST)
NS = "user_user-42"


class LazniIndeks:
    def __init__(self, vektori=None, list_puca=False, delete_puca=False, ne_nestaju=False):
        self.v = {ns: set(ids) for ns, ids in (vektori or {}).items()}
        self.list_puca, self.delete_puca, self.ne_nestaju = list_puca, delete_puca, ne_nestaju
        self.obrisano = []

    def upisi(self, ns, ids):
        self.v.setdefault(ns, set()).update(ids)

    def list(self, prefix, namespace):
        if self.list_puca:
            raise RuntimeError("pinecone list 503")
        yield sorted(i for i in self.v.get(namespace, set()) if i.startswith(prefix))

    def delete(self, ids, namespace):
        if self.delete_puca:
            raise RuntimeError("pinecone delete 503")
        self.obrisano.append((namespace, list(ids)))
        if not self.ne_nestaju:
            self.v[namespace] -= set(ids)


def _ids(scope, ver, n):
    return {canonical_vector_id(scope, ver, i) for i in range(n)}


def _supa(dokumenti=(), vlasnik=UID, greske=None):
    return napravi_supa({}, redovi={
        "predmeti": [{"id": PID, "user_id": vlasnik}],
        "predmet_delegiranja": [],
        "predmet_dokumenti": list(dokumenti),
    }, greske=greske)


def _ocisti(supa, idx, **kw):
    arg = dict(user_id=UID, predmet_id=PID, namespace=NS, verzija=VER)
    arg.update(kw)
    return obrisi_vektore_neupisanog_dokumenta(supa, idx, _spavaj=lambda s: None, **arg)


# ── funkcija čišćenja ──────────────────────────────────────────────────────────────────────────

def test_brise_tacno_vektore_neupisanog_dokumenta():
    drugi_ver = verzija_dokumenta("Drugi dokument.")
    idx = LazniIndeks({NS: _ids(PID, VER, 3) | _ids(PID, drugi_ver, 2) | _ids("pred-2", VER, 2),
                       "user_drugi": _ids(PID, VER, 3)})
    rez = _ocisti(_supa(), idx)
    assert rez.ishod == Ishod.DELETED and rez.obrisano == 3
    assert idx.v[NS] == _ids(PID, drugi_ver, 2) | _ids("pred-2", VER, 2)     # drugi dokumenti netaknuti
    assert idx.v["user_drugi"] == _ids(PID, VER, 3)                          # drugi namespace netaknut
    assert idx.obrisano == [(NS, sorted(_ids(PID, VER, 3)))]


def test_isti_sadrzaj_vec_postoji_u_predmetu_ne_brise_se():
    idx = LazniIndeks({NS: _ids(PID, VER, 3)})
    rez = _ocisti(_supa(dokumenti=[{"id": "d-staro", "predmet_id": PID, "content_sha256": VER}]), idx)
    assert rez.ishod == Ishod.REFUSED and idx.obrisano == [] and idx.v[NS] == _ids(PID, VER, 3)


def test_isti_sadrzaj_u_drugom_predmetu_ne_sprecava_ciscenje():
    idx = LazniIndeks({NS: _ids(PID, VER, 2)})
    rez = _ocisti(_supa(dokumenti=[{"id": "d-x", "predmet_id": "pred-2", "content_sha256": VER}]), idx)
    assert rez.ishod == Ishod.DELETED


def test_provera_baze_pala_ne_brise():
    idx = LazniIndeks({NS: _ids(PID, VER, 2)})
    rez = _ocisti(_supa(greske={"predmet_dokumenti": TimeoutError("db")}), idx)
    assert rez.ishod == Ishod.REFUSED and idx.obrisano == []


def test_tudji_predmet_ne_brise():
    idx = LazniIndeks({NS: _ids(PID, VER, 2)})
    rez = _ocisti(_supa(vlasnik="neko-drugi"), idx)
    assert rez.ishod == Ishod.REFUSED and idx.obrisano == []


@pytest.mark.parametrize("kw", [{"namespace": ""}, {"verzija": ""}, {"verzija": "a" * 64}, {"predmet_id": ""}])
def test_bez_tacnog_identiteta_ne_brise(kw):
    idx = LazniIndeks({NS: _ids(PID, VER, 2)})
    rez = _ocisti(_supa(), idx, **kw)
    assert rez.ishod == Ishod.REFUSED and idx.obrisano == []


def test_listanje_palo_ne_brise():
    idx = LazniIndeks({NS: _ids(PID, VER, 2)}, list_puca=True)
    assert _ocisti(_supa(), idx).ishod == Ishod.REFUSED and idx.obrisano == []


def test_brisanje_palo_je_vidljivo():
    idx = LazniIndeks({NS: _ids(PID, VER, 2)}, delete_puca=True)
    assert _ocisti(_supa(), idx).ishod == Ishod.PARTIAL_FAILURE


def test_neverifikovano_brisanje_nije_uspeh():
    idx = LazniIndeks({NS: _ids(PID, VER, 2)}, ne_nestaju=True)
    rez = _ocisti(_supa(), idx)
    assert rez.ishod == Ishod.PARTIAL_FAILURE and not rez.uspeh


def test_ponovljeno_ciscenje_ne_brise_nista_drugo():
    drugi = _ids(PID, verzija_dokumenta("Drugi."), 2)
    idx = LazniIndeks({NS: _ids(PID, VER, 2) | drugi})
    assert _ocisti(_supa(), idx).ishod == Ishod.DELETED
    assert _ocisti(_supa(), idx).ishod == Ishod.ALREADY_ABSENT
    assert idx.v[NS] == drugi


# ── stvarni upload endpoint ───────────────────────────────────────────────────────────────────

def _supa_insert_pada(postojeci=()):
    def _table(name):
        if name == "predmeti":
            c = MagicMock()
            for m in ("select", "eq", "single", "limit"):
                getattr(c, m).return_value = c
            r = MagicMock(); r.data = {"id": PID, "naziv": "Test", "tip": "opsti"}
            # _sme_predmet čita listu; ruta čita objekat — oba su istinita za vlasnika
            c.execute = MagicMock(side_effect=lambda: types.SimpleNamespace(data=[{"id": PID}])
                                  if c.limit.called else r)
            return c
        if name == "predmet_dokumenti":
            c = MagicMock()
            for m in ("select", "eq", "order", "limit"):
                getattr(c, m).return_value = c
            c.execute = MagicMock(return_value=types.SimpleNamespace(data=list(postojeci)))
            c.insert = MagicMock(side_effect=RuntimeError("supabase 503"))
            return c
        c = MagicMock()
        for m in ("select", "eq", "limit", "order"):
            getattr(c, m).return_value = c
        c.execute = MagicMock(return_value=types.SimpleNamespace(data=[]))
        return c
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)
    return supa


DRUGI = _ids(PID, verzija_dokumenta("Drugi dokument istog predmeta."), 2) | _ids("pred-2", VER, 2)


async def _upload(supa, idx):
    zapis = {}

    def _ingest(manifest, session_id, namespace_override=None, verzija_dokumenta_id=None, extra_metadata=None):
        zapis["ns"] = namespace_override
        idx.upisi(namespace_override, DRUGI)              # tuđi dokument istog vlasnika, isti namespace
        idx.upisi(namespace_override, _ids(extra_metadata["predmet_id"], verzija_dokumenta_id, 3))
        return 3
    with patch("api._require_auth", return_value=_fake_user(UID)), \
         patch("api._get_supa", return_value=supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", return_value=(TEKST, False, False, None, None)), \
         patch("uploaded_doc.chunker.chunk_document", return_value=types.SimpleNamespace(total_chunks=3)), \
         patch("uploaded_doc.ingest.ingest_session", side_effect=_ingest), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx), \
         patch("shared.vector_deletion.VERIFIKACIJA_PAUZA_S", 0), \
         patch("routers.smart_intake._encrypt", return_value=b"ENC"), \
         patch("openai.OpenAI", new=_fake_openai_client()), \
         patch("api.UsageService.consume", new=AsyncMock()):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as ex:
            await api.predmet_upload_auto_analyze(PID, _fake_request(), _upload_file("tuzba.pdf", "application/pdf"),
                                                  authorization="Bearer t")
    return ex.value, zapis


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_upload_pad_upisa_reda_uklanja_svoje_vektore():
    idx = LazniIndeks()
    ex, zapis = await _upload(_supa_insert_pada(), idx)
    assert ex.status_code == 500 and "nije uspešno sačuvan" in ex.detail
    ns = zapis["ns"]
    assert not any(i.startswith(prefiks_dokumenta(PID, VER)) for i in idx.v[ns]), "orphan vektori ostali"
    assert idx.v[ns] == DRUGI, "dirnuti vektori drugih dokumenata"


@pytest.mark.anyio
async def test_upload_pad_upisa_ne_dira_vektore_postojeceg_istog_dokumenta():
    idx = LazniIndeks()
    ex, zapis = await _upload(_supa_insert_pada(postojeci=[{"id": "d-staro", "redni_broj": 1}]), idx)
    assert ex.status_code == 500
    assert idx.obrisano == [] and idx.v[zapis["ns"]] == _ids(PID, VER, 3) | DRUGI
