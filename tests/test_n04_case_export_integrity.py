# -*- coding: utf-8 -*-
"""
N04 — izvoz podataka i integritet (GET /api/export/complete, GET
/api/predmeti/{id}/pdf-export).

Ugovor koji se meri (routers/data_export.py README + static/security.html §14.2):
  * ZIP sadrzi JSON fajlove za tacno 8 navedenih tabela + README.txt;
  * originalni fajlovi dokumenata (PDF/DOCX) NISU ukljuceni i README to kaze;
  * delimican pad citanja nikad ne izlazi kao uspeh (S4-4: 503, ZIP odbacen);
  * „Svaki kompletan izvoz upisuje se u nepromenjivi audit log" — dakle
    neuspeo izvoz NE sme da ostavi `data_export` zapis.

Sve sinteticko: lazni Supabase u memoriji, bez mreze, bez Storage-a.
"""
import asyncio
import io
import json
import os
import sys
import zipfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A = "user-a-0000"
B = "user-b-0000"
PA = "predmet-a-1"
PA_EMPTY = "predmet-a-prazan"
PB = "predmet-b-1"

TABELE_IZVOZA = {
    "predmeti": "predmeti.json",
    "klijenti": "klijenti.json",
    "billing_entries": "billing.json",
    "predmet_dokumenti": "dokumenti.json",
    "predmet_beleske": "beleske.json",
    "rocista": "rocista.json",
    "predmet_hronologija": "hronologija.json",
    "predmet_komentari": "komentari.json",
}


def _seed():
    return {
        "predmeti": [
            {"id": PA, "user_id": A, "naziv": "A protiv C", "created_at": "2026-01-01"},
            {"id": PA_EMPTY, "user_id": A, "naziv": "Prazan predmet", "created_at": "2026-01-02"},
            {"id": PB, "user_id": B, "naziv": "TAJNA-B predmet", "created_at": "2026-01-01"},
        ],
        "klijenti": [
            {"id": "k1", "user_id": A, "ime": "Klijent A", "kreirano": "2026-01-01"},
            {"id": "k2", "user_id": B, "ime": "TAJNA-B klijent", "kreirano": "2026-01-01"},
        ],
        "billing_entries": [
            {"id": "b1", "user_id": A, "iznos_rsd": 1000, "created_at": "2026-01-03"},
        ],
        "predmet_dokumenti": [
            # metapodatak postoji, binarni objekat u Storage-u NE postoji
            {"id": "d1", "user_id": A, "predmet_id": PA, "naziv_fajla": "tuzba.pdf",
             "storage_path": "a/predmet-a-1/tuzba.pdf", "status": "obradjen",
             "tekst_sadrzaj": "IZVUCENI TEKST tuzbe", "created_at": "2026-01-04"},
            # dokument bez ikakvog binarnog traga (nikad uploadovan do kraja)
            {"id": "d2", "user_id": A, "predmet_id": PA, "naziv_fajla": "dokaz.docx",
             "storage_path": None, "status": "greska",
             "tekst_sadrzaj": None, "created_at": "2026-01-05"},
            {"id": "d3", "user_id": A, "predmet_id": PA, "naziv_fajla": "punomocje.pdf",
             "storage_path": "a/predmet-a-1/punomocje.pdf", "status": "obradjen",
             "tekst_sadrzaj": "IZVUCENI TEKST punomocja", "created_at": "2026-01-06"},
            # nedostupan dokument: tudji (B)
            {"id": "d9", "user_id": B, "predmet_id": PB, "naziv_fajla": "TAJNA-B.pdf",
             "storage_path": "b/predmet-b-1/TAJNA-B.pdf", "status": "obradjen",
             "tekst_sadrzaj": "TAJNA-B sadrzaj", "created_at": "2026-01-04"},
        ],
        "predmet_beleske": [
            {"id": "n1", "user_id": A, "predmet_id": PA, "sadrzaj": "beleska A", "created_at": "2026-01-07"},
            {"id": "n9", "user_id": B, "predmet_id": PB, "sadrzaj": "TAJNA-B beleska", "created_at": "2026-01-07"},
        ],
        "rocista": [
            {"id": "r1", "user_id": A, "predmet_id": PA, "datum": "2026-02-01"},
        ],
        "predmet_hronologija": [
            {"id": "h1", "user_id": A, "predmet_id": PA, "dogadjaj": "podneta tuzba",
             "datum": "04.01.2026", "datum_iso": "2026-01-04", "akter": "A", "vaznost": "visoka"},
            {"id": "h9", "user_id": B, "predmet_id": PB, "dogadjaj": "TAJNA-B dogadjaj",
             "datum": "04.01.2026", "datum_iso": "2026-01-04", "akter": "B", "vaznost": "visoka"},
        ],
        "predmet_komentari": [],
    }


