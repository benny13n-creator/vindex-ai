# -*- coding: utf-8 -*-
"""
P1-5 — brisanje predmeta mora biti fail-closed.

SPECIFIKACIJA: `docs/beta_gate/P15_LIFECYCLE_SPECIFICATION.md`

Mereno u T1: podaci predmeta zive u 61 tabeli; 21 ima FK (16 CASCADE, 4 SET
NULL, 1 RESTRICT), a 36 nema nijedan — oslanjanje na kaskadu ostavilo bi orphan
redove, a vektori dokumenata ne bi bili dodirnuti uopste.

CENTRALNA INVARIJANTA
  `200 / ok:True` sme se vratiti ISKLJUCIVO ako je svaki entitet koji politika
  nalaze da se ukloni dokazano uklonjen. Delimicno brisanje je `PARTIAL_FAILURE`
  i `predmeti` red se NE brise — stanje ostaje rekoncilijabilno.
"""
import io

import pytest
from unittest.mock import MagicMock, patch

from shared.predmet_deletion import (
    TABELE_BEZ_FK,
    IshodPredmeta,
    obrisi_predmet,
)

UID = "00000000-0000-0000-0000-000000000001"
TUDJ_UID = "00000000-0000-0000-0000-000000000002"
PID = "p-1"

KVAROVI = {
    "42501_rls": Exception("row-level security policy violated (42501)"),
    "timeout": TimeoutError("connection timeout expired"),
    "neocekivani": ValueError("neocekivano stanje drajvera"),
}


class _Upit:
    def __init__(self, dvojnik, tabela, akcija):
        self.d = dvojnik
        self.t = tabela
        self.a = akcija
        self.filteri = {}

    def eq(self, k, v):
        self.filteri[k] = v
        return self

    def in_(self, k, v):
        # BETA-DEL-001: deca koja vise o `events(id)` brisu se po `event_id`.
        self.filteri["__in__" + k] = list(v)
        return self

    def is_(self, k, v):
        self.filteri["__is__" + k] = v
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
        for k, v in self.filteri.items():
            redovi = [r for r in redovi if r.get(k) == v]
        m = MagicMock()
        m.data = redovi
        return m


class _Tabela:
    def __init__(self, dvojnik, ime):
        self.d = dvojnik
        self.ime = ime

    def select(self, *a, **k):
        return _Upit(self.d, self.ime, "select")

    def delete(self, *a, **k):
        return _Upit(self.d, self.ime, "delete")

    def update(self, *a, **k):
        # Tombstone (BETA-DEL-001). Belezi se odvojeno od brisanja.
        return _Upit(self.d, self.ime, "update")


class _Supa:
    """Dvojnik koji BELEZI sta je stvarno obrisano."""

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


def _index():
    return MagicMock()


_BEZ = object()


def _obrisi(supa, index=_BEZ, uid=UID, sme=True, vektori_uspeh=True):
    v = MagicMock()
    v.uspeh = vektori_uspeh
    v.ishod = "DELETED" if vektori_uspeh else "PARTIAL_FAILURE"  # ishod VEKTORA, drugi enum
    with patch("shared.vector_deletion._sme_predmet", return_value=sme), \
         patch("shared.vector_deletion.obrisi_vektore_dokumenta", return_value=v):
        idx = _index() if index is _BEZ else index
        return obrisi_predmet(supa, idx, user_id=uid, predmet_id=PID)


# ── 1-2. happy path i legitimno prazan predmet ──────────────────────────────

def test_01_happy_delete_bez_dokumenata():
    s = _Supa()
    r = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED and r.uspeh is True
    assert r.vektori == "NEMA_DOKUMENATA"
    assert "predmeti" in s.brisanja, "sam predmet nije obrisan"
    assert len(r.obrisane_tabele) == len(TABELE_BEZ_FK), \
        "nisu ociscene sve tabele bez FK"


def test_02_happy_delete_sa_dokumentima_brise_vektore():
    s = _Supa()
    s.redovi["predmet_dokumenti"] = [{"id": "d1", "predmet_id": PID, "user_id": UID}]
    r = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED
    assert r.vektori == "OBRISANI"


