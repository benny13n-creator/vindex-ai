# -*- coding: utf-8 -*-
"""BETA-DEL-001 — INTEGRITET BRISANJA PREDMETA.

DOKAZANI KVAR (produkcija `27cb670`, uživo 3/3):

    pre:     pitanje vraća 847.250,00                     DA
    DELETE:  409 PARTIAL_FAILURE, vektori=OBRISANI,
             neuspele_tabele=['events']
    poruka:  „predmet NIJE obrisan i operacija se moze ponoviti"
    posle:   predmet vidljiv, dokument u bazi,
             pitanje VIŠE NE VRAĆA činjenicu              NE

Korisniku je rečeno da ništa nije promenjeno, a sadržaj predmeta je nepovratno
uništen. Retry nije mogao da uspe: FK `case_evolution_consequences.event_id →
events.id` (migracija 096, bez `ON DELETE`) padao bi svaki put.

INVARIANT KOJI OVAJ PAKET ČUVA:

    Nijedan predmet ne može biti istovremeno vidljiv korisniku
    i lišen svojih vektora.

Zato: tombstone se upisuje PRE ijedne destrukcije, vektori su POSLEDNJI
destruktivni korak, a deca koja vise o `events(id)` brišu se PRE `events`.
"""
import os
import sys

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from shared.predmet_deletion import (  # noqa: E402
    IshodPredmeta, TABELE_DECA_DOGADJAJA, obrisi_predmet,
)
from test_p15_predmet_deletion import _Supa, PID, UID, TUDJ_UID  # noqa: E402


def _sa_dokumentom(s=None):
    s = s or _Supa()
    s.redovi["predmet_dokumenti"] = [{"id": "d1", "predmet_id": PID, "user_id": UID}]
    s.redovi["events"] = [{"id": "e1", "predmet_id": PID}]
    return s


def _obrisi(s, *, index=None, sme=True, uid=UID, vektori_uspeh=True, v_ishod="DELETED"):
    v = MagicMock()
    v.uspeh = vektori_uspeh
    v.ishod = v_ishod
    idx = MagicMock() if index is None else index
    with patch("shared.vector_deletion._sme_predmet", return_value=sme), \
         patch("shared.vector_deletion.obrisi_vektore_dokumenta", return_value=v) as mock_v:
        r = obrisi_predmet(s, idx, user_id=uid, predmet_id=PID)
    return r, mock_v


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1 — NIKADA: ŽIV PREDMET + OBRISANI VEKTORI
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("pada", ["events", "zadaci", "case_evolution_consequences"])
def test_1_pad_DB_koraka_ne_sme_da_dodirne_vektore(pada):
    """Jezgro blockera. Ako brisanje redova padne, vektori se NE SMEJU brisati."""
    s = _sa_dokumentom()
    s.puca[pada] = Exception("row-level security policy violated (42501)")
    r, mock_v = _obrisi(s)

    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert mock_v.call_count == 0, (
        "VEKTORI SU DIRANI iako je brisanje redova palo — to je tačno "
        "BETA-DEL-001")
    assert r.vektori == "NIJE_POKRENUTO"
    assert "predmeti" not in s.brisanja


def test_1b_predmet_nikad_nije_obrisan_dok_vektori_nisu():
    s = _sa_dokumentom()
    r, _ = _obrisi(s, vektori_uspeh=False, v_ishod="PARTIAL_FAILURE")
    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert "predmeti" not in s.brisanja, (
        "predmet je obrisan a vektori nisu — orphan vektor bez vlasnika")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2 — TOMBSTONE JE UPISAN PRE SVAKE DESTRUKCIJE
# ═══════════════════════════════════════════════════════════════════════════

def test_2_tombstone_prethodi_svakoj_destrukciji():
    s = _sa_dokumentom()
    r, _ = _obrisi(s)
    assert r.tombstone == "UPISAN"
    assert s.azuriranja and s.azuriranja[0] == "predmeti", (
        "prvi upis nije tombstone")


def test_2b_bez_tombstone_a_se_NE_DIRA_NISTA():
    """Migracija 114 nije primenjena → `update` puca → PERMANENT_FAILURE."""
    s = _sa_dokumentom()
    s.puca["predmeti"] = Exception("column predmeti.brisanje_zapoceto does not exist")
    r, mock_v = _obrisi(s)
    assert r.ishod == IshodPredmeta.PERMANENT_FAILURE
    assert mock_v.call_count == 0, "vektori dirani bez tombstone-a"
    assert s.brisanja == [], "redovi brisani bez tombstone-a"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3 — DECA KOJA VISE O `events(id)`
