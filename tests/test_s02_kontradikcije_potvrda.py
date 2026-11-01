# -*- coding: utf-8 -*-
"""S02 / B7 — odluka osnivača A (2026-10-31): AI protivrečnost je KANDIDAT za pregled advokata, ne potvrđena
protivrečnost. Aktivna je i nosi akciju „Razrešiti kontradikciju“ tek posle izričite potvrde ovlašćenog advokata
(vlasnik predmeta); odbijeni kandidat izlazi iz aktivnih tokova i ostaje u istoriji (audit + `RESOLVED`/`WITHDRAWN`).

Produkcioni slučaj (sintetički predmet, 2026-10-31): dva roka za DVE RAZLIČITE takse Genome je upisao kao aktivnu
protivrečnost sa akcijom. Sada je to kandidat: vidljiv, sa oba izvora, označen kao nepotvrđen, bez akcije.

Stvarno: prijem PDF-ova, Evidence Vault, Genome osvežavanje kroz dispečer, V2 paket, Case Actions, `genome-v2`,
ruta odluke, audit, događaj posle odluke. Zamenjeno: modeli (tvrdnje = redovi teksta; Genome vraća protivrečnosti iz
SPECIFIKACIJE nad STVARNIM oznakama iz prompta). Bez leksičkih pravila istovetnosti i bez AI sudije.
"""
import copy
import json
import re

import pytest

from tests import ns006_realni_predmet as rp
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, _pdf, _prijem_dokumenta, solo  # noqa: F401

DOKUMENTI = {
    "Resenje.pdf": ["RESENJE", "Broj predmeta: P 6101/2026",
                    "Rok za uplatu sudske takse istice 04.12.2026. godine.",
                    "Resenje o otkazu je uruceno tuziocu 17.03.2025. godine.",
                    "Tuzeni je primio robu 01.02.2026. godine.",
                    "Potrazivanje tuzioca iznosi 1.000.000,00 dinara.",
                    "Tuzilac tvrdi da je zakup placen u celosti."],
    "Nalog.pdf": ["NALOG", "Broj predmeta: P 6101/2026",
                  "Rok za uplatu dodatne sudske takse istice 27.11.2026. godine.",
                  "Posiljka je urucena primaocu 25.03.2025. godine.",
                  "Tuzeni nije primio robu 01.02.2026. godine.",
                  "Potrazivanje tuzioca iznosi 1.200.000,00 dinara.",
                  "Tuzeni tvrdi da zakup nije placen."],
}
# (labela, deo tvrdnje A, deo tvrdnje B): šta model tvrdi da je protivrečno — i lažno (takse) i stvarno.
TAKSE = ("Razlika u rokovima za uplatu takse", "Rok za uplatu sudske takse istice 04.12", "Rok za uplatu dodatne sudske takse")
URUCENJE = ("Datum urucenja resenja", "uruceno tuziocu 17.03", "urucena primaocu 25.03")
NEGACIJA = ("Prijem robe", "Tuzeni je primio robu", "Tuzeni nije primio robu")
IZNOS = ("Visina potrazivanja", "iznosi 1.000.000", "iznosi 1.200.000")
STRANKE = ("Placanje zakupa", "Tuzilac tvrdi da je zakup", "Tuzeni tvrdi da zakup")
SVE = [TAKSE, URUCENJE, NEGACIJA, IZNOS, STRANKE]


def _klasifikuj(naziv, tekst):
    redovi = [l.strip() for l in tekst.splitlines() if l.strip() and not l.strip().isupper() and not l.startswith("Broj predmeta")]
    return {"tip_dokaza": "dopis", "pravni_elementi": [], "ai_tags": {}, "kljucne_cinjenice": redovi}