# ── 3-4. vec obrisano / ponovljeni DELETE ───────────────────────────────────

def test_03_already_absent_nije_uspeh_brisanja():
    s = _Supa(redovi={"predmeti": [], "billing_entries": [], "predmet_dokumenti": []})
    r = _obrisi(s)
    assert r.ishod == IshodPredmeta.ALREADY_ABSENT
    assert s.brisanja == [], "nista se ne sme brisati za nepostojeci predmet"


def test_04_duplo_brisanje_ne_brise_dvaput():
    s = _Supa()
    assert _obrisi(s).ishod == IshodPredmeta.DELETED
    s.redovi["predmeti"] = []
    assert _obrisi(s).ishod == IshodPredmeta.ALREADY_ABSENT


# ── 5. FK RESTRICT ──────────────────────────────────────────────────────────

def test_05_billing_entries_blokira_i_nista_ne_dira():
    s = _Supa()
    s.redovi["billing_entries"] = [{"id": "b1", "predmet_id": PID}]
    r = _obrisi(s)
    assert r.ishod == IshodPredmeta.BLOCKED
    assert "naplate" in r.razlog
    assert s.brisanja == [], "BLOCKED je moralo ostaviti sve netaknuto"


# ── 6. neovlascen pristup / pogresan tenant ────────────────────────────────

def test_06_bez_prava_pristupa_nista_ne_dira():
    s = _Supa()
    r = _obrisi(s, sme=False)
    assert r.ishod == IshodPredmeta.REFUSED
    assert s.brisanja == []


def test_07_tudji_predmet_je_ALREADY_ABSENT_ne_obrisan():
    """Tenant izolacija: `predmeti` filtrira i po `user_id`."""
    s = _Supa()
    r = _obrisi(s, uid=TUDJ_UID)
    assert r.ishod == IshodPredmeta.ALREADY_ABSENT
    assert s.brisanja == []


# ── 8-10. vektori ───────────────────────────────────────────────────────────
#
# OLD: ova tri testa su tvrdila `s.brisanja == []` — „kad vektori padnu,
#      nijedan red nije obrisan". To je bio invariant STAROG redosleda, u kome
#      su vektori bili PRVI destruktivni korak.
#
# NEW: BETA-DEL-001 je pomerio vektore IZA brisanja redova, pa su pri padu
#      vektora redovi ocekivano vec obrisani. Zamena invarianta:
#      predmet je TOMBSTONOVAN i njegov red POSTOJI, dakle nista nije orphan.
#
# WHY: stari redosled je mereno uzivo 3/3 proizvodio ZIV predmet sa nepovratno
#      obrisanim vektorima. Novi redosled to cini nemogucim: u trenutku kad
#      vektori nestanu, predmet je vec nevidljiv korisniku i RAG-u.
#
# INVARIANT KOJI OVI TESTOVI SADA CUVAJU:
#      pad vektora => RETRYABLE_FAILURE + tombstone upisan + `predmeti` red ostaje

def test_08_pad_vektora_ostavlja_TOMBSTONOVAN_predmet():
    s = _Supa()
    s.redovi["predmet_dokumenti"] = [{"id": "d1", "predmet_id": PID, "user_id": UID}]
    r = _obrisi(s, vektori_uspeh=False)
    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert r.vektori == "NEUSPEH"
    assert r.tombstone == "UPISAN", "predmet nije oznacen za brisanje pre destrukcije"
    assert "predmeti" in s.azuriranja, "tombstone nije upisan u bazu"
    assert "predmeti" not in s.brisanja, "predmet je obrisan iako vektori nisu"


def test_09_indeks_nedostupan_uz_dokumente_je_neuspeh():
    s = _Supa()
    s.redovi["predmet_dokumenti"] = [{"id": "d1", "predmet_id": PID, "user_id": UID}]
    r = _obrisi(s, index=None)
    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert r.tombstone == "UPISAN"
    assert "predmeti" not in s.brisanja