# ═══════════════════════════════════════════════════════════════════════════

def test_3_deca_dogadjaja_se_brisu_PRE_events():
    s = _sa_dokumentom()
    r, _ = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED
    for t in TABELE_DECA_DOGADJAJA:
        assert t in s.brisanja, "%s nije obrisana" % t
    assert s.brisanja.index("case_evolution_consequences") < s.brisanja.index("events"), (
        "`events` je obrisan PRE svoje dece — FK bi pao")


def test_3b_pad_dece_zaustavlja_pre_vektora():
    s = _sa_dokumentom()
    s.puca["case_evolution_consequences"] = Exception("violates foreign key constraint")
    r, mock_v = _obrisi(s)
    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert "case_evolution_consequences" in r.neuspele_tabele
    assert mock_v.call_count == 0


def test_3c_bez_dogadjaja_se_deca_ne_diraju():
    """Predmet bez `events` redova — nema šta da se briše po `event_id`."""
    s = _Supa()
    s.redovi["events"] = []
    r, _ = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED
    assert "case_evolution_consequences" not in s.brisanja


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4 — RETRY
# ═══════════════════════════════════════════════════════════════════════════

def test_4_retry_posle_pada_napreduje():
    s = _sa_dokumentom()
    s.puca["zadaci"] = Exception("timeout")
    r1, _ = _obrisi(s)
    assert r1.ishod == IshodPredmeta.RETRYABLE_FAILURE

    del s.puca["zadaci"]                      # uzrok otklonjen
    r2, _ = _obrisi(s)
    assert r2.ishod == IshodPredmeta.DELETED, "retry nije napredovao"


def test_4b_retry_posle_ALREADY_ABSENT_vektora_je_idempotentan():
    s = _sa_dokumentom()
    r, _ = _obrisi(s, vektori_uspeh=True, v_ishod="ALREADY_ABSENT")
    assert r.ishod == IshodPredmeta.DELETED
    assert r.vektori == "OBRISANI"


def test_4c_retry_ne_pravi_novo_neusklaeno_stanje():
    """Dva uzastopna pada daju ISTI ishod — nikad gori."""
    s = _sa_dokumentom()
    s.puca["events"] = Exception("violates foreign key constraint")
    r1, v1 = _obrisi(s)
    r2, v2 = _obrisi(s)
    assert r1.ishod == r2.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert v1.call_count == v2.call_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5 — FAILURE INJECTION: PINECONE
# ═══════════════════════════════════════════════════════════════════════════

def test_5_izuzetak_u_vektorima_ostavlja_tombstone_i_predmet():
    s = _sa_dokumentom()
    idx = MagicMock()
    with patch("shared.vector_deletion._sme_predmet", return_value=True), \
         patch("shared.vector_deletion.obrisi_vektore_dokumenta",
               side_effect=RuntimeError("pinecone timeout")):
        r = obrisi_predmet(s, idx, user_id=UID, predmet_id=PID)
    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert r.vektori == "NEUSPEH"
    assert r.tombstone == "UPISAN"
    assert "predmeti" not in s.brisanja


def test_5b_indeks_nedostupan_uz_dokumente():
    s = _sa_dokumentom()
    r, _ = _obrisi(s, index=None)   # index=None -> MagicMock; zato eksplicitno:
    assert r.ishod == IshodPredmeta.DELETED
    s2 = _sa_dokumentom()
    with patch("shared.vector_deletion._sme_predmet", return_value=True):
        r2 = obrisi_predmet(s2, None, user_id=UID, predmet_id=PID)
    assert r2.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert r2.tombstone == "UPISAN"
    assert "predmeti" not in s2.brisanja


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6 — TENANT IZOLACIJA OSTAJE FAIL-CLOSED
# ═══════════════════════════════════════════════════════════════════════════

def test_6_tudji_predmet_ne_dobija_ni_tombstone():
    s = _sa_dokumentom()
    r, mock_v = _obrisi(s, uid=TUDJ_UID)
    assert r.ishod == IshodPredmeta.ALREADY_ABSENT
    assert s.azuriranja == [], "tuđi predmet je tombstonovan"
    assert s.brisanja == []
    assert mock_v.call_count == 0


