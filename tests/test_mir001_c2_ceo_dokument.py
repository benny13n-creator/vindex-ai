# -*- coding: utf-8 -*-
"""MIR001 FINAL CLOSURE — TASK-C2: ekstrakcija činjenica iz CELOG dokumenta (ne samo iz prvih 1.500 znakova).

Stvarno: prijem (rute, worker, PDF ekstrakcija), dispečer, PRAVI `_klasifikuj_dokument` i `_klasifikuj_ceo_dokument`,
upis tvrdnji (`shared/evidence_write.upisi_dokaze` — utemeljenje u celom tekstu), Genome osvežavanje i V2 protivrečnosti.
Zamenjen je SAMO poziv modela, i to tako da „vidi“ isključivo tekst koji mu server pošalje: činjenica je tvrdnja samo
ako je bila u poslatom prozoru. Genome model čita stvarni prompt (oznake `[DOK-NN: …]` i `CLAIM-NNN: …`).
"""
import copy
import io
import json
import re
from unittest.mock import MagicMock

import pytest

from tests import ns006_realni_predmet as rp
from tests.test_mir001_t03_kontinuitet import _sekcije
from tests.test_osb002_solo_tok import A, _do_kraja_dogadjaja, _novi_predmet, _otpremi, _radnik, solo  # noqa: F401
from routers.evidence import _klasifikuj_dokument as _PRAVI_KLASIFIKATOR   # pre fixture-a (koji ga zamenjuje)

UVOD = "Recenica uvoda broj {i}: tuzilac opisuje okolnosti ugovora i tok saradnje sa tuzenim."


def _pdf(redovi):
    from reportlab.pdfgen import canvas
    bb = io.BytesIO()
    c = canvas.Canvas(bb, invariant=1)
    y = 800
    for r in redovi:
        if y < 60:
            c.showPage()
            y = 800
        c.drawString(40, y, r)
        y -= 16
    c.showPage()
    c.save()
    return bb.getvalue()


def _redovi(naslov, n_uvod, kasne, sredina=None):
    r = [f"PRIVREDNI SUD (SINTETICKI) — {naslov}"] + [UVOD.format(i=i) for i in range(n_uvod)]
    for poz, tekst in (sredina or []):
        r.insert(poz, tekst)
    return r + kasne + ["Kraj podneska."]


@pytest.fixture
def citac(solo, monkeypatch):
    """Pravi klasifikator; model vraća samo redove sa 'CINJENICA' iz POSLATOG prozora."""
    k, b = solo
    import routers.evidence as ev
    poruke = []

    def _model(client, user_msg):
        poruke.append(user_msg)
        prozor = user_msg.split("znakova):\n", 1)[-1]
        cin = [" ".join(l.split()) for l in prozor.splitlines() if "CINJENICA" in l]
        if any("HALUCINACIJA" in l for l in prozor.splitlines()):
            cin.append("Tuzeni je platio ceo dug 01.01.2020.")      # tvrdnja koje NEMA u tekstu
        r = MagicMock()
        r.choices = [MagicMock()]
        r.choices[0].message.content = json.dumps({"tip_dokaza": "podnesak", "kljucne_cinjenice": cin,
                                                   "pravni_elementi": [f"element prozora {len(poruke)}-{j}" for j in range(3)] if cin else []})
        return r
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _PRAVI_KLASIFIKATOR)
    monkeypatch.setattr(ev, "_pozovi_evidence_api", _model)
    return k, b, poruke


def _prikaci(k, b, pid, ime, redovi):
    r = _otpremi(k, _pdf(redovi), ime=ime)
    assert r.status_code in (200, 202), r.text
    jid = r.json()["rezultati"][0]["job_id"]
    while _radnik():
        pass
    if next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A)
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code == 200, f.text
    _do_kraja_dogadjaja(b, najvise=30)
    return next(d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid and d["naziv_fajla"] == ime)


def _tvrdnje(b, did):
    return [t for t in b.tabele["predmet_dokazi"] if t["dokument_id"] == did and not t.get("deleted_at")]


def _ekstr(d):
    t = d.get("ai_tags")
    t = json.loads(t) if isinstance(t, str) else (t or {})
    return t.get("_ekstrakcija")


def _poz(d, s):
    return " ".join((d.get("tekst_sadrzaj") or "").split()).find(s)