def test_10_izuzetak_u_brisanju_vektora_je_neuspeh():
    s = _Supa()
    s.redovi["predmet_dokumenti"] = [{"id": "d1", "predmet_id": PID, "user_id": UID}]
    with patch("shared.vector_deletion._sme_predmet", return_value=True), \
         patch("shared.vector_deletion.obrisi_vektore_dokumenta",
               side_effect=RuntimeError("pinecone pao")):
        r = obrisi_predmet(s, _index(), user_id=UID, predmet_id=PID)
    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert r.tombstone == "UPISAN"
    assert "predmeti" not in s.brisanja


# ── 11-13. parcijalni pad redova ────────────────────────────────────────────

@pytest.mark.parametrize("kvar", sorted(KVAROVI))
def test_11_pad_jedne_tabele_je_PARTIAL_i_predmet_ostaje(kvar):
    s = _Supa(puca={"zadaci": KVAROVI[kvar]})
    r = _obrisi(s)
    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE, kvar
    assert r.uspeh is False
    assert "zadaci" in r.neuspele_tabele
    assert "predmeti" not in s.brisanja, "predmet je obrisan uprkos neociscenoj tabeli"


def test_12_nepostojeca_tabela_nije_neuspeh():
    """PGRST205 znaci „nema sta da se brise", ne „brisanje nije uspelo"."""
    s = _Supa(puca={"style_analize": Exception("Could not find the table (PGRST205)")})
    r = _obrisi(s)
    assert r.ishod == IshodPredmeta.DELETED
    assert "style_analize" in r.preskocene_tabele
    assert r.neuspele_tabele == []


def test_13_pad_samog_predmeta_je_PARTIAL():
    s = _Supa(puca={"predmeti": None})
    # prvo dozvoli citanje, pa obori brisanje
    orig = s.table

    def _t(ime):
        t = orig(ime)
        if ime == "predmeti":
            realno_delete = t.delete

            def _d(*a, **k):
                u = realno_delete(*a, **k)
                u.execute = lambda: (_ for _ in ()).throw(Exception("42501 RLS"))
                return u
            t.delete = _d
        return t
    s.table = _t
    r = _obrisi(s)
    assert r.ishod == IshodPredmeta.RETRYABLE_FAILURE
    assert "predmeti" in r.neuspele_tabele


# ── 14-15. provera ugovora ──────────────────────────────────────────────────

def test_14_uspeh_je_iskljucivo_DELETED_ili_ALREADY_ABSENT():
    from shared.predmet_deletion import RezultatBrisanja
    for ishod in (IshodPredmeta.BLOCKED, IshodPredmeta.REFUSED,
                  IshodPredmeta.RETRYABLE_FAILURE):
        assert RezultatBrisanja(ishod).uspeh is False, ishod
    for ishod in (IshodPredmeta.DELETED, IshodPredmeta.ALREADY_ABSENT):
        assert RezultatBrisanja(ishod).uspeh is True, ishod


def test_15_lista_tabela_ne_sme_sadrzati_audit_ni_novac():
    """RETAIN entiteti se ne smeju naci u eksplicitnom brisanju."""
    zabranjeno = {"audit_immutable", "audit_log", "saradnja_audit", "klijenti_audit",
                  "billing_entries", "fakture", "timer_sessions", "usage_events",
                  "recurring_templates", "klijent_dokumenti", "predmeti"}
    presek = zabranjeno & set(TABELE_BEZ_FK)
    assert not presek, "RETAIN/SET NULL entiteti u listi za brisanje: %s" % presek


def test_16_ruta_vraca_200_samo_za_DELETED():
    """Staticka brana nad `api.py`: nijedan drugi ishod ne sme dati `ok: True`."""
    import ast
    src = io.open("api.py", encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "predmet_obrisi")
    blok = ast.get_source_segment(src, fn)
    assert 'if rez.ishod == IshodPredmeta.DELETED:' in blok
    assert blok.index('{"ok": True') > blok.index("IshodPredmeta.DELETED"), \
        "`ok: True` je dostizno pre provere ishoda"
    for ishod in ("ALREADY_ABSENT", "REFUSED", "BLOCKED"):
        assert ishod in blok, "ishod %s nema svoju granu u ruti" % ishod
    assert blok.count("HTTPException") >= 4
