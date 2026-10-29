# -*- coding: utf-8 -*-
"""CG001 — PR #60 ciljane korekcije posle pregleda (Task A–D)."""
import asyncio
import copy

import pytest

from shared.genome_contract import promene_genome
from shared.issue_v2 import KLJUC_VERZIJE_OPAZANJA
from tests.ns006_fake import zaglavlje
from tests.test_cg001_incident_uplata import A, B, C, D, KONTR, P, dokazi_v2
from tests import test_cg001_lanac as L
from tests.test_cg001_lanac import lanac  # noqa: F401 — fixture

PAT_NIJE_POTVRDJEN = "kontinuitet nije potvrđen"
PAT_NIJE_PROVEREN = "kontinuitet nije proveren"


# ── Task A — neuspelo čitanje ≠ potvrđen kontinuitet ────────────────────────────────────────────────

@pytest.mark.parametrize("sa_oznakom", [False, True])
@pytest.mark.parametrize("pad", ["v2", "predmet", "predmet_nema_reda"])
def test_A_neuspelo_citanje_je_nije_provereno_na_svim_povrsinama(lanac, monkeypatch, pad, sa_oznakom):
    otvori, _ = lanac
    k, baza = L._zateceno(otvori, L._g(2, [A, C, D], "kriticna"), razlog_sa_oznakom=sa_oznakom)
    upisan = copy.deepcopy(baza.tabele["case_actions"][0])
    import services.v2_projection as vp
    if pad == "v2":
        async def _pad(*a, **kw):
            raise RuntimeError("predmet_contradictions nedostupan")
        monkeypatch.setattr(vp, "ucitaj_v2_kontradikcije", _pad)
    else:
        prava = baza.table

        class _Upit:
            def __init__(self, u):
                self._u = u

            def __getattr__(self, ime):
                atr = getattr(self._u, ime)
                if not callable(atr):
                    return atr
                return lambda *a, **kw: _Upit(atr(*a, **kw)) if ime != "execute" else _izvrsi(self._u)

        def _izvrsi(u):
            if pad == "predmet":
                raise RuntimeError("predmeti nedostupan")
            r = u.execute()
            r.data = None
            return r

        def _table(ime):
            q = prava(ime)
            # samo upit read-modela (`id,user_id,case_dna,observation_version`) pada; vlasništvo/lista prolaze
            if ime == "predmeti":
                orig_select = q.select

                def _select(kolone, *a, **kw):
                    s = orig_select(kolone, *a, **kw)
                    return _Upit(s) if "observation_version" in kolone and "user_id" in kolone else s
                q.select = _select
            return q
        monkeypatch.setattr(baza, "table", _table)
    pred, wl, ws, _ = L._sve_povrsine(k)
    for a in (pred.json()["akcije"][0], wl[0]):
        assert PAT_NIJE_PROVEREN in a["razlog"] and PAT_NIJE_POTVRDJEN not in a["razlog"]
        assert a["dokaz"]["kontinuitet"] == "NEPOZNAT"
        assert (a["id"], a["prioritet"], a["dokaz"]["claim_ids"]) == (upisan["id"], "medium", upisan["dokaz"]["claim_ids"])
    assert PAT_NIJE_PROVEREN in ws[0]["naslov"] and ws[0]["prioritet"] == "medium"
    assert baza.tabele["case_actions"][0] == upisan                                     # trajni red netaknut


# ── Task B — AI kontekst ────────────────────────────────────────────────────────────────────────────

def test_B_ai_kontekst_nosi_isti_signal_kao_radna_lista(lanac):
    otvori, pozivi = lanac
    k, baza = L._zateceno(otvori, L._g(2, [A, C, D], "kriticna"))
    from shared.case_context import build_case_context
    cc = asyncio.run(build_case_context(P, L.UID, baza, include_documents=False))
    [a] = cc["active_actions"]["value"]
    top = cc["top_open_action"]["value"]
    for x in (a, top):
        assert PAT_NIJE_POTVRDJEN in x["razlog"] and x["dokaz"]["kontinuitet"] == "NIJE_POTVRDJEN"
        assert x["prioritet"] == "medium" and x["dokaz"]["claim_ids"] == sorted([A, B])
    assert "kontinuitet" not in baza.tabele["case_actions"][0]["razlog"] and pozivi == []    # bez upisa, bez modela


def test_B_ai_kontekst_tudjeg_predmeta_ostaje_prazan(lanac):
    otvori, _ = lanac
    k, baza = L._zateceno(otvori, L._g(2, [A, C, D], "kriticna"))
    from shared.case_context import build_case_context
    cc = asyncio.run(build_case_context(P, "uid-B", baza, include_documents=False))
    assert not (cc.get("active_actions") or {}).get("value")


# ── Task C — istorija ne implicira spajanje ─────────────────────────────────────────────────────────

def _g(*skupovi, verzija):
    return {"verzija": verzija, "kontradikcije": [{"claim_ids": sorted(s), "relation_type": "cinjenica_cinjenica",
                                                    "issue_label": f"Tačka {i + 1}"} for i, s in enumerate(skupovi)]}


def _kontr(rez):
    return [p for p in rez["promene"] if p["vrsta"].startswith("kontradikcija")]


