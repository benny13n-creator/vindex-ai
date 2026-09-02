# -*- coding: utf-8 -*-
"""FAZA 6.2 — AI OPAZANJE NE SME SAMO POKRENUTI IZVRSIVU OBAVEZU (INV-2).

STA JE BIO PROBLEM — IZMERENO UZIVO
====================================
FAZA 6.1 je pustila jedan pravi Genome refresh nad izolovanim fixture predmetom.
Genome je upisao TRI roka u `predmet_hronologija`, sva tri sa hardkodovanim
`vaznost="kritičan"`, dok je `_ACTIONABLE_VAZNOST = ["kritičan", "važan"]`.

Znaci: sva tri roka bila su podobna za email podsetnik, SMS i notifikaciju
**bez ijedne ljudske potvrde**. Jedini razlog zasto se nista nije desilo je taj
sto je `korisnik_email_notif` prazan — konfiguracija, ne bezbednosna granica.

`vaznost` je AI PROCENA TEZINE. Nije potvrda i nije ovlascenje.

STA JE SADA
===========
`shared/rokovi.py::sme_pokrenuti_obavezu` je JEDINA kapija. Fail-closed: red
ciji je `akter` AI potpis prolazi iskljucivo ako postoji ljudska potvrda.
Potvrda zivi u POSTOJECEM `audit_immutable` (isti oblik kao
`dokument_review_resolved`), pa nema nove tabele ni migracije.

GRANICA KOJA SE OVDE NE PRELAZI
================================
Ovo NIJE identitet roka i NIJE rezolucija identiteta. `resource_id` je
`predmet_hronologija.id` — identitet REDA, ne cinjenice. FAZA 6.1 je dokazala
da identitet cinjenice danas nije resiv i ovaj sprint to ne pokusava.

NIJEDAN TEST NE SALJE PRAVI EMAIL NI SMS.
"""
import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.rokovi import (  # noqa: E402
    AI_AKTERI, je_ai_poreklo, sme_pokrenuti_obavezu, filtriraj_izvrsive,
)

UID = "u-1"
PID = "p-1"
MAIL = "advokat@example.invalid"


def _ai_rok(rid="r-ai", vaznost="kritičan", akter="Genome (AI)", izvor="AI_AUTONOMOUS"):
    return {"id": rid, "akter": akter, "izvor": izvor, "vaznost": vaznost,
            "predmet_id": PID, "user_id": UID,
            "dogadjaj": "Rok za reklamaciju", "datum_iso": "2026-03-15"}


