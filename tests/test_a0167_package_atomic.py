# -*- coding: utf-8 -*-
"""A016.7 — PAKETNO-ATOMSKO OPAŽANJE.

ŠTA OVAJ FAJL JESTE, A ŠTA NIJE
================================
Migracija `124_v2_observation_version.sql` NIJE pokrenuta (izmereno u A016.7:
`column predmeti.observation_version does not exist`; DDL kanal ne postoji).
Zato živi acceptance testovi T1–T10 iz mandata NISU izvedeni i u izveštaju su
označeni **BLOCKED** — ne PASS.

Ovo NIJE dokaz da paketna transakcija radi. Atomičnost, `FOR UPDATE`
serijalizacija i `xmin` revalidacija žive u SQL-u i mogu se dokazati SAMO uživo.

Ovo JESTE brava nad onim što je na Python strani i što se može tiho pokvariti
a da baza i dalje uredno odgovara:
  - da li neispravan predlog obara CEO paket PRE ijednog dodira baze;
  - da li je poziv baze JEDAN, a ne po jedan na predlog;
  - da li se `expected_version` i `expected_xmin` uopšte šalju;
  - da li `REVIEW_REQUIRED` skida tvrdnju o kompletnosti opažanja;
  - da li ustajalo opažanje ima SVOJU semantiku, odvojenu od greške;
  - da li se `__nova__<i>` prosleđuje bazi umesto da se lokalno pogađa.
"""
import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.v2_contradiction_persistence import (  # noqa: E402
    V2PackageRejected,
    V2PersistenceError,
    V2StaleObservation,
    persist_observation_package,
)
from shared.contradiction_identity import (  # noqa: E402
    razdvoji_kontradikcije,
    uporedi_kontradikcije,
)
from shared.issue_v2 import otisak_pocetnog_skupa  # noqa: E402

PREDMET = "11111111-1111-4111-8111-111111111111"
DRUGI = "22222222-2222-4222-8222-222222222222"
UID = "99999999-9999-4999-8999-999999999999"
EVT = "eeeeeeee-0001-4000-8000-000000000001"
FF = "cinjenica_cinjenica"
FN = "cinjenica_norma"

C1 = "aaaaaaaa-0001-4000-8000-000000000001"
C2 = "aaaaaaaa-0002-4000-8000-000000000002"
C3 = "aaaaaaaa-0003-4000-8000-000000000003"
C4 = "aaaaaaaa-0004-4000-8000-000000000004"
C5 = "aaaaaaaa-0005-4000-8000-000000000005"
C6 = "aaaaaaaa-0006-4000-8000-000000000006"
TUDJI = "bbbbbbbb-0001-4000-8000-000000000001"
ISSUE_A = "dddddddd-0001-4000-8000-000000000001"


# ═══════════════════════════════════════════════════════════════════════════
# Lažnjak — beleži šta bi adapter poslao; NE simulira transakciju
# ═══════════════════════════════════════════════════════════════════════════

class _Upit:
    def __init__(self, redovi):
        self._r = list(redovi)

    def select(self, *a, **k):
        return self

    def limit(self, n):
        return _Upit(self._r[:n])

    def eq(self, kol, v):
        return _Upit([r for r in self._r if r.get(kol) == v])

    def in_(self, kol, vs):
        return _Upit([r for r in self._r if r.get(kol) in set(vs)])

    def execute(self):
        class R:
            pass
        r = R()
        r.data = self._r
        return r


class FakeSupa:
    def __init__(self, *, verzija=7, dokazi=(), issues=(), kontradikcije=(),
                 clanovi=(), rpc_ishod=None, predmet_postoji=True):
        self.tabele = {
            "predmeti": ([{"id": PREDMET, "observation_version": verzija}]
                         if predmet_postoji else []),
            "predmet_dokazi": list(dokazi),
            "predmet_issues": list(issues),
            "predmet_contradictions": list(kontradikcije),
            "predmet_contradiction_claims": list(clanovi),
        }
        self.rpc_pozivi = []
        self._ishod = rpc_ishod

    def table(self, ime):
        return _Upit(self.tabele[ime])

    def _podrazumevani(self, payload):
        out = []
        for n, st in enumerate(payload["p_paket"]):
            ref = st["issue_ref"]
            nova = (not ref) or str(ref).startswith("__nova__")
            out.append({
                "out_version": payload["p_expected_version"] + 1,
                "out_indeks": st["indeks"],
                "out_issue_id": f"issue-{n}" if nova else ref,
                "out_contradiction_id": f"kontr-{n}",
                "out_created_issue": nova,
            })
        return out

    def rpc(self, ime, payload):
        assert ime == "v2_persist_observation_package", f"adapter zove tuđi RPC: {ime}"
        self.rpc_pozivi.append(payload)
        ishod = self._ishod(payload) if self._ishod else self._podrazumevani(payload)

        class R:
            def execute(_s):
                if isinstance(ishod, Exception):
                    raise ishod
                class Res:
                    pass
                res = Res()
                res.data = ishod
                return res
        return R()


