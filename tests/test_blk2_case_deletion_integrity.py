# -*- coding: utf-8 -*-
"""BLK-2 — PREDMET IZ DOKUMENTA MORA MOĆI DA SE OBRIŠE.

DOKAZANI KVAR (produkcija `57bec9d`, uživo 3/3 — BLK-2 §14):

    kontrolna grupa (predmet bez dokumenta)  DELETE → 200 DELETED
    predmet iz 1 dokumenta                   DELETE → 409 RETRYABLE_FAILURE
    predmet iz 3 dokumenta                   DELETE → 409 RETRYABLE_FAILURE
    predmet iz dokumenta + rok + događaji    DELETE → 409 RETRYABLE_FAILURE

    neuspele_tabele: ["intake_jobs"] · vektori: "NIJE_POKRENUTO"
    ponovljen pokušaj pada identično — zauvek

Uzrok je ISTA KLASA kao `case_evolution_consequences` iz BETA-DEL-001, samo u
drugom stablu: politika je modelovala ODLAZNE FK ka `predmeti`, a šest tabela
ima DOLAZNU FK ka `intake_jobs` bez `ON DELETE`. Te tabele nemaju kolonu
`predmet_id` pa su bile nedohvatljive jedinom predikatu politike.

INVARIANT KOJI OVAJ PAKET ČUVA:

    Predmet kreiran kroz dokument briše se po istom ugovoru kao i svaki
    drugi — ili se pošteno prijavljuje da nije obrisan.
"""
import os
import sys

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from shared.predmet_deletion import (  # noqa: E402
    IshodPredmeta,
    KOLONE_VEZE_KA_POSLOVIMA,
    TABELE_DECA_POSLOVA,
    obrisi_predmet,
)
from test_p15_predmet_deletion import PID, UID  # noqa: E402


# ─── Verniji test-dvojnik ────────────────────────────────────────────────────
#
# `test_p15_predmet_deletion._Supa` je namerno ostavljen NETAKNUT (§21 naloga:
# ne dirati postojeće testove). Njegov `_Upit.in_()` beleži filter pod ključem
# `__in__<kolona>`, koji se pri `select`-u poredi sa `r.get("__in__<kolona>")`
# i zato uvek eliminiše sve redove. Za BETA-DEL-001 to nije smetalo (`in_` se
# tamo koristi samo na `delete`, gde se filteri ignorišu), ali BLK-2 ČITA
# `intake_documents` preko `in_` — sa starim dvojnikom bi spisak uvek bio
# prazan i test bi „prolazio" ne dodirnuvši ono što meri.
#
# Dvojnik ispod poštuje isti ugovor beleženja (`redovi`, `puca`, `brisanja`,
# `azuriranja`), samo `in_` stvarno filtrira.

class _Upit:
    def __init__(self, d, tabela, akcija):
        self.d, self.t, self.a = d, tabela, akcija
        self.eq_filteri = {}
        self.in_filteri = {}

    def eq(self, k, v):
        self.eq_filteri[k] = v
        return self

    def in_(self, k, v):
        self.in_filteri[k] = list(v)
        return self

    def is_(self, k, v):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        g = self.d.puca.get(self.t)
        if g is not None:
            raise g
        if self.a == "update":
            self.d.azuriranja.append(self.t)
            return MagicMock(data=[])
        if self.a == "delete":
            self.d.brisanja.append(self.t)
            return MagicMock(data=[])
        redovi = self.d.redovi.get(self.t, [])
        for k, v in self.eq_filteri.items():
            redovi = [r for r in redovi if r.get(k) == v]
        for k, v in self.in_filteri.items():
            redovi = [r for r in redovi if r.get(k) in v]
        m = MagicMock()
        m.data = redovi
        return m


class _Tabela:
    def __init__(self, d, ime):
        self.d, self.ime = d, ime

    def select(self, *a, **k):
        return _Upit(self.d, self.ime, "select")

    def delete(self, *a, **k):
        return _Upit(self.d, self.ime, "delete")

    def update(self, *a, **k):
        return _Upit(self.d, self.ime, "update")


class _Supa:
    def __init__(self, redovi=None, puca=None):
        self.redovi = redovi if redovi is not None else {
            "predmeti": [{"id": PID, "user_id": UID}],
            "billing_entries": [],
            "predmet_dokumenti": [],
        }
        self.puca = puca or {}
        self.brisanja = []
        self.azuriranja = []

    def table(self, ime):
        return _Tabela(self, ime)