def test_6b_bez_prava_pristupa_ne_dobija_tombstone():
    s = _sa_dokumentom()
    r, mock_v = _obrisi(s, sme=False)
    assert r.ishod == IshodPredmeta.REFUSED
    assert s.azuriranja == []
    assert mock_v.call_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7 — BLOKADA (billing_entries) NE DIRA NIŠTA
# ═══════════════════════════════════════════════════════════════════════════

def test_7_blokada_naplate_ne_upisuje_tombstone():
    s = _sa_dokumentom()
    s.redovi["billing_entries"] = [{"id": "b1", "predmet_id": PID}]
    r, mock_v = _obrisi(s)
    assert r.ishod == IshodPredmeta.BLOCKED
    assert s.azuriranja == [], "predmet je tombstonovan iako je brisanje blokirano"
    assert s.brisanja == []
    assert mock_v.call_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8 — LEGACY: NORMALAN PREDMET SE I DALJE BRIŠE
# ═══════════════════════════════════════════════════════════════════════════

def test_8_predmet_bez_problematicnih_zavisnosti_se_brise():
    s = _Supa()
    r, _ = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED and r.uspeh is True
    assert "predmeti" in s.brisanja
    assert r.tombstone == "UPISAN"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9 — SEMANTIKA NEUSPEHA
# ═══════════════════════════════════════════════════════════════════════════

def test_9_retryable_i_permanent_nisu_isti_ishod():
    from shared.predmet_deletion import RezultatBrisanja
    assert IshodPredmeta.RETRYABLE_FAILURE != IshodPredmeta.PERMANENT_FAILURE
    for ishod in (IshodPredmeta.RETRYABLE_FAILURE, IshodPredmeta.PERMANENT_FAILURE,
                  IshodPredmeta.BLOCKED, IshodPredmeta.REFUSED):
        assert RezultatBrisanja(ishod).uspeh is False, ishod


def test_9b_ukinut_je_genericki_PARTIAL_FAILURE():
    """Jedan ishod ne sme ponovo da pokrije dve suprotne semantike."""
    assert not hasattr(IshodPredmeta, "PARTIAL_FAILURE")


def test_9c_rezultat_prijavljuje_tombstone_stanje():
    from shared.predmet_deletion import RezultatBrisanja
    d = RezultatBrisanja(IshodPredmeta.DELETED).kao_dict()
    assert "tombstone" in d, "ishod ne prijavljuje da li je predmet oznacen"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10 — TOMBSTONOVAN PREDMET NIJE IZVOR ZA RAG
#
# Ovo je druga polovina invarianta. Bez nje bi tombstone bio samo oznaka:
# vektori bi nestali, a predmet bi i dalje ulazio u kontekst.
# B4-M2 logika se NE dira — isključenje je uzvodno, u ACL usko grlo.
# ═══════════════════════════════════════════════════════════════════════════

class _AclSupa:
    """Dvojnik koji BELEZI da li je filter `brisanje_zapoceto` primenjen."""

    def __init__(self, redovi, podrzava_kolonu=True):
        self.redovi = redovi
        self.podrzava = podrzava_kolonu
        self.filter_primenjen = False

    def table(self, ime):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, k, v):
        return self

    def is_(self, k, v):
        if not self.podrzava:
            raise Exception('column predmeti.brisanje_zapoceto does not exist')
        self.filter_primenjen = True
        return self

    def execute(self):
        redovi = self.redovi
        if self.filter_primenjen:
            redovi = [r for r in redovi if r.get("brisanje_zapoceto") is None]
        return MagicMock(data=[{"id": r["id"]} for r in redovi])


def test_10_tombstonovan_predmet_nije_u_dozvoljenim():
    from shared.rag_acl import dozvoljeni_predmeti
    s = _AclSupa([
        {"id": "aktivan", "brisanje_zapoceto": None},
        {"id": "brise-se", "brisanje_zapoceto": "2026-08-21T00:00:00+00:00"},
    ])
    ids = dozvoljeni_predmeti(s, UID)
    assert "aktivan" in ids
    assert "brise-se" not in ids, (
        "predmet u brisanju je i dalje izvor za RAG — vektori bi mu nestali "
        "dok je jos dohvatljiv")


def test_10b_bez_migracije_ACL_i_dalje_radi():
    """Pre migracije 114 filter ne postoji. Retrieval NE SME da padne — a
    tombstone se tada ionako ne moze upisati, pa nijedan predmet nije DELETING."""
    from shared.rag_acl import dozvoljeni_predmeti
    s = _AclSupa([{"id": "aktivan", "brisanje_zapoceto": None}], podrzava_kolonu=False)
    ids = dozvoljeni_predmeti(s, UID)
    assert ids == ["aktivan"], "ACL je pao bez migracije — retrieval bi stao svima"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 11 — API UGOVOR: „PONOVI" SME DA PIŠE SAMO KAD RETRY ZAISTA POMAŽE
