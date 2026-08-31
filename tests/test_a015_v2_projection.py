# -*- coding: utf-8 -*-
"""A015 — PROJEKCIJA V2 KONTRADIKCIJE (`services/v2_projection.py`).

Ovo je regresiona brava nad ODLUKAMA projekcije. Živi dokaz — stvarni RPC,
stvarne `case_actions`, stvarna `notifications` tabela, 12 paralelnih poziva —
izveden je zasebno i zapisan u `A015_V2_PROJECTION_REPORT.md` (20/20). Mock se
ovde nigde ne predstavlja kao dokaz persistence-a.

Ono što se ovde meri je ono što se može pokvariti tihom izmenom koda a da živi
sistem i dalje odgovara uredno: odakle dolazi identitet projekcije.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.v2_projection import (  # noqa: E402
    IZVOR_TIP,
    PREFIKS,
    TIP_AKCIJE,
    contradiction_id_iz_kljuca,
    je_v2_kljuc,
    projekcioni_kljuc,
    u_akcije,
    u_akciju,
    ucitaj_v2_kontradikcije,
    v2_akcije_za_predmet,
)
from shared.contradiction_identity import contradiction_dedupe_key  # noqa: E402

PRED = "11111111-1111-4111-8111-111111111111"
PRED_B = "22222222-2222-4222-8222-222222222222"
I1 = "aaaa0001-0000-4000-8000-000000000001"
I2 = "aaaa0002-0000-4000-8000-000000000002"
K1 = "cccc0001-0000-4000-8000-000000000001"
K2 = "cccc0002-0000-4000-8000-000000000002"
K3 = "cccc0003-0000-4000-8000-000000000003"
D1 = "dddd0001-0000-4000-8000-000000000001"
D2 = "dddd0002-0000-4000-8000-000000000002"


def _k(cid, issue_id=I1, label="razlika u datumu", rel="cinjenica_cinjenica",
       tezina="vazna", claims=("c1", "c2"), dokumenti=(D1, D2), state="OPEN"):
    return {"id": cid, "issue_id": issue_id, "issue_label": label, "relation_type": rel,
            "state": state, "tezina": tezina, "claim_ids": list(claims),
            "dokument_ids": list(dokumenti)}


# ═══════════════════════════════════════════════════════════════════════════
# 1. Ključ — jedini izvor je contradiction_id
# ═══════════════════════════════════════════════════════════════════════════

def test_kljuc_je_izveden_iz_contradiction_id():
    assert projekcioni_kljuc(K1) == f"{PREFIKS}{K1}"
    assert je_v2_kljuc(projekcioni_kljuc(K1))
    assert contradiction_id_iz_kljuca(projekcioni_kljuc(K1)) == K1


def test_kljuc_bez_id_je_greska_a_ne_prazan_string():
    for lose in (None, "", "   "):
        with pytest.raises(ValueError):
            projekcioni_kljuc(lose)


def test_dve_kontradikcije_istog_issue_a_imaju_RAZLICITE_kljuceve():
    """Jedna sporna tačka sme imati više kontradikcija (po `relation_type`).
    `issue_id` zato NIJE identitet kontradikcije."""
    a = u_akciju(_k(K1, issue_id=I1, rel="cinjenica_cinjenica"))
    b = u_akciju(_k(K2, issue_id=I1, rel="cinjenica_norma"))
    assert a["dedupe_key"] != b["dedupe_key"]
    assert a["dokaz"]["issue_id"] == b["dokaz"]["issue_id"]


def test_isti_dokumenti_ista_relacija_razlicit_spor_daju_razlicite_kljuceve():
    """A005, izražen na nivou projekcije."""
    akcije = u_akcije([
        _k(K1, issue_id=I1, label="datum", dokumenti=(D1, D2)),
        _k(K2, issue_id=I2, label="iznos", dokumenti=(D1, D2)),
    ])
    assert len({a["dedupe_key"] for a in akcije}) == 2
    # ...dok bi legacy kljuc bio identican:
    legacy = {contradiction_dedupe_key({"lokacija_1": "DOK-01 str.1", "lokacija_2": "DOK-02 str.1"})
              for _ in range(2)}
    assert len(legacy) == 1


def test_ista_labela_razlicit_contradiction_id_daju_razlicite_kljuceve():
    akcije = u_akcije([_k(K1, label="ista"), _k(K2, label="ista")])
    assert len({a["dedupe_key"] for a in akcije}) == 2


def test_kljuc_ne_sadrzi_nista_iz_LLM_teksta():
    a = u_akciju(_k(K1, label="Razlika u datumu prestanka radnog odnosa"))
    assert "Razlika" not in a["dedupe_key"]
    assert "DOK" not in a["dedupe_key"]
    assert a["dedupe_key"] == f"{PREFIKS}{K1}"


def test_isti_ulaz_daje_isti_kljuc_svaki_put():
    """Nema `uuid4()` u projekciji — inace bi svaki refresh pravio nov identitet."""
    kljucevi = {u_akciju(_k(K1))["dedupe_key"] for _ in range(20)}
    assert len(kljucevi) == 1


def test_legacy_kljuc_nije_V2_kljuc():
    assert not je_v2_kljuc(contradiction_dedupe_key(
        {"lokacija_1": "DOK-01", "lokacija_2": "DOK-02"}))
    assert contradiction_id_iz_kljuca("abc123") is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. Oblik akcije
# ═══════════════════════════════════════════════════════════════════════════

def test_akcija_nosi_eksplicitnu_vezu_na_domen():
    a = u_akciju(_k(K1))
    assert a["tip"] == TIP_AKCIJE
    assert a["dokaz"]["source_type"] == IZVOR_TIP
    assert a["dokaz"]["source_id"] == K1
    assert a["dokaz"]["issue_id"] == I1
    assert a["dokaz"]["relation_type"] == "cinjenica_cinjenica"


def test_provenijencija_i_clanovi_se_prenose():
    a = u_akciju(_k(K1, claims=("c2", "c1"), dokumenti=(D2, D1)))
    assert a["dokaz"]["claim_ids"] == sorted(["c1", "c2"])
    assert a["dokaz"]["dokument_ids"] == sorted([D1, D2])
    assert a["izvor_dokumenti"] == sorted([D1, D2])


def test_intra_dokumentna_kontradikcija_ima_jedan_dokument():
    a = u_akciju(_k(K1, dokumenti=(D1,)))
    assert a["izvor_dokumenti"] == [D1]
    assert a["dokaz"]["source_id"] == K1


@pytest.mark.parametrize("tezina,ocekivano", [
    ("kriticna", "critical"), ("vazna", "high"), ("manja", "medium"),
    (None, "high"), ("izmisljena", "high"),
])
def test_prioritet_prati_postojecu_skalu(tezina, ocekivano):
    assert u_akciju(_k(K1, tezina=tezina))["prioritet"] == ocekivano


def test_kontradikcija_bez_id_je_greska_a_ne_tiho_preskakanje():
    """Tiho preskakanje bi bilo silent loss."""
    with pytest.raises(ValueError):
        u_akciju({"issue_id": I1, "issue_label": "x"})


def test_prazna_labela_ne_ostavlja_akciju_bez_naslova():
    a = u_akciju(_k(K1, label=""))
    assert a["razlog"].strip()


def test_redosled_akcija_je_deterministican():
    """Dva refresh-a istog stanja moraju dati istu listu — inače razlika u
    redosledu izgleda kao promena predmeta."""
    ulaz = [_k(K3), _k(K1), _k(K2)]
    a = [x["dedupe_key"] for x in u_akcije(ulaz)]
    b = [x["dedupe_key"] for x in u_akcije(list(reversed(ulaz)))]
    assert a == b == sorted(a)


def test_prazan_ulaz_daje_praznu_listu():
    assert u_akcije([]) == []
    assert u_akcije(None) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. Čitanje iz baze — opseg predmeta i povučeni članovi
# ═══════════════════════════════════════════════════════════════════════════

class _Upit:
    def __init__(self, redovi):
        self._r = list(redovi)

    def select(self, *a, **k):
        return self

    def eq(self, kol, v):
        return _Upit([r for r in self._r if r.get(kol) == v])

    def in_(self, kol, vs):
        return _Upit([r for r in self._r if r.get(kol) in set(vs)])

    def execute(self):
        o = MagicMock()
        o.data = self._r
        return o


def _supa(issues=(), kontradikcije=(), clanovi=(), dokazi=()):
    tabele = {"predmet_issues": list(issues), "predmet_contradictions": list(kontradikcije),
              "predmet_contradiction_claims": list(clanovi), "predmet_dokazi": list(dokazi)}
    s = MagicMock()
    s.table.side_effect = lambda ime: _Upit(tabele[ime])
    return s


def test_predmet_bez_V2_daje_praznu_listu():
    """Legacy predmet: nema `predmet_issues` -> nema V2 projekcije, legacy ostaje."""
    assert asyncio.run(v2_akcije_za_predmet(_supa(), PRED)) == []


def test_bez_predmet_id_ne_cita_bazu():
    assert asyncio.run(v2_akcije_za_predmet(_supa(), "")) == []


def test_cita_se_SAMO_opseg_predmeta():
    supa = _supa(
        issues=[{"id": I1, "predmet_id": PRED, "label": "moja", "status": "DISCOVERED"},
                {"id": I2, "predmet_id": PRED_B, "label": "tudja", "status": "DISCOVERED"}],
        kontradikcije=[{"id": K1, "issue_id": I1, "relation_type": "cinjenica_cinjenica",
                        "state": "OPEN", "tezina": "vazna"},
                       {"id": K2, "issue_id": I2, "relation_type": "cinjenica_cinjenica",
                        "state": "OPEN", "tezina": "vazna"}],
        clanovi=[{"contradiction_id": K1, "dokaz_id": "c1", "removed_at": None},
                 {"contradiction_id": K1, "dokaz_id": "c2", "removed_at": None},
                 {"contradiction_id": K2, "dokaz_id": "c9", "removed_at": None}],
        dokazi=[{"id": "c1", "dokument_id": D1}, {"id": "c2", "dokument_id": D2}])
    akcije = asyncio.run(v2_akcije_za_predmet(supa, PRED))
    assert len(akcije) == 1
    assert akcije[0]["dokaz"]["source_id"] == K1


def test_zatvorena_kontradikcija_se_ne_projektuje():
    supa = _supa(
        issues=[{"id": I1, "predmet_id": PRED, "label": "x", "status": "DISCOVERED"}],
        kontradikcije=[{"id": K1, "issue_id": I1, "relation_type": "cinjenica_cinjenica",
                        "state": "RESOLVED", "tezina": "vazna"}])
    assert asyncio.run(v2_akcije_za_predmet(supa, PRED)) == []


def test_povuceni_clan_nije_u_projekciji():
    supa = _supa(
        issues=[{"id": I1, "predmet_id": PRED, "label": "x", "status": "DISCOVERED"}],
        kontradikcije=[{"id": K1, "issue_id": I1, "relation_type": "cinjenica_cinjenica",
                        "state": "OPEN", "tezina": "vazna"}],
        clanovi=[{"contradiction_id": K1, "dokaz_id": "c1", "removed_at": None},
                 {"contradiction_id": K1, "dokaz_id": "c2", "removed_at": None},
                 {"contradiction_id": K1, "dokaz_id": "c3", "removed_at": "2026-01-01"}],
        dokazi=[{"id": "c1", "dokument_id": D1}, {"id": "c2", "dokument_id": D2},
                {"id": "c3", "dokument_id": D2}])
    a = asyncio.run(v2_akcije_za_predmet(supa, PRED))[0]
    assert a["dokaz"]["claim_ids"] == ["c1", "c2"]
    assert "c3" not in a["dokaz"]["claim_ids"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Statička brava nad izvorom
# ═══════════════════════════════════════════════════════════════════════════

def _kod():
    put = os.path.join(os.path.dirname(__file__), "..", "services", "v2_projection.py")
    with open(put, encoding="utf-8") as f:
        izvor = f.read()
    return "\n".join(l.split("#")[0] for l in izvor.split('"""', 2)[-1].splitlines())


@pytest.mark.parametrize("zabranjeno", [
    "uuid4", "contradiction_dedupe_key", "lokacija_1", "lokacija_2",
    "dokument_id_1", "dokument_id_2", "SequenceMatcher", "rapidfuzz", "difflib",
])
def test_projekcija_ne_sadrzi_zabranjeni_pojam(zabranjeno):
    assert zabranjeno not in _kod()


def test_projekcija_ne_pise_u_bazu():
    kod = _kod()
    for w in (".insert(", ".update(", ".upsert(", ".delete(", ".rpc("):
        assert w not in kod, f"projekcija pise u bazu: {w}"


def test_kljuc_se_gradi_na_TACNO_jednom_mestu():
    kod = _kod()
    assert kod.count(f'f"{{PREFIKS}}{{cid}}"') == 1
