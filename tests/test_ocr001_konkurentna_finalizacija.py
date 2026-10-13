# -*- coding: utf-8 -*-
"""OCR001 završni gejt — dva nezavisna finalize procesa (A i B) nad ISTIM Smart Intake poslom.

Scenario: A zauzme posao (`claim_intake_finalize`) i radi duže od 120 s; B preuzme zastarelo zauzeće; oba
provere da dokument ne postoji; oba pokušaju upis; oba pokušaju završni upis.

STVARNO: HTTP rute `routers/smart_intake.py` (dva zahteva u dve niti, svaki sa svojim TestClient-om), stvaran
intake worker i PDF parser, telo `claim_intake_finalize` iz migracije 095 (tests/ns005_intake_fake.py).
SQL-VERNO: jedinstveni indeksi `predmet_dokumenti` — imena, kolone i WHERE tačno iz migracija 094 i 106 (i
predloga 138 kad je uključen), sa Postgres semantikom NULL-a (red sa NULL ključem nikad nije u sukobu) i istim
oblikom greške koji PostgREST vraća (`postgrest.exceptions.APIError`, 23505, ime indeksa u poruci). Da je ta
emulacija verna pravom Postgres-u dokazuje tests/test_ocr001_trka_postgres.py nad stvarnim DDL-om.
KONTROLISANO VREME: sat baze (claim) i monotoni sat procesa pomeraju se za 121 s bez čekanja; niti se
sinhronizuju barijerama na granici baze, ne u kodu koji se testira.
"""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from postgrest.exceptions import APIError

from tests import ns005_harness as _h
from tests import ns005_intake_fake as _fake
from tests.ns005_harness import zaglavlje
from tests.test_ns005_t14_smart_intake import PA, _obradi, _otpremi, ok  # noqa: F401 — `ok` je fixture
from tests.test_vcr002_t02_ocr_korpus import _digitalni_pdf, _job

# Jedinstveni indeksi nad predmet_dokumenti: ime → kolone ključa. Svi su ili bez WHERE (106) ili sa WHERE
# `<kolona> IS NOT NULL` (094, predlog 138) — u oba slučaja red sa bar jednim NULL u ključu nije u sukobu.
INDEKSI_PRODUKCIJA = {
    "predmet_dokumenti_predmet_redni_unique": ("predmet_id", "redni_broj"),          # migracija 106
    "uq_predmet_dokumenti_source_segment": ("source_intake_job_segment_id",),        # migracija 094
}
INDEKS_138 = {"uq_predmet_dokumenti_posao_sadrzaj": ("source_intake_job_id", "content_sha256")}


class _Sat:
    """Sat baze (now() u claim_intake_finalize) i monotoni sat procesa, pomereni zajedno."""

    def __init__(self):
        self.pomak = 0.0

    def sada(self):
        return datetime.now(timezone.utc) + timedelta(seconds=self.pomak)

    def monotoni(self):
        return time.monotonic() + self.pomak


class _Okruzenje:
    def __init__(self, indeksi):
        self.indeksi = indeksi
        self.brava = threading.Lock()          # provera indeksa + upis su jedna atomska operacija, kao u bazi
        self.provere = 0
        self.upisi = 0
        self.proverio = [threading.Event(), threading.Event()]
        self.pusti = [threading.Event(), threading.Event()]
        self.zastoj_upisa = None              # (redni broj upisa, Event koji ga pušta, Event „stigao“)
        self.sukobi = []
        self.tacke = []                        # opšte barijere: _Tacka(uslov) — staje JEDNOM, pre izvršenja
        self.kvar = None                       # (uslov(upit), izuzetak) — pad procesa na granici baze, JEDNOM


class _Tacka:
    def __init__(self, uslov, posle=False):
        self.uslov = uslov
        self.posle = posle                     # True: staje POSLE izvršenja (rezultat je već pročitan)
        self.stigao = threading.Event()
        self.pusti = threading.Event()
        self.iskoriscena = False


def _cekaj_na_tacki(o, upit, posle=False):
    for t in o.tacke:
        with o.brava:
            if t.iskoriscena or t.posle != posle or not t.uslov(upit):
                continue
            t.iskoriscena = True
        t.stigao.set()
        assert t.pusti.wait(30)


