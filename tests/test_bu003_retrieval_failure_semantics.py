# -*- coding: utf-8 -*-
"""B-U-003 — pad Pinecone UPITA nije prazan rezultat.

PRE-STATE (dokazano determinističkom reprodukcijom nad `6bf8070`, 2026-08-21):
  `_pretraga_vec` / `_semanticka_pretraga` hvatali su SVAKI izuzetak i vraćali
  `[]`. Pad upita bio je zato bajt-identičan uspešnoj pretrazi sa nula
  rezultata: `retrieve_documents` je vraćao `izvori_neuspeh=[]`, `ask_agent`
  nije zvao model i advokatu je isporučivao

      „Nemam pouzdan odgovor na ovo pitanje u trenutnoj bazi zakona.
       Mogući razlozi: pitanje izlazi iz indeksiranih oblasti…"

  — tvrdnju o SADRŽAJU srpskog prava, izvedenu iz pretrage koja se nikada nije
  izvršila. Za pad EMBEDDINGA je ista klasa greške bila popravljena (Faza 0 u
  `retrieve_documents`), za pad UPITA nije.

CENTRALNI INVARIANT: FAILURE != EMPTY RESULT.

Granica koju ovi testovi moraju da razlikuju:
  upit IZVRŠEN + 0 rezultata   -> postojeća „nema pronađenog izvora" semantika
  upit NIJE IZVRŠEN (izuzetak) -> tehnička nedostupnost, bez ijedne tvrdnje o pravu

Downstream grana u `main.py` (`IZVOR_ZAKON in izvori_neuspeh`) je POSTOJALA i
bila je ispravna — fail-closed, bez poziva modelu, uz očuvanje činjenica iz
dokumenta (B4-M2). Nedostajao je samo signal iz upitnog sloja; zato je popravka
zatvorena u `app/services/retrieve.py` i `main.py` NIJE menjan.
"""
import re
from types import SimpleNamespace

import pytest
from unittest.mock import MagicMock, patch

import app.services.retrieve as R
import main as M

PITANJE = "Koji je rok za žalbu na presudu u parničnom postupku?"

# Rečenice kojima sistem tvrdi nešto o SADRŽAJU pravnog korpusa. Nijedna ne sme
# izaći iz upita koji nije izvršen.
TVRDNJE_O_KORPUSU = (
    "Nemam pouzdan odgovor",
    "izlazi iz indeksiranih oblasti",
    "nema relevantnog",
)


class _IndexPada:
    """Pinecone koji je nedostupan — svaki upit diže izuzetak."""

    def __init__(self, greska=None):
        self._g = greska or RuntimeError("pinecone: connection reset")

    def query(self, *a, **k):
        raise self._g

    def fetch(self, *a, **k):
        raise self._g


class _IndexPrazan:
    """Pinecone koji RADI, ali za ovaj upit nema nijedan pogodak."""

    def query(self, *a, **k):
        return SimpleNamespace(matches=[])

    def fetch(self, *a, **k):
        return SimpleNamespace(vectors={})


def _match(i, score, clan, zakon, tekst):
    return SimpleNamespace(id=i, score=score, metadata={
        "article": clan, "law": zakon, "text": tekst, "type": "zakon"})


class _IndexSaRezultatima:
    def query(self, *a, **k):
        return SimpleNamespace(matches=[
            _match("z1", 0.93, "Član 401", "Zakon o parničnom postupku",
                   "Član 401\nRok za žalbu na presudu iznosi 15 dana od dana dostavljanja prepisa presude."),
            _match("z2", 0.81, "Član 402", "Zakon o parničnom postupku",
                   "Član 402\nŽalba se podnosi sudu koji je izrekao prvostepenu presudu."),
        ])

    def fetch(self, *a, **k):
        return SimpleNamespace(vectors={})


def _retrieve(index, embed_pada=False):
    """Poziva pravi `retrieve_documents` sa zamenjenim Pinecone-om.

    Svi LLM-ovi u lancu (multi-query, HyDE, GPT-ekspanzija, CRAG) su isključeni
    — mere se granice greške, ne kvalitet prisećanja, i test ne sme da zove
    naplativi API.
    """
    ugradi = (patch.object(R, "_ugradi_query", side_effect=RuntimeError("embed down"))
              if embed_pada else patch.object(R, "_ugradi_query", return_value=[0.0] * 8))
    with ugradi, \
         patch.object(R, "_get_index", return_value=index), \
         patch.object(R, "_vlasnicki_opseg_iz_konteksta", return_value=(None, None)), \
         patch.object(R, "_dekomponuj_query", return_value=[]), \
         patch.object(R, "decompose_query", return_value=[]), \
         patch.object(R, "_generiši_hyde", return_value=""), \
         patch.object(R, "_prosiri_pretragu_crag", return_value=[]), \
         patch.object(R, "_prosiri_query_gpt_wrapper", return_value=[]),          patch.object(R, "_cohere_rerank", side_effect=lambda q, m, k=5: list(m)[:k]),          patch.object(R, "_crag_petlja",
                      side_effect=lambda q, d, z, v, k, max_iter=1: d):
        # `_cohere_rerank` pada nazad na `_gpt_rerank`, a `_crag_petlja` zove
        # `_oceni_relevantnost` — oba su naplativi pozivi. Mere se granice
        # greške, ne kvalitet rerankinga/CRAG-a; oba se zamenjuju identitetom
        # (isto što urade kad je ocena RELEVANTNO).
        return R.retrieve_documents(PITANJE, k=5)


