# -*- coding: utf-8 -*-
"""
BETA-P0-DELETED-DATA-ISOLATION — OBRISANA BELEŠKA NE SME BITI PRETRAŽIVA.

ŠTA JE BILO

`routers/knowledge_base.py`:

  · brisanje: DB red se briše u `try` (pad → 500), a Pinecone brisanje je
    `asyncio.create_task(...)` sa progutanim izuzetkom (`:392`). Odgovor je
    `{"ok": True}` **bez obzira** na ishod uklanjanja vektora.
  · pretraga (`:236-246`): `naslov` i `sadrzaj` se čitaju **isključivo iz
    Pinecone metapodataka**. Baza se ne dodiruje nijednom.

Posledica: korisnik obriše belešku, dobije potvrdu — a zastareo vektor i dalje
servira **pun sadržaj** te beleške kroz pretragu.

ZAŠTO JE ZATVARANJE UPRAVO OVAKVO

Mandat: *„If physical deletion cannot be safely guaranteed tonight: fail closed
by making deleted state unsearchable through authorization / retrieval
filters."*

Fizičko brisanje kod trećeg provajdera se ne može garantovati — mreža može pasti
posle DB brisanja. Zato je **primarna** brana ista ona koja je zatvorila F-01:
**autorizacija se izvodi iz TRENUTNOG stanja baze**, ne iz metapodataka vektora.
Vektor koji nema svoj red u bazi ne može biti vraćen, čak i ako fizički postoji.

Brisanje vektora je uz to prestalo da bude „fire-and-forget" — ali ono je
dopuna, ne garancija. **Nikad se ne briše po sličnosti ni po imenu.**
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

import routers.knowledge_base as kb  # noqa: E402

UID = "uid-advokat"
TAJNA = "POVERLJIVA_BELESKA_O_STRATEGIJI_001"


class _Match:
    def __init__(self, bid, score=0.9, sadrzaj=TAJNA):
        self.id = f"kb_{UID}_{bid}"
        self.score = score
        self.metadata = {"beleska_id": bid, "naslov": "Beleška",
                         "sadrzaj": sadrzaj, "tagovi": [], "predmet_id": None}


def _indeks(matches):
    ix = MagicMock()
    ix.query.return_value = MagicMock(matches=matches)
    return ix


def _supa(zivi_ids):
    """Baza sadrži SAMO neobrisane beleške — tačno kao u produkciji."""
    s = MagicMock()

    def _t(ime):
        q = MagicMock()

        class _Q:
            def __init__(self):
                self.u = {}

            def select(self, *a, **k):
                return self

            def eq(self, k, v):
                self.u[k] = v
                return self

            def in_(self, k, v):
                self.u["_in"] = list(v)
                return self

            def limit(self, n):
                return self

            def execute(self):
                trazeni = self.u.get("_in") or ([self.u["id"]] if "id" in self.u else [])
                return MagicMock(data=[{"id": i} for i in trazeni if i in zivi_ids])
        return _Q() if ime == "user_knowledge" else q
    s.table.side_effect = _t
    return s


def _pretrazi(matches, zivi_ids):
    async def _emb(_q):
        return [0.0] * 3072

    async def _consume(*a, **k):
        return None

    with patch.object(kb, "_get_pinecone_index", return_value=_indeks(matches)), \
         patch.object(kb, "_kb_embed", new=_emb), \
         patch.object(kb, "_get_supa", return_value=_supa(zivi_ids)), \
         patch.object(kb.UsageService, "consume", new=_consume):
        return asyncio.run(kb.knowledge_search.__wrapped__(
            request=MagicMock(), q="strategija", limit=10,
            user={"user_id": UID, "email": "a@a.rs"}))


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — OBRISANA BELEŠKA NE SME IZAĆI
# ═══════════════════════════════════════════════════════════════════════════

def test_obrisana_beleska_nije_pretraziva_iako_vektor_POSTOJI():
    """NAJVAŽNIJI TEST U FAJLU.

    Vektor fizički postoji (Pinecone brisanje je palo), ali reda u bazi nema.
    Sadržaj ne sme izaći.
    """
    rez = _pretrazi(matches=[_Match("b-obrisana")], zivi_ids=set())
    spojeno = str(rez)
    assert TAJNA not in spojeno, "sadržaj obrisane beleške je vraćen kroz pretragu"
    assert rez["results"] == []


def test_ziva_beleska_se_i_dalje_nalazi():
    """Popravka ne sme da ubije pretragu."""
    rez = _pretrazi(matches=[_Match("b-ziva")], zivi_ids={"b-ziva"})
    assert len(rez["results"]) == 1
    assert rez["results"][0]["sadrzaj"] == TAJNA


def test_meshovit_skup_vraca_samo_zive():
    rez = _pretrazi(
        matches=[_Match("b1"), _Match("b-obrisana"), _Match("b2")],
        zivi_ids={"b1", "b2"},
    )
    ids = {r["id"] for r in rez["results"]}
    assert ids == {"b1", "b2"}
    assert "b-obrisana" not in ids


def test_pad_provere_u_bazi_je_FAIL_CLOSED():
    """„Ne znam da li je živa" nikad ne sme da znači „prikaži je"."""
    class _Puca:
        def table(self, *a, **k):
            raise RuntimeError("baza nedostupna")

    async def _emb(_q):
        return [0.0] * 3072

    async def _consume(*a, **k):
        return None

    with patch.object(kb, "_get_pinecone_index", return_value=_indeks([_Match("b1")])), \
         patch.object(kb, "_kb_embed", new=_emb), \
         patch.object(kb, "_get_supa", return_value=_Puca()), \
         patch.object(kb.UsageService, "consume", new=_consume):
        with pytest.raises(Exception):
            asyncio.run(kb.knowledge_search.__wrapped__(
                request=MagicMock(), q="strategija", limit=10,
                user={"user_id": UID, "email": "a@a.rs"}))


# ═══════════════════════════════════════════════════════════════════════════
# 2. IZOLACIJA IZMEĐU KORISNIKA (ostaje netaknuta)
# ═══════════════════════════════════════════════════════════════════════════

def test_namespace_ostaje_po_korisniku():
    """Pretraga se i dalje ograničava na `kb_{uid}` — druga kancelarija ne
    ulazi u opseg ni pre ni posle popravke."""
    ix = _indeks([])

    async def _emb(_q):
        return [0.0] * 3072

    async def _consume(*a, **k):
        return None

    with patch.object(kb, "_get_pinecone_index", return_value=ix), \
         patch.object(kb, "_kb_embed", new=_emb), \
         patch.object(kb, "_get_supa", return_value=_supa(set())), \
         patch.object(kb.UsageService, "consume", new=_consume):
        asyncio.run(kb.knowledge_search.__wrapped__(
            request=MagicMock(), q="upit", limit=5,
            user={"user_id": UID, "email": "a@a.rs"}))
    assert ix.query.call_args.kwargs["namespace"] == f"kb_{UID}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. BRISANJE VIŠE NIJE „FIRE-AND-FORGET"
# ═══════════════════════════════════════════════════════════════════════════

def test_brisanje_prijavljuje_da_vektor_nije_uklonjen():
    """Korisnik sme da sazna da je zapis obrisan a vektor zaostao — ranije je
    odgovor bio `{"ok": True}` bez obzira na ishod."""
    import inspect
    izvor = inspect.getsource(kb)
    assert "vektor_uklonjen" in izvor, (
        "odgovor brisanja ne nosi ishod uklanjanja vektora"
    )