def _ukljuci(monkeypatch, b, indeksi, barijera_na_proveri=True):
    o = _Okruzenje(indeksi)
    sat = _Sat()
    monkeypatch.setattr(_fake, "_sada", sat.sada)
    import routers.smart_intake as si
    monkeypatch.setattr(si, "_sat", sat.monotoni, raising=False)
    orig = _h._Upit.execute

    def execute(self):
        _cekaj_na_tacki(o, self)
        kv = o.kvar
        if kv and kv[0](self):
            o.kvar = None
            raise kv[1]
        if self.t == "predmet_dokumenti" and self.radnja[0] == "insert":
            with o.brava:
                n = o.upisi
                o.upisi += 1
            z = o.zastoj_upisa
            if z and z[0] == n:                # upis je poslat, ali „visi“ u mreži/bazi
                z[2].set()
                assert z[1].wait(30)
            red = self.radnja[1]
            with o.brava:
                for ime, kolone in o.indeksi.items():
                    if any(red.get(c) is None for c in kolone):
                        continue
                    for x in b.tabele.get("predmet_dokumenti", []):
                        if all(x.get(c) == red.get(c) for c in kolone):
                            o.sukobi.append(ime)
                            raise APIError({
                                "code": "23505",
                                "message": f'duplicate key value violates unique constraint "{ime}"',
                                "details": f"Key ({', '.join(kolone)})=({', '.join(str(red[c]) for c in kolone)}) already exists.",
                                "hint": None,
                            })
                return orig(self)
        rez = orig(self)
        _cekaj_na_tacki(o, self, posle=True)
        if (barijera_na_proveri and self.t == "predmet_dokumenti" and self.radnja[0] == "select"
                and any(f[0] == "eq" and f[1] == "content_sha256" for f in self.filt)):
            with o.brava:
                i = o.provere
                o.provere += 1
            if i < 2:                          # i=0: A, i=1: B — provera je obavljena, upis još nije
                o.proverio[i].set()
                assert o.pusti[i].wait(30)
        return rez
    monkeypatch.setattr(_h._Upit, "execute", execute)

    orig_rpc = _h.Baza.rpc

    def rpc(self, ime, params=None, *a, **k):
        poziv = orig_rpc(self, ime, params, *a, **k)
        izvrsi = poziv.execute

        def _execute():
            _cekaj_na_tacki(o, ("rpc", ime))
            return izvrsi()
        poziv.execute = _execute
        return poziv
    monkeypatch.setattr(_h.Baza, "rpc", rpc)

    import uploaded_doc.ingest as ing
    b.vektori = []

    def _ingest(manifest, session_id, namespace_override=None, **kw):
        b.vektori.append({"namespace": namespace_override, "predmet_id": (kw.get("extra_metadata") or {}).get("predmet_id"),
                          "verzija": kw.get("verzija_dokumenta_id")})
        return manifest.total_chunks
    monkeypatch.setattr(ing, "ingest_session", _ingest)
    return o, sat


def _spreman(k, b, segmentiran=False, redovi=None):
    pdf = _digitalni_pdf(redovi) if redovi else _digitalni_pdf()
    jid = _job(_otpremi(k, "A", pdf, ime="01_tuzba_digital_lat.pdf"))
    assert _obradi() is True
    if k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()["job"]["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje("A")).status_code == 200
    if segmentiran:
        dok = next(d for d in b.tabele["intake_documents"] if d.get("intake_job_id") == jid)
        b.tabele.setdefault("intake_job_segments", []).append({
            "id": "seg-" + jid[:8], "job_id": jid, "document_id": dok["id"], "segment_index": 0,
            "start_page": 1, "end_page": 1, "assimilation_status": "pending"})
    return jid


def _posao(b, jid):
    return next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)


def _novi_klijent():
    import api
    from fastapi.testclient import TestClient
    return TestClient(api.app, raise_server_exceptions=False)


def _zahtev(rez, ime, jid, telo, korisnik="A"):
    try:
        r = _novi_klijent().post(f"/api/smart-intake/jobs/{jid}/finalize", json=telo, headers=zaglavlje(korisnik))
        rez[ime] = (r.status_code, r.json())
    except BaseException as e:   # noqa: BLE001 — izveštava se, test odlučuje
        rez[ime] = ("izuzetak", repr(e))