def _genome_model(specifikacija, pozivi):
    async def _pozovi(client, combined, n):
        pozivi.append(combined)
        dok = {ime: oz for oz, ime in re.findall(r"\[(DOK-\d+): ([^\]|]+?)(?: \||\])", combined)}
        claim = dict(re.findall(r"(CLAIM-\d+): ([^\n]+)", combined))
        g = copy.deepcopy(rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["datumi_kljucni"], g["rokovi_kriticni"], g["kontradikcije"] = [], [], []

        def _gde(deo):
            return next((dok.get(ime) for ime, redovi in DOKUMENTI.items() if any(deo in r for r in redovi)), "")
        for labela, a, b in specifikacija:
            ca = [c for c, t in claim.items() if a in t]
            cb = [c for c, t in claim.items() if b in t]
            if ca and cb:
                g["kontradikcije"].append({"issue_label": labela, "claim_refs": [ca[0], cb[0]], "relation_type": "cinjenica_cinjenica",
                                           "opis": f"{a} / {b}", "lokacija_1": _gde(a), "lokacija_2": _gde(b), "tezina": "vazna"})
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


@pytest.fixture
def predmet(solo, monkeypatch):
    k, b = solo
    import routers.case_dna as cd
    import routers.evidence as ev
    import shared.audit_immutable as audit
    from api import _get_supa
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _klasifikuj)
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome_model(SVE, b.genome_pozivi))
    b.audit_ispad = False

    async def _log(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        if b.audit_ispad:
            return None
        r = _get_supa().table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                                       "resource_id": resource_id, "metadata": metadata or {}}).execute()
        return (r.data or [{}])[0].get("id") or "ok"
    monkeypatch.setattr(audit, "log_action", _log)
    p = k.post("/api/predmeti", json={"naziv": "S02 potvrda", "tip": "Parnica"}, headers=A)
    assert p.status_code == 200, p.text
    pid = p.json()["predmet"]["id"]
    for ime, redovi in DOKUMENTI.items():
        _, fin = _prijem_dokumenta(k, b, pid, sadrzaj=_pdf(redovi), ime=ime)
        assert fin["dokumenata_povezano"] == 1, fin
        _do_kraja_dogadjaja(b, najvise=10)
    return k, b, pid


def _kon(k, pid, h=A):
    g = k.get(f"/api/predmeti/{pid}/genome-v2", headers=h)
    assert g.status_code == 200, g.text
    return g.json()["kontradikcije"]


def _po_labeli(lista):
    return {x["sporna_tacka"]: x for x in lista}


def _akcije(b, pid):
    return sorted(a.get("razlog") for a in b.tabele["case_actions"]
                  if a["predmet_id"] == pid and a.get("tip") == "RAZRESITI_KONTRADIKCIJU" and a.get("status") == "open")


def _audit(b, akcija):
    return [r for r in b.tabele["audit_immutable"] if r.get("action") == akcija]


def _odluka(k, pid, kandidat, radnja, h=A):
    """Kao UI: šalje stanje i verziju sadržaja koje ekran TRENUTNO prikazuje za tu spornu tačku (sveže čitanje)."""
    iid = kandidat["odluka"]["issue_id"]
    kon = _kon(k, pid)
    o = next(x["odluka"] for x in kon["aktivne"] + kon["za_pregled"] + kon["zatvorene"]
             if x.get("odluka") and x["odluka"]["issue_id"] == iid)
    telo = {"ocekivano": {"status": o["status"], "odluka_at": o["odluka_at"], "sadrzaj": o["sadrzaj"]}}
    return k.post(f"/api/predmeti/{pid}/sporne-tacke/{iid}/{radnja}", json=telo, headers=h)


def test_svaki_kandidat_je_vidljiv_sa_izvorima_nepotvrdjen_i_bez_akcije(predmet):
    k, b, pid = predmet
    kon = _kon(k, pid)
    assert kon["aktivne"] == []                                                    # nijedna AI protivrečnost nije potvrđena sama
    pr = _po_labeli(kon["za_pregled"])
    assert set(pr) == {x[0] for x in SVE}                                          # negacija, iznos, datum, stranke, takse — sve vidljive
    for x in pr.values():
        assert x["stanje"] == "NEPOTVRDJENA" and x["odluka"]["status"] == "DISCOVERED", x
        assert len(x["ucesnici"]) == 2 and all(u["tvrdnja"] and u["dokument_id"] for u in x["ucesnici"]), x
        assert len(set(x["dokumenti"])) == 2                                       # oba izvora
    assert _akcije(b, pid) == []                                                   # nijedna radnja za nepotvrđeno
    assert {i["status"] for i in b.tabele["predmet_issues"] if i["predmet_id"] == pid} == {"DISCOVERED"}
    assert kon["sazetak"]["aktivnih"] == 0 and kon["sazetak"]["za_pregled"] == len(SVE)