def _dokazi(*ids, predmet=PREDMET):
    return [{"id": i, "predmet_id": predmet, "identitet": None, "deleted_at": None}
            for i in ids]


SVI = _dokazi(C1, C2, C3, C4, C5, C6) + _dokazi(TUDJI, predmet=DRUGI)


def _p(refs, rel=FF, label=None):
    return {"claim_refs": list(refs), "relation_type": rel, "issue_label": label}


def _pokreni(supa, predlozi, **kw):
    with patch("services.v2_contradiction_persistence._get_supa", return_value=supa):
        return asyncio.run(persist_observation_package(
            predmet_id=PREDMET, user_id=UID, event_id=EVT, predlozi=predlozi, **kw))


# ═══════════════════════════════════════════════════════════════════════════
# T1 — NEISPRAVAN PREDLOG OBARA CEO PAKET, PRE BAZE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("naziv,los", [
    ("prazan skup", _p([])),
    ("jedna tvrdnja", _p([C1])),
    ("nepostojeća tvrdnja", _p([C1, "cccccccc-0001-4000-8000-000000000001"])),
    ("tvrdnja iz tuđeg predmeta", _p([C1, TUDJI])),
    ("nepoznat relation_type", _p([C1, C2], rel="izmisljen_tip")),
])
def test_t1_neispravan_predlog_obara_ceo_paket(naziv, los):
    """§4: #0 validan + #1 neispravan => 0/0/0/0. Ne „bar ono što valja"."""
    supa = FakeSupa(dokazi=SVI)
    with pytest.raises(V2PackageRejected) as exc:
        _pokreni(supa, [_p([C1, C2]), los])
    assert supa.rpc_pozivi == [], f"{naziv}: baza je dodirnuta iako je paket neispravan"
    assert 1 in exc.value.indeksi


def test_t1_validan_predlog_pre_neispravnog_nije_upisan():
    """Redosled ne sme da spase prvi predlog — provera i za obrnut raspored."""
    supa = FakeSupa(dokazi=SVI)
    with pytest.raises(V2PackageRejected):
        _pokreni(supa, [_p([C1]), _p([C2, C3])])
    assert supa.rpc_pozivi == []


# ═══════════════════════════════════════════════════════════════════════════
# T2 — USPEŠAN PAKET: JEDAN POZIV, NE N
# ═══════════════════════════════════════════════════════════════════════════

def test_t2_ceo_paket_je_jedan_poziv():
    supa = FakeSupa(dokazi=SVI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C3, C4]), _p([C5, C6])])
    assert len(supa.rpc_pozivi) == 1, "paket je razbijen na više transakcija"
    assert len(supa.rpc_pozivi[0]["p_paket"]) == 3
    assert [i["persisted"] for i in r["ishodi"]] == [True, True, True]
    assert len({i["contradiction_id"] for i in r["ishodi"]}) == 3


def test_t2_paket_nosi_verziju_i_event_id():
    supa = FakeSupa(dokazi=SVI, verzija=41)
    r = _pokreni(supa, [_p([C1, C2])])
    p = supa.rpc_pozivi[0]
    assert p["p_expected_version"] == 41, "opažanje ne saopštava koju je verziju videlo"
    assert p["p_event_id"] == EVT, "identitet run-a se izgubio u adapteru"
    assert r["observation_version"] == 42


def test_t2_otisak_je_domenski_ne_izmisljen():
    supa = FakeSupa(dokazi=SVI)
    _pokreni(supa, [_p([C2, C1])])
    st = supa.rpc_pozivi[0]["p_paket"][0]
    assert st["fingerprint"] == otisak_pocetnog_skupa(sorted([C1, C2]))
    assert st["dokaz_ids"] == sorted([C1, C2]), "redosled tvrdnji nije normalizovan"


