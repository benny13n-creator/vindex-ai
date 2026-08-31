# -*- coding: utf-8 -*-
"""A013 — V2 PERSISTENCE ADAPTER (`services/v2_contradiction_persistence.py`).

ŠTA OVAJ FAJL JESTE, A ŠTA NIJE
================================
Ovo NIJE dokaz da persistence radi. Taj dokaz je izveden UŽIVO, kroz stvarni
Supabase RPC, i zapisan je u `A013 — PRODUCTION V2 PERSISTENCE REPORT.md`
(30/30 provera). A013 §1 izričito zabranjuje da se mock predstavi kao dokaz
persistence correctness-a, pa se to ovde i ne pokušava.

Ovo JESTE regresiona brava nad ODLUKAMA adaptera — nad onim što se može
pokvariti tihom izmenom koda a da živi RPC i dalje odgovara uredno:
  - da li Python odbija pre nego što uopšte dodirne bazu;
  - da li se greška baze PROPAGIRA umesto da se proguta;
  - da li se dva različita spora nad istim dokumentima sažimaju;
  - da li `REVIEW_REQUIRED` ikad završi kao upis;
  - da li identitet ikad zavisi od redosleda, labele ili `dedupe_key`-a.

Lažnjak namerno NE simulira ograničenja baze. Sve što on radi je da zabeleži
šta bi adapter poslao — a upravo se to ovde meri.
"""
import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.v2_contradiction_persistence import (  # noqa: E402
    V2PersistenceError,
    persist_paket,
)
from shared.issue_v2 import otisak_pocetnog_skupa  # noqa: E402

PREDMET = "11111111-1111-4111-8111-111111111111"
DRUGI = "22222222-2222-4222-8222-222222222222"
UID = "99999999-9999-4999-8999-999999999999"
FF = "cinjenica_cinjenica"
FN = "cinjenica_norma"

C1 = "aaaaaaaa-0001-4000-8000-000000000001"
C2 = "aaaaaaaa-0002-4000-8000-000000000002"
C3 = "aaaaaaaa-0003-4000-8000-000000000003"
C4 = "aaaaaaaa-0004-4000-8000-000000000004"
TUDJI = "bbbbbbbb-0001-4000-8000-000000000001"
NEPOSTOJECI = "cccccccc-0001-4000-8000-000000000001"


# ═══════════════════════════════════════════════════════════════════════════
# Lažnjak: beleži, ne simulira bazu
# ═══════════════════════════════════════════════════════════════════════════

class _Upit:
    def __init__(self, redovi):
        self._redovi = list(redovi)

    def select(self, *a, **k):
        return self

    def eq(self, kol, v):
        return _Upit([r for r in self._redovi if r.get(kol) == v])

    def in_(self, kol, vs):
        return _Upit([r for r in self._redovi if r.get(kol) in set(vs)])

    def execute(self):
        class R:
            pass
        r = R()
        r.data = self._redovi
        return r


class FakeSupa:
    def __init__(self, dokazi=(), issues=(), kontradikcije=(), clanovi=(), rpc_ishod=None):
        self.tabele = {
            "predmet_dokazi": list(dokazi),
            "predmet_issues": list(issues),
            "predmet_contradictions": list(kontradikcije),
            "predmet_contradiction_claims": list(clanovi),
        }
        self.rpc_pozivi = []
        self._rpc_ishod = rpc_ishod or self._podrazumevani

    def table(self, ime):
        return _Upit(self.tabele[ime])

    def _podrazumevani(self, payload, redni):
        return [{"out_issue_id": payload["p_issue_id"] or f"issue-{redni}",
                 "out_contradiction_id": f"kontr-{redni}",
                 "out_created_issue": payload["p_issue_id"] is None}]

    def rpc(self, ime, payload):
        assert ime == "v2_persist_contradiction", f"adapter zove tudji RPC: {ime}"
        self.rpc_pozivi.append(payload)
        ishod = self._rpc_ishod(payload, len(self.rpc_pozivi) - 1)

        class R:
            def execute(_self):
                if isinstance(ishod, Exception):
                    raise ishod
                class Res:
                    pass
                res = Res()
                res.data = ishod
                return res
        return R()


def _dokazi(*ids, predmet=PREDMET, obrisan=()):
    return [{"id": i, "predmet_id": predmet, "identitet": None,
             "deleted_at": "2026-01-01T00:00:00Z" if i in obrisan else None} for i in ids]


