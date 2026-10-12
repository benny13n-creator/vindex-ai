# -*- coding: utf-8 -*-
"""VCR002 Release Closure — FIX 1: integritet brisanja dokumenta.

Invarijanta: API nikad ne prijavljuje uspešno brisanje dokumenta dok AI tvrdnje izvučene iz njega ostaju aktivne
i merodavne. Obrnuto takođe ne sme: neuspelo brisanje ne sme tiho da povuče važeće tvrdnje.

Dva puta kroz STVARAN `api.predmet_dokument_obrisi` (lažna baza, stvaran predmet sa tri dokumenta iz T03):
  * ATOMSKI — migracija 137 (`invalidate_dokument_and_ai_claims_and_emit_event`): povlačenje tvrdnji, brisanje
    reda i događaj u jednoj transakciji. Lažna RPC ovde modeluje SQL; sam SQL je dokazan nad pravim PostgreSQL-om
    u `test_vcr002_rc_fix1_migracija137_pg.py`.
  * PRE MIGRACIJE 137 — funkcije nema (PGRST202): povlačenje PRE brisanja reda, sa kompenzacijom ako brisanje ne uspe.

„Pad procesa“ se modeluje izuzetkom `_Pad(BaseException)`: nijedan `except Exception` ga ne hvata, pa se posle
njega ne izvršava ništa — kao smrt radnika.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from shared.vector_deletion import Ishod, Rezultat
from tests.ns005_harness import _Upit
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, solo  # noqa: F401
from tests.test_vcr002_t03_visedokumentni_predmet import _atomsko_rpc, _brisanje_rpc, predmet  # noqa: F401

NOVA = "invalidate_dokument_and_ai_claims_and_emit_event"
STARA = "invalidate_dokument_relational_and_emit_event"


class _Pad(BaseException):
    """Smrt procesa: ne hvata je nijedan `except Exception`."""


def _nema_funkcije(baza, p):
    raise Exception('{"code": "PGRST202", "message": "Could not find the function '
                    'public.invalidate_dokument_and_ai_claims_and_emit_event in the schema cache"}')


@pytest.fixture
def dokument(predmet, monkeypatch):
    """Zapisnik sa AI tvrdnjama + advokatova ručna tvrdnja koja ga navodi; vektori se brišu uspešno."""
    k, b, pid, doks = predmet
    zap = doks["Zapisnik.pdf"]
    r = k.post(f"/api/evidence/predmeti/{pid}/dokaz", headers=A,
               json={"tvrdnja": "Advokat: tuženi je usmeno priznao dug na ročištu.", "kategorija": "cinjenica", "dokument_id": zap})
    assert r.status_code == 200, r.text
    ai = [t["id"] for t in b.tabele["predmet_dokazi"] if t["dokument_id"] == zap and t.get("izvor_tvrdnje") == "ai_klasifikacija"]
    rucna = next(t["id"] for t in b.tabele["predmet_dokazi"] if t["tvrdnja"].startswith("Advokat:"))
    assert ai
    kvar = {}                                                 # {(tabela, radnja): izuzetak} — jednokratno ili trajno
    stanje = {"posle_brisanja": False, "pad_posle_brisanja": False}
    _exec = _Upit.execute

    def _execute(self):
        if stanje["pad_posle_brisanja"] and stanje["posle_brisanja"]:
            raise _Pad("radnik je umro posle brisanja izvora")
        exc = kvar.get((self.t, self.radnja[0]))
        if exc is not None:
            raise exc
        return _exec(self)
    monkeypatch.setattr(_Upit, "execute", _execute)

    def _oznaci(impl):
        def _f(baza, p):
            out = impl(baza, p)
            if out and out[0].get("invalidated"):
                stanje["posle_brisanja"] = True
            return out
        return _f
    b.rpc_impl[NOVA] = _oznaci(_atomsko_rpc)
    b.rpc_impl[STARA] = _oznaci(_brisanje_rpc)
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta",
               lambda *a, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)), \
         patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        yield {"k": k, "b": b, "pid": pid, "zap": zap, "ai": ai, "rucna": rucna, "kvar": kvar, "stanje": stanje,
               "oznaci": _oznaci}


def _bez_137(d):
    d["b"].rpc_impl[NOVA] = _nema_funkcije


def _obrisi(d, ko=A):
    return d["k"].delete(f"/api/predmeti/{d['pid']}/dokumenti/{d['zap']}", headers=ko)


def _obrisi_uz_pad(d):
    """Pad radnika: harness ga može propustiti ili pretvoriti u 500; meri se samo da uspeh NIJE prijavljen."""
    try:
        r = _obrisi(d)
    except _Pad:
        return
    assert r.status_code != 200, r.text


def _tvrdnja(d, i):
    return next(t for t in d["b"].tabele["predmet_dokazi"] if t["id"] == i)


def _aktivne_ai(d):
    return [i for i in d["ai"] if not _tvrdnja(d, i).get("deleted_at")]


def _dokument_postoji(d):
    return any(x["id"] == d["zap"] for x in d["b"].tabele["predmet_dokumenti"])


def _dogadjaji(d):
    return [e for e in d["b"].tabele["events"] if e.get("event_type") == "SourceInvalidated"
            and (e.get("payload") or {}).get("source_id") == d["zap"]]


def _rpc_pozivi(d, ime):
    return [z for z in d["b"].dnevnik if z["tabela"] == "rpc:" + ime]


def _konzistentno_obrisano(d):
    assert not _dokument_postoji(d)
    assert _aktivne_ai(d) == [], "AI tvrdnje obrisanog dokumenta su i dalje aktivne"
    assert not _tvrdnja(d, d["rucna"]).get("deleted_at"), "advokatova tvrdnja je povučena"
    assert len(_dogadjaji(d)) == 1


def _netaknuto(d):
    assert _dokument_postoji(d)
    assert _aktivne_ai(d) == d["ai"], "važeće tvrdnje su povučene iako dokument nije obrisan"
    assert not _tvrdnja(d, d["rucna"]).get("deleted_at")
    assert _dogadjaji(d) == []


# ── 1. greška pri čitanju tvrdnji pre brisanja (put pre migracije 137) ────────────────────────────────────────
def test_greska_citanja_tvrdnji_pre_brisanja_ne_prijavljuje_uspeh_i_nista_ne_dira(dokument):
    d = dokument
    _bez_137(d)
    d["kvar"][("predmet_dokazi", "select")] = Exception("PostgREST 503 pri čitanju tvrdnji")
    r = _obrisi(d)
    assert r.status_code != 200 and r.json().get("success") is not True, r.text
    assert _rpc_pozivi(d, STARA) == []                       # izvor nije obrisan dok tvrdnje nisu poznate
    _netaknuto(d)
    # ponovni pokušaj posle prolazne greške završava posao
    d["kvar"].clear()
    r2 = _obrisi(d)
    assert r2.status_code == 200 and r2.json()["tvrdnje_povucene"] == len(d["ai"]), r2.text
    _konzistentno_obrisano(d)


# ── 2. greška pri povlačenju tvrdnji (put pre migracije 137) ──────────────────────────────────────────────────
def test_greska_povlacenja_tvrdnji_ne_prijavljuje_uspeh_i_izvor_ostaje(dokument):
    d = dokument
    _bez_137(d)
    d["kvar"][("predmet_dokazi", "update")] = Exception("PostgREST 500 pri povlačenju")
    r = _obrisi(d)
    assert r.status_code != 200 and r.json().get("success") is not True, r.text
    assert _rpc_pozivi(d, STARA) == []
    _netaknuto(d)
    d["kvar"].clear()
    r2 = _obrisi(d)
    assert r2.status_code == 200 and r2.json()["tvrdnje_povucene"] == len(d["ai"]), r2.text
    _konzistentno_obrisano(d)


# ── 3. pad procesa odmah posle brisanja izvora ────────────────────────────────────────────────────────────────
def test_pad_procesa_posle_brisanja_izvora_ne_ostavlja_aktivne_ai_tvrdnje(dokument):
    d = dokument
    d["stanje"]["pad_posle_brisanja"] = True
    _obrisi_uz_pad(d)
    assert not _dokument_postoji(d)
    assert _aktivne_ai(d) == [], "pad posle brisanja je ostavio AI tvrdnje aktivne i bez veze sa izvorom"
    assert not _tvrdnja(d, d["rucna"]).get("deleted_at")
    # ponovni pokušaj: dokumenta nema (404), stanje se ne menja
    d["stanje"]["pad_posle_brisanja"] = False
    pre = json.dumps(d["b"].tabele["predmet_dokazi"], sort_keys=True, default=str)
    assert _obrisi(d).status_code == 404
    assert json.dumps(d["b"].tabele["predmet_dokazi"], sort_keys=True, default=str) == pre
    assert len(_dogadjaji(d)) == 1


def test_pad_procesa_izmedju_povlacenja_i_brisanja_bez_137_ponovni_pokusaj_zavrsava(dokument):
    """Pre migracije 137 jedini preostali prozor: tvrdnje povučene, red još postoji (vektori već uklonjeni, uspeh
    NIJE prijavljen). Ponovni pokušaj mora da završi brisanje — ne da ostavi dokument bez tvrdnji zauvek."""
    d = dokument
    _bez_137(d)
    _exec = _Upit.execute
    pad = {"aktivan": True}

    def _posle_povlacenja(self):
        out = _exec(self)
        if pad["aktivan"] and self.t == "predmet_dokazi" and self.radnja[0] == "update":
            raise _Pad("radnik je umro posle povlačenja")
        return out
    with patch.object(_Upit, "execute", _posle_povlacenja):
        _obrisi_uz_pad(d)
        assert _dokument_postoji(d) and _rpc_pozivi(d, STARA) == []
        pad["aktivan"] = False
        r = _obrisi(d)
    assert r.status_code == 200, r.text
    _konzistentno_obrisano(d)


# ── 4. neuspelo brisanje reda ne sme tiho da povuče važeće tvrdnje ────────────────────────────────────────────
def test_neuspelo_brisanje_reda_bez_137_vraca_povucene_tvrdnje(dokument):
    d = dokument
    _bez_137(d)
    d["b"].greske["rpc:" + STARA] = Exception("baza nedostupna")
    r = _obrisi(d)
    assert r.status_code != 200, r.text
    _netaknuto(d)
    d["b"].greske.clear()
    r2 = _obrisi(d)
    assert r2.status_code == 200, r2.text
    _konzistentno_obrisano(d)


def test_neuspela_atomska_funkcija_ne_dira_nista_a_ponovni_pokusaj_uspeva(dokument):
    d = dokument
    d["b"].greske["rpc:" + NOVA] = Exception("could not serialize access")
    r = _obrisi(d)
    assert r.status_code != 200 and r.json().get("success") is not True, r.text
    assert _rpc_pozivi(d, STARA) == []                       # stvarna greška nije „funkcija ne postoji“
    _netaknuto(d)
    d["b"].greske.clear()
    r2 = _obrisi(d)
    assert r2.status_code == 200 and r2.json()["tvrdnje_povucene"] == len(d["ai"]), r2.text
    _konzistentno_obrisano(d)


# ── 5. atomski put: sve u jednoj funkciji, vlasnik iz tokena ──────────────────────────────────────────────────
def test_atomski_put_povlaci_tvrdnje_u_istoj_funkciji_i_cuva_tudje_i_advokatove(dokument):
    d = dokument
    pre_upisa = len(d["b"].upisi("predmet_dokazi"))
    assert _obrisi(d, ko=B).status_code == 404
    _netaknuto(d)
    r = _obrisi(d)
    assert r.status_code == 200 and r.json()["success"] is True and r.json()["tvrdnje_povucene"] == len(d["ai"]), r.text
    assert len(d["b"].upisi("predmet_dokazi")) == pre_upisa    # nijedan zaseban UPDATE tvrdnji van transakcije
    assert _rpc_pozivi(d, STARA) == []
    _konzistentno_obrisano(d)
    zive_drugih = [t for t in d["b"].tabele["predmet_dokazi"] if t["predmet_id"] == d["pid"] and not t.get("deleted_at")
                   and "17.03.2025" in t["tvrdnja"]]
    assert zive_drugih                                         # tvrdnje drugih dokumenata ostaju


def test_odgovor_nikad_ne_nosi_negativan_broj_povucenih_tvrdnji(dokument):
    """Stari ugovor je za neuspelo povlačenje vraćao `success: true, tvrdnje_povucene: -1`."""
    d = dokument
    _bez_137(d)
    d["kvar"][("predmet_dokazi", "update")] = Exception("kvar")
    r = _obrisi(d)
    assert not (r.status_code == 200 and r.json().get("tvrdnje_povucene", 0) < 0), r.text


def test_trka_dva_brisanja_drugi_zahtev_ne_prijavljuje_da_je_on_obrisao(dokument):
    """Konkurentan zahtev je završio atomsko brisanje između provere vlasništva i našeg poziva: naša funkcija vraća
    `invalidated=False`. Odgovor ne sme da tvrdi uspeh ovog zahteva (ugovor 500 kao pre), a stanje je konsistentno."""
    d = dokument

    def _konkurent_pre_nas(baza, p):
        _atomsko_rpc(baza, p)                                  # drugi zahtev je upravo završio
        return _atomsko_rpc(baza, p)                           # naš poziv: reda više nema
    d["b"].rpc_impl[NOVA] = _konkurent_pre_nas
    r = _obrisi(d)
    assert r.status_code == 500 and r.json().get("success") is not True, r.text
    _konzistentno_obrisano(d)
