# -*- coding: utf-8 -*-
"""
NIGHT STABILIZATION 001 / FAZA 2 — BR-004: BRISANJE DOKUMENTA.

ZATEČENO STANJE

Nije postojala nijedna delete ruta za `predmet_dokumenti`, nijedna kontrola u
`static/vindex.js`, a kanonski `shared/vector_deletion.py::obrisi_vektore_dokumenta`
— napisan tačno za ovo — pozivan je isključivo iz `scripts/ingest_case_law.py`.
Dokument otpremljen greškom ostajao je zauvek: u bazi, u storage-u, u Pinecone-u
i u svakom AI odgovoru.

KVAR NAĐEN TEK STVARNIM BRISANJEM

Prvi pun E2E prolaz je pao: ruta je vratila 409 „vektori nisu uklonjeni", a
vektor je STVARNO bio obrisan. Uzrok: `list()` u Pinecone-u je eventualno
konzistentan, pa je verifikacija odmah posle `delete()` još uvek videla stari
vektor. Sa tim ponašanjem brisanje ne bi uspelo NIJEDNOM — a poruka korisniku
(„ništa nije promenjeno") bila bi netačna, jer su vektori već nestali.

ŠTA OVI TESTOVI DRŽE

Ne „da ruta postoji". Drže REDOSLED i FAIL-CLOSED: vektori pre baze, i nijedan
sloj se ne dira ako uklanjanje vektora nije potvrđeno. Obrnut redosled je najgori
mogući ishod — dokument nestane iz liste, a i dalje ulazi u AI odgovore.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from shared import vector_deletion as VD  # noqa: E402
from shared.vector_identity import prefiks_dokumenta, verzija_dokumenta  # noqa: E402

UID = "11111111-1111-1111-1111-111111111111"
PREDMET = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
DOK = "dddddddd-dddd-dddd-dddd-dddddddddddd"
SHA = verzija_dokumenta("kontrolni sadrzaj dokumenta")
NS = f"user_{UID}"
PREFIKS = prefiks_dokumenta(PREDMET, SHA)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — VERIFIKACIJA MORA DA SAČEKA EVENTUALNU KONZISTENTNOST (uzrok kvara)
# ═══════════════════════════════════════════════════════════════════════════

class _IndexKasni:
    """`list()` još `kasni` puta vraća obrisani vektor, pa tek onda prazno."""

    def __init__(self, kasni):
        self.kasni, self.pozivi = kasni, 0

    def list(self, prefix, namespace):
        self.pozivi += 1
        if self.pozivi <= self.kasni:
            yield [prefix + "0"]
        else:
            yield []


def test_1_verifikacija_saceka_da_indeks_stigne_sebe():
    """Bez ovoga brisanje ne uspeva NIKAD — mereno stvarnim brisanjem."""
    idx = _IndexKasni(kasni=3)
    pauze = []
    out = VD._cekaj_da_nestanu(idx, NS, PREFIKS, _spavaj=pauze.append)
    assert out == [], out
    assert idx.pozivi == 4, idx.pozivi
    assert len(pauze) == 3


def test_1b_prozor_je_ogranicen_i_neuspeh_ostaje_neuspeh():
    """„Sačekaj još malo" bez granice je isto što i „proglasi uspeh"."""
    idx = _IndexKasni(kasni=10_000)
    out = VD._cekaj_da_nestanu(idx, NS, PREFIKS, pokusaja=4, _spavaj=lambda s: None)
    assert out == [PREFIKS + "0"], out
    assert idx.pozivi == 4


def test_1c_neproverljivo_se_NE_ponavlja_i_ne_postaje_prazno():
    """`None` znači „ne znam". Čekanje to ne popravlja, i ne sme da se degradira
    u „prazno je" — to bi bio tihi lažni uspeh brisanja."""
    class _Puca:
        pozivi = 0

        def list(self, prefix, namespace):
            _Puca.pozivi += 1
            raise RuntimeError("indeks nedostupan")

    out = VD._cekaj_da_nestanu(_Puca(), NS, PREFIKS, _spavaj=lambda s: None)
    assert out is None
    assert _Puca.pozivi == 1, "ponavljano je ono što se ponavljanjem ne rešava"