SVI_DOKAZI = _dokazi(C1, C2, C3, C4) + _dokazi(TUDJI, predmet=DRUGI)


def _pokreni(supa, predlozi, predmet=PREDMET, **kw):
    with patch("services.v2_contradiction_persistence._get_supa", return_value=supa):
        return asyncio.run(persist_paket(predmet_id=predmet, user_id=UID,
                                         predlozi=predlozi, **kw))


def _p(refs, rel=FF, label=None):
    return {"claim_refs": list(refs), "relation_type": rel, "issue_label": label}


# ═══════════════════════════════════════════════════════════════════════════
# 1. PYTHON JE PRVA LINIJA — baza se ne sme ni dodirnuti
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("naziv,predlog", [
    ("prazan skup", _p([])),
    ("jedna tvrdnja", _p([C1])),
    ("duplikat iste tvrdnje", _p([C1, C1])),
    ("nepostojeca tvrdnja", _p([C1, NEPOSTOJECI])),
    ("tvrdnja iz tudjeg predmeta", _p([C1, TUDJI])),
    ("obe iz tudjeg predmeta", _p([TUDJI, TUDJI])),
    ("nepoznat relation_type", _p([C1, C2], "izmisljeno")),
    ("relation_type = None", _p([C1, C2], None)),
    ("relation_type = dict", _p([C1, C2], {})),
    ("relation_type = list", _p([C1, C2], [])),
    ("claim_refs = None", {"claim_refs": None, "relation_type": FF}),
    ("predlog nije objekat", "ovo je string"),
])
def test_neispravan_predlog_ne_stize_do_baze(naziv, predlog):
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [predlog])
    assert r[0]["odluka"] == "INVALID", naziv
    assert r[0]["persisted"] is False, naziv
    assert supa.rpc_pozivi == [], f"{naziv}: adapter je ipak zvao RPC"


def test_soft_obrisana_tvrdnja_nije_clan():
    supa = FakeSupa(dokazi=_dokazi(C1, C2, obrisan=(C2,)))
    r = _pokreni(supa, [_p([C1, C2])])
    assert r[0]["odluka"] == "INVALID"
    assert supa.rpc_pozivi == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. GREŠKA BAZE SE PROPAGIRA — bez fallback-a, bez gutanja
# ═══════════════════════════════════════════════════════════════════════════

def test_greska_rpc_a_se_propagira_kao_V2PersistenceError():
    supa = FakeSupa(dokazi=SVI_DOKAZI,
                    rpc_ishod=lambda p, i: RuntimeError("23503 tudja tvrdnja"))
    with pytest.raises(V2PersistenceError) as exc:
        _pokreni(supa, [_p([C1, C2])])
    assert exc.value.indeks == 0
    assert "23503" in str(exc.value)
    assert isinstance(exc.value.__cause__, RuntimeError), "originalni uzrok mora ostati"


def test_pad_na_prvom_predlogu_ne_upisuje_tiho_ostatak_paketa():
    """Delimično upisan paket bez signala pozivaocu JESTE tihi gubitak."""
    def ishod(p, i):
        return RuntimeError("pad") if i == 0 else [{"out_issue_id": "x",
                                                    "out_contradiction_id": "y",
                                                    "out_created_issue": True}]
    supa = FakeSupa(dokazi=SVI_DOKAZI, rpc_ishod=ishod)
    with pytest.raises(V2PersistenceError):
        _pokreni(supa, [_p([C1, C2]), _p([C3, C4])])
    assert len(supa.rpc_pozivi) == 1, "adapter je nastavio posle pada"


def test_prazan_odgovor_rpc_a_nije_uspeh():
    supa = FakeSupa(dokazi=SVI_DOKAZI, rpc_ishod=lambda p, i: [])
    with pytest.raises(V2PersistenceError):
        _pokreni(supa, [_p([C1, C2])])


def test_odgovor_bez_issue_id_nije_uspeh():
    supa = FakeSupa(dokazi=SVI_DOKAZI,
                    rpc_ishod=lambda p, i: [{"out_issue_id": None,
                                             "out_contradiction_id": "k",
                                             "out_created_issue": True}])
    with pytest.raises(V2PersistenceError):
        _pokreni(supa, [_p([C1, C2])])


# ═══════════════════════════════════════════════════════════════════════════
# 3. MNOGOSTRUKOST — ovo je kvar zbog kojeg V2 postoji
# ═══════════════════════════════════════════════════════════════════════════

