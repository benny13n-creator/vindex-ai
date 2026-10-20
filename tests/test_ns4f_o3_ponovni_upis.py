# -*- coding: utf-8 -*-
"""NS4 O3 — oporavljiva promocija odobrenog nacrta (`POST /api/staging/{id}/ponovi-upis`).

Kroz STVARNE rute nad lažnom bazom (`tests/ns005_harness` + Python verzije RPC-a iz migracije 140 u
`tests/ns4f_rpc_fake.py`). Pinecone se ne dodiruje: `uploaded_doc.ingest.ingest_session` je zamenjen funkcijom koja
beleži ID-eve vektora (isti `shared/vector_identity.canonical_vector_id` kao pravi ingest) i vraća zadat broj
upisanih delova ili baca izuzetak. Atomičnost preuzimanja, rok, token i jedinstvenost knjigovodstvenog reda u
STVARNOJ bazi dokazuje tests/test_ns4f_pg_promocija.py.

Invarijanta: oporavak NIKAD ne slabi advokatsku overu, prag kvaliteta, autorizaciju ni granicu kancelarije;
nepotpun upis se nikad ne služi kao overen izvor; ponovni pokušaj ne pravi duplikat (ni vektora ni reda).
"""
import datetime as dt
from unittest.mock import patch

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb
from shared.vector_identity import canonical_vector_id

P1 = "aaaaaaaa-0303-4000-8000-000000000001"
S_OK, S_PEND, S_ODB, S_NIZAK, S_GOTOV, S_B = (f"5a5a5a5a-0303-4000-8000-00000000000{i}" for i in range(1, 7))
TEKST = "Odobren nacrt podneska sa činjenicama i predlogom. " * 30


def _staging(sid, user="uid-A", status="approved", odobren=True, ocena=0.92, indeks=False):
    return {"id": sid, "user_id": user, "kancelarija_id": None, "predmet_id": P1, "tip": "podnesak",
            "naziv": "Tužba", "tekst": TEKST, "confidence_score": ocena, "status": status,
            "is_lawyer_approved": odobren, "pinecone_indexed": indeks, "promocija_token": None,
            "promocija_preuzeta_at": None, "created_at": "2026-10-19T00:00:00+00:00"}


@pytest.fixture
def svet(monkeypatch):
    k, b = f8.pripremi(monkeypatch, {
        "staging_memory": [_staging(S_OK), _staging(S_PEND, status="pending", odobren=False),
                           _staging(S_ODB, status="rejected", odobren=False), _staging(S_NIZAK, ocena=0.5),
                           _staging(S_GOTOV, indeks=True), _staging(S_B, user="uid-B")],
        "predmet_dokumenti": [], "predmeti": [{"id": P1, "user_id": "uid-A", "naziv": "P", "tip": "radni"}],
    })
    b.jedinstveno["predmet_dokumenti"] = ("storage_path",)          # delimični UNIQUE iz migracije 140
    import shared.rate as rate
    monkeypatch.setattr(rate.limiter, "enabled", False)
    yield k, b
    f8.ocisti()


class Ingest:
    """Zamena za Pinecone ingest: beleži ID-eve vektora po pokušaju; `plan` = lista ishoda po pozivu."""

    def __init__(self, plan):
        self.plan, self.pozivi = list(plan), []

    def __call__(self, manifest, session_id, namespace_override=None, verzija_dokumenta_id=None,
                 extra_metadata=None, **_):
        ids = [canonical_vector_id(extra_metadata["predmet_id"], verzija_dokumenta_id, c.chunk_index)
               for c in manifest.chunks]
        self.pozivi.append({"ids": ids, "ns": namespace_override, "md": dict(extra_metadata)})
        ishod = self.plan.pop(0)
        if isinstance(ishod, Exception):
            raise ishod
        return manifest.total_chunks if ishod == "sve" else ishod


def _ponovi(k, sid, ko="A"):
    return k.post(f"/api/staging/{sid}/ponovi-upis", headers=f8.zaglavlje(ko))


def _red(b, sid):
    return next(x for x in b.tabele["staging_memory"] if x["id"] == sid)


def _sluzi_se(b):
    return S_OK in lb.vazece_overe(b, [(S_OK, P1)])


# ─── uspeh, nepotpun upis, izuzetak ─────────────────────────────────────────────────────────────────────────