# ═══════════════════════════════════════════════════════════════════════════
# T3 — USTAJALO OPAŽANJE IMA SVOJU SEMANTIKU
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("poruka", [
    # 55000 = kod posle migracije 125. A016.8 je izmerio da `40001` PostgREST
    # ponavlja u krug (30s timeout naspram 0.32s za `23503` nad ISTOM funkcijom),
    # pa je stale guard bio ispravan ali nedohvatljiv.
    '{"code":"55000","message":"ustajalo opazanje (video verziju 7, tekuca je 8)"}',
    '{"code":"40001","message":"ustajalo opazanje (video verziju 7, tekuca je 8)"}',
    "sporna tacka X je promenjena od donosenja odluke (xmin 111 -> 222)",
])
def test_t3_stale_nije_greska(poruka):
    """§10: REJECTED/STALE se NE sme prikazati kao pad. Ništa nije pokvareno."""
    supa = FakeSupa(dokazi=SVI, rpc_ishod=lambda p: RuntimeError(poruka))
    with pytest.raises(V2StaleObservation):
        _pokreni(supa, [_p([C1, C2])])


def test_t3_obicna_greska_ostaje_greska():
    supa = FakeSupa(dokazi=SVI, rpc_ishod=lambda p: RuntimeError("veza prekinuta"))
    with pytest.raises(V2PersistenceError):
        _pokreni(supa, [_p([C1, C2])])


def test_t3_prazan_odgovor_na_neprazan_paket_nije_uspeh():
    supa = FakeSupa(dokazi=SVI, rpc_ishod=lambda p: [])
    with pytest.raises(V2PersistenceError):
        _pokreni(supa, [_p([C1, C2])])


# ═══════════════════════════════════════════════════════════════════════════
# T5 — PONAVLJANJE ISTOG RUN-a
# ═══════════════════════════════════════════════════════════════════════════

def test_t5_isti_event_id_daje_isti_paket():
    """Idempotencija je po SADRŽAJU (vidi ograničenje u migraciji 124: baza ne
    pamti `event_id`, jer bi to tražilo drugu kolonu)."""
    payloadi = []
    for _ in range(5):
        supa = FakeSupa(dokazi=SVI, verzija=3)
        _pokreni(supa, [_p([C1, C2]), _p([C3, C4])])
        payloadi.append(supa.rpc_pozivi[0])
    prvi = payloadi[0]
    for p in payloadi[1:]:
        assert p == prvi, "isti ulaz daje različit paket — nedeterminizam"


# ═══════════════════════════════════════════════════════════════════════════
# T6 — ISTI PAR DOKUMENATA, VIŠE SPOROVA
# ═══════════════════════════════════════════════════════════════════════════

def test_t6_tri_spora_nad_istim_dokumentima_ostaju_tri():
    supa = FakeSupa(dokazi=SVI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C3, C4]), _p([C5, C6])])
    assert len(supa.rpc_pozivi[0]["p_paket"]) == 3
    assert len({i["contradiction_id"] for i in r["ishodi"]}) == 3


def test_t6_iste_tvrdnje_razlicit_relation_type_su_dva_spora():
    """Ključ dedupliciranja mora biti (skup tvrdnji, relation_type) — isti ključ
    koji baza već drži kanonskim (`idx_contradiction_open_per_issue_relation`)."""
    supa = FakeSupa(dokazi=SVI)
    r = _pokreni(supa, [_p([C1, C2], rel=FF), _p([C1, C2], rel=FN)])
    assert len(supa.rpc_pozivi[0]["p_paket"]) == 2, "dva različita spora su sažeta u jedan"
    assert [i["odluka"] for i in r["ishodi"]] == ["NEW_ISSUE", "CONTINUATION"]


def test_t6_iste_tvrdnje_isti_relation_type_ostaju_duplikat():
    """Kontrola: širi ključ ne sme da prestane da prepoznaje pravi duplikat."""
    supa = FakeSupa(dokazi=SVI)
    r = _pokreni(supa, [_p([C1, C2], rel=FF), _p([C1, C2], rel=FF)])
    assert len(supa.rpc_pozivi[0]["p_paket"]) == 1
    assert r["ishodi"][1]["odluka"] == "DUPLICATE"