def test_kasna_cinjenica_postaje_tvrdnja_sa_izvorom_i_potpunim_citanjem(citac):
    k, b, poruke = citac
    _, pid = _novi_predmet(k, b)
    kasna = "CINJENICA: tuzeni je pismeno priznao dug od 2.345.678 dinara dana 03.03.2026."
    rana = "CINJENICA: ugovor o isporuci zakljucen 12.12.2024."
    d = _prikaci(k, b, pid, "Dug podnesak.pdf", _redovi("PODNESAK", 60, [kasna], sredina=[(3, rana)]))
    assert _poz(d, "CINJENICA: tuzeni je pismeno") > 4500                 # iza i stare granice i granice Genome-a
    [t] = [t for t in _tvrdnje(b, d["id"]) if "2.345.678" in t["tvrdnja"]]
    assert t["dokument_id"] == d["id"]                                   # izvor: tačan dokument
    # pravni element prvog prozora ide SAMO uz činjenicu prvog prozora, ne i uz kasnu
    [r0] = [x for x in _tvrdnje(b, d["id"]) if "12.12.2024" in x["tvrdnja"]]
    assert r0["pravni_element"] == "element prozora 1-0" and t["pravni_element"] is None
    e = _ekstr(d)
    assert e["potpuno"] is True and e["procitano_znakova"] == e["ukupno_znakova"] == len(d["tekst_sadrzaj"])
    assert e["prozora"] == len(poruke) == 2 and e["neprocitani_prozori"] == [] and e["cinjenica_odbaceno"] == 0
    assert e["cinjenice_potpune"] is True
    # nikad više od dozvoljenog prozora po pozivu
    assert all(len(p.split("znakova):\n", 1)[-1]) <= 4000 for p in poruke)
    # Genome vidi činjenicu kroz katalog tvrdnji, a zaglavlje dokumenta kaže da je tekst skraćen
    g = b.genome_pozivi[-1]
    assert re.search(r"CLAIM-\d+: [^\n]*2\.345\.678", g)
    assert "TEKST SKRAĆEN: prikazano prvih 4500" in g
    # graf dokaza: stanje čitanja je poznato i potpuno
    gv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    [dk] = [x for x in gv["dokazi"]["dokumenti"] if x["id"] == d["id"]]
    assert dk["klasifikacija"]["citanje"]["potpuno"] is True


def test_dokument_duzi_od_granice_je_delimicno_procitan_nikad_potpun(citac):
    k, b, poruke = citac
    _, pid = _novi_predmet(k, b)
    rana = "CINJENICA: ugovor je zakljucen 10.01.2025."
    kasna = "CINJENICA: rok isporuke je 15.04.2026."
    d = _prikaci(k, b, pid, "Predug.pdf", _redovi("PODNESAK", 320, [kasna], sredina=[(5, rana)]))
    e = _ekstr(d)
    assert e["ukupno_znakova"] > 23000 and e["prozora"] == len(poruke) == 6
    assert e["potpuno"] is False and e["procitano_znakova"] < e["ukupno_znakova"]
    tv = [t["tvrdnja"] for t in _tvrdnje(b, d["id"])]
    assert any("10.01.2025" in t for t in tv) and not any("15.04.2026" in t for t in tv)   # granica je stvarna
    gv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    [dk] = [x for x in gv["dokazi"]["dokumenti"] if x["id"] == d["id"]]
    c = dk["klasifikacija"]["citanje"]
    assert c["potpuno"] is False and c["procitano_znakova"] < c["ukupno_znakova"]


def test_pad_jednog_prozora_ostavlja_dokument_delimicnim(citac, monkeypatch):
    k, b, poruke = citac
    import routers.evidence as ev
    pravi = ev._pozovi_evidence_api

    def _pada_drugi(client, user_msg):
        if "(deo 2/" in user_msg:
            raise RuntimeError("prolazna greška modela")
        return pravi(client, user_msg)
    monkeypatch.setattr(ev, "_pozovi_evidence_api", _pada_drugi)
    _, pid = _novi_predmet(k, b)
    d = _prikaci(k, b, pid, "Pad prozora.pdf", _redovi("PODNESAK", 60, ["CINJENICA: kasna cinjenica 07.07.2026."]))
    e = _ekstr(d)
    assert e["potpuno"] is False and e["neprocitani_prozori"] == [2]
    assert not [t for t in _tvrdnje(b, d["id"]) if "07.07.2026" in t["tvrdnja"]]