def test_nepotpun_pa_ponovljen_upis_jedan_red_isti_vektori_i_tek_tada_overen_izvor(svet):
    k, b = svet
    ing = Ingest([0, "sve"])
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ing):
        prvi = _ponovi(k, S_OK)
        assert prvi.status_code == 200 and prvi.json()["indexed"] is False
        assert prvi.json()["razlog"] == "INDEKSIRANJE_NIJE_USPELO" and prvi.json()["ponovni_upis_moguc"] is True
        assert not _sluzi_se(b), "nepotpun upis serviran kao overen izvor"
        drugi = _ponovi(k, S_OK)
    assert drugi.status_code == 200 and drugi.json()["indexed"] is True
    assert _red(b, S_OK)["pinecone_indexed"] is True and _red(b, S_OK)["promocija_token"] is None
    assert _sluzi_se(b)
    assert ing.pozivi[0]["ids"] == ing.pozivi[1]["ids"], "ponovni upis istog teksta pravi nove ID-eve vektora"
    assert all(p["md"]["origin"] == "LAWYER_VERIFIED" and p["md"]["parent_id"] == S_OK for p in ing.pozivi)
    dok = [d for d in b.tabele["predmet_dokumenti"] if d["storage_path"] == f"draft/staging/{S_OK}"]
    assert len(dok) == 1 and dok[0]["status"] == "indeksirano", "duplikat ili zastareo knjigovodstveni red"


def test_izuzetak_pinecone_ostaje_neindeksiran_i_ponovo_podoban(svet):
    k, b = svet
    with patch("uploaded_doc.ingest.ingest_session", side_effect=Ingest([RuntimeError("pinecone 503 sk-tajna")])):
        r = _ponovi(k, S_OK)
    assert r.status_code == 200 and r.json()["indexed"] is False and "sk-tajna" not in r.text
    assert _red(b, S_OK)["pinecone_indexed"] is False and _red(b, S_OK)["promocija_token"] is None
    assert not _sluzi_se(b)
    lista = k.get(f"/api/staging/predmet/{P1}", headers=f8.zaglavlje("A")).json()["stavke"]
    assert next(x for x in lista if x["id"] == S_OK)["ponovni_upis_moguc"] is True


def test_pad_baze_posle_uspesnog_pinecone_upisa_se_kasnije_uskladjuje(svet):
    """Pinecone uspeo, završni upis stanja u bazu pao → pokušaj ostaje „u toku" (ne služi se); posle roka nov
    pokušaj prepisuje iste vektore i ažurira isti red."""
    k, b = svet
    ing = Ingest(["sve", "sve"])
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ing):
        b.greske["rpc:zavrsi_promociju_nacrta"] = Exception("db down")
        assert _ponovi(k, S_OK).status_code == 500
        del b.greske["rpc:zavrsi_promociju_nacrta"]
        assert _red(b, S_OK)["pinecone_indexed"] is False and not _sluzi_se(b)
        assert _ponovi(k, S_OK).status_code == 409, "dok rok ne istekne, drugi pokušaj ne sme da krene"
        _red(b, S_OK)["promocija_preuzeta_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
        r = _ponovi(k, S_OK)
    assert r.status_code == 200 and r.json()["indexed"] is True and _sluzi_se(b)
    assert ing.pozivi[0]["ids"] == ing.pozivi[1]["ids"]
    assert len([d for d in b.tabele["predmet_dokumenti"] if d["storage_path"] == f"draft/staging/{S_OK}"]) == 1


def test_pad_knjigovodstva_ne_prijavljuje_uspeh_i_oporavak_ga_dovrsava(svet):
    k, b = svet
    with patch("uploaded_doc.ingest.ingest_session", side_effect=Ingest(["sve", "sve"])):
        b.greske["predmet_dokumenti"] = Exception("db down")
        r = _ponovi(k, S_OK)
        assert r.status_code == 200 and r.json()["indexed"] is False and not _sluzi_se(b)
        del b.greske["predmet_dokumenti"]
        assert _ponovi(k, S_OK).json()["indexed"] is True
    assert len(b.tabele["predmet_dokumenti"]) == 1


def test_istovremeni_ponovni_pokusaj_ne_pokrece_drugi_upis(svet):
    k, b = svet
    from tests.ns4f_rpc_fake import preuzmi_ponovni_upis_nacrta
    assert preuzmi_ponovni_upis_nacrta(b, {"p_staging_id": S_OK, "p_user_id": "uid-A", "p_prag": 0.85,
                                           "p_istek_sekundi": 600})            # prvi radnik je preuzeo
    ing = Ingest(["sve"])
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ing):
        r = _ponovi(k, S_OK)
    assert r.status_code == 409 and ing.pozivi == []


