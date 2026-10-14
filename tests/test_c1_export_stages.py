# -*- coding: utf-8 -*-
"""
C1 (Night Sprint II) — faze izvoza i istinit audit (GET /api/export/complete).

Faze: 1 zahtev; 2 citanje zavrseno; 3 arhiva napravljena; 4 odgovor zapocet;
5 isporuka klijentu. Server moze da dokaze najvise fazu 3. Ugovor koji se meri:
  * svaki neuspeh (pre citanja, tokom citanja, tokom pravljenja arhive) ostavlja
    `data_export_failed` sa fazom, a NIKAD `data_export`;
  * uspesan zapis tvrdi samo fazu 3 i izricito kaze da isporuka nije dokaziva;
  * nijedan zapis ne nosi sadrzaj arhive ni tekst izuzetka;
  * pad audit upisa ne obara izvoz i ne pretvara neuspeh u uspeh;
  * ID iz zahteva (query/zaglavlje) nikad ne menja vlasnika izvoza.

Sve sinteticko: lazni Supabase iz test_n04, bez mreze.
"""
import asyncio
import io
import json
import logging
import os
import sys
import zipfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_n04_case_export_integrity import (  # noqa: E402
    A, B, TABELE_IZVOZA, FakeSupa, _izvezi, _sadrzaj,
)

TAJNA = "TAJNA-SADRZAJ-C1"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _samo(audit, akcija):
    return [kw for a, kw in audit if a == akcija]


def _bez_tajne(audit):
    s = json.dumps([[a, kw] for a, kw in audit], default=str)
    assert TAJNA not in s
    assert "TAJNA-B" not in s


# ── faza 1→2: pad pre ijednog citanja tabele ───────────────────────────────

@pytest.mark.anyio
async def test_pad_pre_citanja_pise_failed_pre_retrieval_bez_uspeha(caplog):
    import routers.data_export as de
    from fastapi import HTTPException

    audit = []

    async def _snimi(action, **kw):
        audit.append((action, kw))
        return "id"

    with caplog.at_level(logging.DEBUG), \
         patch.object(de, "_get_supa", side_effect=RuntimeError(TAJNA)), \
         patch("shared.audit_immutable.log_action", new=_snimi):
        with pytest.raises(HTTPException) as exc:
            await de.export_complete(user={"user_id": A, "email": "a@x.rs"})
        for _ in range(5):
            await asyncio.sleep(0)
    assert exc.value.status_code == 503
    assert "nije napravljen" in exc.value.detail
    assert _samo(audit, "data_export") == []
    [kw] = _samo(audit, "data_export_failed")
    assert kw["user_id"] == A
    assert kw["metadata"]["stage"] == "pre_retrieval"
    assert kw["metadata"]["archive_sent"] is False
    assert kw["metadata"]["error_class"] == "RuntimeError"
    _bez_tajne(audit)
    assert TAJNA not in caplog.text


# ── faza 2: delimican pad citanja ──────────────────────────────────────────

@pytest.mark.anyio
@pytest.mark.parametrize("tabela", sorted(TABELE_IZVOZA))
async def test_pad_citanja_pise_failed_retrieval_sa_imenom_tabele(tabela):
    from fastapi import HTTPException

    supa = FakeSupa(padovi={tabela})
    rez, audit = await _izvezi(supa)
    assert isinstance(rez, HTTPException) and rez.status_code == 503
    assert _samo(audit, "data_export") == []
    [kw] = _samo(audit, "data_export_failed")
    m = kw["metadata"]
    assert m["stage"] == "retrieval"
    assert m["failed_tables"] == [tabela]
    assert m["archive_sent"] is False
    assert "email" not in m
    assert supa.mutacije == []


@pytest.mark.anyio
async def test_vise_palih_tabela_sve_imenovane_jedan_zapis():
    supa = FakeSupa(padovi={"klijenti", "rocista"})
    rez, audit = await _izvezi(supa)
    assert rez.status_code == 503
    [kw] = _samo(audit, "data_export_failed")
    assert sorted(kw["metadata"]["failed_tables"]) == ["klijenti", "rocista"]
    # citanje se ne prekida na prvom padu: svih 8 tabela je pokusano
    assert {t for t, _ in supa.citanja} == set(TABELE_IZVOZA)


# ── faza 3: pad pravljenja arhive ──────────────────────────────────────────

