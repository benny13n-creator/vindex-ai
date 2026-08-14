# -*- coding: utf-8 -*-
"""
BETA-P0-SENSITIVE-DATA-AUDIT — NEUSPEO AUDIT NE SME DA POSTANE NEAUDITIRAN USPEH.

ŠTA JE VEĆ BILO ISPRAVNO (i nije dirano)

Inventar je mali: **tri** produkcijska pozivaoca `decrypt_field`, od kojih samo
`klijenti/router.py:431` dodiruje JMBG / broj pasoša / PIB. Na toj putanji već
postoji:

  · provera dozvole `access_confidential` (`:409`)
  · `log_event(... VIEW_CONFIDENTIAL ...)` **pre** dešifrovanja (`:415`)
  · audit koji beleži **samo imena polja**, nikad plaintext
  · nula pojavljivanja JMBG-a u logovima u celom produkcijskom kodu (mereno)

ŠTA NIJE BILO ISPRAVNO

`klijenti/audit.py:66` guta svaki izuzetak:

    except Exception as e:
        logger.warning("[AUDIT] log_event greška (non-blocking): %s", e)

Docstring to i imenuje: *„Fire-and-forget audit log. Greška ne blokira odgovor."*

Za većinu akcija je to prihvatljivo. Za **ovu** nije: ako upis audita padne,
dešifrovanje ipak prođe i JMBG izlazi iz sistema **bez ijednog traga o tome ko
ga je i kada video**. Tačno test E iz mandata — neuspeh audita se ne sme
pretvoriti u neauditiran uspeh.

POPRAVKA JE NAMERNO USKA

`log_event` **nije** menjan — ima preko 20 pozivalaca kojima je „fire-and-forget"
ispravna semantika. Umesto toga je uveden strogi ulaz koji se koristi **samo** na
poverljivoj putanji.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import klijenti.audit as ka  # noqa: E402

JMBG_PLAIN = "0101990710011"


# ═══════════════════════════════════════════════════════════════════════════
# 1. STROGI AUDIT — SRŽ POPRAVKE
# ═══════════════════════════════════════════════════════════════════════════

def _supa(puca=False):
    s = MagicMock()
    if puca:
        s.table.return_value.insert.return_value.execute.side_effect = \
            RuntimeError("audit tabela nedostupna")
    else:
        s.table.return_value.insert.return_value.execute.return_value = \
            MagicMock(data=[{"id": "a1"}])
    return s


def test_audit_strogi_ulaz_postoji():
    """Bez njega poverljiva putanja nema način da traži garantovan trag."""
    assert hasattr(ka, "log_event_strict"), \
        "nedostaje strogi ulaz za auditovanje poverljivih podataka"


def test_audit_strogi_pad_DIZE_izuzetak():
    """NAJVAŽNIJI TEST U FAJLU (test E iz mandata).

    Ranije je pad audita bio `logger.warning` i tok je nastavljao do
    dešifrovanja — JMBG bi izašao bez traga.
    """
    with pytest.raises(ka.AuditNijeZapisan):
        asyncio.run(ka.log_event_strict(
            supa=_supa(puca=True), user_id="u1", user_email="a@a.rs",
            user_role="advokat", akcija=ka.Akcija.VIEW_CONFIDENTIAL,
            entitet_id="k1", detalji={"polja": ["jmbg"]}, ip_adresa="1.2.3.4",
        ))


def test_audit_strogi_uspeh_ne_dize_nista():
    asyncio.run(ka.log_event_strict(
        supa=_supa(), user_id="u1", user_email="a@a.rs", user_role="advokat",
        akcija=ka.Akcija.VIEW_CONFIDENTIAL, entitet_id="k1",
        detalji={"polja": ["jmbg"]}, ip_adresa="1.2.3.4",
    ))


def test_audit_obicni_log_event_OSTAJE_fire_and_forget():
    """Popravka je uska: 20+ drugih pozivalaca ne sme da se promeni."""
    asyncio.run(ka.log_event(
        supa=_supa(puca=True), user_id="u1", user_email="a@a.rs",
        user_role="advokat", akcija=ka.Akcija.VIEW, entitet_id="k1",
    ))


# ═══════════════════════════════════════════════════════════════════════════
# 2. PLAINTEXT NIKAD U AUDITU (test C iz mandata)
# ═══════════════════════════════════════════════════════════════════════════

def test_audit_nikad_ne_nosi_plaintext_jmbg():
    """Audit sme da kaže KOJA su polja viđena, nikad NJIHOVU vrednost."""
    s = _supa()
    asyncio.run(ka.log_event_strict(
        supa=s, user_id="u1", user_email="a@a.rs", user_role="advokat",
        akcija=ka.Akcija.VIEW_CONFIDENTIAL, entitet_id="k1",
        detalji={"polja": ["jmbg", "broj_pasosa", "pib"]}, ip_adresa="1.2.3.4",
    ))
    upisano = str(s.table.return_value.insert.call_args)
    assert JMBG_PLAIN not in upisano
    assert "jmbg" in upisano, "ime polja mora biti zabeleženo"


# ═══════════════════════════════════════════════════════════════════════════
# 3. UGOVOR ZAPISA (polja koja mandat traži)
# ═══════════════════════════════════════════════════════════════════════════

def test_audit_zapis_nosi_trazena_polja():
    s = _supa()
    asyncio.run(ka.log_event_strict(
        supa=s, user_id="u1", user_email="a@a.rs", user_role="partner",
        akcija=ka.Akcija.VIEW_CONFIDENTIAL, entitet_id="k1",
        detalji={"polja": ["jmbg"]}, ip_adresa="1.2.3.4",
    ))
    red = s.table.return_value.insert.call_args[0][0]
    for polje in ("user_id", "user_email", "user_role", "akcija",
                  "entitet_id", "detalji", "ip_adresa"):
        assert polje in red, f"audit zapis nema {polje}"
    assert red["akcija"] == ka.Akcija.VIEW_CONFIDENTIAL


# ═══════════════════════════════════════════════════════════════════════════
# 4. ŠTO JE VEĆ BILO ISPRAVNO — zaključano da ne regresira
# ═══════════════════════════════════════════════════════════════════════════

def test_produkcijski_kod_ne_loguje_jmbg():
    """Mereno: 0 pojavljivanja. Ovaj test to drži na nuli."""
    import glob
    import io
    import re
    sumnjivi = []
    for f in glob.glob("**/*.py", recursive=True):
        if f.startswith(("tests" + os.sep, "scripts" + os.sep)):
            continue
        try:
            t = io.open(f, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for m in re.finditer(r"(logger\.\w+|print)\s*\([^)]*jmbg[^)]*\)", t, re.I):
            sumnjivi.append(f"{f}: {m.group(0)[:60]}")
    assert not sumnjivi, f"JMBG ulazi u log: {sumnjivi[:3]}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. OŽIČENJE — mutacija B je otkrila rupu u testovima
# ═══════════════════════════════════════════════════════════════════════════
#
# Mutacija „ruta više ne zove strogi audit, nego običan `log_event`" nije
# oborila nijedan test iznad — jer svi mere `log_event_strict` u IZOLACIJI, ne
# ožičenje. Isti oblik rupe koji je ID-02 već jednom otkrio.
#
# Ovaj test vozi PRAVU rutu i meri POSLEDICU: kad audit padne, dešifrovanje se
# ne sme ni pokušati, a poverljivi podaci ne smeju izaći.

def _klijent_red():
    return {
        "id": "k1", "user_id": "u1", "ime": "Petar", "prezime": "Petrović",
        "jmbg_encrypted": "enc_v1:xxx", "broj_pasosa_encrypted": "enc_v1:yyy",
        "pib_encrypted": "enc_v1:zzz", "status": "aktivan",
    }


def _supa_klijent():
    s = MagicMock()

    def _t(ime):
        q = MagicMock()
        if ime == "klijenti":
            q.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                MagicMock(data=_klijent_red())
            q.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                MagicMock(data=_klijent_red())
        else:
            q.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        q.insert.return_value.execute.return_value = MagicMock(data=[{"id": "a1"}])
        return q
    s.table.side_effect = _t
    return s


def test_ozicenje_pad_audita_SPRECAVA_desifrovanje():
    """NAJVAŽNIJI TEST OŽIČENJA.

    Meri se posledica, ne poziv: ako audit padne, `decrypt_field` se ne sme
    izvršiti nijednom, a ruta mora vratiti grešku — nikad poverljive podatke.
    """
    import klijenti.router as kr

    desifrovano = []

    async def _auth(_r):
        return {"user_id": "u1", "email": "a@a.rs", "role": 99, "role_str": "partner"}

    async def _audit_pada(**kw):
        raise ka.AuditNijeZapisan("audit nije upisan")

    with patch.object(kr, "_get_supa", return_value=_supa_klijent()), \
         patch.object(kr, "_auth_from_request", new=_auth), \
         patch.object(kr, "can_perform", return_value=True), \
         patch.object(kr, "get_client_ip", return_value="1.2.3.4"), \
         patch.object(kr, "log_event_strict", new=_audit_pada), \
         patch.object(kr, "decrypt_field",
                      side_effect=lambda v: desifrovano.append(v) or "PLAINTEXT"):
        with pytest.raises(HTTPException) as e:
            asyncio.run(kr.get_klijent("k1", MagicMock(headers={}),
                                       reveal_confidential=True))

    assert e.value.status_code == 503, "pad audita mora vratiti grešku"
    assert desifrovano == [], (
        "JMBG je dešifrovan uprkos neuspelom auditu — nema uvida bez traga"
    )