def _kroz_ask_agent(docs, meta):
    """Provlači retrieval rezultat kroz pravi `ask_agent` i vraća
    (odgovor_dict, koliko_puta_je_model_pozvan)."""
    llm = MagicMock(return_value='{"pravni_zakljucak":"x"}')
    with patch.object(M, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(M, "retrieve_sudska_praksa", return_value=[]), \
         patch.object(M, "retrieve_misljenja", return_value=[]), \
         patch.object(M, "_pozovi_openai", side_effect=llm), \
         patch.object(M, "_supa_cache_get", return_value=None), \
         patch.object(M, "_supa_cache_set", return_value=None):
        M._CACHE.clear()
        try:
            rez = M.ask_agent(PITANJE)
        finally:
            M._CACHE.clear()
    return rez, llm.call_count


def _tekst(rez):
    return (rez.get("data") or rez.get("message") or "")


# ── 1. Pad upita -> RETRIEVAL_FAILURE, nikako EMPTY ──────────────────────────

KVAROVI = {
    "connection_reset": RuntimeError("pinecone: connection reset"),
    "timeout": TimeoutError("read timed out"),
    "503": Exception("PineconeException: 503 Service Unavailable"),
    "auth": Exception("PineconeApiKeyError: invalid api key"),
}


@pytest.mark.parametrize("kvar", sorted(KVAROVI))
def test_1_pad_upita_je_FAILURE_a_ne_EMPTY(kvar):
    docs, meta = _retrieve(_IndexPada(KVAROVI[kvar]))
    assert R.IZVOR_ZAKON in (meta.get("izvori_neuspeh") or []), \
        "pad upita nije prijavljen — nerazlučiv je od prazne pretrage (%s)" % kvar
    assert docs == []


# ── 2. Model NE sme biti pozvan ──────────────────────────────────────────────

def test_2_model_nije_pozvan_i_nema_tvrdnje_o_korpusu():
    docs, meta = _retrieve(_IndexPada())
    rez, pozivi = _kroz_ask_agent(docs, meta)
    assert pozivi == 0, "model je pozvan iako pravni korpus nije pretražen"
    assert rez.get("retrieval_unavailable") is True
    t = _tekst(rez)
    for tvrdnja in TVRDNJE_O_KORPUSU:
        assert tvrdnja not in t, "pao upit proizveo tvrdnju o korpusu: %r" % tvrdnja
    assert "ne može da pretraži pravni korpus" in t
    assert "NIJE tvrdnja da odgovor ne postoji" in t
    # Nijedan pravni izvor ne sme biti pripisan odgovoru.
    assert not (rez.get("izvori") or [])


# ── 3. GRANICA: uspešan upit + 0 rezultata ostaje EMPTY ──────────────────────

def test_3_uspesan_upit_sa_nula_rezultata_JESTE_prazan_rezultat():
    """Bez ovoga bi „popravka" koja sve proglašava kvarom prolazila kao ispravna."""
    docs, meta = _retrieve(_IndexPrazan())
    assert (meta.get("izvori_neuspeh") or []) == [], \
        "izvršen upit sa nula pogodaka pogrešno prijavljen kao kvar izvora"
    assert docs == []


def test_3b_prazan_rezultat_zadrzava_postojecu_no_results_semantiku():
    docs, meta = _retrieve(_IndexPrazan())
    rez, _ = _kroz_ask_agent(docs, meta)
    t = _tekst(rez)
    assert rez.get("retrieval_unavailable") is not True
    assert "Nemam pouzdan odgovor" in t, \
        "postojeća no-results poruka je izgubljena: %r" % t[:200]


def test_3c_pad_i_prazno_daju_RAZLICIT_odgovor():
    """Srce B-U-003: ova dva stanja su ranije bila bajt-identična."""
    rez_pad, _ = _kroz_ask_agent(*_retrieve(_IndexPada()))
    rez_prazno, _ = _kroz_ask_agent(*_retrieve(_IndexPrazan()))
    assert _tekst(rez_pad) != _tekst(rez_prazno)
    assert rez_pad.get("retrieval_unavailable") is True
    assert rez_prazno.get("retrieval_unavailable") is not True


# ── 4. Uspešan upit sa rezultatima — normalan tok ────────────────────────────

def test_4_uspesan_retrieval_sa_rezultatima_ne_dira_nista():
    docs, meta = _retrieve(_IndexSaRezultatima())
    assert (meta.get("izvori_neuspeh") or []) == []
    assert docs, "rezultati su izgubljeni"
    assert meta.get("top_score", 0) > 0
    rez, pozivi = _kroz_ask_agent(docs, meta)
    assert pozivi >= 1, "model nije pozvan iako je korpus uspešno pretražen"
    assert rez.get("retrieval_unavailable") is not True


# ── 5. Pad embeddinga — postojeći signal ostaje ──────────────────────────────

def test_5_pad_embeddinga_zadrzava_postojeci_signal():
    docs, meta = _retrieve(_IndexSaRezultatima(), embed_pada=True)
    ne = meta.get("izvori_neuspeh") or []
    assert R.IZVOR_ZAKON in ne and R.IZVOR_DOKUMENTI in ne, ne
    assert docs == []
    rez, pozivi = _kroz_ask_agent(docs, meta)
    assert pozivi == 0
    assert rez.get("retrieval_unavailable") is True


# ── 6. Delimičan pad: primarni prošao, rezultati postoje -> NIJE kvar ────────

def test_6_pad_EKSPANZIJE_ne_obara_ispravan_odgovor():
    """Fail-closed ne sme da postane fail-useless: pad dodatnog, širećeg upita
    dok su primarni prošli i rezultati postoje NE znači da korpus nije
    pretražen. Da ovo nije tako, jedan prolazni blip oborio bi savršeno dobar
    odgovor u odbijanje — nov kvar, ne popravka."""
    neuspeh = []
    with patch.object(R, "_get_index", return_value=_IndexPada()),          patch.object(R, "_ugradi_query", return_value=[0.0] * 8):
        R._semanticka_pretraga("ekspanzija", 3, "KZ", neuspeh=neuspeh)
    assert neuspeh == [R.IZVOR_ZAKON], "helper ne beleži pad kad mu se preda kanal"
    # ...ali `_jedan_retrieval_krug` taj kanal predaje SAMO primarnim upitima:
    import inspect
    src = inspect.getsource(R._jedan_retrieval_krug)
    assert src.count("neuspeh=neuspeh_primarni") == 2, \
        "broj upita koji šalju signal se promenio — v. _ZAKON_PRIMARNIH_UPITA"


def test_broj_primarnih_upita_prati_kod():
    """`_ZAKON_PRIMARNIH_UPITA` je jedini razlog zbog kog „svi primarni pali"
    uopšte može da bude tačno. Ako se u `_jedan_retrieval_krug` doda ili oduzme
    primarni upit a konstanta ne prati, signal tiho oslabi."""
    import inspect
    src = inspect.getsource(R._jedan_retrieval_krug)
    assert src.count("neuspeh=neuspeh_primarni") == R._ZAKON_PRIMARNIH_UPITA


# ── 7. Signal se ne pali bez razloga ─────────────────────────────────────────

def test_7_bez_ijednog_pada_kanal_ostaje_prazan():
    for index in (_IndexPrazan(), _IndexSaRezultatima()):
        _, meta = _retrieve(index)
        assert R.IZVOR_ZAKON not in (meta.get("izvori_neuspeh") or []), \
            "lažni kvar na zdravom indeksu: %r" % type(index).__name__


# ── 8. Podrazumevani pozivaoci nisu promenjeni ───────────────────────────────

def test_8_helperi_bez_kanala_rade_kao_i_pre():
    """`neuspeh` je opcion; svih ~8 postojećih pozivalaca ga ne prosleđuje i
    mora da dobije istu praznu listu kao ranije, bez izuzetka."""
    with patch.object(R, "_get_index", return_value=_IndexPada()):
        assert R._pretraga_vec([0.0] * 8, 5, None) == []
        with patch.object(R, "_ugradi_query", return_value=[0.0] * 8):
            assert R._semanticka_pretraga("x", 3, None) == []


# ── 9. Nijedan pravni zaključak iz pada ──────────────────────────────────────

def test_9_pad_ne_proizvodi_pravni_zakljucak():
    rez, _ = _kroz_ask_agent(*_retrieve(_IndexPada()))
    t = _tekst(rez)
    assert not re.search(r"[čc]lan\s*\d+", t, re.I), \
        "odgovor iz palog retrievala pominje konkretan član: %r" % t[:200]
    assert rez.get("top_article") == ""
    assert rez.get("top_law") == ""
