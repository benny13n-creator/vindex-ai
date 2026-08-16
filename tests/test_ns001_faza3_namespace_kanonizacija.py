# -*- coding: utf-8 -*-
"""
NIGHT STABILIZATION 001 / FAZA 3 — BR-005: JEDNA KANONSKA ŠEMA NAMESPACE-A.

ŠTA JE DOKAZANO MERENJEM, PRE IJEDNE IZMENE

Legacy `pred_*` šema nije bila samo mrtav kod — **aktivno je kvarila trenutni
tok**:

  · `pred_upload_doc` je posle uploada postavljao `_docNamespacePrefix='pred_'`
    sa `session_id` iz odgovora. Vektori tog dokumenta idu u vlasnički
    namespace, pa je `pred_<session_id>` namespace koji ne postoji.
    Mereno stvarnim pozivom: **HTTP 404 „Sesija nije pronađena ili je istekla"**.
  · `dokUcitajZaAnalizu` (klik na dokument) je računao
    `prefix = ns.startsWith('pred_') ? 'pred_' : 'tmp_'`, pa je za kanonski
    `user_<uid>` namespace slao `tmp_user_<uid>`. Mereno: **HTTP 404**.

Dakle advokat NIJE MOGAO da postavi pitanje o dokumentu — ni odmah po
otpremanju, ni klikom na dokument u predmetu.

DOKAZ DA JE `pred_` BIO MRTAV (a ne „za svaki slučaj")

  · nijedan pisac ne proizvodi `pred_` namespace
  · u Pinecone-u postoji 6 `pred_*` namespace-ova; **nijednom sufiks nije
    `predmeti.id`**, a `_verify_pred_namespace_ownership` je tražila baš to
  · `predmet_dokumenti` referiše 43 `pred_*` namespace-a; **nijedan ne postoji
    u Pinecone-u** i nijednom sufiks nije `predmeti.id`

BEZBEDNOSNI RAZLOG ZA UKLANJANJE, NEZAVISAN OD MRTVOG KODA

`/api/dokument/pitanje` pretražuje kroz `extra_namespaces`, a ta grana u
`app/services/retrieve.py` ide **bez metadata filtera** (namerno — za ad-hoc
`tmp_` dokument). Da vlasnički namespace ikad stigne tim putem, pretraga bi
zaobišla `shared/rag_acl.py` kapiju. Zato se vlasnički prostor sada izričito
odbija na ulazu.
"""
import asyncio
import io
import os
import re
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

UID = "bc8fb51c-4ee8-4124-aa64-39d35b502af7"


def _js():
    return io.open(os.path.join(_KOREN, "static", "vindex.js"), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════════════════════
# 1 — ULAZ: `pred_` VIŠE NE POSTOJI KAO PRIHVATLJIVA ŠEMA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("prefiks", ["pred_", "kancelarija_", "user_", "", "x_"])
def test_1_samo_tmp_prolazi_kapiju(prefiks):
    import routers.dokument as D
    if prefiks == "tmp_":
        return
    with pytest.raises(HTTPException) as e:
        asyncio.run(D._verify_pred_namespace_ownership("bilo-sta", prefiks, UID))
    assert e.value.status_code == 404


def test_1b_tmp_i_dalje_prolazi_kroz_svoju_proveru():
    """Uklanjanje `pred_` ne sme da obori legitimni `tmp_` tok."""
    import routers.dokument as D

    idx = MagicMock()
    idx.query.return_value = MagicMock(matches=[
        MagicMock(metadata={"owner_user_id": UID})
    ])
    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx):
        asyncio.run(D._verify_pred_namespace_ownership("sesija-1", "tmp_", UID))


# ═══════════════════════════════════════════════════════════════════════════
# 2 — VLASNIČKI NAMESPACE NE SME DA UĐE U PUT BEZ ACL FILTERA
# ═══════════════════════════════════════════════════════════════════════════

def _pitaj(session_id, prefiks=None):
    import routers.dokument as D

    telo = D.PitanjeDocRequest(session_id=session_id, pitanje="test",
                               namespace_prefix=prefiks)
    f = D.dokument_pitanje
    while hasattr(f, "__wrapped__"):
        f = f.__wrapped__
    return asyncio.run(f(telo, user={"user_id": UID, "email": "a@b.c"}))


@pytest.mark.parametrize("sid", [
    f"user_{UID}", "kancelarija_abc", "tmp_abc", "pred_abc",
])
def test_2_vlasnicki_i_prefiksirani_session_id_se_odbijaju(sid):
    """NAJVAŽNIJI BEZBEDNOSNI TEST FAZE 3.

    `extra_namespaces` pretraga nema metadata filter. Da vlasnički namespace
    stigne ovim putem, `rag_acl` kapija bi bila zaobiđena i pozivalac bi dobio
    doslovan tekst iz predmeta koje ne sme ni da otvori.
    """
    with pytest.raises(HTTPException) as e:
        _pitaj(sid)
    assert e.value.status_code == 422, e.value.detail


def test_2b_prosledjen_namespace_prefix_ne_moze_da_promeni_semu():
    """Pozivalac je ranije birao šemu poljem `namespace_prefix`. Sada je to
    polje bez uticaja — šema je `tmp_`, bez izuzetka."""
    import inspect
    import routers.dokument as D
    izvor = inspect.getsource(D.dokument_pitanje)
    assert 'ns_prefix = "tmp_"' in izvor
    assert "body.namespace_prefix" not in izvor


