# -*- coding: utf-8 -*-
"""
Z014 R3/R4 — SERVERSKA PRETRAGA REGISTRA I LAKA PROJEKCIJA.

Registar predmeta nije imao ni pretragu ni filter statusa, a `select("*")`
je vukao `case_dna` u SVAKI red liste — mereno na zivom backendu: 87.733 B
za 20 predmeta naspram 6.027 B bez njega, dakle 93% odgovora.

Nijedno se nije smelo popraviti lomljenjem zatecenog ugovora, pa je
`view=summary` opt-in: bez njega ponasanje je bajt u bajt isto kao pre.

Dva ugovora koja se ovde cuvaju i koja nisu ocigledna:

  1. `brisanje_zapoceto` MORA ostati u projekciji. `_je_u_brisanju` cita bas
     to polje nad rezultatom; bez njega bi tombstonovan predmet ponovo
     osvanuo u registru. Mutacija M8 obara bas taj test.

  2. Sortiranje mora imati drugi kljuc (`id`). Sa samo `created_at`, dva
     predmeta istog vremena mogu zameniti mesta izmedju dve stranice, pa se
     red preskoci ili prikaze dvaput. Mutacija M9 obara bas taj test.
"""
import asyncio
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402


def _req():
    from starlette.requests import Request as StarletteRequest

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return StarletteRequest(
        scope={"type": "http", "method": "GET", "path": "/api/predmeti", "headers": [],
               "query_string": b"", "app": MagicMock(), "state": MagicMock(),
               "client": ("127.0.0.1", 1234)},
        receive=receive,
    )


def _pozovi(**kw):
    lanac = MagicMock()
    for metod in ("select", "eq", "neq", "order", "range", "ilike", "or_"):
        setattr(lanac, metod, MagicMock(return_value=lanac))
    lanac.execute = MagicMock(return_value=MagicMock(data=[{"id": "p1"}], count=1))
    supa = MagicMock()
    supa.table.return_value = lanac
    user = types.SimpleNamespace(id="u1", email="a@b.com")
    with patch.object(api, "_require_auth", return_value=user), \
         patch.object(api, "_get_supa", return_value=supa):
        rez = asyncio.run(api.lista_predmeta(_req(), authorization="Bearer x", **kw))
    return rez, lanac


class TestZatecenoPonasanje:

    def test_podrazumevano_i_dalje_zvezda(self):
        rez, lanac = _pozovi()
        assert lanac.select.call_args.args[0] == "*"

    def test_podrazumevano_bez_ijednog_novog_filtera(self):
        _, lanac = _pozovi()
        lanac.ilike.assert_not_called()
        assert ("status",) not in {(c.args[0],) for c in lanac.eq.call_args_list}

    def test_stari_kljucevi_odgovora_ostaju(self):
        rez, _ = _pozovi()
        assert "predmeti" in rez and "ukupno" in rez

    def test_limit_i_dalje_ogranicen_na_500(self):
        _, lanac = _pozovi(limit=99999)
        lanac.range.assert_called_once_with(0, 499)

    def test_podrazumevan_limit_ostaje_200(self):
        _, lanac = _pozovi()
        lanac.range.assert_called_once_with(0, 199)


class TestProjekcija:

    def test_summary_izostavlja_case_dna(self):
        _, lanac = _pozovi(view="summary")
        assert "case_dna" not in lanac.select.call_args.args[0]

    def test_summary_zadrzava_polje_za_tombstone(self):
        """_je_u_brisanju cita bas `brisanje_zapoceto` — bez njega bi se
        obrisan predmet vratio u registar."""
        _, lanac = _pozovi(view="summary")
        assert "brisanje_zapoceto" in lanac.select.call_args.args[0]

    def test_summary_nosi_polja_koja_registru_trebaju(self):
        _, lanac = _pozovi(view="summary")
        kolone = lanac.select.call_args.args[0]
        for k in ("id", "naziv", "tip", "status", "broj_predmeta"):
            assert k in kolone

    def test_nepoznat_view_se_ponasa_kao_podrazumevan(self):
        _, lanac = _pozovi(view="nesto-drugo")
        assert lanac.select.call_args.args[0] == "*"


class TestPretraga:

    def test_q_daje_ilike_po_nazivu(self):
        _, lanac = _pozovi(q="spor")
        lanac.ilike.assert_called_once_with("naziv", "%spor%")

    def test_dzokeri_se_uklanjaju(self):
        """PostgREST ne izlaze SQL ESCAPE, pa je uklanjanje jedini
        deterministican nacin."""
        _, lanac = _pozovi(q="a%b_c")
        lanac.ilike.assert_called_once_with("naziv", "%abc%")

    def test_prazan_i_beli_q_ne_dodaju_filter(self):
        for prazno in ("", "   ", None):
            _, lanac = _pozovi(q=prazno)
            lanac.ilike.assert_not_called()

    def test_predugacak_q_se_skracuje(self):
        _, lanac = _pozovi(q="x" * 500)
        obrazac = lanac.ilike.call_args.args[1]
        assert len(obrazac) <= 122


class TestFilterStatusa:

    def test_status_daje_eq(self):
        _, lanac = _pozovi(status="zatvoren")
        assert ("status", "zatvoren") in {c.args for c in lanac.eq.call_args_list}

    def test_prazan_status_ne_dodaje_filter(self):
        _, lanac = _pozovi(status="  ")
        assert ("status",) not in {(c.args[0],) for c in lanac.eq.call_args_list}


class TestStabilnoStranicenje:

    def test_sortiranje_ima_drugi_kljuc(self):
        _, lanac = _pozovi()
        kljucevi = [c.args[0] for c in lanac.order.call_args_list]
        assert "created_at" in kljucevi
        assert "id" in kljucevi, "bez drugog kljuca stranicenje moze preskociti red"

    def test_odgovor_nosi_limit_i_offset(self):
        rez, _ = _pozovi(limit=7, offset=14)
        assert rez["limit"] == 7 and rez["offset"] == 14

    def test_range_racuna_tacno(self):
        _, lanac = _pozovi(limit=50, offset=100)
        lanac.range.assert_called_once_with(100, 149)


class TestIzolacijaKorisnika:

    def test_user_id_ostaje_i_uz_filtere(self):
        _, lanac = _pozovi(q="spor", status="aktivan", view="summary")
        assert ("user_id", "u1") in {c.args for c in lanac.eq.call_args_list}