def test_C_dve_nezavisne_stare_i_jedno_novo_nisu_spojene():
    rez = promene_genome(_g({A, B}, {A, C}, verzija=1), _g({A, D}, verzija=2))
    [p] = _kontr(rez)                                             # jedna nerazrešena promena, ne dve „iste“
    assert p["vrsta"] == "kontradikcija_promenjena" and p["oznaka"] == "!"
    assert p["staro"] == sorted([sorted([A, B]), sorted([A, C])]) and p["novo"] == [sorted([A, D])]   # skupovi zasebno
    assert "nije utvrđeno" in p["opis"] and "Tačka 1" in p["opis"] and "Tačka 2" in p["opis"]
    assert sorted(p["tvrdnje"]) == sorted([A, B, C, D])


def test_C_jedna_stara_i_dva_nova_nisu_spojena_u_uniju():
    rez = promene_genome(_g({A, B}, verzija=1), _g({A, C}, {B, D}, verzija=2))
    [p] = _kontr(rez)
    assert p["staro"] == [sorted([A, B])] and p["novo"] == sorted([sorted([A, C]), sorted([B, D])])
    # obrnut redosled ulaza → isti izlaz
    assert _kontr(promene_genome(_g({A, B}, verzija=1), _g({B, D}, {A, C}, verzija=2)))[0]["novo"] == p["novo"]
    assert "nije utvrđeno" in p["opis"]


def test_C_jedan_na_jedan_ostaje_kako_je_bio():
    rez = promene_genome(_g({A, B}, verzija=1), _g({A, C, D}, verzija=2))
    [p] = _kontr(rez)
    assert p["staro"] == sorted([A, B]) and p["novo"] == sorted([A, C, D])
    assert p["opis"] == "Povezane tvrdnje su se promenile; kontinuitet sporne tačke nije potvrđen: Tačka 1"


def test_C_nepovezane_ostaju_dodata_i_nestala():
    rez = promene_genome(_g({A, B}, {C, D}, verzija=1), _g({A, C}, verzija=2))
    vrste = sorted(p["vrsta"] for p in _kontr(rez))
    assert vrste == ["kontradikcija_promenjena"]                 # {A,C} dodiruje obe → jedna nerazrešena grupa
    rez2 = promene_genome(_g({A, B}, verzija=1), _g({C, D}, verzija=2))
    assert sorted(p["vrsta"] for p in _kontr(rez2)) == ["kontradikcija_dodata", "kontradikcija_nestala"]


# ── Task D — tvrdnja istog predmeta, drugog korisnika ───────────────────────────────────────────────

X = "99999999-0000-4000-8000-000000000099"


def test_D_tudja_tvrdnja_istog_predmeta_ne_utice_na_odluku(lanac):
    """Opažanje {A, X}, X = živ red sa istim predmet_id, ali user_id drugog korisnika. Prikaz ga ne vidi (opažanje {A}
    nije skup odluke → bez oznake); read-model akcija i reconcile moraju dati ISTU odluku."""
    otvori, pozivi = lanac
    g = L._g(2, [A, X], "kriticna")
    g[KLJUC_VERZIJE_OPAZANJA] = 1
    k, baza = L._zateceno(otvori, g)
    baza.tabele["predmet_dokazi"].append({**dokazi_v2()[0], "id": X, "user_id": "uid-B", "tvrdnja": "tuđa tvrdnja"})
    pred, wl, ws, gv = L._sve_povrsine(k)
    assert "kontinuitet" not in gv.json()["kontradikcije"]["aktivne"][0]          # prikaz
    [a] = pred.json()["akcije"]
    assert "kontinuitet" not in a["dokaz"] and a["razlog"] == L.LABEL              # read-model
    from services.case_evolution import _compute_target_actions
    [t] = [x for x in asyncio.run(_compute_target_actions(P)) if x["tip"] == "RAZRESITI_KONTRADIKCIJU"]
    assert "kontinuitet" not in t["dokaz"] and t["razlog"] == L.LABEL              # reconcile


def test_D_tudja_sporna_tacka_istog_predmeta_ne_ulazi_u_reconcile(lanac):
    """Sporna tačka drugog korisnika zakačena za isti predmet (odbrana u dubinu iza GUARD-a paketnog RPC-a): reconcile
    je ne projektuje kao radnju vlasnika i ne koristi je za odluku o kontinuitetu vlasnikove teme."""
    otvori, _ = lanac
    g = L._g(2, [A, B, C], "manja")                    # nadskup vlasnikove teme = nastavak
    g[KLJUC_VERZIJE_OPAZANJA] = 1
    k, baza = L._zateceno(otvori, g)
    baza.tabele["predmet_issues"].append({"id": "i-tudja", "predmet_id": P, "user_id": "uid-B", "label": "x",
                                          "status": "DISCOVERED"})
    baza.tabele["predmet_contradictions"].append({"id": "k-tudja", "issue_id": "i-tudja", "relation_type": "cinjenica_cinjenica",
                                                  "state": "OPEN", "tezina": "kriticna"})
    baza.tabele["predmet_contradiction_claims"] += [{"id": f"t-{x[:3]}", "contradiction_id": "k-tudja", "dokaz_id": x,
                                                     "removed_at": None} for x in (A, C)]
    from services.case_evolution import _compute_target_actions
    akcije = [x for x in asyncio.run(_compute_target_actions(P)) if x["tip"] == "RAZRESITI_KONTRADIKCIJU"]
    assert [x["dokaz"]["source_id"] for x in akcije] == [KONTR]                  # samo vlasnikova
    assert "kontinuitet" not in akcije[0]["dokaz"] and akcije[0]["prioritet"] == "medium"