class _Res:
    def __init__(self, data):
        self.data = data


class _Upit:
    def __init__(self, baza, tabela):
        self.baza, self.tabela = baza, tabela
        self.filteri = []
        self.single = False
        self.redosled = []
        self.granica = None

    def select(self, *_a, **_k):
        return self

    def eq(self, k, v):
        self.filteri.append((k, v))
        return self

    def in_(self, k, vs):
        self.filteri.append((k, ("in", tuple(vs))))
        return self

    def gt(self, k, v):
        self.filteri.append((k, ("gt", v)))
        return self

    def order(self, kolona, *_a, **_k):
        self.redosled.append(kolona)
        return self

    def limit(self, n, *_a, **_k):
        self.granica = n
        return self

    def maybe_single(self):
        self.single = True
        return self

    def _mutacija(self, vrsta):
        self.baza.mutacije.append((vrsta, self.tabela))
        return self

    def insert(self, *_a, **_k):
        return self._mutacija("insert")

    def update(self, *_a, **_k):
        return self._mutacija("update")

    def upsert(self, *_a, **_k):
        return self._mutacija("upsert")

    def delete(self, *_a, **_k):
        return self._mutacija("delete")

    def execute(self):
        self.baza.citanja.append((self.tabela, tuple(self.filteri)))
        # Ograniceno: petlja straničenja koja se ne zaustavlja PADA, ne visi (C1-N1)
        if len(self.baza.citanja) > self.baza.budzet_citanja:
            self.baza.prekoracen = True
            raise RuntimeError("sinteticka baza: previse citanja")
        if self.tabela in self.baza.padovi:
            raise RuntimeError(f"sinteticki pad citanja: {self.tabela}")
        redovi = []
        for r in self.baza.podaci.get(self.tabela, []):
            ok = True
            for k, v in self.filteri:
                if isinstance(v, tuple) and v and v[0] == "in":
                    ok = ok and r.get(k) in v[1]
                elif isinstance(v, tuple) and v and v[0] == "gt":
                    ok = ok and r.get(k) is not None and str(r.get(k)) > str(v[1])
                else:
                    ok = ok and r.get(k) == v
            if ok:
                redovi.append(dict(r))
        if self.single:
            return _Res(redovi[0] if redovi else None)
        for kolona in reversed(self.redosled):
            redovi.sort(key=lambda r, c=kolona: (r.get(c) is None, str(r.get(c))))
        if self.granica is not None:
            redovi = redovi[:self.granica]
        # PostgREST `max-rows`: odgovor se TIHO seče, bez greške (C1-F1)
        if self.baza.max_rows is not None:
            redovi = redovi[:self.baza.max_rows]
        return _Res(redovi)