def test_dva_spora_nad_ISTIM_dokumentima_daju_dva_poziva():
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2], FF, "datum"), _p([C3, C4], FF, "iznos")])
    assert len(supa.rpc_pozivi) == 2
    assert [x["persisted"] for x in r] == [True, True]
    assert {tuple(sorted(p["p_dokaz_ids"])) for p in supa.rpc_pozivi} == {
        tuple(sorted([C1, C2])), tuple(sorted([C3, C4]))}
    assert r[0]["issue_id"] != r[1]["issue_id"]


def test_ista_labela_ne_spaja_razlicite_sporove():
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2], FF, "ista"), _p([C3, C4], FF, "ista")])
    assert len(supa.rpc_pozivi) == 2
    assert r[0]["issue_id"] != r[1]["issue_id"]


def test_isti_skup_dva_puta_u_paketu_je_DUPLICATE_a_ne_tihi_gubitak():
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C2, C1])])
    assert r[0]["odluka"] == "NEW_ISSUE"
    assert r[1]["odluka"] == "DUPLICATE"
    assert len(supa.rpc_pozivi) == 1
    assert len(r) == 2, "duplikat mora ostati VIDLJIV u ishodu"


def test_intra_dokumentna_kontradikcija_nije_odbijena():
    """Dve tvrdnje iz istog dokumenta su validan spor — adapter ne zna
    ni ne pita za `dokument_id`, i to je namerno."""
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2])])
    assert r[0]["persisted"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 4. KONTINUITET — sadržavanje, nikad preklapanje
# ═══════════════════════════════════════════════════════════════════════════

def _postojeca(issue_id, claims, status="DISCOVERED"):
    return ([{"id": issue_id, "predmet_id": PREDMET, "status": status}],
            [{"id": f"k-{issue_id}", "issue_id": issue_id}],
            [{"contradiction_id": f"k-{issue_id}", "dokaz_id": c, "removed_at": None}
             for c in claims])


def test_isti_skup_nastavlja_postojecu_temu():
    iss, kon, cl = _postojeca("I1", [C1, C2])
    supa = FakeSupa(dokazi=SVI_DOKAZI, issues=iss, kontradikcije=kon, clanovi=cl)
    r = _pokreni(supa, [_p([C1, C2])])
    assert r[0]["odluka"] == "CONTINUATION"
    assert supa.rpc_pozivi[0]["p_issue_id"] == "I1"


def test_prosiren_skup_nastavlja_postojecu_temu():
    iss, kon, cl = _postojeca("I1", [C1, C2])
    supa = FakeSupa(dokazi=SVI_DOKAZI, issues=iss, kontradikcije=kon, clanovi=cl)
    r = _pokreni(supa, [_p([C1, C2, C3])])
    assert r[0]["odluka"] == "CONTINUATION"
    assert supa.rpc_pozivi[0]["p_issue_id"] == "I1"


def test_zamenjen_clan_ide_na_pregled_a_NE_u_bazu():
    """`{C1,C2}` vs `{C1,C3}` — presek bez sadržavanja. Lažno spajanje je gore
    od pregleda, pa se ovde NIŠTA ne upisuje."""
    iss, kon, cl = _postojeca("I1", [C1, C2])
    supa = FakeSupa(dokazi=SVI_DOKAZI, issues=iss, kontradikcije=kon, clanovi=cl)
    r = _pokreni(supa, [_p([C1, C3])])
    assert r[0]["odluka"] == "REVIEW_REQUIRED"
    assert r[0]["persisted"] is False
    assert supa.rpc_pozivi == [], "REVIEW_REQUIRED je upisan kao OPEN"
    assert r[0]["kandidati"] == ["I1"]


def test_dva_kandidata_idu_na_pregled():
    supa = FakeSupa(
        dokazi=SVI_DOKAZI,
        issues=[{"id": "I1", "predmet_id": PREDMET, "status": "DISCOVERED"},
                {"id": "I2", "predmet_id": PREDMET, "status": "DISCOVERED"}],
        kontradikcije=[{"id": "k1", "issue_id": "I1"}, {"id": "k2", "issue_id": "I2"}],
        clanovi=[{"contradiction_id": "k1", "dokaz_id": C1, "removed_at": None},
                 {"contradiction_id": "k1", "dokaz_id": C2, "removed_at": None},
                 {"contradiction_id": "k2", "dokaz_id": C1, "removed_at": None}])
    r = _pokreni(supa, [_p([C1, C2, C3])])
    assert r[0]["odluka"] == "REVIEW_REQUIRED"
    assert supa.rpc_pozivi == []


def test_zatvorena_tema_nije_kandidat_za_kontinuitet():
    iss, kon, cl = _postojeca("I1", [C1, C2], status="RESOLVED")
    supa = FakeSupa(dokazi=SVI_DOKAZI, issues=iss, kontradikcije=kon, clanovi=cl)
    r = _pokreni(supa, [_p([C1, C2])])
    assert r[0]["odluka"] == "NEW_ISSUE"
    assert supa.rpc_pozivi[0]["p_issue_id"] is None


def test_povuceni_clan_se_ne_racuna_u_clanstvo():
    supa = FakeSupa(
        dokazi=SVI_DOKAZI,
        issues=[{"id": "I1", "predmet_id": PREDMET, "status": "DISCOVERED"}],
        kontradikcije=[{"id": "k1", "issue_id": "I1"}],
        clanovi=[{"contradiction_id": "k1", "dokaz_id": C1, "removed_at": None},
                 {"contradiction_id": "k1", "dokaz_id": C2, "removed_at": None},
                 {"contradiction_id": "k1", "dokaz_id": C4, "removed_at": "2026-01-01"}])
    r = _pokreni(supa, [_p([C1, C2])])
    assert r[0]["odluka"] == "CONTINUATION"


def test_tema_iz_DRUGOG_predmeta_nije_kandidat():
    supa = FakeSupa(
        dokazi=SVI_DOKAZI,
        issues=[{"id": "I-tudji", "predmet_id": DRUGI, "status": "DISCOVERED"}],
        kontradikcije=[{"id": "k1", "issue_id": "I-tudji"}],
        clanovi=[{"contradiction_id": "k1", "dokaz_id": C1, "removed_at": None},
                 {"contradiction_id": "k1", "dokaz_id": C2, "removed_at": None}])
    r = _pokreni(supa, [_p([C1, C2])])
    assert r[0]["odluka"] == "NEW_ISSUE"
    assert supa.rpc_pozivi[0]["p_issue_id"] is None


def test_predlozi_u_odnosu_sadrzavanja_unutar_ISTOG_paketa_ne_cepaju_spor():
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C1, C2, C3])])
    assert r[0]["odluka"] == "NEW_ISSUE"
    assert r[1]["odluka"] == "CONTINUATION"
    assert supa.rpc_pozivi[1]["p_issue_id"] == r[0]["issue_id"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. IDENTITET — nezavisan od redosleda, labele i teksta
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("redosled", [[C1, C2, C3], [C3, C1, C2], [C2, C3, C1]])
def test_otisak_ne_zavisi_od_redosleda(redosled):
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    _pokreni(supa, [_p(redosled)])
    assert supa.rpc_pozivi[0]["p_fingerprint"] == otisak_pocetnog_skupa([C1, C2, C3])


def test_otisak_ne_zavisi_od_labele():
    otisci = set()
    for lab in ("prva labela", "sasvim druga formulacija", None):
        supa = FakeSupa(dokazi=SVI_DOKAZI)
        _pokreni(supa, [_p([C1, C2], FF, lab)])
        otisci.add(supa.rpc_pozivi[0]["p_fingerprint"])
    assert len(otisci) == 1


def test_relation_type_se_prosledjuje_doslovno_i_ne_izvodi():
    for rel in (FF, FN):
        supa = FakeSupa(dokazi=SVI_DOKAZI)
        _pokreni(supa, [_p([C1, C2], rel)])
        assert supa.rpc_pozivi[0]["p_relation_type"] == rel


def test_ista_relacija_razliciti_skupovi_su_dva_entiteta():
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2], FF), _p([C3, C4], FF)])
    assert supa.rpc_pozivi[0]["p_fingerprint"] != supa.rpc_pozivi[1]["p_fingerprint"]
    assert r[0]["issue_id"] != r[1]["issue_id"]