def _trka(o, sat, jid, telo, redosled="A_prvi"):
    """A zauzme i proveri → sat +121 s → B preuzme i proveri → oba pokušaju upis (redosled puštanja zadat)."""
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, telo))
    ta.start()
    assert o.proverio[0].wait(30), "A nije stigao do provere dokumenta"
    sat.pomak += 121                                   # A radi duže od 120 s; zauzeće je u bazi zastarelo
    tb = threading.Thread(target=_zahtev, args=(rez, "B", jid, telo))
    tb.start()
    assert o.proverio[1].wait(30), ("B nije stigao do provere dokumenta", rez)
    prvi, drugi = (0, 1) if redosled == "A_prvi" else (1, 0)
    niti = (ta, tb)
    o.pusti[prvi].set()
    niti[prvi].join(30)
    o.pusti[drugi].set()
    niti[drugi].join(30)
    assert not ta.is_alive() and not tb.is_alive()
    return rez


def _merenje(b, jid, rez, predmeta_pre):
    p = _posao(b, jid)
    dok = [d for d in b.tabele.get("predmet_dokumenti", []) if d.get("source_intake_job_id") == jid]
    dog = [e for e in b.tabele.get("events", []) if e.get("predmet_id") == p.get("predmet_id")]
    dokazi = [e for e in dog if e.get("event_type") == "NewEvidenceRegistered" or "EVIDENCE" in str(e.get("event_type")).upper()]
    return {
        "dokumenata": len(dok),
        "redni_brojevi": sorted(d.get("redni_broj") for d in dok),
        "predmeta_novih": len(b.tabele["predmeti"]) - predmeta_pre,
        "dogadjaja_dokaza": len(dokazi),
        "dogadjaji_po_tipu": sorted(str(e.get("event_type")) for e in dog),
        "ingest_poziva": len(b.vektori),
        "vektorskih_identiteta": len({(v["namespace"], v["predmet_id"], v["verzija"]) for v in b.vektori}),
        "finalizing_at": p.get("finalizing_at"),
        "assimilation_complete": p.get("assimilation_complete"),
        "predmet_id": p.get("predmet_id"),
        "A": rez.get("A"), "B": rez.get("B"),
    }


def _ponovo(k, jid, telo):
    r = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json=telo, headers=zaglavlje("A"))
    return r.status_code, r.json()


def _invarijante(m, b, jid, k, telo):
    """Zajednički ishod koji mora da važi posle trke, bez obzira na redosled."""
    assert m["dokumenata"] == 1, m
    assert m["dogadjaja_dokaza"] <= 1, m
    assert m["vektorskih_identiteta"] == 1, m
    # Tačno jedan zahtev je uspeo; drugi NIJE prijavio uspeh.
    statusi = sorted([m["A"][0], m["B"][0]], key=str)
    uspesi = [x for x in (m["A"], m["B"]) if x[0] == 200 and x[1].get("ok") is True]
    assert len(uspesi) == 1, m
    gubitnik = m["A"] if uspesi[0] is m["B"] else m["B"]
    assert gubitnik[0] in (409, 503) and not (isinstance(gubitnik[1], dict) and gubitnik[1].get("ok") is True), (statusi, m)
    assert m["assimilation_complete"] is True, m
    # Ponovni pokušaj posle trke: već prikačeno, bez novog dokumenta.
    s, j = _ponovo(k, jid, telo)
    assert s == 200 and j["prikacivanje"] == "POTPUNO" and j["dokumenata_povezano"] == 1, (s, j)
    assert len([d for d in b.tabele["predmet_dokumenti"] if d.get("source_intake_job_id") == jid]) == 1


# ── ZADATAK 1/3: obavezan slučaj — običan, nesegmentiran dokument (source_intake_job_segment_id = NULL) ──────

