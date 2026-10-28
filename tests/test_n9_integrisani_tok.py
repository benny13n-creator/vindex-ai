# -*- coding: utf-8 -*-
"""N9 deo D — jedan predmet kroz ceo Bojanov tok N2–N9, stvarnim rutama nad bazom u memoriji (solo okruženje,
modeli/embedding simulirani — dokazuje ugovor i stanja, NE živu integraciju):
klijent + provera sukoba (N2) → predmet → dokument sa ročištem i rokom (N7) → ročište je PREDLOG pa ga advokat
zakazuje (N3) → AI rok je PREDLOG, advokat ga ispravlja (N4) → podsetnik ide za zakazano ročište i ISPRAVLJEN rok, nikad
za AI predlog (N4) → evidencija rada i faktura izdata→plaćena (N5) → PDF predmeta i mesečni izveštaj (N6) →
pravna pitanja: nadležnost (N8) i višestruki povrat (N9) kroz determinističke slojeve. Nijedan pravi email se ne šalje."""
import asyncio
import re
from datetime import timedelta
from unittest.mock import patch

from routers.email_notif import _danas_beograd
from tests.test_n7_azuriranje_predmeta import _prikaci, _sr, lanac  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401


def test_jedan_predmet_kroz_ceo_tok(lanac):
    k, b = lanac
    for t in ("billing_entries", "fakture", "timer_sessions", "tarifne_stavke_custom"):
        b.tabele.setdefault(t, [])

    # N2: klijent i provera sukoba pre otvaranja predmeta
    kid = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": "Jovana", "prezime": "Ristic"}, headers=A).json()["klijent"]["id"]
    coi = k.post("/api/conflict-check", json={"ime_prezime": "Gradnja Sever DOO"}, headers=A)
    assert coi.status_code == 200 and [x for x in coi.json()["konflikti"] if x.get("sloj") == "predmeti"] == []
    pid = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "Ristic protiv Gradnja Sever", "opis": "Naknada štete"},
                 headers=A).json()["predmet_id"]

    # N7: dokument sa ročištem i rokom ažurira TAJ predmet
    rociste = _danas_beograd() + timedelta(days=1)
    rok_ai = _danas_beograd() + timedelta(days=10)
    _, r = _prikaci(k, b, pid, ["OSNOVNI SUD U NOVOM SADU", "Posl. br. P 501/2026", "RESENJE",
                                f"Pripremno rociste zakazuje se za {_sr(rociste)} godine u 09:30 casova, sudnica 7.",
                                f"Rok za odgovor na tuzbu istice {_sr(rok_ai)} godine."], "Poziv.pdf")
    assert r.status_code == 200, r.text
    assert [x for x in b.tabele.get("rocista", []) if x["predmet_id"] == pid] == []          # ništa nije zakazano samo

    # N3: predlog ročišta → advokat zakazuje
    p = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"]
    assert len(p) == 1 and p[0]["datum"] == rociste.isoformat() and p[0]["vreme"] == "09:30"
    assert k.post("/api/rocista", json={"predmet_id": pid, "sud": p[0]["sud"], "datum": p[0]["datum"], "vreme": p[0]["vreme"],
                                        "sudnica": p[0].get("sudnica")}, headers=A).status_code == 200
    assert k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"] == []

    # N4: AI rok je predlog; advokat ispravlja datum (ispravka je potvrđena, predlog odbijen)
    ai = [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and h.get("vrsta") == "rok"]
    assert len(ai) == 1 and ai[0].get("izvor") != "HUMAN_DIRECT", ai
    tacan = (_danas_beograd() + timedelta(days=1)).isoformat()
    ispr = k.post(f"/api/rokovi/{ai[0]['id']}/ispravi", json={"datum_iso": tacan}, headers=A)
    assert ispr.status_code == 200, ispr.text
    novi = [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and h.get("vrsta", "rok") == "rok" and h["id"] != ai[0]["id"]]
    assert [h["datum_iso"] for h in novi] == [tacan]

    # N4: podsetnik — zakazano ročište i ispravljen (potvrđen) rok za sutra; AI predlog nikad
    import routers.email_notif as en
    from shared.rok_potvrda import potvrdjeni_ids
    poslati = []
    b.tabele.setdefault("korisnik_email_notif", []).append({"user_id": "uid-A", "aktivan": True, "dan_1": True, "dan_3": False, "dan_7": False})
    b.tabele.setdefault("profiles", []).append({"id": "uid-A", "email": "advokat@example.invalid"})
    b.tabele.setdefault("email_notif_log", [])
    with patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), patch.object(en, "_get_supa", return_value=b), \
         patch.object(en, "_smtp_send", lambda to, subj, html: poslati.append((to, subj, html))):
        from tests import test_b10_reminder_claim as b10
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    assert potvrdjeni_ids([novi[0]["id"]]) == {novi[0]["id"]} and potvrdjeni_ids([ai[0]["id"]]) == set()
    assert rez["poslato"] == 1 and len(poslati) == 1, (rez, poslati)
    import html as _html
    telo = _html.unescape(poslati[0][2]).lower()
    assert poslati[0][1] == "Vindex AI — Sutra: rok i ročište"
    assert "ročište — osnovni sud u novom sadu, sudnica 7" in telo and "odgovor na tužbu" in telo and "09:30" in telo

    # N5: rad i faktura izdata → plaćena
    eid = k.post("/billing/entries", json={"predmet_id": pid, "opis": "Priprema ročišta", "iznos_rsd": 6000}, headers=A).json()["entry"]["id"]
    f = k.post("/billing/faktura", json={"predmet_id": pid, "entry_ids": [eid], "klijent_naziv": "Jovana Ristic", "pdv_stopa": 20},
               headers=A).json()["faktura"]
    # baza u memoriji ne primenjuje DEFAULT kolona; šema: `datum_fakture DATE NOT NULL DEFAULT CURRENT_DATE` (migracija 003)
    next(x for x in b.tabele["fakture"] if x["id"] == f["id"]).setdefault("datum_fakture", _danas_beograd().isoformat())
    put = f"/billing/faktura/{f['id']}/status"
    assert k.patch(put, json={"status": "izdata", "iz_statusa": "nacrt"}, headers=A).status_code == 200
    assert k.patch(put, json={"status": "placena", "iz_statusa": "izdata"}, headers=A).status_code == 200
    assert k.patch(put, json={"status": "placena", "iz_statusa": "izdata"}, headers=A).status_code == 409   # zastareo prikaz

    # N6: PDF predmeta i mesečni izveštaj
    pdf = k.get(f"/api/predmeti/{pid}/pdf-export", headers=A)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert k.get(f"/api/predmeti/{pid}/pdf-export", headers=B).status_code == 404
    mes = k.get("/billing/report/mesecni", params={"mesec": _danas_beograd().strftime("%Y-%m")}, headers=A)
    assert mes.status_code == 200, mes.text
    d = mes.json()
    assert d["naplaceno_rsd"] == 7200.0, d                                   # 6000 + 20% PDV, plaćena
    sled = {x["id"]: x["stanje_odluke"] for x in d["sledecih_14_dana"]}
    assert sled.get(novi[0]["id"]) == "CONFIRMED" and sled.get(ai[0]["id"]) is None   # odbijen AI predlog nije obaveza

    # N8/N9: pravna pitanja kroz determinističke slojeve (model se ovde ne poziva)
    import main as M
    t = M._napomene_nadleznosti("Tužimo dva tužena solidarno, jedan iz Sombora, drugi iz Leskovca. Kom sudu podnosimo tužbu?", "")
    assert "ZPP čl. 42" in t
    v = M._dodaj_proracun_povrata(
        "Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, otpušten je pre tri godine, "
        "a sada je sa umišljajem izvršio krađu za koju je propisan zatvor od jedne do osam godina. Ranija dela su istovrsna "
        "sa novim. Koji je raspon kazne?",
        {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nx"})
    assert re.search(r"više od 4 godine i 6 meseci, najviše 8 godina", v["data"]) and v["proracun_povrata"] == "DA"