def test_1d_kanonsko_brisanje_STVARNO_koristi_cekanje():
    """MUTACIJA KOJA JE PREŽIVELA PRVI KRUG.

    Testovi 1–1c mere `_cekaj_da_nestanu` izolovano — pa je vraćanje
    `obrisi_vektore_dokumenta` na jedno čitanje (tačno originalni kvar) prošlo
    nekažnjeno. Ovde se vozi CELA kanonska funkcija sa indeksom koji kasni:
    bez čekanja vraća `PARTIAL_FAILURE`, sa čekanjem `DELETED`.
    """
    class _Baza:
        def table(self, ime):
            q = MagicMock()
            if ime == "predmeti":
                q.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": PREDMET}])
            else:
                q.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": DOK, "predmet_id": PREDMET, "user_id": UID,
                           "content_sha256": SHA, "pinecone_namespace": NS}])
            return q

    class _Index:
        def __init__(self):
            self.pozivi, self.obrisano = 0, []

        def list(self, prefix, namespace):
            self.pozivi += 1
            # 1. poziv: skup ID-eva pre brisanja. 2–3: indeks jos kasni. 4: prazno.
            if self.pozivi <= 3:
                yield [PREFIKS + "0"]
            else:
                yield []

        def delete(self, ids, namespace):
            self.obrisano.extend(ids)

    idx = _Index()
    with patch.object(VD, "VERIFIKACIJA_PAUZA_S", 0):
        rez = VD.obrisi_vektore_dokumenta(_Baza(), idx, user_id=UID,
                                          predmet_id=PREDMET, document_id=DOK)
    assert idx.obrisano == [PREFIKS + "0"], idx.obrisano
    assert rez.ishod == VD.Ishod.DELETED, f"{rez} — verifikacija ne čeka indeks"
    assert rez.uspeh


# ═══════════════════════════════════════════════════════════════════════════
# LAŽNA BAZA / INDEKS ZA RUTU
# ═══════════════════════════════════════════════════════════════════════════

RED = {
    "id": DOK, "naziv_fajla": "dokaz.docx", "status": "indeksirano",
    "storage_path": "intake-dokumenti/a/b.docx",
    "pinecone_namespace": NS, "content_sha256": SHA,
    "predmet_id": PREDMET, "user_id": UID,
}


class _Q:
    def __init__(self, t, b):
        self.t, self.b, self.f, self.op = t, b, {}, "select"

    def select(self, *a, **k): self.op = "select"; return self
    def delete(self, *a, **k): self.op = "delete"; return self
    def eq(self, k, v): self.f[k] = v; return self
    def limit(self, *a, **k): return self
    def maybe_single(self): return self

    def execute(self):
        self.b.dnevnik.append((self.t, self.op))
        if self.t != "predmet_dokumenti":
            return MagicMock(data=[])
        if self.op == "delete":
            if self.b.db_puca:
                raise RuntimeError("baza nedostupna")
            self.b.red_postoji = False
            return MagicMock(data=[])
        if not self.b.red_postoji:
            return MagicMock(data=None if "maybe" not in self.op else None)
        if self.f.get("user_id") not in (None, UID):
            return MagicMock(data=None)
        if self.f.get("id") != DOK:
            return MagicMock(data=None)
        return MagicMock(data=dict(self.b.red))


class _Storage:
    def __init__(self, b): self.b = b
    def from_(self, *a, **k): return self
    def remove(self, putanje):
        if self.b.storage_puca:
            raise RuntimeError("storage nedostupan")
        self.b.obrisani_originali.extend(putanje)
        return None


class _Baza:
    def __init__(self, red=None, db_puca=False, storage_puca=False):
        self.red = dict(red or RED)
        self.red_postoji = True
        self.db_puca, self.storage_puca = db_puca, storage_puca
        self.obrisani_originali, self.dnevnik = [], []
        self.storage = _Storage(self)

    def table(self, ime):
        return _Q(ime, self)