@pytest.mark.anyio
async def test_pad_serijalizacije_pise_failed_bez_teksta_izuzetka(caplog):
    import routers.data_export as de
    from fastapi import HTTPException

    with caplog.at_level(logging.DEBUG), \
         patch.object(de.json, "dumps", side_effect=ValueError(TAJNA)):
        rez, audit = await _izvezi(FakeSupa())
    assert isinstance(rez, HTTPException)
    assert rez.status_code == 500
    assert "nije napravljen" in rez.detail
    assert _samo(audit, "data_export") == []
    [kw] = _samo(audit, "data_export_failed")
    assert kw["metadata"]["stage"] == "serialization"
    assert kw["metadata"]["error_class"] == "ValueError"
    _bez_tajne(audit)
    assert TAJNA not in caplog.text


@pytest.mark.anyio
async def test_kruzna_referenca_u_redu_je_neuspeh_a_ne_uspeh():
    from fastapi import HTTPException

    supa = FakeSupa()
    petlja = []
    petlja.append(petlja)
    supa.podaci["klijenti"][0]["oznake"] = petlja
    rez, audit = await _izvezi(supa)
    assert isinstance(rez, HTTPException) and rez.status_code == 500
    assert _samo(audit, "data_export") == []
    assert [kw["metadata"]["stage"] for kw in _samo(audit, "data_export_failed")] == ["serialization"]


# ── uspeh: zapis tvrdi samo fazu 3 ─────────────────────────────────────────

@pytest.mark.anyio
async def test_uspesan_zapis_tvrdi_samo_napravljenu_arhivu_ne_isporuku():
    (resp, telo), audit = await _izvezi(FakeSupa())
    assert _samo(audit, "data_export_failed") == []
    [kw] = _samo(audit, "data_export")
    m = kw["metadata"]
    assert m["stage"] == "archive_generated"
    assert m["delivery"] == "not_verified_by_server"
    for kljuc in m:
        assert kljuc not in {"delivered", "completed", "downloaded"}
    # nijedan bajt sadrzaja arhive ne ulazi u zapis
    s = json.dumps(m)
    for bajtovi in _sadrzaj(telo).values():
        if len(bajtovi) > 40:
            assert bajtovi.decode("utf-8")[:40] not in s


@pytest.mark.anyio
async def test_prekinut_prijem_ne_menja_zapis_server_ne_tvrdi_isporuku():
    """Klijent nikad ne procita telo (prekid veze). Zapis je isti kao kod
    procitanog odgovora: faza 3, isporuka neproverena. Server ne moze da
    razlikuje ova dva slucaja i zato ne tvrdi nijedan."""
    import routers.data_export as de

    audit = []

    async def _snimi(action, **kw):
        audit.append((action, kw))
        return "id"

    with patch.object(de, "_get_supa", return_value=FakeSupa()), \
         patch("shared.audit_immutable.log_action", new=_snimi):
        resp = await de.export_complete(user={"user_id": A, "email": "a@x.rs"})
        for _ in range(5):
            await asyncio.sleep(0)
    assert resp.status_code == 200
    [kw] = _samo(audit, "data_export")
    assert kw["metadata"]["delivery"] == "not_verified_by_server"


@pytest.mark.anyio
async def test_ponovljen_izvoz_dva_nezavisna_zapisa_bez_neuspeha():
    supa = FakeSupa()
    _, a1 = await _izvezi(supa)
    _, a2 = await _izvezi(supa)
    assert [a for a, _ in a1] == ["data_export"]
    assert [a for a, _ in a2] == ["data_export"]


@pytest.mark.anyio
async def test_prazan_izvoz_je_uspeh_faze_3():
    (resp, telo), audit = await _izvezi(FakeSupa(), uid="user-prazan")
    assert all(json.loads(_sadrzaj(telo)[f]) == [] for f in TABELE_IZVOZA.values())
    [kw] = _samo(audit, "data_export")
    assert kw["user_id"] == "user-prazan"
    assert kw["metadata"]["stage"] == "archive_generated"


# ── audit sink nedostupan ──────────────────────────────────────────────────

def test_data_export_failed_je_u_recniku_akcija():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "data_export_failed" in AUDITABLE_ACTIONS
    assert "data_export" in AUDITABLE_ACTIONS


@pytest.mark.anyio
async def test_pravi_log_action_stize_do_upisa_za_failed():
    """Bez mok-a log_action-a: neregistrovana akcija bi tiho vratila None."""
    import shared.audit_immutable as ai

    upisano = []
    with patch.object(ai, "_build_and_insert",
                      side_effect=lambda action, *a, **k: upisano.append(action) or "id"):
        rez, _ = await _izvezi_pravi_audit(FakeSupa(padovi={"rocista"}))
    assert rez.status_code == 503
    assert upisano == ["data_export_failed"]