def test_potvrda_aktivira_odbijanje_iskljucuje_i_oba_ostaju_u_istoriji(predmet):
    k, b, pid = predmet
    pr = _po_labeli(_kon(k, pid)["za_pregled"])
    stanja_kontradikcija = {c["id"]: c["state"] for c in b.tabele["predmet_contradictions"]}

    r = _odluka(k, pid, pr[URUCENJE[0]], "potvrdi")
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED" and r.json()["promenjeno"] is True, r.text
    r = _odluka(k, pid, pr[TAKSE[0]], "odbij")
    assert r.status_code == 200 and r.json()["status"] == "RESOLVED", r.text
    _do_kraja_dogadjaja(b, najvise=10)                                              # događaj posle odluke usklađuje akcije

    kon = _kon(k, pid)
    assert [x["sporna_tacka"] for x in kon["aktivne"]] == [URUCENJE[0]] and kon["aktivne"][0]["stanje"] == "AKTIVNA"
    assert TAKSE[0] not in _po_labeli(kon["za_pregled"])
    zat = _po_labeli(kon["zatvorene"])
    assert zat[TAKSE[0]]["stanje"] == "ODBIJENA" and zat[TAKSE[0]]["odluka"]["vazi"] == "ODBIJENA"   # nudi „Ipak potvrdi“
    assert _akcije(b, pid) == [URUCENJE[0]]                                         # radnja samo za potvrđenu
    iss = {i["label"]: i for i in b.tabele["predmet_issues"] if i["predmet_id"] == pid}
    assert iss[URUCENJE[0]]["status"] == "CONFIRMED"
    assert iss[TAKSE[0]]["status"] == "RESOLVED" and iss[TAKSE[0]]["close_reason"] == "WITHDRAWN" and iss[TAKSE[0]]["closed_at"]
    assert {c["id"]: c["state"] for c in b.tabele["predmet_contradictions"]} == stanja_kontradikcija   # opažanje netaknuto
    [p] = _audit(b, "sporna_tacka_potvrdjena")
    [o] = _audit(b, "sporna_tacka_odbijena")
    assert p["user_id"] == "uid-A" and p["resource_id"] == iss[URUCENJE[0]]["id"] and p["metadata"]["prethodni_status"] == "DISCOVERED"
    assert o["resource_id"] == iss[TAKSE[0]]["id"] and o["metadata"]["novi_status"] == "RESOLVED"
    assert {e["payload"].get("odluka") for e in b.tabele["events"] if e["event_type"] == "ManualCorrectionApplied"} \
        == {"potvrda_sporne_tacke", "odbijanje_sporne_tacke"}


def test_osvezavanje_ne_vraca_odbijenu_ne_gasi_potvrdjenu_i_ne_duplira(predmet):
    k, b, pid = predmet
    pr = _po_labeli(_kon(k, pid)["za_pregled"])
    assert _odluka(k, pid, pr[URUCENJE[0]], "potvrdi").status_code == 200
    assert _odluka(k, pid, pr[TAKSE[0]], "odbij").status_code == 200
    _do_kraja_dogadjaja(b, najvise=10)
    pre = _kon(k, pid)
    issues_pre = {i["id"]: (i["status"], i.get("close_reason")) for i in b.tabele["predmet_issues"] if i["predmet_id"] == pid}
    assert k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A).status_code in (200, 202)
    _do_kraja_dogadjaja(b, najvise=10)
    posle = _kon(k, pid)
    assert [x["id"] for x in posle["aktivne"]] == [x["id"] for x in pre["aktivne"]]            # ista potvrđena tačka
    assert TAKSE[0] not in _po_labeli(posle["za_pregled"]) and TAKSE[0] not in _po_labeli(posle["aktivne"])
    assert _po_labeli(posle["zatvorene"])[TAKSE[0]]["stanje"] == "ODBIJENA"
    assert {i["id"]: (i["status"], i.get("close_reason")) for i in b.tabele["predmet_issues"] if i["predmet_id"] == pid} == issues_pre
    assert _akcije(b, pid) == [URUCENJE[0]]