def _ljudski_rok(rid="r-h"):
    return {"id": rid, "akter": "Advokat Marko", "izvor": "HUMAN_DIRECT",
            "vaznost": "kritičan",
            "predmet_id": PID, "user_id": UID,
            "dogadjaj": "Rok iz ugovora", "datum_iso": "2026-03-15"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. KANONSKI PREDIKAT — TEST A/B/C/D/E
# ═══════════════════════════════════════════════════════════════════════════

def test_akter_VISE_NIJE_provenijencija():
    """Migracija 127: kapija cita `izvor`, ne `akter`.

    `je_ai_poreklo` je zadrzano samo za prikaz i za ovaj regresioni dokaz —
    FAZA 6.2.1 je izmerila da `akter` nosi ime stranke iz LLM izlaza."""
    assert set(AI_AKTERI) == {"Genome (AI)", "Pipeline (AI)"}
    # `akter` koji "izgleda ljudski" NE otvara kapiju ako je `izvor` AI:
    r = {"id": "x", "akter": "Poslodavac DOO Sever", "izvor": "AI_AUTONOMOUS"}
    assert sme_pokrenuti_obavezu(r, set()) is False


def test_ljudski_akter_nije_ai():
    for a in ("Advokat Marko", "DOO Alfa Trejd", "Automatski — ZPP lanac | ...", "", None):
        assert not je_ai_poreklo(a), "%r pogresno svrstan u AI poreklo" % (a,)


def test_poredjenje_je_doslovno_a_ne_labavo():
    """`startswith`/`in` bi ljudski unos koji POMINJE AI ugasio kao AI rok."""
    assert not je_ai_poreklo("Genome (AI) je pogresio, ispravio Marko")
    assert not je_ai_poreklo("prepisano iz Pipeline (AI)")


@pytest.mark.parametrize("vaznost", ["kritičan", "važan", "informativan"])
def test_A_B_C_nepotvrdjen_ai_rok_nije_izvrsiv_ni_za_jednu_vaznost(vaznost):
    """TEST A/B/C: `vaznost` NIJE ovlascenje — nijedna vrednost ne otvara kapiju."""
    assert sme_pokrenuti_obavezu(_ai_rok(vaznost=vaznost), set()) is False


def test_D_potvrdjen_ai_rok_prolazi_kapiju():
    """TEST D: posle potvrde red ide dalje u POSTOJECU logiku (koja i dalje
    sama odlucuje po `vaznost`/datumu — ovaj gejt je ne zamenjuje)."""
    assert sme_pokrenuti_obavezu(_ai_rok(rid="r-ok"), {"r-ok"}) is True


def test_E_odbijen_rok_nije_izvrsiv():
    """TEST E: odbijanje se u `potvrdjeni_ids` manifestuje kao ODSUSTVO iz
    skupa potvrdjenih — pa red ne prolazi."""
    assert sme_pokrenuti_obavezu(_ai_rok(rid="r-no"), {"r-neki-drugi"}) is False


def test_ljudski_rok_nije_gejtovan():
    """Regresija: rok koji je uneo covek nikad nije trazio potvrdu i ne trazi je sada."""
    assert sme_pokrenuti_obavezu(_ljudski_rok(), set()) is True


def test_red_BEZ_izvora_je_FAIL_CLOSED():
    """`izvor` je `NOT NULL` u bazi (migracija 127), pa odsutan kljuc moze da
    znaci SAMO da ga upit nije dovukao. Pogadjanje na osnovu nedostajuceg
    podatka je tacno ono sto je otvorilo rupu iz FAZE 6.2.1.

    Meri se BEZ potvrde: potvrda je jaci signal od provenijencije."""
    assert sme_pokrenuti_obavezu({"id": "x", "vaznost": "kritičan"}, set()) is False


def _zastarelo_test_red_bez_kljuca_akter():
    """SVESNA GRANICA, ne previd.

    Kapija poreklo cita iz `akter`. Ako ga upit ne dovuce, red izgleda ljudski
    i prolazi. Razmatrano je strozije pravilo (odsutan kljuc -> fail-closed),
    ali ono gasi rokove u 10 postojecih testova cije fixture-e ne modeluju
    `akter` — dakle i u svakom buducem pozivaocu koji ga zaboravi, sto bi bio
    tih GUBITAK funkcionalnosti umesto tihe opasnosti.

    Zastita je zato pomerena na nivo UPITA: `test_faza62_gate_e2e_paths.py`
    ima veran harness koji postuje `.select(...)`, pa mutacija koja izbaci
    `akter` iz upita obara TEST F. Dokazano: M6 KILLED."""
    bez_kljuca = {"id": "x", "vaznost": "kritičan", "predmet_id": PID}
    assert sme_pokrenuti_obavezu(bez_kljuca, set()) is True


def test_ai_rok_bez_id_je_fail_closed():
    r = _ai_rok()
    r.pop("id")
    assert sme_pokrenuti_obavezu(r, {"bilo-sta"}) is False


def test_filtriranje_zadrzava_ljudske_a_uklanja_nepotvrdjene_ai():
    redovi = [_ai_rok("a1"), _ljudski_rok("h1"), _ai_rok("a2")]
    assert [r["id"] for r in filtriraj_izvrsive(redovi, {"a2"})] == ["h1", "a2"]
    assert [r["id"] for r in filtriraj_izvrsive(redovi, set())] == ["h1"]
    assert filtriraj_izvrsive(None, set()) == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. NOSILAC POTVRDE — fail-closed i "poslednja odluka pobedjuje"
# ═══════════════════════════════════════════════════════════════════════════

class _AuditUpit:
    def __init__(self, redovi):
        self._r = list(redovi)

    def select(self, *a, **k):
        return self

    def eq(self, k, v):
        return _AuditUpit([r for r in self._r if r.get(k) == v])

    def in_(self, k, vs):
        return _AuditUpit([r for r in self._r if r.get(k) in set(vs)])

    def order(self, k, **kw):
        return _AuditUpit(sorted(self._r, key=lambda r: r.get(k, 0)))

    def execute(self):
        class R:
            pass
        r = R()
        r.data = self._r
        return r


def _audit_supa(redovi):
    class S:
        def table(self, t):
            assert t == "audit_immutable"
            return _AuditUpit(redovi)
    return S()


def _zapis(rid, akcija, seq):
    return {"resource_type": "rok", "resource_id": rid, "action": akcija, "seq": seq}


def test_potvrda_daje_id_u_skupu():
    from shared import rok_potvrda as rp
    with patch("shared.deps._get_supa", lambda: _audit_supa([_zapis("r1", "rok_potvrdjen", 1)])):
        assert rp.potvrdjeni_ids(["r1"]) == {"r1"}


def test_odbijanje_POSLE_potvrde_gasi_izvrsivost():
    """Poslednja odluka pobedjuje — kljucna semantika."""
    from shared import rok_potvrda as rp
    zapisi = [_zapis("r1", "rok_potvrdjen", 1), _zapis("r1", "rok_odbijen", 2)]
    with patch("shared.deps._get_supa", lambda: _audit_supa(zapisi)):
        assert rp.potvrdjeni_ids(["r1"]) == set()


def test_potvrda_POSLE_odbijanja_vraca_izvrsivost():
    from shared import rok_potvrda as rp
    zapisi = [_zapis("r1", "rok_odbijen", 1), _zapis("r1", "rok_potvrdjen", 2)]
    with patch("shared.deps._get_supa", lambda: _audit_supa(zapisi)):
        assert rp.potvrdjeni_ids(["r1"]) == {"r1"}


def test_pad_upita_ne_otvara_kapiju():
    """FAIL-CLOSED: greska u citanju odluka NE SME da propusti AI rok."""
    from shared import rok_potvrda as rp

    def _puca():
        raise RuntimeError("baza nedostupna")

    with patch("shared.deps._get_supa", _puca):
        assert rp.potvrdjeni_ids(["r1"]) == set()


def test_prazan_ulaz_ne_zove_bazu():
    from shared import rok_potvrda as rp

    def _ne_sme():
        raise AssertionError("baza pozvana za prazan ulaz")

    with patch("shared.deps._get_supa", _ne_sme):
        assert rp.potvrdjeni_ids([]) == set()


def test_akcije_su_u_AUDITABLE_ACTIONS():
    """Bez ovoga `log_action` TIHO vraca None i potvrda se nikad ne upise —
    a gejt je fail-closed, pa rok ostaje zauvek neizvrsiv."""
    from shared.audit_immutable import AUDITABLE_ACTIONS
    from shared.rok_potvrda import AKCIJA_POTVRDA, AKCIJA_ODBIJANJE
    assert AKCIJA_POTVRDA in AUDITABLE_ACTIONS
    assert AKCIJA_ODBIJANJE in AUDITABLE_ACTIONS


def test_neupisana_potvrda_prijavljuje_neuspeh():
    """`log_action` vraca None -> `potvrdi_rok` mora vratiti False, nikad True."""
    from shared import rok_potvrda as rp

    async def _none(*a, **k):
        return None

    with patch("shared.audit_immutable.log_action", _none):
        assert asyncio.run(rp.potvrdi_rok("r1", UID)) is False


def test_idempotencija_ponovljena_potvrda_daje_isti_ishod():
    """CONFIRM, pa CONFIRM ponovo, pa retry — skup potvrdjenih se ne menja."""
    from shared import rok_potvrda as rp
    zapisi = [_zapis("r1", "rok_potvrdjen", i) for i in (1, 2, 3)]
    with patch("shared.deps._get_supa", lambda: _audit_supa(zapisi)):
        assert rp.potvrdjeni_ids(["r1"]) == {"r1"}
        assert rp.potvrdjeni_ids(["r1"]) == {"r1"}