def test_t6_nova_tema_u_istom_paketu_ide_kao_token():
    """`__nova__<i>` se NE prevodi u adapteru: u paketnom režimu nema
    međurezultata. Prevod pripada migraciji 124, u istoj transakciji."""
    supa = FakeSupa(dokazi=SVI)
    _pokreni(supa, [_p([C1, C2]), _p([C1, C2, C3])])
    refs = [s["issue_ref"] for s in supa.rpc_pozivi[0]["p_paket"]]
    assert refs == [None, "__nova__0"]
    assert supa.rpc_pozivi[0]["p_paket"][1]["expected_xmin"] is None, \
        "tema nastala u ovom paketu nema raniji xmin — nije ni postojala"


# ═══════════════════════════════════════════════════════════════════════════
# T7/T8 — SNAPSHOT ODLUKE SE REVALIDIRA
# ═══════════════════════════════════════════════════════════════════════════

def test_t8_nastavak_postojece_teme_nosi_xmin():
    """§7: odluka doneta nad redom u stanju X ne sme da se primeni na stanje Y."""
    supa = FakeSupa(
        dokazi=SVI,
        issues=[{"id": ISSUE_A, "predmet_id": PREDMET, "status": "DISCOVERED", "xmin": "555111"}],
        kontradikcije=[{"id": "k-a", "issue_id": ISSUE_A}],
        clanovi=[{"contradiction_id": "k-a", "dokaz_id": C1, "removed_at": None},
                 {"contradiction_id": "k-a", "dokaz_id": C2, "removed_at": None}],
    )
    r = _pokreni(supa, [_p([C1, C2, C3])])
    st = supa.rpc_pozivi[0]["p_paket"][0]
    assert r["ishodi"][0]["odluka"] == "CONTINUATION"
    assert st["issue_ref"] == ISSUE_A
    assert st["expected_xmin"] == "555111", "snapshot se ne šalje — baza ga ne može revalidirati"


def test_t7_identitet_sporne_tacke_dolazi_iz_baze_ne_iz_adaptera():
    supa = FakeSupa(dokazi=SVI)
    r = _pokreni(supa, [_p([C1, C2])])
    assert r["ishodi"][0]["issue_id"] == "issue-0"
    assert r["ishodi"][0]["contradiction_id"] == "kontr-0"


# ═══════════════════════════════════════════════════════════════════════════
# KOMPLETNOST OPAŽANJA
# ═══════════════════════════════════════════════════════════════════════════

def test_review_required_skida_tvrdnju_o_kompletnosti():
    """Ako se ne zna kojoj postojećoj temi predlog pripada, ne sme se tvrditi da
    ono što nije upisano „više nije opaženo" — inače bi zatvaranje neopaženih
    ugasilo baš tu tačku."""
    supa = FakeSupa(dokazi=SVI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C2, C3])])
    assert any(i["odluka"] == "REVIEW_REQUIRED" for i in r["ishodi"])
    assert r["observation_complete"] is False
    assert supa.rpc_pozivi[0]["p_observation_complete"] is False


def test_cist_paket_tvrdi_kompletnost():
    supa = FakeSupa(dokazi=SVI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C3, C4])])
    assert r["observation_complete"] is True
    assert supa.rpc_pozivi[0]["p_observation_complete"] is True


def test_review_required_se_ne_upisuje():
    supa = FakeSupa(dokazi=SVI)
    r = _pokreni(supa, [_p([C1, C2]), _p([C2, C3])])
    pregled = [i for i in r["ishodi"] if i["odluka"] == "REVIEW_REQUIRED"][0]
    assert pregled["persisted"] is False
    assert pregled["contradiction_id"] is None


# ═══════════════════════════════════════════════════════════════════════════
# T10 — BEZ LEGACY FALLBACK-a
# ═══════════════════════════════════════════════════════════════════════════

def test_t10_bez_migracije_124_nema_upisa():
    """Nedostajuća `observation_version` mora da zaustavi upis, ne da ga pusti
    „na stari način". Tihi fallback je upravo klasa kvara koju ovaj lanac zatvara."""
    supa = FakeSupa(dokazi=SVI)
    supa.tabele["predmeti"] = [{"id": PREDMET}]          # kolona ne postoji
    with pytest.raises(RuntimeError, match="observation_version"):
        _pokreni(supa, [_p([C1, C2])])
    assert supa.rpc_pozivi == []