def test_cinjenica_u_preklopu_prozora_nije_duplirana(citac):
    k, b, poruke = citac
    _, pid = _novi_predmet(k, b)
    granicna = "CINJENICA: zapisnik o primopredaji potpisan 20.02.2026."
    red = next(r for r in (_redovi("PODNESAK", 60, [], sredina=[(n, granicna)]) for n in range(40, 56))
               if 3800 < "\n".join(r).find("CINJENICA") < 4000 - len(granicna))          # red u preklopu prozora
    d = _prikaci(k, b, pid, "Preklop.pdf", red)
    p = _poz(d, "CINJENICA")
    assert 3800 <= p and p + len(granicna) <= 4000, p                     # zaista u oba prozora
    assert sum(1 for x in poruke if granicna in " ".join(x.split())) == 2
    assert len([t for t in _tvrdnje(b, d["id"]) if "20.02.2026" in t["tvrdnja"]]) == 1


def test_kratak_dokument_jedan_poziv_kao_ranije(citac):
    k, b, poruke = citac
    _, pid = _novi_predmet(k, b)
    d = _prikaci(k, b, pid, "Kratak.pdf", ["PRIVREDNI SUD (SINTETICKI)", "CINJENICA: rociste je 05.05.2026."])
    assert len(poruke) == 1 and _ekstr(d)["potpuno"] is True and _ekstr(d)["prozora"] == 1
    assert [t["tvrdnja"] for t in _tvrdnje(b, d["id"])] == ["CINJENICA: rociste je 05.05.2026."]


def test_izmisljena_cinjenica_nije_utemeljena_u_izvoru(citac):
    k, b, poruke = citac
    _, pid = _novi_predmet(k, b)
    d = _prikaci(k, b, pid, "Halucinacija.pdf", _redovi("PODNESAK", 60, ["HALUCINACIJA okidac", "CINJENICA: dug 1.000 dinara."]))
    gv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    po = {t["vrednost"]: t for t in gv["dokazi"]["tvrdnje"]}
    assert po["Tuzeni je platio ceo dug 01.01.2020."]["potpora"] != "LOCIRANA_U_DOKUMENTU"   # nema je u tekstu
    assert po["CINJENICA: dug 1.000 dinara."]["potpora"] == "LOCIRANA_U_DOKUMENTU"


def test_kasne_cinjenice_dva_dokumenta_mogu_da_protivrece(citac, monkeypatch):
    k, b, poruke = citac
    import routers.case_dna as cd

    async def _genome(client, combined, n):
        b.genome_pozivi.append(combined)
        claim = dict(re.findall(r"(CLAIM-\d+): ([^\n]+)", combined))
        sek = _sekcije(combined)
        g = copy.deepcopy(rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["rokovi_kriticni"], g["kontradikcije"], g["datumi_kljucni"] = [], [], []
        ca = [c for c, t in claim.items() if "rok isporuke je 01.03.2026" in t]
        cb = [c for c, t in claim.items() if "rok isporuke je 15.04.2026" in t]
        if ca and cb and "Tuzba.pdf" in sek and "Odgovor.pdf" in sek:
            g["kontradikcije"].append({"issue_label": "Rok isporuke", "claim_refs": [ca[0], cb[0]],
                                       "relation_type": "cinjenica_cinjenica", "opis": "01.03.2026 naspram 15.04.2026",
                                       "lokacija_1": sek["Tuzba.pdf"][0], "lokacija_2": sek["Odgovor.pdf"][0], "tezina": "kriticna"})
        return json.dumps(g, ensure_ascii=False)
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome)
    _, pid = _novi_predmet(k, b)
    d1 = _prikaci(k, b, pid, "Tuzba.pdf", _redovi("TUZBA", 60, ["CINJENICA: rok isporuke je 01.03.2026."]))
    d2 = _prikaci(k, b, pid, "Odgovor.pdf", _redovi("ODGOVOR NA TUZBU", 60, ["CINJENICA: rok isporuke je 15.04.2026."]))
    assert _poz(d1, "CINJENICA") > 4500 and _poz(d2, "CINJENICA") > 4500   # Genome ih NE vidi u tekstu dokumenta
    gv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    [kon] = gv["kontradikcije"]["aktivne"]
    assert kon["sporna_tacka"] == "Rok isporuke"
    dok_ids = {t["dokument_id"] for t in b.tabele["predmet_dokazi"]
               if t["id"] in {c["dokaz_id"] for c in b.tabele["predmet_contradiction_claims"]}}
    assert dok_ids == {d1["id"], d2["id"]}


