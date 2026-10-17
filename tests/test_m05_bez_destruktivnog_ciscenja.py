# -*- coding: utf-8 -*-
"""M05 (PHOENIX-004) — ODLOŽENO: neuspeo upis dokumenta NE briše vektore.

Invarijanta: neuspeo upload nikad ne sme da obriše vektore dokumenta koji je uspešno sačuvan, ni pod
istovremenim radom. ID vektora je deterministički (predmet + verzija sadržaja), pa uspešan upload ISTOG
sadržaja u ISTI predmet deli iste ID-eve; on upisuje vektore pre reda u bazi, a Pinecone nema uslovno
brisanje. Svaka provera baze pre `delete()` ostavlja prozor (korektivna kapija PR #45, T01: B-ovi vektori
obrisani i kad B upiše red pre A-ovog brisanja, i posle A-ove završne provere — tada bez ikakvog signala).

Zato je M05 čišćenje vraćeno: sirotni vektori neuspelog upisa ostaju (poznat, nerešen defekt), a ovaj
test čuva da se brisanje ne vrati bez dokazano bezbednog mehanizma (odluka osnivača)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import shared.vector_deletion as vd
from tests.test_sprint002_pipeline_a_orphan_cleanup import _base_patches, _run_with_patches, _supa_upload_succeeds

TEKST = ("Sadržaj dokumenta.", False, False, None, None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _upload(insert_fails):
    indeks = MagicMock()
    supa = _supa_upload_succeeds(insert_fails=insert_fails)
    zakrpe = _base_patches(supa, extract_return=TEKST) + [
        patch("uploaded_doc.ingest._get_pinecone_index", return_value=indeks),
        patch("openai.OpenAI", return_value=MagicMock(chat=MagicMock(completions=MagicMock(
            create=MagicMock(return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="{}"))])))))),
        patch("api.UsageService.consume", new=AsyncMock())]
    return supa, indeks, zakrpe


@pytest.mark.anyio
async def test_neuspeo_upis_reda_ne_brise_vektore():
    _, indeks, zakrpe = await _upload(insert_fails=True)
    with pytest.raises(HTTPException) as e:
        await _run_with_patches(zakrpe)
    assert e.value.status_code == 500
    assert not indeks.delete.called, "neuspeo upload je brisao vektore — mogu pripadati uspešnom dokumentu"
    assert not indeks.method_calls, f"neuspeo upload je dirao indeks: {indeks.method_calls}"


@pytest.mark.anyio
async def test_uspesan_upload_ne_brise_vektore():
    _, indeks, zakrpe = await _upload(insert_fails=False)
    await _run_with_patches(zakrpe)
    assert not indeks.delete.called


def test_nema_ciscenja_po_prefiksu_za_neupisan_dokument():
    assert not hasattr(vd, "obrisi_vektore_neupisanog_dokumenta")