def _iz_dokumenta(poslova=1, dokumenata=1):
    """Predmet TAČNO onakav kakav Smart Intake finalize ostavlja."""
    s = _Supa()
    s.redovi["intake_jobs"] = [
        {"id": "job-%d" % i, "predmet_id": PID} for i in range(poslova)
    ]
    s.redovi["intake_documents"] = [
        {"id": "idok-%d" % i, "intake_job_id": "job-0"} for i in range(dokumenata)
    ]
    s.redovi["predmet_dokumenti"] = [
        {"id": "d1", "predmet_id": PID, "user_id": UID,
         "source_intake_job_id": "job-0", "source_intake_job_segment_id": None}
    ]
    s.redovi["events"] = [{"id": "e1", "predmet_id": PID}]
    return s


def _obrisi(s, *, sme=True, vektori_uspeh=True):
    v = MagicMock()
    v.uspeh = vektori_uspeh
    v.ishod = "DELETED" if vektori_uspeh else "PARTIAL_FAILURE"
    with patch("shared.vector_deletion._sme_predmet", return_value=sme), \
         patch("shared.vector_deletion.obrisi_vektore_dokumenta", return_value=v) as mv:
        r = obrisi_predmet(s, MagicMock(), user_id=UID, predmet_id=PID)
    return r, mv


# ═══════════════════════════════════════════════════════════════════════════
# 1 — JEZGRO BLOKERA
# ═══════════════════════════════════════════════════════════════════════════

def test_1_predmet_iz_dokumenta_moze_da_se_obrise():
    """Doslovan slučaj B iz reprodukcije: pre popravke 409, sada DELETED."""
    s = _iz_dokumenta()
    r, _ = _obrisi(s)

    assert r.ishod == IshodPredmeta.DELETED
    assert r.uspeh is True
    assert "predmeti" in s.brisanja, "sam predmet nije obrisan"
    assert r.neuspele_tabele == []


def test_1b_deca_poslova_se_brisu_PRE_intake_jobs():
    """Redosled je jedina stvar koja ovo drži — FK-ovi nisu menjani."""
    s = _iz_dokumenta()
    _obrisi(s)

    poz_jobs = s.brisanja.index("intake_jobs")
    for tabela, _kolona in TABELE_DECA_POSLOVA:
        assert tabela in s.brisanja, "%s nije očišćena" % tabela
        assert s.brisanja.index(tabela) < poz_jobs, (
            "%s je brisana POSLE intake_jobs — baza bi odbila ceo korak" % tabela)


def test_1c_redosled_medju_decom_postuje_graf():
    """outcomes PRE segments (segment_id FK), segments i entities PRE documents."""
    s = _iz_dokumenta()
    _obrisi(s)
    r = {t: s.brisanja.index(t) for t, _ in TABELE_DECA_POSLOVA}

    assert r["intake_processing_outcomes"] < r["intake_job_segments"]
    assert r["intake_job_segments"] < r["intake_documents"]
    assert r["extracted_entities"] < r["intake_documents"]


def test_1d_vise_poslova_i_dokumenata():
    """Slučaj C iz reprodukcije: 3 dokumenta = 4 posla, 4 intake dokumenta."""
    s = _iz_dokumenta(poslova=4, dokumenata=4)
    r, _ = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED


# ═══════════════════════════════════════════════════════════════════════════
# 2 — `predmet_dokumenti` SE ODVEZUJE, NE BRIŠE
# ═══════════════════════════════════════════════════════════════════════════

def test_2_veza_ka_poslovima_se_raskida():
    """Obe lineage kolone (migracije 094 i 095) moraju biti postavljene na NULL."""
    s = _iz_dokumenta()
    _obrisi(s)
    assert s.azuriranja.count("predmet_dokumenti") == len(KOLONE_VEZE_KA_POSLOVIMA)


def test_2b_predmet_dokumenti_se_NE_brise_pre_vektora():
    """Korak 6 iz `predmet_dokumenti` čita koje vektore treba ukloniti. Ako bi
    red bio obrisan ranije, vektori bi tiho ostali — PINE-01 klasa."""
    s = _iz_dokumenta()
    r, mv = _obrisi(s)

    assert "predmet_dokumenti" not in s.brisanja, (
        "predmet_dokumenti je obrisan eksplicitno — vektori bi ostali; "
        "CASCADE sa `predmeti` ga briše u koraku 7")
    assert mv.call_count == 1, "vektori dokumenta nisu obrisani"
    assert r.vektori == "OBRISANI"