def test_vise_od_granice_cinjenica_odbacuje_se_i_belezi(citac):
    k, b, poruke = citac
    _, pid = _novi_predmet(k, b)
    cin = [f"CINJENICA broj {i}: isplata rate {i}.000 dinara." for i in range(25)]
    d = _prikaci(k, b, pid, "Mnogo cinjenica.pdf", ["PRIVREDNI SUD (SINTETICKI)"] + cin)
    e = _ekstr(d)
    assert e["potpuno"] is True and e["cinjenica_izdvojeno"] == 25 and e["cinjenica_odbaceno"] == 5
    assert e["cinjenice_potpune"] is False                               # pročitano celo, ali ne i sve upisano
    assert len(_tvrdnje(b, d["id"])) == 20
    gv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    [dk] = [x for x in gv["dokazi"]["dokumenti"] if x["id"] == d["id"]]
    assert dk["klasifikacija"]["citanje"]["cinjenica_odbaceno"] == 5          # odbacivanje je vidljivo, ne tiho
    assert dk["klasifikacija"]["citanje"]["cinjenice_potpune"] is False


def test_gust_dokument_odlucna_kasna_cinjenica_prezivljava_granicu(citac, monkeypatch):
    """GATE-C2: model vraća 8 činjenica po prozoru (6 prozora = 48); odlučna činjenica je PRVA (najodlučnija) u 5.
    prozoru. Granica od 20 se deli naizmenično po prozorima → ona ostaje; odbacivanje je zabeleženo."""
    k, b, poruke = citac
    import routers.evidence as ev

    def _osam(client, user_msg):
        poruke.append(user_msg)
        prozor = user_msg.split("znakova):\n", 1)[-1]
        odl = [" ".join(l.split()) for l in prozor.splitlines() if "PRIZNANJE" in l]
        ost = [" ".join(l.split()) for l in prozor.splitlines() if "Faktura" in l][:8 - len(odl)]
        r = MagicMock()
        r.choices = [MagicMock()]
        r.choices[0].finish_reason = "stop"
        r.choices[0].message.content = json.dumps({"tip_dokaza": "podnesak", "pravni_elementi": [],
                                                   "kljucne_cinjenice": odl + ost})
        return r
    monkeypatch.setattr(ev, "_pozovi_evidence_api", _osam)
    redovi = [f"Faktura br. {i:03d} od {1 + i % 28:02d}.0{1 + i % 9}.2025. na iznos od {1000 + i * 7}.000 dinara placena je o roku."
              for i in range(260)]
    redovi.insert(200, "PRIZNANJE: tuzeni je dopisom br. 118/26 od 03.03.2026. priznao dug od 2.345.678,00 dinara.")
    _, pid = _novi_predmet(k, b)
    d = _prikaci(k, b, pid, "Gust.pdf", ["PRIVREDNI SUD (SINTETICKI)"] + redovi)
    e = _ekstr(d)
    p = _poz(d, "PRIZNANJE")
    assert e["prozora"] == 6 and p > 3 * 3800, p                          # u prozoru ≥ 4
    assert e["cinjenica_izdvojeno"] > 20 and e["cinjenica_odbaceno"] == e["cinjenica_izdvojeno"] - 20
    assert e["cinjenice_potpune"] is False
    assert [t for t in _tvrdnje(b, d["id"]) if "118/26" in t["tvrdnja"]]
    assert len(_tvrdnje(b, d["id"])) == 20


def test_prekinut_odgovor_modela_je_neprocitan_prozor(citac, monkeypatch):
    k, b, poruke = citac
    import routers.evidence as ev
    pravi = ev._pozovi_evidence_api

    def _prekid(client, user_msg):
        r = pravi(client, user_msg)
        if "(deo 2/" in user_msg:
            r.choices[0].finish_reason = "length"
            # i ispravan JSON se odbacuje kad je model prekinut (sadržaj je možda odsečen pre ostalih činjenica)
            r.choices[0].message.content = json.dumps({"tip_dokaza": "podnesak", "kljucne_cinjenice": ["CINJENICA: kasna 08.08.2026."]})
        return r
    monkeypatch.setattr(ev, "_pozovi_evidence_api", _prekid)
    _, pid = _novi_predmet(k, b)
    d = _prikaci(k, b, pid, "Prekid.pdf", _redovi("PODNESAK", 60, ["CINJENICA: kasna 08.08.2026."]))
    e = _ekstr(d)
    assert e["potpuno"] is False and e["neprocitani_prozori"] == [2]
    assert not [t for t in _tvrdnje(b, d["id"]) if "08.08.2026" in t["tvrdnja"]]