@pytest.mark.parametrize("redosled", ["A_prvi", "B_prvi"])
def test_trka_A_B_nesegmentiran_postojeci_predmet_najvise_jedan_dokument(ok, monkeypatch, redosled):
    k, b = ok
    jid = _spreman(k, b)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    pre = len(b.tabele["predmeti"])
    rez = _trka(o, sat, jid, {"predmet_id": PA}, redosled)
    m = _merenje(b, jid, rez, pre)
    print(ascii(("MERENJE", redosled, m)))
    assert [d.get("source_intake_job_segment_id") for d in b.tabele["predmet_dokumenti"]
            if d.get("source_intake_job_id") == jid] == [None], m
    assert m["predmeta_novih"] == 0 and m["predmet_id"] == PA, m
    assert "nije ništa upisao" in m["A"][1]["detail"], m                     # A je odustao PRE upisa
    _invarijante(m, b, jid, k, {"predmet_id": PA})


def test_trka_A_B_novi_predmet_bez_drugog_predmeta(ok, monkeypatch):
    k, b = ok
    jid = _spreman(k, b)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    pre = len(b.tabele["predmeti"])
    rez = _trka(o, sat, jid, {})
    m = _merenje(b, jid, rez, pre)
    print(ascii(("MERENJE novi predmet", m)))
    assert m["predmeta_novih"] == 1, m
    assert len([e for e in m["dogadjaji_po_tipu"] if "KREIRAN" in e.upper() or "CREATED" in e.upper()]) <= 1, m
    _invarijante(m, b, jid, k, {})


def test_trka_A_B_segmentiran_indeks_094_ne_zaobilazi_se_uzim_upisom(ok, monkeypatch):
    """Segment ima jedinstven indeks (094). Drugi upis istog segmenta ne sme da „uspe“ tako što izbaci lineage
    kolone i upiše isti dokument bez njih."""
    k, b = ok
    jid = _spreman(k, b, segmentiran=True)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    pre = len(b.tabele["predmeti"])
    rez = _trka(o, sat, jid, {"predmet_id": PA})
    m = _merenje(b, jid, rez, pre)
    print(ascii(("MERENJE segmentiran", m, o.sukobi)))
    svi = [d for d in b.tabele["predmet_dokumenti"] if d.get("predmet_id") == PA]
    assert len(svi) == 1 and svi[0].get("source_intake_job_segment_id") == "seg-" + jid[:8], (svi, m)
    seg = next(x for x in b.tabele["intake_job_segments"] if x["id"] == "seg-" + jid[:8])
    assert seg["assimilation_status"] == "resolved", seg                     # gubitnik ga nije oborio na „failed“
    assert "nije ništa upisao" in m["A"][1]["detail"], m
    _invarijante(m, b, jid, k, {"predmet_id": PA})


# ── Preostali prozor: upis poslat dok je zauzeće važilo, ali „visi“ duže od rezerve ──────────────────────────

@pytest.mark.parametrize("sa_138", [False, True], ids=["bez_indeksa_138", "sa_indeksom_138"])
def test_zaglavljen_poslat_upis_zatvara_samo_indeks_baze(ok, monkeypatch, sa_138):
    """Aplikacija ne može da povuče upis koji je već poslat. Ako on stigne posle B-ovog, samo jedinstven indeks
    baze ga odbija. Bez indeksa 138 ovaj test DOKUMENTUJE preostali prozor (2 reda); sa indeksom: 1 red."""
    k, b = ok
    jid = _spreman(k, b)
    indeksi = dict(INDEKSI_PRODUKCIJA, **(INDEKS_138 if sa_138 else {}))
    o, sat = _ukljuci(monkeypatch, b, indeksi, barijera_na_proveri=False)
    pusti_a, stigao_a = threading.Event(), threading.Event()
    o.zastoj_upisa = (0, pusti_a, stigao_a)
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, {"predmet_id": PA}))
    ta.start()
    assert stigao_a.wait(30)                           # A je poslao upis dokumenta; odgovor ne stiže
    sat.pomak += 121
    _zahtev(rez, "B", jid, {"predmet_id": PA})          # B preuzima, upisuje, završava
    pusti_a.set()                                      # A-ov upis tek sada stiže do baze
    ta.join(30)
    m = _merenje(b, jid, rez, len(b.tabele["predmeti"]))
    print(ascii(("MERENJE zaglavljen upis", sa_138, m, o.sukobi)))
    assert rez["B"][0] == 200 and rez["B"][1]["ok"] is True, m
    assert not (rez["A"][0] == 200 and rez["A"][1].get("ok") is True), m      # A nikad ne tvrdi uspeh
    if sa_138:
        assert m["dokumenata"] == 1 and "uq_predmet_dokumenti_posao_sadrzaj" in o.sukobi, m
        assert m["dogadjaja_dokaza"] <= 1, m
    else:
        assert m["dokumenata"] == 2, ("očekivan preostali prozor bez indeksa baze", m)


