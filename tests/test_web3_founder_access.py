# -*- coding: utf-8 -*-
"""
Web3 / Digitalna imovina — founder pristup se propagira u `/api/me`.

NADJENI KVAR: `PermissionService.require` (shared/permissions.py) na svakoj
`da_*` ruti ima granu `if is_founder: ... return user` KOJA SE IZVRSAVA PRE
provere `digital_assets` dodatka -- dakle founder vec ima pun backend pristup
Web3 modulu. Ali `/api/me` je za `digitalna_imovina_aktivirano` citao SIROVU
kolonu profila i vracao False, pa je frontend (`_dimRenderAiwsPill`,
static/vindex.js:2229) krio dugme
"Vindex AI - Digitalna imovina & usklađenost" (#aiws-pill-dim) korisniku koji
na backendu prolazi. Nesklad PRIKAZA, ne nedostatak ovlascenja.

Ovi testovi dokazuju da popravka NIJE bypass:
  * founder dobija True (kroz postojeci `_is_founder`, bez hardkodovanog emaila)
  * ne-founder BEZ dodatka i dalje dobija False -- nema privilege escalation-a
  * ne-founder SA dodatkom se ponasa kao i pre
  * `standalone` ostaje nepromenjen za sve
  * backend autorizacija ostaje izvor istine (frontend vidljivost nije granica)
"""
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FOUNDER = "founder@example.invalid"
OBICAN = "advokat@example.invalid"
UID = "aaaa0000-0000-4000-8000-00000000000a"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _profil(dim=False, standalone=False):
    return {
        "credits_remaining": 12,
        "is_pro": False,
        "digitalna_imovina_aktivirano": dim,
        "digitalna_imovina_standalone": standalone,
        "addons": [],
    }


async def _pozovi_me(email, profil, founderi=(FOUNDER,)):
    """Poziva stvarnu `/api/me` funkciju. `_is_founder` se ne mockuje -- podesava
    se stvarni skup founder adresa, isti mehanizam koji koristi produkcija."""
    import api

    # NAPOMENA: `api.py` ima SOPSTVENI `_is_founder`/`FOUNDER_EMAILS`
    # (api.py:129, :144), odvojen od istoimenih u `shared/deps.py`. Patch mora
    # gadjati bas `api.FOUNDER_EMAILS` -- inace test lazno kaze is_founder=False.
    with patch.object(api, "_ensure_profile", return_value=profil), \
         patch.object(api, "FOUNDER_EMAILS", {e.lower() for e in founderi}):
        return await api.me({"user_id": UID, "email": email})


# ── TEST A — FOUNDER ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_A_founder_dobija_pristup_digitalnoj_imovini():
    d = await _pozovi_me(FOUNDER, _profil(dim=False))
    assert d["is_founder"] is True
    assert d["digitalna_imovina_aktivirano"] is True, (
        "founder prolazi na backendu, ali `/api/me` i dalje kaze False — "
        "dugme #aiws-pill-dim bi ostalo sakriveno")


@pytest.mark.anyio
async def test_A2_founder_NIJE_standalone():
    """Standalone skriva ostatak platforme; founderu treba cela platforma."""
    d = await _pozovi_me(FOUNDER, _profil(dim=False, standalone=False))
    assert d["digitalna_imovina_standalone"] is False, (
        "founder je greskom prebacen u standalone rezim — izgubio bi ostatak UI-ja")


# ── TEST B — NE-FOUNDER SA DODATKOM ────────────────────────────────────────

@pytest.mark.anyio
async def test_B_ne_founder_sa_dodatkom_ostaje_nepromenjen():
    d = await _pozovi_me(OBICAN, _profil(dim=True))
    assert d["is_founder"] is False
    assert d["digitalna_imovina_aktivirano"] is True, (
        "postojece ponasanje pretplatnika sa dodatkom je promenjeno")


# ── TEST C — NE-FOUNDER BEZ DODATKA (nema eskalacije) ──────────────────────

@pytest.mark.anyio
async def test_C_ne_founder_bez_dodatka_NE_dobija_pristup():
    d = await _pozovi_me(OBICAN, _profil(dim=False))
    assert d["is_founder"] is False
    assert d["digitalna_imovina_aktivirano"] is False, (
        "PRIVILEGE ESCALATION: korisnik bez `digital_assets` dodatka je dobio pristup")
    assert d["digitalna_imovina_standalone"] is False


@pytest.mark.anyio
async def test_C2_prazan_email_ne_prolazi_kao_founder():
    d = await _pozovi_me("", _profil(dim=False))
    assert d["is_founder"] is False
    assert d["digitalna_imovina_aktivirano"] is False


# ── TEST D — BACKEND AUTORIZACIJA JE IZVOR ISTINE ──────────────────────────