def test_odluka_se_menja_samo_izricito_uz_audit_a_ponavljanje_ne_pise_dvaput(predmet):
    k, b, pid = predmet
    pr = _po_labeli(_kon(k, pid)["za_pregled"])
    assert _odluka(k, pid, pr[NEGACIJA[0]], "potvrdi").status_code == 200
    r = _odluka(k, pid, pr[NEGACIJA[0]], "potvrdi")                                 # ponovljen klik / retry
    assert r.status_code == 200 and r.json()["promenjeno"] is False
    assert len(_audit(b, "sporna_tacka_potvrdjena")) == 1
    r = _odluka(k, pid, pr[NEGACIJA[0]], "odbij")                                   # promena odluke (pogrešan klik)
    assert r.status_code == 200 and r.json()["status"] == "RESOLVED"
    [o] = _audit(b, "sporna_tacka_odbijena")
    assert o["metadata"]["prethodni_status"] == "CONFIRMED" and o["metadata"]["prethodno_vazi"] == "POTVRDJENA"
    assert _odluka(k, pid, pr[NEGACIJA[0]], "potvrdi").status_code == 200           # i nazad — svaki put nov zapis
    assert len(_audit(b, "sporna_tacka_potvrdjena")) == 2
    assert _po_labeli(_kon(k, pid)["aktivne"])[NEGACIJA[0]]["stanje"] == "AKTIVNA"


def test_zastareo_prozor_ne_menja_tudju_noviju_odluku(predmet):
    """Advokat šalje stanje koje je VIDEO; ako ga je druga sesija u međuvremenu promenila — 409, ništa se ne beleži."""
    k, b, pid = predmet
    kandidat = _po_labeli(_kon(k, pid)["za_pregled"])[IZNOS[0]]
    iid = kandidat["odluka"]["issue_id"]
    vidjeno = {"status": kandidat["odluka"]["status"], "odluka_at": kandidat["odluka"]["odluka_at"],
               "sadrzaj": kandidat["odluka"]["sadrzaj"]}                              # sadržaj se NE menja — samo odluka
    assert _odluka(k, pid, kandidat, "potvrdi").status_code == 200                  # druga sesija potvrdi
    r = k.post(f"/api/predmeti/{pid}/sporne-tacke/{iid}/odbij", json={"ocekivano": vidjeno}, headers=A)
    assert r.status_code == 409, r.text
    assert next(i for i in b.tabele["predmet_issues"] if i["id"] == iid)["status"] == "CONFIRMED"
    assert _audit(b, "sporna_tacka_odbijena") == []


def test_tudji_korisnik_i_neprijavljen_ne_mogu_da_odluce(predmet):
    k, b, pid = predmet
    kandidat = _po_labeli(_kon(k, pid)["za_pregled"])[TAKSE[0]]
    issue_id = kandidat["odluka"]["issue_id"]
    pb = k.post("/api/predmeti", json={"naziv": "B predmet", "tip": "Parnica"}, headers=B).json()["predmet"]["id"]
    for put, h in ((f"/api/predmeti/{pid}/sporne-tacke/{issue_id}/potvrdi", B),           # tuđ predmet
                   (f"/api/predmeti/{pb}/sporne-tacke/{issue_id}/potvrdi", B),            # sopstven predmet, tuđa tačka
                   (f"/api/predmeti/{pid}/sporne-tacke/{issue_id}/odbij", B)):
        assert k.post(put, headers=h).status_code == 404, put
    assert k.post(f"/api/predmeti/{pid}/sporne-tacke/{issue_id}/potvrdi").status_code in (401, 403)
    assert k.get(f"/api/predmeti/{pid}/genome-v2", headers=B).status_code == 404
    assert {i["status"] for i in b.tabele["predmet_issues"] if i["predmet_id"] == pid} == {"DISCOVERED"}
    assert _audit(b, "sporna_tacka_potvrdjena") == [] and _audit(b, "sporna_tacka_odbijena") == []


