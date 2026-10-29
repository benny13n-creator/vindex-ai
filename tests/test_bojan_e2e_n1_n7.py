# -*- coding: utf-8 -*-
"""Bojan E2E — N1–N7 kao JEDAN tok nad JEDNIM predmetom (Operation Bojan Final Closure, Task 3).

Spaja dva postojeća, nezavisno proverena toka nad istim `solo` okruženjem (stvarne rute, baza u memoriji):
  N1/N2  tests/test_n1_zlatni_prijem.py::_zlatni_tok — klijent, provera sukoba, predmet sa opisom i ciljem, 4 dokumenta
         (digitalni PDF, sken PDF, fotografija PNG, DOCX), STVARAN OCR, ispravka entiteta;
  N3–N7  koraci iz tests/test_n9_integrisani_tok.py — ali nad predmetom iz prijema, ne nad novim.
Sintetički podaci; modeli (klasifikacija, stranke, embedding) simulirani kao u oba izvorna testa; OCR NIJE simuliran.
Datumi su relativni prema `_danas_beograd()` i označeni kao sintetički — ne predstavljaju stvarne procesne rokove.
Nijedan pravi email: `_smtp_send` je zamenjen. Ovo NIJE dokaz produkcione ispravnosti (vidi BOJAN_E2E_ACCEPTANCE.md)."""
import asyncio
import csv
import html as _html
import io
import os
from datetime import timedelta
from unittest.mock import patch

import pytest

from routers.email_notif import _danas_beograd
from tests.test_n1_zlatni_prijem import _OCR, DOKUMENTI, SLIKOVNI, _sadrzaj, _zlatni_tok
from tests.test_n7_azuriranje_predmeta import _prikaci, _sr, lanac  # noqa: F401 — fixture
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401 — fixture

if os.environ.get("VINDEX_REQUIRE_OCR") == "1" and _OCR is None:
    raise RuntimeError("VINDEX_REQUIRE_OCR=1, a Tesseract nije dostupan")
treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — tok traži stvaran OCR skena i fotografije")


def _hron(b, pid, vrsta="rok"):
    return [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and h.get("vrsta", "rok") == vrsta]