def test_zaglavljen_upis_segmenta_indeks_094_bez_upisa_bez_identiteta(ok, monkeypatch):
    """Bez predloga 138, ali segmentiran dokument: postojeći indeks 094 odbija A-ov zakasneli upis. Kod ranije nije
    prihvatao odbijanje — prelazio je na užu varijantu bez lineage kolona i upisivao isti dokument drugi put."""
    k, b = ok
    jid = _spreman(k, b, segmentiran=True)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA), barijera_na_proveri=False)
    pusti_a, stigao_a = threading.Event(), threading.Event()
    o.zastoj_upisa = (0, pusti_a, stigao_a)
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, {"predmet_id": PA}))
    ta.start()
    assert stigao_a.wait(30)
    sat.pomak += 121
    _zahtev(rez, "B", jid, {"predmet_id": PA})
    pusti_a.set()
    ta.join(30)
    svi = [d for d in b.tabele["predmet_dokumenti"] if d.get("predmet_id") == PA]
    print(ascii(("MERENJE zaglavljen segment", rez, o.sukobi, len(svi))))
    assert "uq_predmet_dokumenti_source_segment" in o.sukobi
    assert len(svi) == 1 and svi[0]["source_intake_job_segment_id"] == "seg-" + jid[:8], svi
    assert rez["B"][0] == 200 and rez["B"][1]["ok"] is True
    assert not (rez["A"][0] == 200 and rez["A"][1].get("ok") is True), rez


# ── Bez takmaca: dug finalize obnavlja zauzeće i završava (nema zaključavanja dugih poslova) ─────────────────────

def test_dug_finalize_bez_takmaca_obnavlja_zauzece_i_zavrsava(ok, monkeypatch):
    k, b = ok
    jid = _spreman(k, b)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    o.pusti[1].set()
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, {"predmet_id": PA}))
    ta.start()
    assert o.proverio[0].wait(30)
    prvo = _posao(b, jid)["finalizing_at"]
    sat.pomak += 121                                   # ekstrakcija/Pinecone trajali duže od roka zauzeća
    o.pusti[0].set()
    ta.join(30)
    p = _posao(b, jid)
    assert rez["A"][0] == 200 and rez["A"][1]["ok"] is True, rez
    assert p["assimilation_complete"] is True and p["finalizing_at"] != prvo     # obnovljeno, pa završni CAS prošao
    assert len([d for d in b.tabele["predmet_dokumenti"] if d.get("source_intake_job_id") == jid]) == 1


# ── Zastareo snimak posla: B je pročitao posao PRE nego što je A upisao novi predmet ───────────────────────────

BEZ_BROJA = ["OSNOVNI SUD U BEOGRADU", "TUZBA radi naknade stete", "Tuzilac: Zlatibor Fiktivic",
             "Tuzeni: Primer Gradnja DOO", "Vrednost spora: 100.000 dinara"]