def test_zastareo_prikaz_ne_pregazi_odluku_druge_sesije(predmet, monkeypatch):
    """Čitanje vidi DISCOVERED, a druga sesija je u međuvremenu potvrdila: uslovni upis (status = viđeni) ne prolazi."""
    k, b, pid = predmet
    kandidat = _po_labeli(_kon(k, pid)["za_pregled"])[URUCENJE[0]]
    iid = kandidat["odluka"]["issue_id"]
    import routers.sporna_tacka as st
    pravo = st._sporna_tacka

    def _zastarelo(supa, predmet_id, issue_id, uid):
        red = pravo(supa, predmet_id, issue_id, uid)
        next(i for i in b.tabele["predmet_issues"] if i["id"] == iid)["status"] = "CONFIRMED"   # druga sesija, posle čitanja
        return red
    monkeypatch.setattr(st, "_sporna_tacka", _zastarelo)
    assert _odluka(k, pid, kandidat, "odbij").status_code == 409
    assert next(i for i in b.tabele["predmet_issues"] if i["id"] == iid)["status"] == "CONFIRMED"
    assert _audit(b, "sporna_tacka_odbijena") == []


def test_bez_zapisa_odluke_nema_odluke(predmet):
    k, b, pid = predmet
    kandidat = _po_labeli(_kon(k, pid)["za_pregled"])[URUCENJE[0]]
    b.audit_ispad = True
    assert _odluka(k, pid, kandidat, "potvrdi").status_code == 503
    b.audit_ispad = False
    assert next(i for i in b.tabele["predmet_issues"] if i["id"] == kandidat["odluka"]["issue_id"])["status"] == "DISCOVERED"
    assert _kon(k, pid)["aktivne"] == []


def test_kontekst_pitanja_kaze_nepotvrdjeno_i_izostavlja_odbijeno():
    from shared.genome_contract import kontekst_tvrdnji
    dokazi = [{"id": "a", "tvrdnja": "A", "dokument_id": "d1", "nacin_pronalaska": "egzaktan", "izvor_tvrdnje": "ai_klasifikacija"},
              {"id": "b", "tvrdnja": "B", "dokument_id": "d2", "nacin_pronalaska": "egzaktan", "izvor_tvrdnje": "ai_klasifikacija"},
              {"id": "c", "tvrdnja": "C", "dokument_id": "d2", "nacin_pronalaska": "egzaktan", "izvor_tvrdnje": "ai_klasifikacija"}]
    t0, t1 = "2026-10-31T10:00:00+00:00", "2026-10-31T11:00:00+00:00"           # opažanje, pa odluka advokata
    kon = [{"state": "OPEN", "issue_status": "DISCOVERED", "issue_label": "Kandidat", "claim_ids": ["a", "b"], "created_at": t0},
           {"state": "OPEN", "issue_status": "RESOLVED", "issue_close_reason": "WITHDRAWN", "issue_label": "Odbijena",
            "claim_ids": ["b", "c"], "created_at": t0, "clanovi_od": [t0, t0], "issue_odluka_at": t1},
           {"state": "OPEN", "issue_status": "CONFIRMED", "issue_label": "Potvrdjena", "claim_ids": ["a", "c"],
            "created_at": t0, "clanovi_od": [t0, t0], "issue_odluka_at": t1}]
    t = kontekst_tvrdnji(dokazi, kon)
    assert "Kandidat (nepotvrđena — analiza je predlaže, advokat je nije potvrdio" in t
    assert "Potvrdjena (aktivna, potvrdio advokat" in t
    assert "Odbijena" not in t