def test_t10_nepostojeci_predmet_ne_upisuje():
    supa = FakeSupa(dokazi=SVI, predmet_postoji=False)
    with pytest.raises(RuntimeError):
        _pokreni(supa, [_p([C1, C2])])
    assert supa.rpc_pozivi == []


def test_t10_adapter_ne_zove_stari_rpc():
    supa = FakeSupa(dokazi=SVI)
    _pokreni(supa, [_p([C1, C2])])
    assert all(p is not None for p in supa.rpc_pozivi)   # assert je u FakeSupa.rpc


def test_t10_dedupe_key_se_nigde_ne_salje():
    supa = FakeSupa(dokazi=SVI)
    _pokreni(supa, [_p([C1, C2])])
    tekst = repr(supa.rpc_pozivi[0])
    assert "dedupe" not in tekst.lower()
    assert "lokacija" not in tekst.lower()


# ═══════════════════════════════════════════════════════════════════════════
# T9 — DELTA
# ═══════════════════════════════════════════════════════════════════════════

def _k(opis, refs, rel=FF, l1="DOK-01 str.3", l2="DOK-02 str.7"):
    d = {"opis": opis, "lokacija_1": l1, "lokacija_2": l2, "relation_type": rel}
    if refs:
        d["claim_refs"] = list(refs)
    return d


R = lambda *a: [f"CLAIM-{i:03d}" for i in a]  # noqa: E731


@pytest.mark.parametrize("naziv,stare,nove,ocekivano", [
    ("3 nove nad istim parom lokacija", [], [_k("a", R(1, 2)), _k("b", R(3, 4)), _k("c", R(5, 6))], (3, 0)),
    ("3 eliminisane", [_k("a", R(1, 2)), _k("b", R(3, 4)), _k("c", R(5, 6))], [], (0, 3)),
    ("2 nestale + 3 nove", [_k("a", R(1, 2)), _k("b", R(3, 4))],
     [_k("c", R(5, 6)), _k("d", R(7, 8)), _k("e", R(9, 10))], (3, 2)),
    ("prošireno članstvo zadržava identitet", [_k("a", R(1, 2))], [_k("a", R(1, 2, 7))], (0, 0)),
    ("suženo članstvo zadržava identitet", [_k("a", R(1, 2, 7))], [_k("a", R(1, 2))], (0, 0)),
    ("preformulisan opis nije promena", [_k("iznos duga", R(1, 2))], [_k("neslaganje", R(1, 2))], (0, 0)),
    ("različit relation_type je različit spor", [_k("a", R(1, 2))],
     [_k("a", R(1, 2)), _k("b", R(1, 2), rel=FN)], (1, 0)),
    ("preklapanje bez sadržavanja nije isti spor", [_k("a", R(1, 2))], [_k("b", R(2, 3))], (1, 1)),
    ("nepromenjeno stanje", [_k("a", R(1, 2))], [_k("a", R(1, 2))], (0, 0)),
])
def test_t9_delta(naziv, stare, nove, ocekivano):
    assert uporedi_kontradikcije(stare, nove) == ocekivano, naziv


def test_t9_vraca_STAVKE_a_ne_poslednjih_n():
    """C-2: `posle[-N:]` je pretpostavljao da GPT nove uvek dopisuje na kraj."""
    stare = [_k("a", R(1, 2)), _k("b", R(3, 4))]
    nove = [_k("c", R(5, 6)), _k("d", R(7, 8)), _k("e", R(9, 10))]
    d = razdvoji_kontradikcije(stare, nove)
    assert [x["opis"] for x in d["nove"]] == ["c", "d", "e"]
    assert [x["opis"] for x in d["eliminisane"]] == ["a", "b"]
    # Šta bi stari kod prikazao: len(nove)-len(stare) == 1 => samo poslednja.
    assert nove[-1:] != d["nove"]


def test_t9_prelaz_pre_i_posle_A014_ne_pravi_laznu_promenu():
    """Snimci pre A014 nemaju `claim_refs`. Mešanje dve šeme bi na prvom
    refresh-u prijavilo svaku staru kao nestalu i svaku novu kao nastalu."""
    from routers.case_dna import _compute_delta
    st = {"snaga_predmeta_procent": 50,
          "kontradikcije": [_k("a", None), _k("b", None, l1="DOK-03 str.1")]}
    nv = {"snaga_predmeta_procent": 50,
          "kontradikcije": [_k("a", R(1, 2)), _k("b", R(3, 4), l1="DOK-03 str.1")]}
    d = _compute_delta(st, nv)
    assert (d["kontr_nove"], d["kontr_eliminisane"]) == (0, 0)