# ═══════════════════════════════════════════════════════════════════════════
# 3 — NIJEDAN PISAC NE PROIZVODI `pred_`
# ═══════════════════════════════════════════════════════════════════════════

def test_3_nijedan_produkcijski_pisac_ne_gradi_pred_namespace():
    """Brava nad IZVOROM fragmentacije. Kanonska šema je jedna:
    `shared/kancelarija_utils.py::rag_owner_namespace`."""
    sumnjivi = []
    for koren, dirs, files in os.walk(_KOREN):
        if any(x in koren for x in ("node_modules", ".git", "tests", "scripts")):
            continue
        for f in files:
            if not f.endswith((".py", ".js")) or f.endswith(".bak"):
                continue
            p = os.path.join(koren, f)
            try:
                s = io.open(p, encoding="utf-8").read()
            except Exception:
                continue
            for m in re.finditer(r"""(f?["']pred_\{|["']pred_["']\s*\+|=\s*["']pred_["'])""", s):
                red = s[:m.start()].count("\n") + 1
                linija = s.splitlines()[red - 1] if red <= len(s.splitlines()) else ""
                if linija.lstrip().startswith(("#", "//", "*")):
                    continue
                sumnjivi.append(f"{os.path.relpath(p, _KOREN)}:{red}: {linija.strip()[:90]}")
    assert not sumnjivi, "pred_ namespace se ponovo gradi:\n" + "\n".join(sumnjivi)


def test_3b_kanonska_sema_je_i_dalje_jedna_funkcija():
    from shared.kancelarija_utils import rag_owner_namespace
    assert rag_owner_namespace("u1", None) == "user_u1"
    assert rag_owner_namespace("u1", "k1") == "kancelarija_k1"


# ═══════════════════════════════════════════════════════════════════════════
# 4 — FRONTEND VIŠE NE IZMIŠLJA NAMESPACE
# ═══════════════════════════════════════════════════════════════════════════

def test_4_frontend_ne_postavlja_pred_prefiks():
    js = _js()
    dodele = [l.strip() for l in js.splitlines()
              if re.search(r"_docNamespacePrefix\s*=\s*'pred_'", l)
              and not l.strip().startswith("//")]
    assert not dodele, dodele


def test_4b_klik_na_kanonski_dokument_ne_pravi_tmp_sesiju():
    """Ranije: `ns.replace(/^(pred_|tmp_)/,'')` je za `user_<uid>` vraćalo ceo
    namespace, pa je klijent slao `tmp_user_<uid>` — 404 svaki put."""
    js = _js()
    telo = js.split("function dokUcitajZaAnalizu(")[1][:1400]
    assert "if (!ns.startsWith('tmp_'))" in telo, telo[:400]
    assert "dokPreviewOpen(" in telo
    assert "/^(pred_|tmp_)/" not in telo


def test_4c_auto_restore_pred_sesije_je_uklonjen():
    js = _js()
    assert "_rNs.startsWith('pred_')" not in js
    assert "replace(/^pred_/" not in js


# ═══════════════════════════════════════════════════════════════════════════
# 5 — PREVIEW FALLBACK ČITA IZ PRAVOG NAMESPACE-A
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ns,ocekivano", [
    ("tmp_abc123", ("abc123", "tmp_")),
    (f"user_{UID}", ("", f"user_{UID}")),
    ("kancelarija_k1", ("", "kancelarija_k1")),
])
def test_5_fallback_gradi_isti_namespace_koji_je_u_bazi(ns, ocekivano):
    """Ranije je za `user_<uid>` prefiks padao na `tmp_`, a session_id ostajao
    ceo namespace → čitalo se iz `tmp_user_<uid>`, koji ne postoji. Fallback je
    tiho vraćao prazno za SVAKI savremen dokument."""
    import api

    zabelezeno = {}

    def _fetch(session_id, namespace_prefix="tmp_"):
        zabelezeno["arg"] = (session_id, namespace_prefix)
        return "tekst"

    class _Q:
        def __init__(self, t): self.t = t
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def maybe_single(self): return self
        def single(self): return self
        def execute(self):
            return MagicMock(data={"id": "d1", "naziv_fajla": "x.docx",
                                   "pinecone_namespace": ns, "velicina_kb": 1,
                                   "status": "indeksirano", "created_at": "",
                                   "tekst_sadrzaj": ""})

    class _Supa:
        def table(self, t): return _Q(t)

    async def _nista(*a, **k):
        return None

    f = api.predmet_dokument_preview
    while hasattr(f, "__wrapped__"):
        f = f.__wrapped__
    zahtev = MagicMock(); zahtev.client = MagicMock(host="127.0.0.1")

    with patch.object(api, "_get_supa", lambda: _Supa()), \
         patch("routers.dokument._fetch_session_tekst", _fetch), \
         patch("shared.audit_immutable.log_action", _nista):
        out = asyncio.run(f("p1", "d1", zahtev, user={"user_id": UID, "email": "a@b.c"}))

    assert zabelezeno["arg"] == ocekivano, zabelezeno
    # Namespace koji se stvarno čita mora biti identičan onome u bazi.
    assert zabelezeno["arg"][1] + zabelezeno["arg"][0] == ns
    assert out["dostupan"] is True