def test_B_sa_zastarelim_snimkom_posla_nastavlja_u_predmet_iz_zauzeca(ok, monkeypatch):
    """Dokument bez broja predmeta (B ne može da nađe A-ov predmet po broju): jedini trag je predmet koji je A upisao
    na posao, a B ga vidi tek u redu koji vraća zauzeće — ne u snimku posla pročitanom pre zauzeća."""
    k, b = ok
    jid = _spreman(k, b, redovi=BEZ_BROJA)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    a_otvara = _Tacka(lambda u: getattr(u, "t", None) == "predmeti" and u.radnja[0] == "insert")
    b_zauzima = _Tacka(lambda u: u == ("rpc", "claim_intake_finalize"))
    o.tacke.append(a_otvara)
    pre = len(b.tabele["predmeti"])
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, {}))
    ta.start()
    assert a_otvara.stigao.wait(30)                    # A je zauzeo posao i otvara novi predmet
    o.tacke.append(b_zauzima)
    tb = threading.Thread(target=_zahtev, args=(rez, "B", jid, {}))
    tb.start()
    assert b_zauzima.stigao.wait(30)                   # B je pročitao posao (bez predmeta), zauzimanje još nije
    a_otvara.pusti.set()
    assert o.proverio[0].wait(30)                      # A je upisao predmet na posao i stigao do dokumenta
    sat.pomak += 121
    b_zauzima.pusti.set()
    assert o.proverio[1].wait(30), rez                  # B je preuzeo zastarelo zauzeće
    o.pusti[0].set()
    ta.join(30)
    o.pusti[1].set()
    tb.join(30)
    m = _merenje(b, jid, rez, pre)
    print(ascii(("MERENJE zastareo snimak", m)))
    assert m["predmeta_novih"] == 1, m
    _invarijante(m, b, jid, k, {})


def test_A_zastane_pre_otvaranja_predmeta_ne_otvara_drugi_predmet(ok, monkeypatch):
    """A zauzme posao i ne nađe postojeći predmet po broju, pa zastane pre otvaranja novog. B za to vreme preuzme
    zastarelo zauzeće i završi ceo posao. A posle toga ne sme da otvori drugi predmet."""
    k, b = ok
    jid = _spreman(k, b)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    o.pusti[0].set()
    o.pusti[1].set()
    a_trazi = _Tacka(lambda u: getattr(u, "t", None) == "predmeti" and u.radnja[0] == "select", posle=True)
    o.tacke.append(a_trazi)
    pre = len(b.tabele["predmeti"])
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, {}))
    ta.start()
    assert a_trazi.stigao.wait(30)
    sat.pomak += 121
    _zahtev(rez, "B", jid, {})
    a_trazi.pusti.set()
    ta.join(30)
    m = _merenje(b, jid, rez, pre)
    print(ascii(("MERENJE A zastao pre predmeta", m)))
    assert m["predmeta_novih"] == 1, m
    assert len([e for e in m["dogadjaji_po_tipu"] if e == "predmet_kreiran"]) == 1, m
    assert m["B"][0] == 200 and m["B"][1]["ok"] is True and m["A"][0] == 409, m
    assert "nije ništa upisao" in m["A"][1]["detail"], m
    assert m["dokumenata"] == 1, m


# ── Bezbednost u trci: tuđ korisnik ne preuzima zastarelo zauzeće ───────────────────────────────────────────────

def test_tudj_korisnik_ne_preuzima_zastarelo_zauzece(ok, monkeypatch):
    k, b = ok
    jid = _spreman(k, b)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, {"predmet_id": PA}))
    ta.start()
    assert o.proverio[0].wait(30)
    zauzece_a = _posao(b, jid)["finalizing_at"]
    sat.pomak += 121
    _zahtev(rez, "B", jid, {"predmet_id": "pred-B-1"}, korisnik="B")
    assert rez["B"][0] == 404, rez
    assert _posao(b, jid)["finalizing_at"] == zauzece_a                       # B nije dirao zauzeće
    o.pusti[0].set()
    o.pusti[1].set()
    ta.join(30)
    assert rez["A"][0] == 200 and rez["A"][1]["ok"] is True, rez
    dok = [d for d in b.tabele["predmet_dokumenti"] if d.get("source_intake_job_id") == jid]
    assert len(dok) == 1 and dok[0]["user_id"] == "uid-A" and dok[0]["predmet_id"] == PA
    assert all(v["predmet_id"] == PA and "uid-B" not in str(v["namespace"]) for v in b.vektori)


# ── Pobednik dobije odbijanje indeksa: zakasneli upis gubitnika stigao je PRVI ─────────────────────────────────