def test_t9_determinizam_na_promenjen_redosled():
    stare = [_k("a", R(1, 2)), _k("b", R(3, 4)), _k("c", R(5, 6))]
    nove = [_k("x", R(7, 8)), _k("a", R(1, 2)), _k("b", R(3, 4))]
    prvi = uporedi_kontradikcije(stare, nove)
    for _ in range(5):
        assert uporedi_kontradikcije(list(reversed(stare)), list(reversed(nove))) == prvi


# ═══════════════════════════════════════════════════════════════════════════
# EVENT_ID PROPAGACIJA (§6)
# ═══════════════════════════════════════════════════════════════════════════

def test_event_id_je_deo_ugovora_oba_genome_sloja():
    import inspect
    from routers.case_dna import _do_genome_refresh, _run_genome_background
    for f in (_run_genome_background, _do_genome_refresh):
        assert "event_id" in inspect.signature(f).parameters, \
            f"{f.__name__} je izgubio event_id iz ugovora"


def test_event_id_se_prosledjuje_eksplicitno_a_ne_kroz_trigger_string():
    """Izvor se čita IZ FAJLA, ne kroz `import`.

    `services.case_evolution` ulazi u kružni import sa `event_bus` kada se uveze
    prvi, pa je varijanta sa `inspect.getsource` prolazila ili padala zavisno od
    toga da li je neki raniji test već uvezao `routers.case_dna`. Test koji zavisi
    od redosleda ne dokazuje ništa — izmereno: pao izolovano, prošao u fajlu."""
    put = os.path.join(os.path.dirname(__file__), "..", "services", "case_evolution.py")
    with open(put, encoding="utf-8") as fh:
        izvor = fh.read()
    assert "event_id=event.event_id" in izvor, \
        "event_id opet putuje samo ukalupljen u `trigger` string"


def test_adapter_ne_izmislja_event_id():
    supa = FakeSupa(dokazi=SVI)
    with patch("services.v2_contradiction_persistence._get_supa", return_value=supa):
        r = asyncio.run(persist_observation_package(
            predmet_id=PREDMET, user_id=UID, event_id=None, predlozi=[_p([C1, C2])]))
    assert supa.rpc_pozivi[0]["p_event_id"] is None, "adapter je izmislio identitet run-a"
    assert r["event_id"] is None


# ═══════════════════════════════════════════════════════════════════════════
# T9 — POJAČANJE (§13: mutacije M10/M11/M13/M14 su preživele prvi krug)
#
# Prvi krug testova zvao je `uporedi_kontradikcije` DIREKTNO, pa je zaobilazio
# i izbor šeme u `_compute_delta` i put briefinga. Mutacije koje gase tačno te
# dve stvari zato nisu imale šta da obore. Mutacije se ne slabe — testovi se
# ojačavaju.
# ═══════════════════════════════════════════════════════════════════════════

def _delta(stare, nove):
    from routers.case_dna import _compute_delta
    d = _compute_delta({"snaga_predmeta_procent": 50, "kontradikcije": stare},
                       {"snaga_predmeta_procent": 50, "kontradikcije": nove})
    return d["kontr_nove"], d["kontr_eliminisane"]


@pytest.mark.parametrize("naziv,stare,nove,ocekivano", [
    ("prazna stara strana ne sme da obori šemu",
     [], [_k("a", R(1, 2)), _k("b", R(3, 4)), _k("c", R(5, 6))], (3, 0)),
    ("prazna nova strana",
     [_k("a", R(1, 2)), _k("b", R(3, 4)), _k("c", R(5, 6))], [], (0, 3)),
    ("3 spora nad ISTIM parom lokacija",
     [], [_k("a", R(1, 2)), _k("b", R(3, 4)), _k("c", R(5, 6))], (3, 0)),
    ("2 nestale + 3 nove",
     [_k("a", R(1, 2)), _k("b", R(3, 4))],
     [_k("c", R(5, 6)), _k("d", R(7, 8)), _k("e", R(9, 10))], (3, 2)),
])
def test_t9_kroz_compute_delta(naziv, stare, nove, ocekivano):
    """Ide kroz `_compute_delta`, a ne kroz deljenu funkciju — jedino tako se
    meri i IZBOR šeme, ne samo poređenje."""
    assert _delta(stare, nove) == ocekivano, naziv


