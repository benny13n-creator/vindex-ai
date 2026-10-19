# -*- coding: utf-8 -*-
"""NS4 — ispravke po nezavisnom pregledu commita 2388df33. Svaki test je pao na tom commitu.

R1  Promena SAMO vrste spora (isti ishod, isti faktori) nije preračunavala `case_patterns`: `isti_ishod` je
    gledao samo ishod i faktore, pa je doprinos ostajao u staroj vrsti, a nova ga nije dobila.
R2  Pravilo važenja overe (`services/law_brain.vazece_overe`) nije tražilo `pinecone_indexed=True`: posle
    NEPOTPUNOG upisa nacrta u indeks (deo delova upisan, red `approved`, `pinecone_indexed=False`) upisani delovi
    su se u RAG-u i Law Brain pretrazi servirali kao kompletan, overen izvor.
R3  Slični predmeti su model vezivali po prvih 8 znakova id-a: predmeti sa istim prefiksom su se slivali, pa je
    JEDAN predmet brojan kao četiri (uzorak 4, „4 sličnih predmeta").
R4  Greška čitanja baze u sličnim predmetima vraćala je isti odgovor kao prazna istorija („nema predmeta").

Bez mreže: baza u memoriji (NS008), Pinecone i model su zamenjeni.
"""
import asyncio
import json
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.learning as L
import tests.ns005_harness as h5
import tests.ns008_fake as f8
from services.law_brain import vazece_overe
from tests import ns008_scenario as sc

PA = "aaaaaaaa-3333-4000-8000-00000000000a"


# ─── R1: promena vrste spora bez promene ishoda ─────────────────────────────────────────────────────

@pytest.fixture
def ishodi(monkeypatch):
    k, baza = f8.pripremi(monkeypatch, {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "A1", "status": "aktivan", "tip": "radni"}],
        "outcome_log": [], "case_patterns": [], "recommendation_log": [], "lessons_learned": [],
        "predmet_hronologija": [], "events": [], "case_actions": [], "v2_mutation_idempotency": [],
    })
    yield k, baza
    f8.ocisti()


def _posalji(k, ishod, faktori):
    r = k.post("/api/learning/outcome", headers=f8.zaglavlje("A"),
               json={"predmet_id": PA, "ishod": ishod, "presudni_faktori": faktori})
    assert r.status_code == 200, r.text
    return r.json()


def _obrasci(baza, tip):
    return {r["faktor"]: (r["pobede"], r["porazi"], r["ukupno"]) for r in baza.tabele["case_patterns"]
            if r["tip_spora"] == tip and (r["pobede"] or r["porazi"] or r["ukupno"])}


def test_r1_promena_samo_vrste_spora_premesta_doprinos(ishodi):
    k, baza = ishodi
    _posalji(k, "pobeda", ["svedoci", "vestacenje"])
    next(p for p in baza.tabele["predmeti"] if p["id"] == PA).update({"tip": "porodicni", "status": "aktivan"})
    _posalji(k, "pobeda", ["vestacenje", "svedoci"])          # isti ishod, isti faktori (drugi redosled)
    assert [o["tip_spora"] for o in baza.tabele["outcome_log"]] == ["porodicni"], "jedan ishod, nova vrsta"
    assert _obrasci(baza, "radni") == {}, "doprinos ostao u staroj vrsti spora"
    assert _obrasci(baza, "porodicni") == {"svedoci": (1, 0, 1), "vestacenje": (1, 0, 1)}
    kljucevi = [(r["tip_spora"], r["faktor"]) for r in baza.tabele["case_patterns"]]
    assert len(kljucevi) == len(set(kljucevi)), "dupli red faktora"


def test_r1_kontrola_isto_slanje_ne_dira_obrasce(ishodi):
    k, baza = ishodi
    _posalji(k, "pobeda", ["svedoci"])
    pre = [dict(r) for r in baza.tabele["case_patterns"]]
    assert _posalji(k, "pobeda", ["svedoci"])["ponovljen_ishod"] is True
    assert baza.tabele["case_patterns"] == pre