async def _izvezi_pravi_audit(supa):
    import routers.data_export as de
    from fastapi import HTTPException

    with patch.object(de, "_get_supa", return_value=supa):
        try:
            resp = await de.export_complete(user={"user_id": A, "email": "a@x.rs"})
        except HTTPException as exc:
            for _ in range(20):
                await asyncio.sleep(0.01)
            return exc, None
        telo = b""
        async for deo in resp.body_iterator:
            telo += deo
        for _ in range(20):
            await asyncio.sleep(0.01)
        return (resp, telo), None


@pytest.mark.anyio
async def test_nedostupan_audit_ne_obara_uspesan_izvoz():
    import shared.audit_immutable as ai

    with patch.object(ai, "_build_and_insert", side_effect=ConnectionError("audit down")):
        (resp, telo), _ = await _izvezi_pravi_audit(FakeSupa())
    assert resp.status_code == 200
    assert set(_sadrzaj(telo)) == {"README.txt", *TABELE_IZVOZA.values()}


@pytest.mark.anyio
async def test_nedostupan_audit_ne_pretvara_neuspeh_u_uspeh():
    import shared.audit_immutable as ai
    from fastapi import HTTPException

    with patch.object(ai, "_build_and_insert", side_effect=ConnectionError("audit down")):
        rez, _ = await _izvezi_pravi_audit(FakeSupa(padovi={"predmeti"}))
    assert isinstance(rez, HTTPException) and rez.status_code == 503


# ── ubacivanje tudjeg ID-a kroz pravu HTTP rutu ────────────────────────────