class FakeSupa:
    def __init__(self, padovi=()):
        self.podaci = _seed()
        self.padovi = set(padovi)
        self.mutacije = []
        self.citanja = []
        self.storage_pozivi = []
        self.max_rows = 1000
        self.budzet_citanja = 500
        self.prekoracen = False

    def table(self, ime):
        return _Upit(self, ime)

    @property
    def storage(self):  # svaki pristup Storage-u se belezi
        self.storage_pozivi.append("storage")
        raise AssertionError("izvoz ne sme da cita Storage (ugovor: bez fajlova)")


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _izvezi(supa, uid=A):
    """Pozove endpoint i vrati (zip_bytes|HTTPException, audit_pozivi)."""
    import routers.data_export as de
    from fastapi import HTTPException

    audit = []

    async def _snimi(action, **kw):
        audit.append((action, kw))
        return "audit-id"

    with patch.object(de, "_get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=_snimi):
        try:
            resp = await de.export_complete(user={"user_id": uid, "email": f"{uid}@x.rs"})
        except HTTPException as exc:
            for _ in range(5):
                await asyncio.sleep(0)
            assert not getattr(supa, "prekoracen", False), "petlja straničenja se ne zaustavlja"
            return exc, audit
        assert not getattr(supa, "prekoracen", False), "petlja straničenja se ne zaustavlja"
        telo = b""
        async for deo in resp.body_iterator:
            telo += deo if isinstance(deo, bytes) else deo.encode()
        for _ in range(5):
            await asyncio.sleep(0)
        return (resp, telo), audit


def _sadrzaj(telo):
    zf = zipfile.ZipFile(io.BytesIO(telo))
    return {n: zf.read(n) for n in zf.namelist()}


# ── 1. vlastiti zapisi, vise dokumenata ────────────────────────────────────

@pytest.mark.anyio
async def test_izvoz_sadrzi_tacno_ugovorene_fajlove_i_vlastite_zapise():
    supa = FakeSupa()
    (resp, telo), audit = await _izvezi(supa)
    assert resp.media_type == "application/zip"
    assert 'attachment; filename="vindex-export-' in resp.headers["content-disposition"]
    f = _sadrzaj(telo)
    assert set(f) == {"README.txt", *TABELE_IZVOZA.values()}
    dok = json.loads(f["dokumenti.json"])
    assert [d["id"] for d in dok] == ["d1", "d2", "d3"]
    pred = json.loads(f["predmeti.json"])
    assert {p["id"] for p in pred} == {PA, PA_EMPTY}
    # svako citanje je ograniceno na vlasnika
    for tabela, filteri in supa.citanja:
        assert ("user_id", A) in filteri, (tabela, filteri)


# ── 2. tudji podaci (B) se nikad ne pojavljuju ─────────────────────────────

@pytest.mark.anyio
async def test_izvoz_ne_sadrzi_nijedan_bajt_tudjih_podataka():
    (resp, telo), _ = await _izvezi(FakeSupa())
    for ime, bajtovi in _sadrzaj(telo).items():
        assert b"TAJNA-B" not in bajtovi, ime
        assert B.encode() not in bajtovi, ime


@pytest.mark.anyio
async def test_pdf_izvoz_tudjeg_predmeta_pada_zatvoreno_bez_b_podataka():
    import routers.export as ex
    from fastapi import HTTPException

    supa = FakeSupa()
    pozvan = []
    with patch.object(ex, "_get_supa", return_value=supa), \
         patch.object(ex, "_generiši_pdf", side_effect=lambda *a: pozvan.append(a) or b"%PDF"), \
         patch.object(ex, "_odluke", return_value={}):
        with pytest.raises(HTTPException) as exc:
            await ex.get_predmet_pdf_export(PB, user={"user_id": A})
    assert exc.value.status_code == 404
    assert "TAJNA-B" not in str(exc.value.detail)
    assert pozvan == []
    # posle odbijanja predmeta nijedna povezana tabela nije ni procitana
    assert [t for t, _ in supa.citanja] == ["predmeti"]


@pytest.mark.anyio
async def test_pdf_izvoz_vlastitog_predmeta_ograniceno_na_vlasnika():
    import routers.export as ex

    supa = FakeSupa()
    pozvan = []
    with patch.object(ex, "_get_supa", return_value=supa), \
         patch.object(ex, "_generiši_pdf", side_effect=lambda *a: pozvan.append(a) or b"%PDF"), \
         patch.object(ex, "_odluke", return_value={}):
        resp = await ex.get_predmet_pdf_export(PA, user={"user_id": A})
    assert resp.media_type == "application/pdf"
    predmet, dokumenti, beleske, hron = pozvan[0]
    assert predmet["id"] == PA
    assert "TAJNA-B" not in json.dumps([dokumenti, beleske, hron])
    assert [h["id"] for h in hron] == ["h1"]
    assert all(h["stanje_odluke"] != "CONFIRMED" for h in hron)


@pytest.mark.anyio
async def test_pdf_izvoz_pad_povezane_tabele_nije_uspeh():
    import routers.export as ex

    supa = FakeSupa(padovi={"predmet_beleske"})
    with patch.object(ex, "_get_supa", return_value=supa), \
         patch.object(ex, "_generiši_pdf", return_value=b"%PDF"), \
         patch.object(ex, "_odluke", return_value={}):
        with pytest.raises(Exception):
            await ex.get_predmet_pdf_export(PA, user={"user_id": A})


# ── 3. originali: metapodatak bez binarnog objekta ─────────────────────────

@pytest.mark.anyio
async def test_nedostajuci_originali_nisu_zamenjeni_izvucenim_tekstom():
    supa = FakeSupa()
    (resp, telo), _ = await _izvezi(supa)
    f = _sadrzaj(telo)
    # nijedan unos u arhivi ne izgleda kao original
    for ime in f:
        assert not ime.lower().endswith((".pdf", ".docx", ".doc")), ime
        assert ime not in {"tuzba.pdf", "dokaz.docx", "punomocje.pdf"}
    # Storage nije ni dodirnut — izvoz ne glumi da je pokusao da ponese fajl
    assert supa.storage_pozivi == []
    readme = f["README.txt"].decode("utf-8")
    assert "nisu uključeni" in readme
    # izvuceni tekst, ako je prisutan, ostaje polje metapodatka uz svoj red
    dok = {d["id"]: d for d in json.loads(f["dokumenti.json"])}
    assert dok["d1"]["naziv_fajla"] == "tuzba.pdf"
    assert dok["d2"]["storage_path"] is None
    # README imenuje izvuceni tekst kao ne-original
    assert "izvučeni tekst" in readme.lower()
    assert "nije original" in readme.lower()


# ── 4. delimican pad citanja ───────────────────────────────────────────────

@pytest.mark.anyio
@pytest.mark.parametrize("tabela", sorted(TABELE_IZVOZA))
async def test_pad_bilo_koje_tabele_nije_uspeh_i_ne_pise_audit(tabela):
    from fastapi import HTTPException

    supa = FakeSupa(padovi={tabela})
    rez, audit = await _izvezi(supa)
    assert isinstance(rez, HTTPException)
    assert rez.status_code == 503
    assert tabela in rez.detail
    assert "nije kompletan" in rez.detail
    # neuspeo izvoz NE sme da ostavi `data_export` u nepromenjivom logu
    # (security.html §14.2: „Svaki kompletan izvoz upisuje se ...")
    assert [a for a, _ in audit if a == "data_export"] == []
    assert supa.mutacije == []


@pytest.mark.anyio
async def test_uspesan_izvoz_pise_tacno_jedan_audit_zapis():
    (resp, telo), audit = await _izvezi(FakeSupa())
    akcije = [a for a, _ in audit]
    assert akcije == ["data_export"]
    kw = audit[0][1]
    assert kw["user_id"] == A
    assert kw["resource_type"] == "all_user_data"
    assert kw["metadata"]["format"] == "zip"


# ── 5. prazan predmet / prazan nalog ───────────────────────────────────────

@pytest.mark.anyio
async def test_nalog_bez_ikakvih_podataka_daje_validan_prazan_izvoz():
    supa = FakeSupa()
    (resp, telo), audit = await _izvezi(supa, uid="user-novi")
    f = _sadrzaj(telo)
    for ime in TABELE_IZVOZA.values():
        assert json.loads(f[ime]) == [], ime
    assert [a for a, _ in audit] == ["data_export"]


@pytest.mark.anyio
async def test_prazan_predmet_je_ukljucen_bez_izmisljenih_dokumenata():
    (resp, telo), _ = await _izvezi(FakeSupa())
    f = _sadrzaj(telo)
    assert PA_EMPTY in {p["id"] for p in json.loads(f["predmeti.json"])}
    assert not [d for d in json.loads(f["dokumenti.json"]) if d["predmet_id"] == PA_EMPTY]


# ── 6. ponovljen izvoz: deterministican, bez mutacije ─────────────────────

@pytest.mark.anyio
async def test_ponovljen_izvoz_je_deterministican_i_ne_menja_izvor():
    supa = FakeSupa()
    pre = json.dumps(supa.podaci, sort_keys=True)
    (_, t1), _ = await _izvezi(supa)
    (_, t2), _ = await _izvezi(supa)
    f1, f2 = _sadrzaj(t1), _sadrzaj(t2)
    assert set(f1) == set(f2)
    for ime in TABELE_IZVOZA.values():
        assert f1[ime] == f2[ime], ime
    assert supa.mutacije == []
    assert json.dumps(supa.podaci, sort_keys=True) == pre


@pytest.mark.anyio
async def test_neuspeo_izvoz_ne_menja_izvorne_zapise():
    supa = FakeSupa(padovi={"rocista"})
    pre = json.dumps(supa.podaci, sort_keys=True)
    await _izvezi(supa)
    assert supa.mutacije == []
    assert json.dumps(supa.podaci, sort_keys=True) == pre


# ── 7. manifest: README imenuje ukljuceno i iskljuceno ─────────────────────

@pytest.mark.anyio
async def test_readme_imenuje_svaki_fajl_i_iskljucene_originale():
    (_, telo), _ = await _izvezi(FakeSupa())
    readme = _sadrzaj(telo)["README.txt"].decode("utf-8")
    for ime in TABELE_IZVOZA.values():
        assert ime in readme, ime
    assert "PDF, DOCX" in readme


# ── 8. korisnicki tekst ne obecava vise nego sto izvoz nosi ───────────────

_KOREN = os.path.join(os.path.dirname(__file__), "..")


def _procitaj(rel):
    with open(os.path.join(_KOREN, rel), "rb") as fh:
        return fh.read().decode("utf-8")


def test_dugme_u_podesavanjima_ne_obecava_sve_podatke():
    html = _procitaj("index.html")
    i = html.index('id="export-btn"')
    blok = html[max(0, i - 600):i]
    assert "Preuzmite sve vaše podatke" not in blok
    assert "bez originalnih fajlova" in blok


def test_bezbednosni_list_ne_obecava_aktivnost_ni_kompletan_izvoz():
    html = _procitaj("static/bezbednosni-list.html")
    assert "Kompletan izvoz svih Vaših podataka" not in html
    i = html.index("mašinski čitljivom formatu")
    red = html[html.rfind("<li", 0, i):html.index("</li>", i)]
    assert "aktivnost" not in red
    assert "originalni fajlovi" in red.lower()