# ─── R2: nepotpun upis u indeks nije overen izvor ───────────────────────────────────────────────────

P1, P2 = "aaaaaaaa-6666-4000-8000-000000000001", "aaaaaaaa-6666-4000-8000-000000000002"


@pytest.mark.parametrize("red,predmet,vazi", [
    ({"status": "approved", "is_lawyer_approved": True, "pinecone_indexed": True}, P1, True),
    ({"status": "approved", "is_lawyer_approved": True, "pinecone_indexed": False}, P1, False),
    ({"status": "approved", "is_lawyer_approved": True}, P1, False),                 # stanje nepoznato
    ({"status": "approved", "is_lawyer_approved": True, "pinecone_indexed": "true"}, P1, False),
    ({"status": "rejected", "is_lawyer_approved": False, "pinecone_indexed": True}, P1, False),
    ({"status": "pending", "is_lawyer_approved": False, "pinecone_indexed": True}, P1, False),
    ({"status": "approved", "is_lawyer_approved": True, "pinecone_indexed": True}, P2, False),  # tuđ predmet
], ids=["indeksiran", "nepotpun", "bez-podatka", "string", "odbijen", "na-cekanju", "pozajmljen"])
def test_r2_overa_vazi_samo_za_potpuno_indeksiran(red, predmet, vazi):
    b = h5.Baza({"staging_memory": [{"id": "s", "predmet_id": P1, **red}]})
    assert ("s" in vazece_overe(b, [("s", predmet)])) is vazi


@pytest.fixture
def odobrenje(monkeypatch):
    k, b = f8.pripremi(monkeypatch, sc.tabele())
    import uploaded_doc.ingest as ing
    st = {"rezim": "potpun", "pozivi": 0}

    def _ingest(manifest, *a, **kw):
        st["pozivi"] += 1
        if st["rezim"] == "izuzetak":
            raise RuntimeError("pinecone 503 posle dela upisa (test)")
        return manifest.total_chunks - (1 if st["rezim"] == "nepotpun" else 0)
    monkeypatch.setattr(ing, "ingest_session", _ingest)
    try:
        from shared.rate import limiter
        monkeypatch.setattr(limiter, "enabled", False)
    except Exception:
        pass
    yield k, b, st
    f8.ocisti()


def _vektor(predmet=None, parent=None):
    return SimpleNamespace(id="v-s", score=0.95, metadata={
        "text": "Overena tužba — poništaj rešenja o otkazu, obrazloženje dovoljno dugo za prikaz.",
        "predmet_id": predmet or sc.OLD1, "type": "draft_final", "origin": "LAWYER_VERIFIED",
        "parent_id": parent or sc.S_TUZBA, "chunk_index": 0, "source_filename": "Nacrt",
        "article_label": "", "created_at": "2026-10-18"})


def _rag(b, uid, vektor):
    """RAG kancelarijska grana kroz stvaran `retrieve_documents`; ACL korisnika iz stvarnog `rag_acl`."""
    import shared.deps as deps
    import tests.test_bu004_injection_chunk_quarantine as Q
    from shared.rag_acl import dozvoljeni_predmeti
    acl = tuple(dozvoljeni_predmeti(b, uid))
    with patch.object(deps, "_get_supa", return_value=b):
        docs, _ = Q._retrieve(Q._Index(vlasnicki=[vektor]), acl=acl, ns=Q.NS)
    return any("Overena tužba" in d for d in docs)


def _odobri(k):
    r = k.post(f"/api/staging/{sc.S_TUZBA}/approve", headers=f8.zaglavlje("A"))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("rezim", ["nepotpun", "izuzetak"])