def test_tudji_id_u_upitu_i_zaglavlju_ne_menja_vlasnika_izvoza():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.data_export as de
    from shared.deps import get_current_user

    app = FastAPI()
    app.include_router(de.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": A, "email": "a@x.rs"}
    supa = FakeSupa()
    audit = []

    async def _snimi(action, **kw):
        audit.append((action, kw))
        return "id"

    with patch.object(de, "_get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=_snimi):
        with TestClient(app) as c:
            r = c.get(
                f"/api/export/complete?user_id={B}&uid={B}&predmet_id=predmet-b-1",
                headers={"X-User-Id": B, "X-Tenant-Id": B},
            )
    assert r.status_code == 200
    for ime, bajtovi in _sadrzaj(r.content).items():
        assert b"TAJNA-B" not in bajtovi, ime
        assert B.encode() not in bajtovi, ime
    for tabela, filteri in supa.citanja:
        assert ("user_id", A) in filteri, (tabela, filteri)
        assert ("user_id", B) not in filteri, (tabela, filteri)
    assert all(kw["user_id"] == A for _, kw in audit)


# ── C1-F1: PostgREST max-rows (1000) ne sme tiho da skrati izvoz ───────────

def _napuni(supa, tabela, n, uid=A):
    supa.podaci[tabela] = [
        {"id": f"r-{i}", "user_id": uid, "predmet_id": "p", "datum_iso": f"2026-01-{(i % 28) + 1:02d}",
         "dogadjaj": "sinteticki"}
        for i in range(n)
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("n", [0, 1, 999, 1000, 1001, 1500, 2000, 2500])
async def test_svi_redovi_preko_max_rows_su_izvezeni(n):
    supa = FakeSupa()
    assert supa.max_rows == 1000
    _napuni(supa, "predmet_hronologija", n)
    supa.podaci["predmet_hronologija"] += [{"id": "tudji", "user_id": B, "datum_iso": "2026-01-01"}]
    (resp, telo), audit = await _izvezi(supa)
    izvezeno = json.loads(_sadrzaj(telo)["hronologija.json"])
    ids = [r["id"] for r in izvezeno]
    assert len(ids) == n
    assert set(ids) == {f"r-{i}" for i in range(n)}
    assert [a for a, _ in audit] == ["data_export"]


@pytest.mark.anyio
async def test_nizi_max_rows_od_strane_ne_skracuje_izvoz():
    """Petlja staje na PRAZNOJ strani, ne na kratkoj: i server sa max-rows=300
    daje kompletan izvoz."""
    supa = FakeSupa()
    supa.max_rows = 300
    _napuni(supa, "predmet_dokumenti", 1000)
    (resp, telo), audit = await _izvezi(supa)
    assert len(json.loads(_sadrzaj(telo)["dokumenti.json"])) == 1000
    assert [a for a, _ in audit] == ["data_export"]


class _PadNaStrani(FakeSupa):
    """Druga strana zadate tabele pada (npr. istek konekcije usred citanja)."""

    def __init__(self, tabela, strana=2, **kw):
        super().__init__(**kw)
        self._t, self._s, self._n = tabela, strana, 0

    def table(self, ime):
        q = super().table(ime)
        if ime == self._t:
            izvrsi = q.execute

            def execute():
                self._n += 1
                if self._n == self._s:
                    raise RuntimeError(TAJNA)
                return izvrsi()
            q.execute = execute
        return q


@pytest.mark.anyio
async def test_pad_usred_stranicenja_je_neuspeh_citanja(caplog):
    from fastapi import HTTPException

    supa = _PadNaStrani("predmet_hronologija")
    _napuni(supa, "predmet_hronologija", 1500)
    with caplog.at_level(logging.DEBUG):
        rez, audit = await _izvezi(supa)
    assert isinstance(rez, HTTPException) and rez.status_code == 503
    assert _samo(audit, "data_export") == []
    [kw] = _samo(audit, "data_export_failed")
    assert kw["metadata"]["stage"] == "retrieval"
    assert kw["metadata"]["failed_tables"] == ["predmet_hronologija"]
    _bez_tajne(audit)
    # C1-F3: u logu je samo klasa izuzetka, ne tekst greske baze
    assert TAJNA not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.anyio
async def test_brisanje_izmedju_strana_ne_preskace_druge_redove():
    """Offset bi posle brisanja reda sa prve strane preskocio jedan red sa
    druge. Kljuc (`id > poslednji`) ne preskace."""
    supa = FakeSupa()
    _napuni(supa, "predmet_hronologija", 1500)
    obrisan = {}

    izvorni_table = supa.table

    def table(ime):
        q = izvorni_table(ime)
        if ime == "predmet_hronologija":
            izvrsi = q.execute

            def execute():
                r = izvrsi()
                if not obrisan and r.data:
                    prvi = r.data[0]["id"]
                    supa.podaci[ime] = [x for x in supa.podaci[ime] if x["id"] != prvi]
                    obrisan["id"] = prvi
                return r
            q.execute = execute
        return q
    supa.table = table
    (resp, telo), _ = await _izvezi(supa)
    ids = {r["id"] for r in json.loads(_sadrzaj(telo)["hronologija.json"])}
    assert ids == {f"r-{i}" for i in range(1500)}


@pytest.mark.anyio
async def test_server_koji_ignorise_kljuc_ne_vrti_petlju_vec_pada():
    from fastapi import HTTPException

    supa = FakeSupa()
    _napuni(supa, "rocista", 1500)
    izvorni_table = supa.table

    def table(ime):
        q = izvorni_table(ime)
        q.gt = lambda *a, **k: q  # filter ignorisan: uvek ista prva strana
        return q
    supa.table = table
    rez, audit = await _izvezi(supa)
    assert isinstance(rez, HTTPException) and rez.status_code == 503
    assert "rocista" in _samo(audit, "data_export_failed")[0]["metadata"]["failed_tables"]


@pytest.mark.anyio
async def test_redosled_izvoza_po_koloni_pa_id_deterministican():
    supa = FakeSupa()
    supa.podaci["predmet_hronologija"] = [
        {"id": "z", "user_id": A, "datum_iso": "2026-01-01"},
        {"id": "a", "user_id": A, "datum_iso": "2026-03-01"},
        {"id": "m", "user_id": A, "datum_iso": None},
        {"id": "b", "user_id": A, "datum_iso": "2026-01-01"},
    ]
    (resp, telo), _ = await _izvezi(supa)
    ids = [r["id"] for r in json.loads(_sadrzaj(telo)["hronologija.json"])]
    assert ids == ["b", "z", "a", "m"]


def test_upit_trazi_stabilan_redosled_po_id_i_stranu_najvise_max_rows():
    import routers.data_export as de

    supa = FakeSupa()
    _napuni(supa, "rocista", 10)
    upiti = []
    izvorni_table = supa.table

    def table(ime):
        q = izvorni_table(ime)
        upiti.append(q)
        return q
    supa.table = table
    asyncio.run(de._fetch(supa, "rocista", A, "datum"))
    assert upiti
    for q in upiti:
        assert q.redosled == ["id"]
        assert q.granica is not None and q.granica <= 1000