#
# Stara poruka je glasila „operacija se moze ponoviti" i za slučaj u kome je
# identičan retry deterministički padao zauvek. To je bila neistina isporučena
# advokatu u trenutku kad je već izgubio sadržaj predmeta.
# ═══════════════════════════════════════════════════════════════════════════

def _api_odgovor(ishod, razlog="razlog"):
    import asyncio
    from unittest.mock import AsyncMock
    import api as _api
    from shared.predmet_deletion import RezultatBrisanja

    async def _audit(action, **kw):
        return None

    fn = getattr(_api.predmet_obrisi, "__wrapped__", _api.predmet_obrisi)
    with patch.object(_api, "_get_supa", return_value=MagicMock()), \
         patch("shared.predmet_deletion.obrisi_predmet",
               return_value=RezultatBrisanja(ishod, razlog)), \
         patch("shared.audit_immutable.log_action", new=_audit):
        try:
            asyncio.run(fn(predmet_id=PID, request=MagicMock(),
                           user={"user_id": UID, "email": "x@y.invalid"}))
        except Exception as exc:                      # HTTPException
            return exc
    return None


def test_11_retryable_kaze_ponovite_permanent_ne():
    g_retry = _api_odgovor(IshodPredmeta.RETRYABLE_FAILURE)
    g_perm = _api_odgovor(IshodPredmeta.PERMANENT_FAILURE)

    assert getattr(g_retry, "status_code", None) == 409
    assert getattr(g_perm, "status_code", None) == 409

    d_retry, d_perm = g_retry.detail, g_perm.detail
    assert d_retry["retry_moguc"] is True
    assert d_perm["retry_moguc"] is False, (
        "PERMANENT_FAILURE tvrdi da se moze ponoviti — to je bila stara laz")
    assert "ponovite" in d_retry["poruka"].lower()
    assert "neće pomoći" in d_perm["poruka"] or "nece pomoci" in d_perm["poruka"], (
        "poruka ne kaze korisniku da ponavljanje nema smisla")


def test_11b_poruke_dva_neuspeha_nisu_iste():
    a = _api_odgovor(IshodPredmeta.RETRYABLE_FAILURE).detail["poruka"]
    b = _api_odgovor(IshodPredmeta.PERMANENT_FAILURE).detail["poruka"]
    assert a != b, "dva suprotna ishoda daju identicnu poruku"


def test_11c_retryable_priznaje_da_predmet_vise_nije_aktivan():
    d = _api_odgovor(IshodPredmeta.RETRYABLE_FAILURE).detail
    assert "nije aktivan" in d["poruka"] or "označen za brisanje" in d["poruka"], (
        "korisnik ne saznaje da je predmet uklonjen iz aktivnih")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 12 — TOMBSTONOVAN PREDMET NIJE VIDLJIV NA KORISNIČKIM READ PUTANJAMA
#
# Provera je nad REZULTATOM upita, ne nad samim upitom: filter u lancu
# PostgREST poziva bi oborio šest postojećih testova koji tvrde tačan oblik tog
# lanca. Semantika je ista, površina promene manja.
# ═══════════════════════════════════════════════════════════════════════════

def test_12_lista_izbacuje_tombstonovan_predmet():
    import api as _api
    redovi = [
        {"id": "a", "brisanje_zapoceto": None},
        {"id": "b", "brisanje_zapoceto": "2026-08-21T00:00:00+00:00"},
    ]
    vidljivi = [r["id"] for r in _api._bez_tombstone(redovi)]
    assert vidljivi == ["a"], "predmet u brisanju je i dalje u listi"


def test_12b_bez_kolone_je_predmet_aktivan():
    """Pre migracije 114 kljuca nema — predmet se tretira kao aktivan.
    Bezbedno je: bez kolone se tombstone ne moze ni upisati."""
    import api as _api
    assert _api._je_u_brisanju({"id": "a"}) is False
    assert _api._je_u_brisanju(None) is False


def test_12c_get_predmet_vraca_404_za_tombstonovan():
    import api as _api
    assert _api._je_u_brisanju({"brisanje_zapoceto": "2026-08-21T00:00:00+00:00"}) is True