def test_r2_nepotpun_upis_se_ne_servira_kao_overen_izvor(odobrenje, rezim):
    k, b, st = odobrenje
    st["rezim"] = rezim
    d = _odobri(k)
    assert st["pozivi"] == 1 and d["indexed"] is False and d["razlog"] == "INDEKSIRANJE_NIJE_USPELO"
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == sc.S_TUZBA)
    assert (red["status"], red["is_lawyer_approved"], red["pinecone_indexed"]) == ("approved", True, False)
    assert not _rag(b, "uid-A", _vektor()), "delimično upisan nacrt serviran kao overen izvor"


def test_r2_poruka_ne_tvrdi_sigurnu_nepretrazivost(odobrenje):
    k, _, st = odobrenje
    st["rezim"] = "nepotpun"
    p = _odobri(k)["poruka"].lower()
    assert "nije pretraživ" not in p, "tvrdnja koju sistem ne može da garantuje (delovi su možda upisani)"
    assert "nije potvrđen" in p and "dodat u bazu znanja" not in p


def test_r2_potpun_upis_ostaje_dostupan_vlasniku(odobrenje):
    k, b, st = odobrenje
    d = _odobri(k)
    assert d["indexed"] is True
    assert _rag(b, "uid-A", _vektor()), "kontrola: odobren i potpuno indeksiran nacrt se servira"


def test_r2_potpun_upis_nedostupan_neovlascenom_i_pozajmljen(odobrenje):
    k, b, _ = odobrenje
    _odobri(k)
    assert not _rag(b, "uid-B", _vektor()), "kolega bez delegiranja dobio tuđ overen nacrt"
    assert not _rag(b, "uid-A", _vektor(predmet=sc.CUR)), "overa pozajmljena drugom predmetu"


def test_r2_neodobren_nacrt_nije_izvor(odobrenje):
    _, b, _ = odobrenje
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == sc.S_NACRT2)
    red["pinecone_indexed"] = True                       # i kad bi vektor postojao
    assert not _rag(b, "uid-A", _vektor(parent=sc.S_NACRT2))


def test_r2_greska_baze_fail_closed(odobrenje):
    k, b, _ = odobrenje
    _odobri(k)
    b.greske["staging_memory"] = Exception("db down (test)")
    assert not _rag(b, "uid-A", _vektor())


# ─── R3 / R4: slični predmeti ──────────────────────────────────────────────────────────────────────

TEK = "aaaaaaaa-4444-4000-8000-000000000001"


def _razliciti(i):
    return f"{i + 1:x}{i + 1:x}{i + 1:x}{i + 1:x}c0de-4444-4000-8000-0000000001{i:02d}"


def _isti_prefiks(i):
    return f"aaaaaaaa-4444-4000-8000-0000000001{i:02d}"


@pytest.fixture
def slicni(monkeypatch):
    def napravi(n, ids):
        zatv = [{"id": ids(i), "user_id": "uid-A", "naziv": f"Zatvoren {i}", "status": "zatvoren", "tip": "radni"}
                for i in range(n)]
        k, baza = f8.pripremi(monkeypatch, {
            "predmeti": [{"id": TEK, "user_id": "uid-A", "naziv": "Tekući", "status": "aktivan", "tip": "radni",
                          "opis": "otkaz"}] + zatv,
            "outcome_log": [{"predmet_id": p["id"], "user_id": "uid-A", "ishod": "pobeda",
                             "presudni_faktori": ["svedoci"], "tip_spora": "radni"} for p in zatv],
        })
        monkeypatch.setattr(L, "_get_supa", lambda: baza)

        async def _bez_naplate(*_a, **_k):
            return None
        monkeypatch.setattr(L.UsageService, "consume", _bez_naplate)
        return baza, zatv
    yield napravi
    f8.ocisti()


def _model_vraca(monkeypatch, stavke):
    monkeypatch.setenv("OPENAI_API_KEY", "test-nije-pravi")
    sadrzaj = json.dumps({"rezultati": stavke})
    promptovi = []

    def _lazni(_client, **kw):
        promptovi.append(kw["messages"][-1]["content"])
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=sadrzaj))])
    monkeypatch.setattr(L, "_pozovi_learning_api", _lazni)
    return promptovi