def _vozi_delete(baza, rezultat_vektora, uid=UID):
    import api

    pozivi = {"vektori": 0, "redosled": []}

    def _obrisi(*a, **k):
        pozivi["vektori"] += 1
        pozivi["redosled"].append("vektori")
        return rezultat_vektora

    _orig_exec = _Q.execute

    def _exec(self):
        if self.t == "predmet_dokumenti" and self.op == "delete":
            pozivi["redosled"].append("db")
        return _orig_exec(self)

    async def _nista(*a, **k):
        return None

    f = api.predmet_dokument_obrisi
    while hasattr(f, "__wrapped__"):
        f = f.__wrapped__

    zahtev = MagicMock()
    zahtev.client = MagicMock(host="127.0.0.1")

    with patch.object(api, "_get_supa", lambda: baza), \
         patch.object(_Q, "execute", _exec), \
         patch("shared.vector_deletion.obrisi_vektore_dokumenta", _obrisi), \
         patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()), \
         patch("shared.audit_immutable.log_action", _nista):
        try:
            out = asyncio.run(f(PREDMET, DOK, zahtev, user={"user_id": uid, "email": "a@b.c"}))
            return out, None, pozivi
        except HTTPException as e:
            return None, e, pozivi


# ═══════════════════════════════════════════════════════════════════════════
# 2 — SREĆAN PUT: VEKTORI PRE BAZE
# ═══════════════════════════════════════════════════════════════════════════

def test_2_brisanje_uklanja_sva_tri_sloja():
    baza = _Baza()
    out, greska, p = _vozi_delete(baza, VD.Rezultat(VD.Ishod.DELETED, obrisano=3, ocekivano=3))
    assert greska is None, greska.detail if greska else ""
    assert out["success"] is True
    assert out["vektori"]["ishod"] == "DELETED"
    assert out["storage"] == "OBRISAN"
    assert baza.obrisani_originali == ["intake-dokumenti/a/b.docx"]
    assert baza.red_postoji is False


def test_2b_vektori_se_brisu_PRE_reda_u_bazi():
    """Obrnut redosled je najgori mogući ishod: dokument nestane iz liste, a
    i dalje ulazi u AI odgovore."""
    baza = _Baza()
    _out, _g, p = _vozi_delete(baza, VD.Rezultat(VD.Ishod.DELETED, obrisano=1, ocekivano=1))
    assert p["redosled"].index("vektori") < p["redosled"].index("db"), p["redosled"]


def test_2c_already_absent_je_uspeh():
    """Dokument bez vektora u indeksu je već u traženom stanju."""
    baza = _Baza()
    out, greska, _ = _vozi_delete(baza, VD.Rezultat(VD.Ishod.ALREADY_ABSENT))
    assert greska is None
    assert out["success"] is True
    assert baza.red_postoji is False


# ═══════════════════════════════════════════════════════════════════════════
# 3 — FAIL-CLOSED: BEZ POTVRĐENIH VEKTORA NEMA BRISANJA NIGDE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ishod", [
    VD.Ishod.REFUSED, VD.Ishod.PARTIAL_FAILURE, VD.Ishod.VERIFICATION_FAILED,
])
def test_3_neuspeh_vektora_ne_dira_ni_bazu_ni_storage(ishod):
    baza = _Baza()
    out, greska, _ = _vozi_delete(baza, VD.Rezultat(ishod, "razlog"))
    assert out is None
    assert greska.status_code == 409
    assert baza.red_postoji is True, "red obrisan iako vektori nisu potvrđeni"
    assert baza.obrisani_originali == [], "original obrisan iako vektori nisu potvrđeni"


def test_3b_poruka_razlikuje_nedirano_od_zapocetog():
    """`REFUSED` = nije se ni stiglo do indeksa. `PARTIAL_FAILURE` = `delete()`
    je pozvan. Tvrditi „ništa nije promenjeno" u drugom slučaju je netačno, a
    lažna umirujuća poruka je gora od nikakve."""
    _o1, g1, _ = _vozi_delete(_Baza(), VD.Rezultat(VD.Ishod.REFUSED, "nema prava"))
    _o2, g2, _ = _vozi_delete(_Baza(), VD.Rezultat(VD.Ishod.PARTIAL_FAILURE, "ostalo 2"))
    assert "Ništa nije promenjeno" in g1.detail
    assert "Ništa nije promenjeno" not in g2.detail
    assert "možda već uklonjen" in g2.detail