@pytest.mark.parametrize("vrsta", ["segment_094", "indeks_138"])
def test_pobednik_povezuje_red_koji_je_gubitnik_upisao_pre_njega(ok, monkeypatch, vrsta):
    """A-ov upis visi; B preuzme i proveri (nema reda); A-ov upis tada stigne; B-ov upis baza odbija. B mora da
    poveže postojeći red (isti identitet) i iskreno prijavi prikačeno — ne „nije prikačeno“ i ne drugi red."""
    k, b = ok
    jid = _spreman(k, b, segmentiran=(vrsta == "segment_094"))
    indeksi = dict(INDEKSI_PRODUKCIJA, **(INDEKS_138 if vrsta == "indeks_138" else {}))
    o, sat = _ukljuci(monkeypatch, b, indeksi, barijera_na_proveri=False)
    pusti_a, stigao_a = threading.Event(), threading.Event()
    o.zastoj_upisa = (0, pusti_a, stigao_a)
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, {"predmet_id": PA}))
    ta.start()
    assert stigao_a.wait(30)
    b_upisuje = _Tacka(lambda u: getattr(u, "t", None) == "predmet_dokumenti" and u.radnja[0] == "insert")
    o.tacke.append(b_upisuje)
    sat.pomak += 121
    tb = threading.Thread(target=_zahtev, args=(rez, "B", jid, {"predmet_id": PA}))
    tb.start()
    assert b_upisuje.stigao.wait(30)                   # B je proverio i šalje upis
    pusti_a.set()
    ta.join(30)                                        # A-ov red je u bazi; A gubi na završnom CAS-u
    b_upisuje.pusti.set()
    tb.join(30)
    m = _merenje(b, jid, rez, len(b.tabele["predmeti"]))
    print(ascii(("MERENJE pobednik povezuje", vrsta, m, o.sukobi)))
    assert o.sukobi, m
    svi = [d for d in b.tabele["predmet_dokumenti"] if d.get("predmet_id") == PA]
    assert len(svi) == 1, svi
    assert m["B"][0] == 200 and m["B"][1]["ok"] is True and m["B"][1]["prikacivanje"] == "POTPUNO", m
    assert m["assimilation_complete"] is True and m["dogadjaja_dokaza"] == 1, m
    assert not (m["A"][0] == 200 and m["A"][1].get("ok") is True), m


# ── B upiše pa padne; A posle toga ne sme da „obnovi“ B-ovo zastarelo zauzeće i upiše po staroj proveri ───────

def test_A_ne_preuzima_zauzece_koje_je_u_medjuvremenu_drzao_B(ok, monkeypatch):
    k, b = ok
    jid = _spreman(k, b)
    o, sat = _ukljuci(monkeypatch, b, dict(INDEKSI_PRODUKCIJA))
    o.pusti[1].set()
    rez = {}
    ta = threading.Thread(target=_zahtev, args=(rez, "A", jid, {"predmet_id": PA}))
    ta.start()
    assert o.proverio[0].wait(30)                      # A: dokument ne postoji
    sat.pomak += 121
    o.kvar = (lambda u: u.t == "intake_jobs" and u.radnja[0] == "update"
              and isinstance(u.radnja[1], dict) and "assimilation_complete" in u.radnja[1], _UbijenProces())
    _zahtev(rez, "B", jid, {"predmet_id": PA})          # B preuzme, upiše dokument, proces umre pre markera
    assert rez["B"][0] == "izuzetak", rez
    assert len([d for d in b.tabele["predmet_dokumenti"] if d.get("source_intake_job_id") == jid]) == 1
    sat.pomak += 121                                   # i B-ovo zauzeće je sada zastarelo
    o.pusti[0].set()
    ta.join(30)
    dok = [d for d in b.tabele["predmet_dokumenti"] if d.get("source_intake_job_id") == jid]
    print(ascii(("MERENJE B pao", rez, len(dok))))
    assert len(dok) == 1, ("A je upisao po proveri starijoj od B-ovog upisa", rez, dok)
    assert rez["A"][0] == 409 and "nije ništa upisao" in rez["A"][1]["detail"], rez
    s, j = _ponovo(k, jid, {"predmet_id": PA})          # oporavak posle oba prekida
    assert s == 200 and j["prikacivanje"] == "POTPUNO", (s, j)
    assert len([d for d in b.tabele["predmet_dokumenti"] if d.get("source_intake_job_id") == jid]) == 1


class _UbijenProces(BaseException):
    """Pad procesa (OOM/SIGKILL): ne hvata ga `except Exception`."""