def _zovi():
    from tests.test_ns4_t3_slicni_predmeti_iskreno import _lazni_request
    return asyncio.run(L.slicni_predmeti(predmet_id=TEK, request=_lazni_request(), user={"user_id": "uid-A"}))


def test_r3_isti_prefiks_ne_umnozava_jedan_predmet(slicni, monkeypatch):
    _, zatv = slicni(4, _isti_prefiks)
    _model_vraca(monkeypatch, [{"predmet_id_prefix": p["id"][:8], "slicnost": 90, "razlog": "isti tip"} for p in zatv])
    rez = _zovi()
    ids = [x["predmet_id"] for x in rez["slicni_predmeti"]]
    assert len(ids) == len(set(ids)), f"jedan predmet brojan više puta: {ids}"
    assert rez["uzorak"] == len(set(ids)) and rez["uzorak"] < 4
    assert rez["stanje"] == "NEDOVOLJNO_PODATAKA", "dvosmislena identifikacija dala je zbirni zaključak"
    assert ids == [], "dvosmislen prefiks pripisan jednom (proizvoljnom) predmetu — lažna sličnost"


def test_r3_uzorak_cetiri_razlicita_predmeta(slicni, monkeypatch):
    _, zatv = slicni(4, _razliciti)
    assert len({p["id"][:8] for p in zatv}) == 4
    promptovi = _model_vraca(monkeypatch, [{"predmet_id": p["id"], "slicnost": 90, "razlog": "isti tip"} for p in zatv])
    rez = _zovi()
    assert all(f"predmet_id={p['id']} " in promptovi[0] for p in zatv), "model ne dobija pun identitet predmeta"
    assert sorted(x["predmet_id"] for x in rez["slicni_predmeti"]) == sorted(p["id"] for p in zatv)
    assert rez["uzorak"] == 4 and rez["stanje"] == "OPIS_ISTORIJE" and "nije predviđanje" in rez["strategija_preporuka"]


def test_r3_ponovljen_isti_predmet_u_odgovoru_modela_broji_se_jednom(slicni, monkeypatch):
    _, zatv = slicni(4, _razliciti)
    _model_vraca(monkeypatch, [{"predmet_id": zatv[0]["id"], "slicnost": 90, "razlog": "x"}] * 4)
    rez = _zovi()
    assert rez["uzorak"] == 1 and rez["stanje"] == "NEDOVOLJNO_PODATAKA"


def test_r3_nepoznat_identitet_ne_stvara_slicnost(slicni, monkeypatch):
    slicni(4, _razliciti)
    _model_vraca(monkeypatch, [{"predmet_id": "ffffffff-0000-4000-8000-000000000000", "slicnost": 99, "razlog": "x"},
                               {"predmet_id_prefix": "", "slicnost": 99, "razlog": "x"}])
    rez = _zovi()
    assert rez["slicni_predmeti"] == [] and rez["uzorak"] == 0


@pytest.mark.parametrize("tabela", ["predmeti", "outcome_log"])
def test_r4_greska_citanja_nije_prazna_istorija(slicni, monkeypatch, tabela):
    baza, _ = slicni(4, _razliciti)
    izvorni = baza.table

    def _pada_posle_tekuceg(ime):
        u = izvorni(ime)
        if ime == tabela:
            iz = u.execute

            def execute():
                if ime == "outcome_log" or any(f[0] == "neq" for f in u.filt):
                    raise Exception("db down (test)")
                return iz()
            u.execute = execute
        return u
    monkeypatch.setattr(baza, "table", _pada_posle_tekuceg)
    with pytest.raises(HTTPException) as e:
        _zovi()
    assert e.value.status_code == 503


def test_r4_kontrola_prazna_istorija_je_uspesno_procitana(slicni):
    slicni(0, _razliciti)
    rez = _zovi()
    assert rez["stanje"] == "NEDOVOLJNO_PODATAKA" and rez["uzorak"] == 0