def test_odbijanje_tokom_ponovnog_upisa_ne_postaje_overen_izvor(svet):
    k, b = svet

    def ingest_pa_odbij(manifest, *a, **kw):
        _red(b, S_OK).update({"status": "rejected", "is_lawyer_approved": False})     # opoziv usred upisa
        return manifest.total_chunks
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ingest_pa_odbij):
        r = _ponovi(k, S_OK)
    assert r.json()["indexed"] is False and _red(b, S_OK)["pinecone_indexed"] is False and not _sluzi_se(b)


# ─── podobnost i autorizacija ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sid", [S_PEND, S_ODB, S_NIZAK])
def test_nepodoban_nacrt_se_ne_promovise(svet, sid):
    k, b = svet
    ing = Ingest(["sve"])
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ing):
        r = _ponovi(k, sid)
    assert r.status_code == 409 and ing.pozivi == [] and _red(b, sid)["pinecone_indexed"] is False


def test_vec_indeksiran_ne_upisuje_ponovo(svet):
    k, _ = svet
    ing = Ingest(["sve"])
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ing):
        r = _ponovi(k, S_GOTOV)
    assert r.status_code == 200 and r.json()["indexed"] is True and ing.pozivi == []


@pytest.mark.parametrize("sid", [S_B, "5a5a5a5a-0303-4000-8000-0000000000ff", "nije-uuid"])
def test_tudji_nepostojeci_i_neispravan_isti_404_bez_upisa(svet, sid):
    k, b = svet
    ing = Ingest(["sve"])
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ing):
        r = _ponovi(k, sid)
        ref = _ponovi(k, "5a5a5a5a-0303-4000-8000-0000000000fe")
    assert r.status_code == ref.status_code == 404 and r.content == ref.content
    assert ing.pozivi == [] and _red(b, S_B)["pinecone_indexed"] is False


def test_lista_nudi_ponovni_upis_samo_podobnom(svet):
    k, _ = svet
    lista = {x["id"]: x["ponovni_upis_moguc"] for x in
             k.get(f"/api/staging/predmet/{P1}", headers=f8.zaglavlje("A")).json()["stavke"]}
    assert lista == {S_OK: True, S_PEND: False, S_ODB: False, S_NIZAK: False, S_GOTOV: False}
    assert "promocija_token" not in k.get(f"/api/staging/predmet/{P1}", headers=f8.zaglavlje("A")).text


def test_greska_preuzimanja_ne_menja_nista(svet):
    k, b = svet
    b.greske["rpc:preuzmi_ponovni_upis_nacrta"] = Exception("db down")
    ing = Ingest(["sve"])
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ing):
        r = _ponovi(k, S_OK)
    assert r.status_code == 503 and ing.pozivi == [] and _red(b, S_OK)["promocija_token"] is None


# ─── prvo odobrenje uzima isti token ────────────────────────────────────────────────────────────────────────

def test_odobrenje_drzi_pokusaj_pa_ponovni_upis_ne_tece_uporedo(svet):
    k, b = svet
    b.tabele["staging_memory"].append(_staging("5a5a5a5a-0303-4000-8000-000000000010", status="pending", odobren=False))
    sid = "5a5a5a5a-0303-4000-8000-000000000010"
    uporedo = {}

    def ingest_sa_upadom(manifest, *a, **kw):
        uporedo["r"] = _ponovi(k, sid)          # drugi zahtev dok prvo odobrenje još upisuje
        return 0
    with patch("uploaded_doc.ingest.ingest_session", side_effect=ingest_sa_upadom):
        r = k.post(f"/api/staging/{sid}/approve", headers=f8.zaglavlje("A"))
    assert uporedo["r"].status_code == 409, "ponovni upis je krenuo dok je prvo odobrenje bilo u toku"
    assert r.json()["razlog"] == "INDEKSIRANJE_NIJE_USPELO" and r.json()["ponovni_upis_moguc"] is True
    assert _red(b, sid)["promocija_token"] is None