# ═══════════════════════════════════════════════════════════════════════════
# 3 — PAD KORAKA NE SME DA DODIRNE VEKTORE (BETA-DEL-001 invariant)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("pada", [t for t, _ in TABELE_DECA_POSLOVA])
def test_3_pad_deteta_posla_ne_dira_vektore(pada):
    s = _iz_dokumenta()
    s.puca[pada] = Exception("row-level security policy violated (42501)")
    r, mv = _obrisi(s)

    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert pada in r.neuspele_tabele
    assert mv.call_count == 0, "VEKTORI DIRANI iako je brisanje redova palo"
    assert r.vektori == "NIJE_POKRENUTO"
    assert "predmeti" not in s.brisanja


def test_3b_pad_citanja_poslova_zaustavlja_sve():
    s = _iz_dokumenta()
    s.puca["intake_jobs"] = TimeoutError("connection timeout expired")
    r, mv = _obrisi(s)

    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert mv.call_count == 0
    assert "predmeti" not in s.brisanja


def test_3c_tombstone_je_upisan_pre_svega():
    """Prvi upis mora biti tombstone, ne raskidanje veze."""
    s = _iz_dokumenta()
    r, _ = _obrisi(s)
    assert r.tombstone == "UPISAN"
    assert s.azuriranja[0] == "predmeti", "prvi upis nije tombstone"


# ═══════════════════════════════════════════════════════════════════════════
# 4 — NEPOSTOJEĆE TABELE SE PRESKAČU, NE OBARAJU BRISANJE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("pada", [t for t, _ in TABELE_DECA_POSLOVA])
def test_4_nepostojeca_tabela_ne_obara_brisanje(pada):
    """Deploy pre migracije mora ostati bezbedan — isto pravilo koje politika
    već primenjuje na `TABELE_BEZ_FK`."""
    s = _iz_dokumenta()
    s.puca[pada] = Exception(
        "Could not find the table 'public.%s' in the schema cache (PGRST205)" % pada)
    r, _ = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED


# ═══════════════════════════════════════════════════════════════════════════
# 5 — REGRESIJA: PREDMET BEZ DOKUMENTA NEPROMENJEN
# ═══════════════════════════════════════════════════════════════════════════

def test_5_obican_predmet_bez_intake_poslova_i_dalje_radi():
    """Kontrolna grupa iz reprodukcije — bila je 200 i pre popravke."""
    s = _Supa()
    r, _ = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED
    assert r.vektori == "NEMA_DOKUMENATA"


def test_5b_bez_poslova_se_ne_dira_nijedna_intake_tabela():
    """Predmet bez intake istorije ne sme da plati cenu ove popravke."""
    s = _Supa()
    _obrisi(s)
    for tabela, _k in TABELE_DECA_POSLOVA:
        assert tabela not in s.brisanja, (
            "%s je dirana za predmet koji nema nijedan intake posao" % tabela)


# ═══════════════════════════════════════════════════════════════════════════
# 6 — AUDIT KOJI JE ZAŠTIĆEN OKIDAČEM SE NE DIRA
# ═══════════════════════════════════════════════════════════════════════════

def test_6_audit_immutable_se_nikad_ne_dira():
    """Invarijanta 3 specifikacije. `intake_audit_log` NIJE ista stvar —
    nema okidač, nema REVOKE (v. BLK-2 izveštaj §6)."""
    s = _iz_dokumenta()
    _obrisi(s)
    for t in ("audit_immutable", "audit_log", "saradnja_audit"):
        assert t not in s.brisanja, "%s je dirana — zabranjeno" % t


def test_6b_billing_entries_i_dalje_blokira_predmet_iz_dokumenta():
    """FK RESTRICT mora da važi i za dokument-predmete — finansijski trag
    se ne gubi zato što je predmet nastao iz dokumenta."""
    s = _iz_dokumenta()
    s.redovi["billing_entries"] = [{"id": "b1", "predmet_id": PID}]
    r, mv = _obrisi(s)

    assert r.ishod == IshodPredmeta.BLOCKED
    assert s.brisanja == [], "nešto je dirano uprkos blokadi"
    assert s.azuriranja == [], "tombstone upisan uprkos blokadi"
    assert mv.call_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# 7 — AUTORIZACIJA (§8 naloga) — nepromenjena, ali dokazana i za ovaj put
# ═══════════════════════════════════════════════════════════════════════════

def test_7_bez_prava_pristupa_nista_se_ne_dira():
    s = _iz_dokumenta()
    r, mv = _obrisi(s, sme=False)

    assert r.ishod == IshodPredmeta.REFUSED
    assert s.brisanja == []
    assert s.azuriranja == []
    assert mv.call_count == 0