@treba_ocr
def test_jedan_predmet_od_prijema_do_azuriranja(lanac):
    k, b = lanac
    t = b.tabele
    for ime in ("billing_entries", "fakture", "timer_sessions", "tarifne_stavke_custom"):
        t.setdefault(ime, [])

    # ── N1/N2: prijem — jedan klijent, jedan predmet, četiri dokumenta, stvaran OCR ──────────────────────────────
    kid, pid, poslovi, ispravka, fin = _zlatni_tok(k, b)
    assert [p["id"] for p in t["predmeti"] if p["user_id"] == "uid-A"] == [pid]
    dok = [d for d in t["predmet_dokumenti"] if d["predmet_id"] == pid]
    assert len(dok) == 4, [d["naziv_fajla"] for d in dok]
    ocr = {d["intake_job_id"]: d for d in t["intake_documents"]}
    assert all(ocr[poslovi[ime]]["ocr_used"] is True for ime in SLIKOVNI)
    # ponovljen pokušaj istog dokumenta: isti posao, bez novog dokumenta i predmeta
    ime0 = next(iter(DOKUMENTI))
    r = k.post("/api/smart-intake/documents", files=[("files", (ime0, _sadrzaj(ime0), DOKUMENTI[ime0][1]))], headers=A)
    assert r.json()["rezultati"][0]["already_submitted"] is True
    assert len([d for d in t["predmet_dokumenti"] if d["predmet_id"] == pid]) == 4
    # „reload“: predmet, opis/cilj i klijent se čitaju iz baze
    g = k.get(f"/api/predmeti/{pid}", headers=A)
    assert g.status_code == 200 and "Cilj:" in (g.json().get("opis") or g.json().get("predmet", {}).get("opis") or ""), g.text
    assert [(v["predmet_id"], v["klijent_id"]) for v in t["predmet_klijenti"]] == [(pid, kid)]
    ent = next(e for e in t["extracted_entities"] if e["id"] == ispravka["entity_id"])
    assert ent["corrected_value"] == ispravka["vrednost"]
    pre_polja = {f: next(p for p in t["predmeti"] if p["id"] == pid).get(f) for f in ("naziv", "opis", "tuzilac", "tuzeni")}

    # ── N7 (1): dokument sa ročištem i rokom ide u ISTI predmet ─────────────────────────────────────────────────────
    rociste = _danas_beograd() + timedelta(days=1)
    rok_ai = _danas_beograd() + timedelta(days=10)
    _, r = _prikaci(k, b, pid, ["OSNOVNI SUD U NOVOM SADU", "Posl. br. P 501/2026 (SINTETICKI)", "RESENJE",
                                f"Pripremno rociste zakazuje se za {_sr(rociste)} godine u 09:30 casova, sudnica 7.",
                                f"Rok za odgovor na tuzbu istice {_sr(rok_ai)} godine."], "05 Poziv.pdf")
    assert r.status_code == 200, r.text
    assert len([d for d in t["predmet_dokumenti"] if d["predmet_id"] == pid]) == 5
    assert [p["id"] for p in t["predmeti"] if p["user_id"] == "uid-A"] == [pid]
    assert [x for x in t.get("rocista", []) if x["predmet_id"] == pid] == []                 # predlog nije ročište

    # ── N3: ročište — predlog → advokat zakazuje; dupli klik = jedno ročište; zastarela izmena odbijena ─────────
    [p] = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"]
    assert p["datum"] == rociste.isoformat() and p["vreme"] == "09:30"
    telo = {"predmet_id": pid, "sud": p["sud"], "datum": p["datum"], "vreme": p["vreme"], "sudnica": p.get("sudnica")}
    r1, r2 = (k.post("/api/rocista", json=telo, headers=A) for _ in range(2))
    assert r1.status_code == r2.status_code == 200 and r1.json()["rociste"]["id"] == r2.json()["rociste"]["id"]
    roc = [x for x in t["rocista"] if x["predmet_id"] == pid]
    assert len(roc) == 1 and roc[0]["status"] == "zakazano"
    kal = k.get("/api/kalendar/pregled", headers=A)
    assert kal.status_code == 200 and p["datum"] in kal.text, kal.text[:300]
    stari = k.patch(f"/api/rocista/{roc[0]['id']}", json={"sudnica": "8", "if_updated_at": "2000-01-01T00:00:00+00:00"}, headers=A)
    assert stari.status_code == 409 and roc[0].get("sudnica") in ("7", None, "sudnica 7")
    assert k.patch(f"/api/rocista/{roc[0]['id']}", json={"status": "otkazano"}, headers=B).status_code == 404

    # ── N4: rok — AI predlog nije obaveza; advokat ispravlja datum; podsetnik samo za potvrđeno ──────────────────
    from shared.rok_potvrda import potvrdjeni_ids
    [ai] = _hron(b, pid)
    assert ai["datum_iso"] == rok_ai.isoformat() and ai.get("izvor") != "HUMAN_DIRECT" and potvrdjeni_ids([ai["id"]]) == set()
    # drugi dokument: AI rok za SUTRA koji advokat NE potvrdi (jedan predlog po dokumentu — shared/intake_extract.py)
    _, r = _prikaci(k, b, pid, ["OBAVESTENJE O TAKSI (SINTETICKI)", f"Rok za uplatu sudske takse istice {_sr(rociste)} godine."],
                    "05b Taksa.pdf")
    assert r.status_code == 200, r.text
    [ai_sutra] = [h for h in _hron(b, pid) if h["id"] != ai["id"]]
    assert ai_sutra["datum_iso"] == rociste.isoformat() and potvrdjeni_ids([ai_sutra["id"]]) == set()
    tacan = (_danas_beograd() + timedelta(days=1)).isoformat()
    assert k.post(f"/api/rokovi/{ai['id']}/ispravi", json={"datum_iso": tacan}, headers=B).status_code == 404
    assert k.post(f"/api/rokovi/{ai['id']}/ispravi", json={"datum_iso": tacan}, headers=A).status_code == 200
    [potvrdjen] = [h for h in _hron(b, pid) if h["id"] not in (ai["id"], ai_sutra["id"])]
    assert potvrdjen["datum_iso"] == tacan and potvrdjeni_ids([potvrdjen["id"]]) == {potvrdjen["id"]}
    assert k.post(f"/api/rokovi/{ai['id']}/potvrdi", json={}, headers=A).status_code == 409   # odbijen predlog ostaje odbijen

    import routers.email_notif as en
    from tests import test_b10_reminder_claim as b10
    poslati = []
    t.setdefault("korisnik_email_notif", []).append({"user_id": "uid-A", "aktivan": True, "dan_1": True, "dan_3": False, "dan_7": False})
    t.setdefault("profiles", []).append({"id": "uid-A", "email": "advokat@example.invalid"})
    t.setdefault("email_notif_log", [])
    with patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), patch.object(en, "_get_supa", return_value=b), \
         patch.object(en, "_smtp_send", lambda to, subj, h: poslati.append((to, subj, h))):
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
        rez2 = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))   # ponovljeno
    assert rez["poslato"] == 1 and rez2["poslato"] == 0 and len(poslati) == 1, (rez, rez2, poslati)
    tekst = _html.unescape(poslati[0][2]).lower()
    assert poslati[0][0] == "advokat@example.invalid" and "09:30" in tekst and "odgovor na tužbu" in tekst
    assert _sr(rok_ai) not in tekst
    rez_dog = {(x["tip"], str(x["dogadjaj_id"])) for x in t.get("email_podsetnik_dogadjaj", [])}
    assert ("rok", potvrdjen["id"]) in rez_dog and ("rociste", roc[0]["id"]) in rez_dog, rez_dog
    assert not {d for _, d in rez_dog} & {ai["id"], ai_sutra["id"]}                     # AI predlozi nikad nisu podsetnik

    # ── N5: naplata — stavka, faktura nacrt → izdata → plaćena; nedozvoljen i zastareo prelaz odbijeni ──────────
    eid = k.post("/billing/entries", json={"predmet_id": pid, "opis": "Priprema ročišta", "iznos_rsd": 6000}, headers=A).json()["entry"]["id"]
    f = k.post("/billing/faktura", json={"predmet_id": pid, "entry_ids": [eid], "klijent_naziv": "Milica Zlatic", "pdv_stopa": 20},
               headers=A).json()["faktura"]
    # baza u memoriji ne primenjuje DEFAULT kolona; šema: `datum_fakture DATE NOT NULL DEFAULT CURRENT_DATE` (migracija 003)
    next(x for x in t["fakture"] if x["id"] == f["id"]).setdefault("datum_fakture", _danas_beograd().isoformat())
    put = f"/billing/faktura/{f['id']}/status"
    assert k.patch(put, json={"status": "placena", "iz_statusa": "nacrt"}, headers=A).status_code == 409   # preskok stanja
    assert k.patch(put, json={"status": "izdata", "iz_statusa": "nacrt"}, headers=A).status_code == 200
    assert k.patch(put, json={"status": "placena", "iz_statusa": "izdata"}, headers=A).status_code == 200
    assert k.patch(put, json={"status": "nacrt", "iz_statusa": "placena"}, headers=A).status_code == 409
    assert k.patch(put, json={"status": "placena", "iz_statusa": "izdata"}, headers=B).status_code == 404
    assert next(x for x in t["fakture"] if x["id"] == f["id"])["status"] == "placena"

    # ── N6: izveštaji — PDF predmeta (tekst), CSV naplate; drugi korisnik nema pristup ───────────────────────────
    pdf = k.get(f"/api/predmeti/{pid}/pdf-export", headers=A)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    import pymupdf
    pt = "\n".join(s.get_text() for s in pymupdf.open(stream=pdf.content, filetype="pdf"))
    assert "Zlatic" in pt and "09:30" in pt, pt[:500]
    assert "[ODBIJENO]" in pt and "[NEPOTVRĐENO] Rok za odgovor" not in pt          # odbijen AI predlog nije obaveza
    assert k.get(f"/api/predmeti/{pid}/pdf-export", headers=B).status_code == 404
    c = k.get("/billing/report/csv", params={"od": _danas_beograd().replace(day=1).isoformat()}, headers=A)
    assert c.status_code == 200
    redovi = list(csv.reader(io.StringIO(c.content.decode("utf-8-sig")), delimiter=";"))
    zaglavlje = redovi[0]
    [moj] = [dict(zip(zaglavlje, rr)) for rr in redovi[1:] if "Priprema ročišta" in rr]
    assert moj["Predmet"] == "Zlatic protiv Zlatna Linija — otkaz" and moj["Status fakture"] == "plaćena", moj
    # „Klijent“ je u CSV-u prazan PO ODLUCI (routers/billing_reports.py: stavka nema klijent_id; nema izmišljenog pravila)
    assert moj["Klijent"] == ""
    cb = k.get("/billing/report/csv", params={"od": _danas_beograd().replace(day=1).isoformat()}, headers=B)
    assert cb.status_code == 200 and "Priprema ročišta" not in cb.content.decode("utf-8-sig")

    # ── N7 (2): dopuna — nov dokument sa novim rokom ne dira potvrđen rok, ispravku ni polja predmeta ───────────
    rok2 = _danas_beograd() + timedelta(days=20)
    _, r = _prikaci(k, b, pid, ["DOPUNA PODNESKA (SINTETICKI)", f"Rok za dostavljanje dokaza istice {_sr(rok2)} godine."], "06 Dopuna.pdf")
    assert r.status_code == 200, r.text
    assert [p["id"] for p in t["predmeti"] if p["user_id"] == "uid-A"] == [pid]
    assert len([d for d in t["predmet_dokumenti"] if d["predmet_id"] == pid]) == 7
    assert potvrdjeni_ids([potvrdjen["id"]]) == {potvrdjen["id"]}                     # ljudska odluka ostaje
    novi = [h for h in _hron(b, pid) if h["datum_iso"] == rok2.isoformat()]
    assert len(novi) == 1 and potvrdjeni_ids([novi[0]["id"]]) == set()                # nov AI rok = predlog
    assert {f: next(p for p in t["predmeti"] if p["id"] == pid).get(f) for f in pre_polja} == pre_polja
    assert next(e for e in t["extracted_entities"] if e["id"] == ispravka["entity_id"])["corrected_value"] == ispravka["vrednost"]
    assert len([x for x in t["rocista"] if x["predmet_id"] == pid]) == 1

    # ── izolacija: korisnik B ne vidi ništa od predmeta A ────────────────────────────────────────────────────────
    for ruta in (f"/api/predmeti/{pid}", f"/api/rocista/predlozi?predmet_id={pid}", f"/api/case-actions/predmeti/{pid}",
                 f"/api/predmeti/{pid}/genome-v2"):
        assert k.get(ruta, headers=B).status_code == 404, ruta
    assert "Zlatic" not in k.get("/api/kalendar/pregled", headers=B).text