def test_protivrecnost_iz_analize_bez_tvrdnji_je_samo_za_pregled():
    """Legacy: analiza navodi protivrečnost koja nije vezana za tvrdnje (nema V2) — ne može se potvrditi, pa nije aktivna."""
    from shared.genome_contract import sastavi_kontradikcije
    kon = sastavi_kontradikcije(v2=[], case_dna={"kontradikcije": [{"issue_label": "Razlika", "opis": "x", "lokacija_1": "DOK-01",
                                                                     "lokacija_2": "DOK-02", "relation_type": "cinjenica_cinjenica"}]},
                                dokazi=[], dokumenti=[])
    assert kon["aktivne"] == [] and [x["stanje"] for x in kon["za_pregled"]] == ["NEPOTVRDJENA_TVRDNJAMA"]
    assert kon["za_pregled"][0].get("odluka") is None


# ── Nalazi nezavisnog pregleda (S02, krug 1) ─────────────────────────────────────────────────────────────────────
def test_odbijene_se_ne_vracaju_kad_je_sve_odluceno(predmet):
    """H1: posle odbijanja SVIH kandidata, protivrečnosti iz analize se ne vraćaju kao „čekaju odluku“."""
    k, b, pid = predmet
    for x in _kon(k, pid)["za_pregled"]:
        assert _odluka(k, pid, x, "odbij").status_code == 200
    _do_kraja_dogadjaja(b, najvise=10)
    kon = _kon(k, pid)
    assert kon["aktivne"] == [] and kon["za_pregled"] == []
    assert {x["stanje"] for x in kon["zatvorene"]} == {"ODBIJENA"} and len(kon["zatvorene"]) == len(SVE)
    assert kon["sazetak"]["za_pregled"] == 0 and _akcije(b, pid) == []


def test_ai_kontekst_izostavlja_odbijene_i_oznacava_nepotvrdjene(predmet):
    """H2: kanonski kontekst predmeta (sudska prognoza, priprema ročišta, CIO, copilot) ne dobija odbijenu protivrečnost
    kao činjenicu predmeta; nepotvrđena je označena; potvrđena je bez oznake."""
    import asyncio
    from api import _get_supa
    from shared.case_context import build_case_context
    k, b, pid = predmet
    pr = _po_labeli(_kon(k, pid)["za_pregled"])
    assert _odluka(k, pid, pr[TAKSE[0]], "odbij").status_code == 200
    assert _odluka(k, pid, pr[URUCENJE[0]], "potvrdi").status_code == 200
    ctx = asyncio.run(build_case_context(pid, "uid-A", _get_supa(), include_documents=False))
    razlozi = [g["razlog"] for g in ctx["contradictions"]["value"]]
    assert razlozi and not any("dodatne sudske takse" in r for r in razlozi)                  # odbijena izostavljena
    potvrdjena = [r for r in razlozi if "uruceno tuziocu" in r]
    assert len(potvrdjena) == 1 and not potvrdjena[0].startswith("[")                         # potvrđena bez oznake
    ostale = [r for r in razlozi if "uruceno tuziocu" not in r]
    assert ostale and all(r.startswith("[nepotvrđena — predlog analize") for r in ostale)


