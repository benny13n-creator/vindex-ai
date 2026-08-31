# -*- coding: utf-8 -*-
"""A013 §22 — ADVERSARIAL MUTATION SUITE nad V2 persistence adapterom.

Svaka mutacija ovde VRAĆA tačno jedan poznati kvar i dokazuje da ga postojeći
test hvata. Mutacija je „ubijena" ako pod njom odgovarajuća provera padne.

Tri ishoda se NE mešaju:

  UBIJENA          mutacija je stvarno primenjena i provera je pod njom pala.
  NEPREDSTAVLJIVA  kvar se ne može uneti jer adapter nema ni ulaz za njega
                   (npr. nikad ne čita `dokument_id`). Jače od ubijene, i to
                   se ovde dokazuje statički, ne tvrdnjom.
  BLOKIRANA        mutacija cilja projekcioni sloj koji A013 nije mogao da
                   izgradi (v. GAP-1 u izveštaju). NIJE prijavljena kao ubijena.

Referentni mandat: M1–M20 iz A013 §22.
"""
import asyncio
import hashlib
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import services.v2_contradiction_persistence as adapter  # noqa: E402
from services.v2_contradiction_persistence import V2PersistenceError  # noqa: E402
from shared.issue_v2 import delta_clanstva, razresi_kontinuitet  # noqa: E402

from test_a013_v2_persistence_adapter import (  # noqa: E402
    C1, C2, C3, C4, FF, PREDMET, SVI_DOKAZI, TUDJI, UID, FakeSupa, _p, _pokreni,
)


# ═══════════════════════════════════════════════════════════════════════════
# M1 / M3 / M18 — legacy identitet po paru dokumenata
# ═══════════════════════════════════════════════════════════════════════════

def _otisak_po_dokumentima(claim_ids):
    """MUTANT: identitet iz para dokumenata, kao stari `contradiction_dedupe_key`.

    Sve tvrdnje u testu dolaze iz istog para dokumenata, pa ovaj mutant daje
    ISTI otisak za dva stvarno različita spora."""
    return hashlib.sha256(b"isti-par-dokumenata").hexdigest()


def test_M1_M3_M18_document_pair_identitet_je_ubijen():
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    with patch.object(adapter, "otisak_pocetnog_skupa", _otisak_po_dokumentima):
        _pokreni(supa, [_p([C1, C2], FF, "datum"), _p([C3, C4], FF, "iznos")])
    otisci = {p["p_fingerprint"] for p in supa.rpc_pozivi}
    # Pod mutacijom dva razlicita spora nose ISTI otisak -> baza bi ih spojila
    # u jednu spornu tacku. To je tacno A005 gubitak.
    assert len(otisci) == 1, "mutacija nije primenjena"

    # Kanonska funkcija ih razdvaja — provera koja pod mutacijom pada:
    supa2 = FakeSupa(dokazi=SVI_DOKAZI)
    _pokreni(supa2, [_p([C1, C2], FF, "datum"), _p([C3, C4], FF, "iznos")])
    assert len({p["p_fingerprint"] for p in supa2.rpc_pozivi}) == 2


# ═══════════════════════════════════════════════════════════════════════════
# M5 / M6 / M7 / M8 — uklonjene ulazne provere
# ═══════════════════════════════════════════════════════════════════════════

def _propusti_sve(predlozi, predmet_id, poznati, postojece):
    """MUTANT: validacija uklonjena — svaki predlog prolazi kao NEW_ISSUE."""
    from shared.issue_v2 import _kao_lista
    out = []
    for i, p in enumerate(_kao_lista(predlozi)):
        refs = (p or {}).get("claim_refs") or []
        out.append({"indeks": i, "odluka": "NEW_ISSUE", "issue_id": None,
                    "claim_set": frozenset(refs), "label": (p or {}).get("issue_label"),
                    "relation_type": (p or {}).get("relation_type"),
                    "kandidati": [], "razlog": "", "odbacene_reference": []})
    return out


@pytest.mark.parametrize("oznaka,predlog", [
    ("M7 jedna tvrdnja", _p([C1])),
    ("M5 tudja tvrdnja", _p([C1, TUDJI])),
    ("M8 bez relation_type", _p([C1, C2], None)),
])
def test_M5_M7_M8_uklonjena_validacija_je_ubijena(oznaka, predlog):
    # Pod mutacijom neispravan predlog STIZE do baze...
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    with patch.object(adapter, "razresi_paket", _propusti_sve):
        r = _pokreni(supa, [predlog])
    assert r[0]["persisted"] is True, f"{oznaka}: mutacija nije primenjena"
    assert len(supa.rpc_pozivi) == 1

    # ...dok kanonski put odbija pre nego sto dodirne bazu.
    supa2 = FakeSupa(dokazi=SVI_DOKAZI)
    r2 = _pokreni(supa2, [predlog])
    assert r2[0]["odluka"] == "INVALID"
    assert supa2.rpc_pozivi == [], f"{oznaka}: kanonski put je ipak zvao RPC"


