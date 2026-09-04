# -*- coding: utf-8 -*-
"""
Z014 R2 — ROLLOUT KAPIJA ZA VINDEX V2.

`v2_pristup` je obican feature_key u kanonskom registru, dodeljen preko
`profiles.addons` — isti mehanizam kojim `digital_assets` vec gejtuje osam
`da_*` funkcija. NIJE paralelan permission sistem i NIJE founder bypass.

Dva ugovora koja ovi testovi cuvaju:

  1. `_sme_v2` nema sopstvenu logiku — samo poziva `PermissionService`.
     Cim bi pocela da sama cita `addons` ili `subscription_type`, kapija bi
     postala drugi permission sistem koji moze da se raziđe od prvog.

  2. FAIL-CLOSED. Dok red `v2_pristup` ne postoji u registru, `get_policy`
     baca RuntimeError — i odgovor mora biti False, nikad tiho True.
     Mutacija M5 (`return True` u except grani) obara bas taj test.
"""
import asyncio
import os
import sys
from unittest.mock import patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routers.plans as plans  # noqa: E402

KORISNIK = {"user_id": "u1", "email": "a@b.com"}


def _lazni_require(ishod):
    """ishod: True -> propusta · Exception instanca -> baca je."""
    zapis = {}

    def require(kljuc):
        zapis["kljuc"] = kljuc

        async def dep(user=None):
            zapis["user"] = user
            if isinstance(ishod, Exception):
                raise ishod
            return user
        return dep

    return require, zapis


class TestKanonskiLanac:

    def test_poziva_permission_service_sa_tacnim_kljucem(self):
        require, zapis = _lazni_require(True)
        with patch.object(plans.PermissionService, "require", staticmethod(require)):
            rez = asyncio.run(plans._sme_v2(KORISNIK))
        assert rez is True
        assert zapis["kljuc"] == "v2_pristup"

    def test_prosledjuje_korisnika_lancu(self):
        require, zapis = _lazni_require(True)
        with patch.object(plans.PermissionService, "require", staticmethod(require)):
            asyncio.run(plans._sme_v2(KORISNIK))
        assert zapis["user"]["user_id"] == "u1"
        assert zapis["user"]["email"] == "a@b.com"

    def test_nema_sopstvenu_logiku_dozvola(self):
        """Kapija ne sme sama da cita tarifu, addon-e ni founder status.

        Gleda se ISKLJUCIVO izvrsni kod: docstring i komentari se uklanjaju
        preko `ast`, jer oni ta ista imena legitimno pominju u objasnjenju.
        Provera nad sirovim tekstom izvora merila bi komentar, ne ponasanje.
        """
        import ast
        import inspect
        import textwrap

        stablo = ast.parse(textwrap.dedent(inspect.getsource(plans._sme_v2)))
        fn = stablo.body[0]
        if (fn.body and isinstance(fn.body[0], ast.Expr)
                and isinstance(fn.body[0].value, ast.Constant)
                and isinstance(fn.body[0].value.value, str)):
            fn.body = fn.body[1:]          # skini docstring
        kod = ast.unparse(fn)

        for zabranjeno in ("subscription_type", "_is_founder", "effective_tier", "addons"):
            assert zabranjeno not in kod, "kapija sama odlucuje o %s" % zabranjeno
        assert "PermissionService.require" in kod


class TestFailClosed:

    def test_registry_red_ne_postoji(self):
        """get_policy baca RuntimeError -> False, nikad True."""
        require, _ = _lazni_require(RuntimeError("Feature Registry: 'v2_pristup' nema red"))
        with patch.object(plans.PermissionService, "require", staticmethod(require)):
            assert asyncio.run(plans._sme_v2(KORISNIK)) is False

    def test_dozvola_odbijena(self):
        from fastapi import HTTPException
        require, _ = _lazni_require(HTTPException(status_code=403, detail="Nema addon"))
        with patch.object(plans.PermissionService, "require", staticmethod(require)):
            assert asyncio.run(plans._sme_v2(KORISNIK)) is False

    def test_kill_switch(self):
        from fastapi import HTTPException
        require, _ = _lazni_require(HTTPException(status_code=503, detail="Privremeno onemoguceno"))
        with patch.object(plans.PermissionService, "require", staticmethod(require)):
            assert asyncio.run(plans._sme_v2(KORISNIK)) is False

    def test_pad_baze(self):
        require, _ = _lazni_require(ConnectionError("baza nedostupna"))
        with patch.object(plans.PermissionService, "require", staticmethod(require)):
            assert asyncio.run(plans._sme_v2(KORISNIK)) is False


class TestOdgovorPlanStatus:

    def test_polje_je_deklarisano_u_odgovoru(self):
        """`v2_pristup` mora biti u telu /api/plan/status, uz sva legacy polja."""
        import inspect
        izvor = inspect.getsource(plans.plan_status)
        assert '"v2_pristup"' in izvor
        for legacy in ('"plan"', '"plan_display"', '"addons"', '"credits_remaining"',
                       '"year_month"', '"usage_this_month"', '"subscription_expires_at"',
                       '"subscription_seats_extra"'):
            assert legacy in izvor, "legacy polje %s nestalo iz odgovora" % legacy