def test_3c_izuzetak_indeksa_ne_brise_nista():
    """Pinecone nedostupan → 503, i nijedan sloj se ne dira."""
    import api

    baza = _Baza()

    def _puca(*a, **k):
        raise RuntimeError("pinecone nedostupan")

    async def _nista(*a, **k):
        return None

    f = api.predmet_dokument_obrisi
    while hasattr(f, "__wrapped__"):
        f = f.__wrapped__
    zahtev = MagicMock(); zahtev.client = MagicMock(host="127.0.0.1")

    with patch.object(api, "_get_supa", lambda: baza), \
         patch("shared.vector_deletion.obrisi_vektore_dokumenta", _puca), \
         patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()), \
         patch("shared.audit_immutable.log_action", _nista):
        with pytest.raises(HTTPException) as e:
            asyncio.run(f(PREDMET, DOK, zahtev, user={"user_id": UID, "email": "a@b.c"}))
    assert e.value.status_code == 503
    assert baza.red_postoji is True
    assert baza.obrisani_originali == []


# ═══════════════════════════════════════════════════════════════════════════
# 4 — VLASNIŠTVO
# ═══════════════════════════════════════════════════════════════════════════

def test_4_tudji_dokument_se_ne_brise_i_kanonsko_brisanje_se_ne_zove():
    baza = _Baza()
    out, greska, p = _vozi_delete(baza, VD.Rezultat(VD.Ishod.DELETED),
                                  uid="99999999-9999-9999-9999-999999999999")
    assert out is None
    assert greska.status_code == 404
    assert p["vektori"] == 0, "kanonsko brisanje pozvano za tuđi dokument"
    assert baza.red_postoji is True


# ═══════════════════════════════════════════════════════════════════════════
# 5 — DOKUMENT KOJI NIKAD NIJE INDEKSIRAN
# ═══════════════════════════════════════════════════════════════════════════

def test_5_neindeksiran_dokument_preskace_vektore_ali_se_brise():
    """Bez identiteta i bez `indeksirano` u Pinecone-u nema šta da se briše.
    Taj slučaj se IMENUJE u odgovoru, ne ćuti se."""
    red = {**RED, "status": "sacuvano", "content_sha256": None,
           "storage_path": "session/abc"}
    baza = _Baza(red=red)
    out, greska, p = _vozi_delete(baza, VD.Rezultat(VD.Ishod.DELETED))
    assert greska is None
    assert p["vektori"] == 0
    assert out["vektori"]["ishod"] == "PRESKOCENO_NIJE_INDEKSIRAN"
    assert out["storage"] == "PRESKOCENO_NEMA_ORIGINALA"
    assert baza.red_postoji is False


def test_5b_sacuvan_dokument_SA_identitetom_ipak_ide_kroz_vektore():
    """`status='sacuvano'` ne dokazuje da vektora nema — parcijalan ingest je
    postojeće stanje. Ako identitet postoji, provera se NE preskače."""
    baza = _Baza(red={**RED, "status": "sacuvano"})
    _out, _g, p = _vozi_delete(baza, VD.Rezultat(VD.Ishod.DELETED))
    assert p["vektori"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 6 — UPIS U BAZU SE PROVERAVA, HTTP 200 NIJE DOKAZ
# ═══════════════════════════════════════════════════════════════════════════

def test_6_pad_brisanja_reda_ne_sme_da_vrati_uspeh():
    baza = _Baza(db_puca=True)
    out, greska, _ = _vozi_delete(baza, VD.Rezultat(VD.Ishod.DELETED))
    assert out is None
    assert greska.status_code == 500


def test_6b_ruta_postoji_kao_DELETE_na_kanonskoj_putanji():
    """Brava nad ugovorom koji UI zove."""
    import api
    putanje = {(r.path, tuple(sorted(r.methods))) for r in api.app.routes
               if hasattr(r, "methods")}
    assert ("/api/predmeti/{predmet_id}/dokumenti/{dok_id}", ("DELETE",)) in putanje


def test_6c_UI_ima_kontrolu_za_brisanje():
    """BR-004 nije zatvoren rutom koju niko ne zove — do ovog sprinta nije
    postojala nijedna kontrola u `vindex.js`."""
    import io
    js = io.open(os.path.join(_KOREN, "static", "vindex.js"), encoding="utf-8").read()
    assert "function dok_obrisi(" in js
    assert "dok_obrisi(" in js.split("function dok_obrisi(")[0], \
        "funkcija postoji ali je niko ne poziva"
    assert "method: 'DELETE'" in js.split("function dok_obrisi(")[1][:1500]