def test_M6_nula_tvrdnji_zaustavlja_DRUGA_nezavisna_brava():
    """M6 se ponaša drugačije od M5/M7/M8, i to je izmereno, ne pretpostavljeno.

    Kad se validacija ukloni, prazan skup NE stigne do baze: `otisak_pocetnog_skupa`
    odbija da izračuna identitet nad praznim skupom i podiže `GreskaTeme`. Dakle
    prazan skup čuvaju DVE nezavisne brave (validacija i identitet), plus treća
    u SQL-u (`22023`, A012 J1).

    Ovaj test to i zaključava: pod mutacijom RPC i dalje ne sme biti pozvan."""
    supa = FakeSupa(dokazi=SVI_DOKAZI)
    with patch.object(adapter, "razresi_paket", _propusti_sve):
        with pytest.raises(V2PersistenceError) as exc:
            _pokreni(supa, [_p([])])
    assert "bar jednu tvrdnju" in str(exc.value)
    assert supa.rpc_pozivi == [], "prazan skup je stigao do baze"

    supa2 = FakeSupa(dokazi=SVI_DOKAZI)
    r2 = _pokreni(supa2, [_p([])])
    assert r2[0]["odluka"] == "INVALID"
    assert supa2.rpc_pozivi == []


# ═══════════════════════════════════════════════════════════════════════════
# M9 / M10 — fallback i progutan izuzetak
# ═══════════════════════════════════════════════════════════════════════════

def test_M10_progutan_izuzetak_je_ubijen():
    """Mutant hvata gresku baze i vraca 'uspeh'. Kanonski put mora podici."""
    supa = FakeSupa(dokazi=SVI_DOKAZI,
                    rpc_ishod=lambda p, i: RuntimeError("23503 pad baze"))

    async def _mutant(**kw):
        try:
            return await adapter.persist_paket(**kw)
        except V2PersistenceError:
            return [{"indeks": 0, "odluka": "NEW_ISSUE", "persisted": True,
                     "issue_id": "lazni", "contradiction_id": "lazni"}]

    with patch("services.v2_contradiction_persistence._get_supa", return_value=supa):
        pod_mutacijom = asyncio.run(_mutant(predmet_id=PREDMET, user_id=UID,
                                            predlozi=[_p([C1, C2])]))
    assert pod_mutacijom[0]["persisted"] is True, "mutacija nije primenjena"

    with pytest.raises(V2PersistenceError):
        _pokreni(supa, [_p([C1, C2])])


def test_M9_fallback_na_legacy_je_NEPREDSTAVLJIV():
    """Adapter uopšte ne uvozi legacy persistence — fallback nema odakle."""
    izvor = open(os.path.join(os.path.dirname(__file__), "..", "services",
                              "v2_contradiction_persistence.py"), encoding="utf-8").read()
    kod = izvor.split('"""', 2)[-1]
    for zabranjeno in ("case_evolution", "case_actions", "dedupe_key",
                       "_compute_target_actions", "contradiction_dedupe_key"):
        assert zabranjeno not in kod, f"adapter dodiruje legacy: {zabranjeno}"


# ═══════════════════════════════════════════════════════════════════════════
# M12 — uklonjena idempotencija
# ═══════════════════════════════════════════════════════════════════════════

def test_M12_uklonjena_idempotencija_je_ubijena():
    """Mutant uvek salje `p_issue_id=None` -> svaki replay pravi novu temu."""
    iss = [{"id": "I1", "predmet_id": PREDMET, "status": "DISCOVERED"}]
    kon = [{"id": "k1", "issue_id": "I1"}]
    cl = [{"contradiction_id": "k1", "dokaz_id": C1, "removed_at": None},
          {"contradiction_id": "k1", "dokaz_id": C2, "removed_at": None}]

    def _uvek_nova(claim_set, postojece):
        return {"odluka": "NEW_ISSUE", "issue_id": None, "kandidati": []}

    supa = FakeSupa(dokazi=SVI_DOKAZI, issues=iss, kontradikcije=kon, clanovi=cl)
    with patch("shared.issue_v2.razresi_kontinuitet", _uvek_nova):
        r = _pokreni(supa, [_p([C1, C2])])
    assert r[0]["odluka"] == "NEW_ISSUE", "mutacija nije primenjena"
    assert supa.rpc_pozivi[0]["p_issue_id"] is None

    supa2 = FakeSupa(dokazi=SVI_DOKAZI, issues=iss, kontradikcije=kon, clanovi=cl)
    r2 = _pokreni(supa2, [_p([C1, C2])])
    assert r2[0]["odluka"] == "CONTINUATION"
    assert supa2.rpc_pozivi[0]["p_issue_id"] == "I1"