@pytest.mark.anyio
async def test_D_founder_prolazi_kroz_PermissionService():
    """Backend grana koja daje pristup postoji NEZAVISNO od `/api/me`."""
    from shared.permissions import PermissionService

    politika = {"aktivno": True, "status": "ACTIVE", "addon": "digital_assets",
                "minimum_plan": None}
    zavisnost = PermissionService.require("da_regulatory_review")

    with patch("shared.permissions.get_policy", new=AsyncMock(return_value=politika)), \
         patch("shared.permissions._check_dependencies", new=AsyncMock(return_value=None)), \
         patch("shared.deps.FOUNDER_EMAILS", {FOUNDER}):
        user = await zavisnost.__wrapped__({"user_id": UID, "email": FOUNDER}) \
            if hasattr(zavisnost, "__wrapped__") else await zavisnost({"user_id": UID, "email": FOUNDER})

    assert user["subscription_type"] == "enterprise", (
        "founder ne dobija pun pristup na backendu — popravka `/api/me` bi bila lazna")


@pytest.mark.anyio
async def test_D2_ne_founder_bez_dodatka_je_ODBIJEN_na_backendu():
    """Frontend vidljivost NIJE bezbednosna granica — backend mora odbiti."""
    from fastapi import HTTPException
    from shared.permissions import PermissionService

    politika = {"aktivno": True, "status": "ACTIVE", "addon": "digital_assets",
                "minimum_plan": None}
    zavisnost = PermissionService.require("da_regulatory_review")
    fn = getattr(zavisnost, "__wrapped__", zavisnost)

    with patch("shared.permissions.get_policy", new=AsyncMock(return_value=politika)), \
         patch("shared.permissions._check_dependencies", new=AsyncMock(return_value=None)), \
         patch("shared.permissions._ensure_profile", return_value={"addons": [], "is_pro": False}), \
         patch("shared.deps.FOUNDER_EMAILS", {FOUNDER}):
        with pytest.raises(HTTPException) as exc:
            await fn({"user_id": UID, "email": OBICAN})

    assert exc.value.status_code == 403, (
        "korisnik bez dodatka je propusten na Web3 API — to je stvarna eskalacija")


# ── TEST E — UI ELEMENT I NJEGOV IZVOR ISTINE ──────────────────────────────

def test_E_ui_dugme_postoji_i_cita_isti_flag():
    """Kanonska lokacija se ne menja; dokazuje se da postoji i da zavisi bas od
    polja koje `/api/me` sada ispravno racuna."""
    import io as _io
    import os as _os

    koren = _os.path.join(_os.path.dirname(__file__), "..")
    html = _io.open(_os.path.join(koren, "index.html"), encoding="utf-8").read()
    js = _io.open(_os.path.join(koren, "static", "vindex.js"), encoding="utf-8").read()

    assert 'id="aiws-pill-dim"' in html, "kanonsko dugme vise ne postoji"
    assert 'data-mode="digitalna_imovina"' in html
    assert html.count('id="aiws-pill-dim"') == 1, "napravljena je druga navigaciona stavka"

    assert "currentUserDigitalnaImovinaAktivirano = !!d.digitalna_imovina_aktivirano" in js, (
        "frontend vise ne cita `digitalna_imovina_aktivirano` iz /api/me")
    assert "pill.style.display = currentUserDigitalnaImovinaAktivirano" in js, (
        "vidljivost dugmeta vise ne zavisi od tog polja")


# ── TEST F — TENANT IZOLACIJA NIJE DIRANA ──────────────────────────────────

def test_F_izmena_ne_dira_tenant_ni_rbac():
    """Popravka sme da promeni SAMO izvedenu vrednost jednog polja odgovora.

    Z017.2 §5 (PATTERN A provenance contract) je dodao `izvori`/
    `retrieval_unavailable` u `routers/web3.py::post_web3_pretraga` --
    legitimna, additive izmena odgovora, van opsega ovog testa. Originalna
    verzija je testirala "fajl uopste nije diran u odnosu na HEAD u trenutku
    pisanja" sto je bio tacan opis TE JEDNE popravke, ali nije trajan
    invarijant -- svaka buduca legitimna izmena `routers/web3.py` bi ovaj
    test pogresno oborila. Sada se proverava STVARNA namera: da diff ne
    dira permission/tenant/scoping linije, ne da fajl ostaje bajt-za-bajt
    zamrznut."""
    import io as _io
    import os as _os
    import re as _re
    import subprocess

    koren = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
    diff = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=koren,
                          capture_output=True, text=True).stdout.split()
    zabranjeno_fajlovi = [f for f in diff if f.startswith(("migrations/", "shared/permissions.py",
                                                           "routers/ofac_screening.py",
                                                           "routers/wallet_provenance.py",
                                                           "routers/source_of_funds.py"))]
    assert not zabranjeno_fajlovi, "dirane su zabranjene povrsine: %s" % zabranjeno_fajlovi

    if "routers/web3.py" in diff:
        patch = subprocess.run(["git", "diff", "HEAD", "--", "routers/web3.py"], cwd=koren,
                               capture_output=True, text=True).stdout
        dirane_linije = [l for l in patch.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
        rbac_markeri = _re.compile(r"PermissionService|Depends\(|tenant_id|user\[.user_id.\]|require\(")
        rbac_dirano = [l for l in dirane_linije if rbac_markeri.search(l)]
        assert not rbac_dirano, "routers/web3.py diff dira permission/tenant liniju: %s" % rbac_dirano

    perm = _io.open(_os.path.join(koren, "shared", "permissions.py"), encoding="utf-8").read()
    assert "digital_assets" not in perm or "addon_required" in perm, (
        "logika dodatka u PermissionService je promenjena")