def test_nov_sadrzaj_posle_odluke_trazi_novu_odluku(predmet):
    """M1: potvrda (ili odbijanje) važi za sadržaj koji je advokat video. Tvrdnja dodata spornoj tački posle odluke
    → ponovo kandidat, bez radnje, sa objašnjenjem; nova potvrda je ponovo aktivira."""
    import datetime as dt
    k, b, pid = predmet
    pr = _po_labeli(_kon(k, pid)["za_pregled"])
    assert _odluka(k, pid, pr[URUCENJE[0]], "potvrdi").status_code == 200
    _do_kraja_dogadjaja(b, najvise=10)
    assert _akcije(b, pid) == [URUCENJE[0]]
    kid = _po_labeli(_kon(k, pid)["aktivne"])[URUCENJE[0]]["id"]
    treca = next(d["id"] for d in b.tabele["predmet_dokazi"] if d["predmet_id"] == pid and "1.200.000" in d["tvrdnja"])
    odluka_at = next(i for i in b.tabele["predmet_issues"] if i["label"] == URUCENJE[0])["updated_at"].split("#")[0]
    kasnije = (dt.datetime.fromisoformat(odluka_at) + dt.timedelta(milliseconds=1)).isoformat()   # nastavak opažanja (RPC) posle odluke
    b.tabele["predmet_contradiction_claims"].append({"id": "novi-clan", "contradiction_id": kid, "dokaz_id": treca,
                                                     "removed_at": None, "observed_at": kasnije})
    kon = _kon(k, pid)
    x = _po_labeli(kon["za_pregled"])[URUCENJE[0]]
    assert URUCENJE[0] not in _po_labeli(kon["aktivne"]) and x["stanje"] == "NEPOTVRDJENA"
    assert "ranija odluka ne važi za nov sadržaj" in x["napomena"] and x["odluka"]["vazi"] == "CEKA_ODLUKU"
    assert _odluka(k, pid, pr[TAKSE[0]], "odbij").status_code == 200                           # događaj → usklađivanje radnji
    _do_kraja_dogadjaja(b, najvise=10)
    assert _akcije(b, pid) == []                                                               # bez radnje dok ne odluči
    r = _odluka(k, pid, x, "potvrdi")
    assert r.status_code == 200 and r.json()["promenjeno"] is True                              # ista tačka, nova potvrda
    assert _po_labeli(_kon(k, pid)["aktivne"])[URUCENJE[0]]["stanje"] == "AKTIVNA"


def test_radnja_se_zatvara_sa_istinitim_razlogom(predmet):
    """M3: radnja potvrđene protivrečnosti koju advokat potom odbije zatvara se razlogom „odbijena“, ne „činjenica više
    ne važi“; postojeća radnja za protivrečnost koja nikad nije potvrđena (stanje produkcije pre S02) — „nije potvrđena“."""
    k, b, pid = predmet
    pr = _po_labeli(_kon(k, pid)["za_pregled"])
    assert _odluka(k, pid, pr[URUCENJE[0]], "potvrdi").status_code == 200
    _do_kraja_dogadjaja(b, najvise=10)
    assert _odluka(k, pid, _po_labeli(_kon(k, pid)["aktivne"])[URUCENJE[0]], "odbij").status_code == 200
    _do_kraja_dogadjaja(b, najvise=10)
    zatvorena = [a for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a.get("tip") == "RAZRESITI_KONTRADIKCIJU"]
    assert len(zatvorena) == 1 and zatvorena[0]["status"] == "closed"
    assert zatvorena[0]["dokaz"]["zatvaranje"]["razlog"] == "PROTIVRECNOST_ODBIJENA"
    # stanje produkcije pre S02: otvorena V2 radnja za kandidata koji nikad nije potvrđen
    kand = _po_labeli(_kon(k, pid)["za_pregled"])[IZNOS[0]]
    from services.v2_projection import projekcioni_kljuc
    b.tabele["case_actions"].append({"id": "stara-radnja", "predmet_id": pid, "user_id": "uid-A", "tip": "RAZRESITI_KONTRADIKCIJU",
                                     "status": "open", "dedupe_key": projekcioni_kljuc(kand["id"]), "razlog": IZNOS[0],
                                     "dokaz": {"source_type": "v2_contradiction", "source_id": kand["id"]}, "prioritet": "high",
                                     "created_at": "2026-10-30T10:00:00+00:00", "updated_at": "2026-10-30T10:00:00+00:00"})
    assert _odluka(k, pid, _po_labeli(_kon(k, pid)["za_pregled"])[NEGACIJA[0]], "potvrdi").status_code == 200   # događaj
    _do_kraja_dogadjaja(b, najvise=10)
    stara = next(a for a in b.tabele["case_actions"] if a["id"] == "stara-radnja")
    assert stara["status"] == "closed" and stara["dokaz"]["zatvaranje"]["razlog"] == "PROTIVRECNOST_NIJE_POTVRDJENA"


def test_neispravan_identifikator_je_404_ne_500(predmet):
    k, b, pid = predmet
    assert k.post(f"/api/predmeti/{pid}/sporne-tacke/nije-uuid/potvrdi", headers=A).status_code == 404
    assert k.post("/api/predmeti/nije-uuid/sporne-tacke/nije-uuid/odbij", headers=A).status_code == 404