# ═══════════════════════════════════════════════════════════════════════════
# M15 — zamenjen član tretiran kao isti spor
# ═══════════════════════════════════════════════════════════════════════════

def test_M15_preklapanje_kao_kontinuitet_je_ubijeno():
    """`{C1,C2}` vs `{C1,C3}` -- mutant spaja po preseku, kanon salje na pregled."""
    postojece = [{"issue_id": "I1", "status": "DISCOVERED", "claim_set": frozenset({C1, C2})}]

    def _spoji_po_preseku(claim_set, postojece_teme):
        for t in postojece_teme:
            if frozenset(t.get("claim_set") or ()) & claim_set:
                return {"odluka": "CONTINUATION", "issue_id": t["issue_id"], "kandidati": []}
        return {"odluka": "NEW_ISSUE", "issue_id": None, "kandidati": []}

    pod_mutacijom = _spoji_po_preseku(frozenset({C1, C3}), postojece)
    assert pod_mutacijom["odluka"] == "CONTINUATION", "mutacija nije primenjena"

    kanon = razresi_kontinuitet(frozenset({C1, C3}), postojece)
    assert kanon["odluka"] == "REVIEW_REQUIRED"
    assert kanon["issue_id"] is None
    assert kanon["kandidati"] == ["I1"]


# ═══════════════════════════════════════════════════════════════════════════
# M16 — povlačenje člana kao RESOLVED
# ═══════════════════════════════════════════════════════════════════════════

def test_M16_povlacenje_kao_RESOLVED_je_ubijeno():
    d = delta_clanstva([C1, C2, C3], [C1, C2])
    assert d["izostale"] == [C3]
    assert d["izostale_stanje"] == "NOT_OBSERVED"
    assert d["izostale_stanje"] != "RESOLVED", "izostanak iz izlaza nije razresen spor"


# ═══════════════════════════════════════════════════════════════════════════
# M4 — odbijanje intra-dokumentne kontradikcije
# ═══════════════════════════════════════════════════════════════════════════

def test_M4_odbijanje_intra_dokumentne_je_NEPREDSTAVLJIVO():
    """Adapter nikad ne čita `dokument_id`, pa uslov `dok_1 != dok_2` nema
    odakle da nastane. Jače od ubijene mutacije: kvar je nepredstavljiv."""
    izvor = open(os.path.join(os.path.dirname(__file__), "..", "services",
                              "v2_contradiction_persistence.py"), encoding="utf-8").read()
    kod = izvor.split('"""', 2)[-1]
    for pojam in ("dokument_id", "predmet_dokumenti", "lokacija"):
        assert pojam not in kod, f"adapter cita {pojam} — intra-dok kvar postaje moguc"

    supa = FakeSupa(dokazi=SVI_DOKAZI)
    r = _pokreni(supa, [_p([C1, C2])])
    assert r[0]["persisted"] is True


# ═══════════════════════════════════════════════════════════════════════════
# M11 / M13 / M14 — atomičnost i trka (nosilac je baza, ne adapter)
# ═══════════════════════════════════════════════════════════════════════════

def test_M11_M13_M14_nosilac_je_baza_a_adapter_ne_sme_da_ga_zaobidje():
    """Atomičnost i bezbednost od trke garantuje `v2_persist_contradiction`
    (A012: M6 i M4 ubijene uživo). Ovde se brani JEDINO što adapter može da
    pokvari — da počne da piše u tabele mimo RPC-a, čime bi izašao iz
    transakcione granice."""
    izvor = open(os.path.join(os.path.dirname(__file__), "..", "services",
                              "v2_contradiction_persistence.py"), encoding="utf-8").read()
    kod = izvor.split('"""', 2)[-1]
    for zabranjen_upis in (".insert(", ".upsert(", ".delete("):
        assert zabranjen_upis not in kod, (
            f"adapter pise mimo RPC-a ({zabranjen_upis}) — izlazi iz transakcije")
    # `.update(` se ne sme meriti sirovo: `dict.update` je legitiman i adapter ga
    # koristi nad sopstvenim ishodom. Meri se ono sto zaista znaci upis u bazu.
    import re
    for m in re.finditer(r"\.table\(\s*[\"']([a-z_]+)[\"']\s*\)((?:\s*\\?\s*\.\w+\([^)]*\))*)",
                         kod):
        lanac = m.group(2)
        assert ".select(" in lanac, f"table({m.group(1)}) bez .select — moguc upis: {lanac[:60]}"
        for w in (".insert(", ".update(", ".upsert(", ".delete("):
            assert w not in lanac, f"upis u {m.group(1)} mimo RPC-a: {w}"
    # A016.7: adapter je dobio DRUGI ulaz (`persist_observation_package`), pa je
    # tvrdi broj `== 1` prestao da meri nameru. Namera je bila „nema pisca mimo
    # RPC-a", ne „postoji tacno jedan poziv". Sada se meri namera, i to strože:
    # SVAKI `.rpc(` mora ici preko modulske konstante `_RPC*`, nikad preko
    # sirovog stringa koji bi mogao da uvede neproveren cetvrti put do baze.
    import re as _re
    pozivi = _re.findall(r"\.rpc\(\s*([^,]+),", kod)
    assert pozivi, "adapter vise ne zove nijedan RPC"
    for poziv in pozivi:
        assert poziv.strip().startswith("_RPC"), \
            f"RPC se zove mimo modulske konstante: {poziv.strip()!r}"