def test_t9_relation_type_sam_po_sebi_razlikuje_spor():
    """Iste tvrdnje, SAMO drugi tip relacije, bez ijednog drugog razlikovanja.

    Slabija varijanta (stari spor + novi spor sa istim tvrdnjama) je prolazila i
    kad `relation_type` uopšte nije u identitetu, jer uparivanje 1:1 ionako
    ostavi drugu stavku neuparenu. Ovde stara i nova strana imaju po TAČNO jednu
    stavku, pa se razlika vidi samo ako tip relacije zaista ulazi u identitet."""
    assert uporedi_kontradikcije([_k("a", R(1, 2), rel=FF)],
                                 [_k("a", R(1, 2), rel=FN)]) == (1, 1)
    assert _delta([_k("a", R(1, 2), rel=FF)], [_k("a", R(1, 2), rel=FN)]) == (1, 1)


def test_t9_identitet_bez_relation_type_bi_slagao():
    """Kontrola nad kontrolom: isti tip relacije mora ostati isti spor."""
    assert uporedi_kontradikcije([_k("a", R(1, 2), rel=FF)],
                                 [_k("a", R(1, 2), rel=FF)]) == (0, 0)


# ═══════════════════════════════════════════════════════════════════════════
# BRIEFING (C-2) — jedan vlasnik, pa merljivo
# ═══════════════════════════════════════════════════════════════════════════

def test_c2_briefing_broji_uparivanjem_a_ne_razlikom_duzina():
    from shared.contradiction_identity import nove_kontradikcije_za_briefing
    stare = [_k("a", R(1, 2)), _k("b", R(3, 4))]
    posle = [_k("c", R(5, 6)), _k("d", R(7, 8)), _k("e", R(9, 10))]
    broj, stavke = nove_kontradikcije_za_briefing(stare, posle, pre_broj=2)
    assert broj == 3, "razlika dužina bi rekla 1 — dve nove bi ostale nevidljive"
    assert [x["opis"] for x in stavke] == ["c", "d", "e"]


def test_c2_briefing_ne_bira_stavke_po_poziciji():
    """GPT ne garantuje da nove kontradikcije dopisuje na kraj."""
    from shared.contradiction_identity import nove_kontradikcije_za_briefing
    stare = [_k("stara", R(1, 2))]
    posle = [_k("nova", R(5, 6)), _k("stara", R(1, 2))]   # nova je PRVA
    broj, stavke = nove_kontradikcije_za_briefing(stare, posle, pre_broj=1)
    assert broj == 1
    assert [x["opis"] for x in stavke] == ["nova"], "izabrana je poslednja umesto nove"


def test_c2_bez_prethodnog_snimka_pada_na_stari_put():
    """`None` znači „nema sa čim porediti", NE „sve je nestalo"."""
    from shared.contradiction_identity import nove_kontradikcije_za_briefing
    posle = [_k("a", R(1, 2)), _k("b", R(3, 4))]
    broj, stavke = nove_kontradikcije_za_briefing(None, posle, pre_broj=1)
    assert broj == 1
    assert stavke == posle[-1:]


def test_c2_snimak_bez_claim_refs_pada_na_stari_put():
    from shared.contradiction_identity import nove_kontradikcije_za_briefing
    stare = [_k("a", None)]
    posle = [_k("a", None), _k("b", None, l1="DOK-09 str.1")]
    broj, _ = nove_kontradikcije_za_briefing(stare, posle, pre_broj=1)
    assert broj == 1


def test_c2_case_evolution_koristi_jednog_vlasnika():
    """Odluka ne sme da se vrati u `case_evolution.py` kao druga implementacija."""
    put = os.path.join(os.path.dirname(__file__), "..", "services", "case_evolution.py")
    with open(put, encoding="utf-8") as fh:
        izvor = fh.read()
    assert "nove_kontradikcije_za_briefing(" in izvor
    assert "kontradikcije_posle[-nove_kontradikcije:]" not in izvor, \
        "poziciono biranje stavki se vratilo u posledicu"