# ── Nalazi nezavisnog pregleda (S02, krug 2) ─────────────────────────────────────────────────────────────────────
def test_odluka_sa_zastarelog_ekrana_ne_pokriva_nov_sadrzaj(predmet):
    """R2-H1: advokat je video dve tvrdnje; pozadinsko opažanje je u međuvremenu dodalo treću. Potvrda sa tog ekrana
    se odbija (409) — odluka ne sme da pokrije sadržaj koji advokat nije video."""
    import datetime as dt
    k, b, pid = predmet
    x = _po_labeli(_kon(k, pid)["za_pregled"])[URUCENJE[0]]
    vidjeno = {"status": x["odluka"]["status"], "odluka_at": x["odluka"]["odluka_at"], "sadrzaj": x["odluka"]["sadrzaj"]}
    treca = next(d["id"] for d in b.tabele["predmet_dokazi"] if d["predmet_id"] == pid and "1.200.000" in d["tvrdnja"])
    b.tabele["predmet_contradiction_claims"].append({"id": "pozadina", "contradiction_id": x["id"], "dokaz_id": treca,
                                                     "removed_at": None, "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    r = k.post(f"/api/predmeti/{pid}/sporne-tacke/{x['odluka']['issue_id']}/potvrdi", json={"ocekivano": vidjeno}, headers=A)
    assert r.status_code == 409, r.text
    assert next(i for i in b.tabele["predmet_issues"] if i["id"] == x["odluka"]["issue_id"])["status"] == "DISCOVERED"
    assert _audit(b, "sporna_tacka_potvrdjena") == []
    novi = _po_labeli(_kon(k, pid)["za_pregled"])[URUCENJE[0]]
    assert novi["odluka"]["sadrzaj"] != vidjeno["sadrzaj"] and len(novi["ucesnici"]) == 3      # osvežen prikaz vidi sve


def test_sadrzaj_promenjen_tokom_upisa_vraca_odluku(predmet, monkeypatch):
    """R2-H1: opažanje se upisalo dok je odluka čekala zaključan red — provera posle upisa vraća odluku (409)."""
    import routers.sporna_tacka as st
    k, b, pid = predmet
    x = _po_labeli(_kon(k, pid)["za_pregled"])[URUCENJE[0]]
    pravo, pozivi = st._stanje_sadrzaja, []

    def _posle_drugaciji(supa, red):
        vazi, sadrzaj = pravo(supa, red)
        pozivi.append(1)
        return vazi, (sadrzaj if len(pozivi) == 1 else sadrzaj + "-promenjen")
    monkeypatch.setattr(st, "_stanje_sadrzaja", _posle_drugaciji)
    assert _odluka(k, pid, x, "potvrdi").status_code == 409
    assert next(i for i in b.tabele["predmet_issues"] if i["id"] == x["odluka"]["issue_id"])["status"] == "DISCOVERED"
    assert _audit(b, "sporna_tacka_potvrdjena") == []



def test_bez_vidjenog_sadrzaja_nema_odluke(predmet):
    """R3-M2: odluka bez stanja i verzije sadržaja koje je advokat video (stari prozor, API poziv) se ne beleži."""
    k, b, pid = predmet
    x = _po_labeli(_kon(k, pid)["za_pregled"])[URUCENJE[0]]
    iid = x["odluka"]["issue_id"]
    assert k.post(f"/api/predmeti/{pid}/sporne-tacke/{iid}/potvrdi", headers=A).status_code == 409
    bez = {"ocekivano": {"status": x["odluka"]["status"], "odluka_at": x["odluka"]["odluka_at"]}}
    assert k.post(f"/api/predmeti/{pid}/sporne-tacke/{iid}/potvrdi", json=bez, headers=A).status_code == 409
    assert next(i for i in b.tabele["predmet_issues"] if i["id"] == iid)["status"] == "DISCOVERED"
    assert _audit(b, "sporna_tacka_potvrdjena") == []