def _nadji_upise(kod: str) -> list[str]:
    """Ista logika koju koristi test iznad, izdvojena da bi mogla da se META-testira."""
    import re
    nalazi = []
    for m in re.finditer(r"\.table\(\s*[\"']([a-z_]+)[\"']\s*\)((?:\s*\\?\s*\.\w+\([^)]*\))*)",
                         kod):
        lanac = m.group(2)
        if ".select(" not in lanac:
            nalazi.append(f"table({m.group(1)}) bez .select")
        for w in (".insert(", ".update(", ".upsert(", ".delete("):
            if w in lanac:
                nalazi.append(f"{m.group(1)}{w}")
    return nalazi


def test_META_staticka_provera_upisa_zaista_puca():
    """Statička provera koja ne može da padne je prazna provera.

    Ovde se dokazuje da `_nadji_upise` stvarno vidi upis — inače bi test iznad
    prolazio i nad adapterom koji piše direktno u tabele."""
    assert _nadji_upise('supa.table("predmet_issues").insert(red).execute()')
    assert _nadji_upise('supa.table("predmet_contradictions").delete().eq("id", x).execute()')
    assert _nadji_upise('supa.table("predmet_issues").update({"a": 1}).execute()')
    # a nad stvarnim, ispravnim oblikom ne sme naći ništa
    assert _nadji_upise('supa.table("predmet_dokazi").select("id").eq("x", 1).execute()') == []


# ═══════════════════════════════════════════════════════════════════════════
# M2 / M17 / M19 / M20 — bile BLOKIRANE u A013, ODBLOKIRANE u A015
# ═══════════════════════════════════════════════════════════════════════════

def test_M2_M17_M19_M20_vise_nisu_blokirane():
    """A013 je ove četiri mutacije prijavio kao BLOKIRANE jer projekcioni sloj
    tada nije postojao, i ostavio zamku koja pada čim ga neko doda.

    A015 ga je dodao (`services/v2_projection.py`), pa zamka više nije na mestu.
    Umesto nje se ovde mere **sama svojstva** koja su te mutacije ciljale — ne
    postojanje fajla, nego ponašanje. Puna mutaciona suita je u
    `tests/test_a015_mutations.py`."""
    from services.v2_projection import je_v2_kljuc, projekcioni_kljuc, u_akcije

    K1 = "cccc0001-0000-4000-8000-000000000001"
    K2 = "cccc0002-0000-4000-8000-000000000002"

    def _k(cid, label):
        return {"id": cid, "issue_id": "i1", "issue_label": label,
                "relation_type": "cinjenica_cinjenica", "state": "OPEN",
                "tezina": "vazna", "claim_ids": ["c1", "c2"],
                "dokument_ids": ["d1", "d2"]}

    akcije = u_akcije([_k(K1, "datum"), _k(K2, "iznos")])

    # M2 — opseg: ključ je globalno jedinstven, pa `predmet_id` ne može ispasti
    #      iz identiteta projekcije.
    assert len({a["dedupe_key"] for a in akcije}) == 2
    assert all(je_v2_kljuc(a["dedupe_key"]) for a in akcije)

    # M17 — replay: isti ulaz daje isti ključ, pa ponovljeni refresh ne pravi
    #      novu akciju.
    assert {a["dedupe_key"] for a in akcije} == {projekcioni_kljuc(K1), projekcioni_kljuc(K2)}
    assert projekcioni_kljuc(K1) == projekcioni_kljuc(K1)

    # M19 — sudar obaveštenja: dva različita `contradiction_id` daju dva ključa
    #      i pod `(user_id, dedupe_key)` opsegom.
    assert projekcioni_kljuc(K1) != projekcioni_kljuc(K2)

    # M20 — provenijencija: `dokaz` nosi izvor i dokumente.
    for a in akcije:
        assert a["dokaz"]["source_type"] == "v2_contradiction"
        assert a["dokaz"]["source_id"] in (K1, K2)
        assert a["dokaz"]["dokument_ids"] == ["d1", "d2"]
        assert a["izvor_dokumenti"] == ["d1", "d2"]