def test_claim_identiteti_su_poravnati_sa_sortiranim_claim_ids():
    dokazi = [{"id": C1, "predmet_id": PREDMET, "identitet": "ident-1", "deleted_at": None},
              {"id": C2, "predmet_id": PREDMET, "identitet": "ident-2", "deleted_at": None}]
    supa = FakeSupa(dokazi=dokazi)
    _pokreni(supa, [_p([C2, C1])])
    poziv = supa.rpc_pozivi[0]
    assert poziv["p_dokaz_ids"] == sorted([C1, C2])
    ocekivano = ["ident-1" if i == C1 else "ident-2" for i in poziv["p_dokaz_ids"]]
    assert poziv["p_claim_identiteti"] == ocekivano


def test_nedostajuci_identitet_ostaje_None_i_ne_izmislja_se():
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    _pokreni(supa, [_p([C1, C2])])
    assert supa.rpc_pozivi[0]["p_claim_identiteti"] == [None, None]


# ═══════════════════════════════════════════════════════════════════════════
# 6. ZABRANJENI OBRASCI — statička brava nad izvorom adaptera
# ═══════════════════════════════════════════════════════════════════════════

def _izvor():
    put = os.path.join(os.path.dirname(__file__), "..", "services",
                       "v2_contradiction_persistence.py")
    with open(put, encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("obrazac", [
    "dedupe_key",
    "uuid4",
    "lokacija_1",
    "lokacija_2",
    "izvor_dokumenti",
    "contradiction_dedupe_key",
    "SequenceMatcher",
    "rapidfuzz",
    "difflib",
])
def test_adapter_ne_sadrzi_zabranjeni_pojam(obrazac):
    """Ovi pojmovi su tačno oni kojima je stari model gubio podatke.
    Provera je namerno statička: pojam ne sme ni da postoji u modulu."""
    izvor = _izvor()
    # docstring smе da ih pomene kao ZABRANU — meri se samo kod.
    kod = izvor.split('"""', 2)[-1]
    assert obrazac not in kod, f"adapter koristi zabranjeni pojam: {obrazac}"


def _samo_kod():
    """Izvor bez komentara i bez docstring-ova.

    Prva verzija ove provere je merila ceo fajl i pala je na sopstvenom
    komentaru koji pojam `return legacy_result` navodi kao ZABRANU. Provera
    nije oslabljena — suzena je na ono što se izvršava."""
    izvor = _izvor().split('"""', 2)[-1]
    return "\n".join(l.split("#")[0] for l in izvor.splitlines())


def test_adapter_nema_except_koji_vraca_legacy():
    kod = _samo_kod()
    assert "return legacy" not in kod
    assert "pass" not in kod, "tiho preskakanje izuzetka"
    # A016.7: adapter je dobio drugi ulaz, pa i drugi `except`. Tvrdi broj `== 1`
    # je merio KOLIKO ih ima, a namera je bila da NIJEDAN ne guta izuzetak. Sada
    # se meri to: svaki `except Exception` blok mora da podigne dalje.
    import re
    blokovi = re.findall(r"except Exception.*?\n((?:[ \t]{8,}.*\n|\s*\n)+)", kod)
    assert blokovi, "adapter vise nema nijedan `except Exception` — proveri da li je hvatanje uklonjeno"
    for i, telo in enumerate(blokovi):
        assert "raise" in telo, f"`except Exception` #{i} guta izuzetak umesto da ga podigne"
    assert "raise V2PersistenceError" in kod


def test_placeholder_nove_teme_NIKAD_ne_stize_do_baze():
    """`razresi_paket` označava temu nastalu u istom paketu rezervisanim imenom
    `__nova__<i>` — to nije UUID. Adapter ga mora prevesti u stvarni id.

    Bez prevoda paket `{C1,C2}` pa `{C1,C2,C3}` poslao bi `p_issue_id`
    `"__nova__0"` i pao na `22P02`. Nađeno testom, popravljeno u adapteru."""
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C1, C2, C3])])
    assert r[1]["odluka"] == "CONTINUATION"
    for poziv in supa.rpc_pozivi:
        assert not str(poziv["p_issue_id"] or "").startswith("__nova__"), poziv
    assert supa.rpc_pozivi[1]["p_issue_id"] == r[0]["issue_id"]


def test_placeholder_se_prevodi_i_u_kandidatima():
    """Ishod koji ide na ljudski pregled ne sme nositi interni token domena."""
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C2, C3])])
    assert r[1]["odluka"] == "REVIEW_REQUIRED"
    assert r[1]["kandidati"] == [r[0]["issue_id"]]
    assert not any(str(k).startswith("__nova__") for k in r[1]["kandidati"])


def test_adapter_zove_samo_kanonski_rpc():
    kod = _izvor()
    assert kod.count('_RPC = "v2_persist_contradiction"') == 1
    assert "v2_mut_" not in kod
