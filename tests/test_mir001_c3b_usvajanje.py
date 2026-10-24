# -*- coding: utf-8 -*-
"""MIR001 C3b FINAL CLOSURE TASK-01 — ugovor izričitog usvajanja: AI RADNI PREDLOG → DOKUMENT ZA SUD.

Stvarne rute (`/api/agents/run` → staging → `/dokument-za-sud`, `/stavka`, `/procesne-tacke`, `PATCH /tekst`,
`/approve`, `/docx`), Golden Case spis (OCR), model zamenjen zadatim JSON odgovorom. Mere SERVERSKU granicu: AI tekst
ne postaje potvrđen ni izvezen bez izričitog usvajanja; usvajanje nije provera izvora; odobren je tačan tekst.
"""
import json
import re
import types

import pytest

from tests import c3b_usvajanje_pomoc as U
from tests.test_mir001_t06_nacrt_iz_spisa import _nacrti, nacrt, treba_ocr  # noqa: F401
from tests.test_mir001_t04_savetnik_spis import savetnik  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401

from shared import usvajanje_nacrta as UN

# AI predlog: zaglavlje, tačna stavka, stavka sa AUTENTIČNIM izvodom ali POGREŠNIM tumačenjem (sud je PRIHVATIO
# dopunu — model tvrdi da ju je odbio i da nije potrebna), legitiman stav stranke, upozorenje AI.
ZAGLAVLJE = "PRIVREDNOM SUDU U PRIMERGRADU\nBroj predmeta: P 9901/2026"
TACNA = "Vestak u nalazu navodi da je uzrok prokisnjavanja neodgovarajuce izvedena hidroizolacija na spoju atike."
POGRESNA = "Kako je sud odbio predlog za dopunu vestacenja [[{ps}]], dopuna vestacenja nije potrebna i tuzilac je ne predlaze."
STAV = "Tuzilac osporava navode tuzenog iz izjasnjenja na nalaz i smatra da je nalaz vestaka potpun i jasan."
UPOZORENJE = "⚠️ Ovaj nacrt je izradila AI; mora ga pregledati advokat."


def _model(monkeypatch, snimljeno, napomene=("Proveriti iznos zahteva.",)):
    import routers.multi_agent as MA

    def _m(client, system, user_msg):
        snimljeno.append({"system": system, "user": user_msg})
        # oznaka AUTENTIČNOG događaja „Sud prihvata predlog za dopunu vestacenja.“ iz bloka procesnog stanja
        ps = re.search(r"\[\[(PS-\d+)\]\] DOK-07 \| akter po tekstu: SUD \| vrsta \(kandidat\): SUD_PRIHVATA", user_msg).group(1)
        tekst = "\n\n".join([ZAGLAVLJE, TACNA, POGRESNA.format(ps=ps), STAV, UPOZORENJE])
        telo = json.dumps({"tekst_za_sud": tekst, "napomene_za_advokata": list(napomene)}, ensure_ascii=False)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=telo),
                                                                    finish_reason="stop")])
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", _m)


@pytest.fixture
def predlog(nacrt, monkeypatch):
    k, b, pid, doks, snimljeno = nacrt
    _model(monkeypatch, snimljeno)
    r = k.post("/api/agents/run", json={"agent": "drafting", "task": "Sastavi podnesak tuzioca.", "predmet_id": pid},
               headers=A)
    assert r.status_code == 200, r.text
    [st] = _nacrti(b, pid)
    return k, b, pid, doks, st


def _stavka_sa(p, deo):
    return next(s for s in p["predlog"]["stavke"] if deo in s["tekst"])


@treba_ocr
def test_snimak_predloga_nista_nije_potvrdjeno_ni_popunjeno(predlog):
    k, b, pid, doks, st = predlog
    p = U.predlog(k, A, st["id"])
    assert p["status_teksta"] == "AI_RADNI_PREDLOG" and [s["id"] for s in p["predlog"]["stavke"]] == [
        "S-01", "S-02", "S-03", "S-04", "S-05"]
    assert all(s["status"] == "AI_RADNI_PREDLOG" for s in p["predlog"]["stavke"])
    # oznaka je zamenjena DOSLOVNIM izvodom iz DOK-07 — prikaz izvora koji je model izabrao, ne potvrda
    pog = _stavka_sa(p, "sud odbio")
    assert "„Sud prihvata predlog za dopunu vestacenja.“" in pog["tekst"] and pog["izvori"] == ["DOK-07"]
    # osam procesnih tačaka; kandidati su doslovni izvodi sa identitetom dokumenta; odluka NE postoji
    tacke = {t["kljuc"]: t for t in p["predlog"]["procesne_tacke"]}
    assert list(tacke) == list(UN.KLJUCEVI_TACAKA)
    odluke = [c for c in tacke["ODLUKE_SUDA"]["kandidati"] if c["oznaka"] == "DOK-07"]
    assert any(c["izvod"] == "Sud prihvata predlog za dopunu vestacenja." and c["dokument_id"] == doks["DOK-07"]["id"]
               for c in odluke)
    assert tacke["OSNOVNI_ZAHTEV"]["kandidati"] == [] and "ne izdvaja iznose" in tacke["OSNOVNI_ZAHTEV"]["pomoc"]
    zapis = json.dumps(p["predlog"], ensure_ascii=False)
    for zabranjeno in ("VERIFIED", "POTVRDJENO", "USVOJENO", "\"odluka\""):
        assert zabranjeno not in zapis, zabranjeno
    assert all(d["dokument_id"] for d in p["predlog"]["dokumenti"] if d["stanje"] == "PROCITAN")
    assert p["dokumenti_za_sud"] == []


@treba_ocr
def test_adversarijalno_autentican_izvod_pogresno_tumacenje_nije_potvrdjeno_i_ne_prelazi_samo(predlog):
    """Izvod u stavci je DOSLOVAN i iz pravog dokumenta, a tumačenje je suprotno. Server ga ne smatra potvrđenim zbog
    citata: stavka ostaje AI predlog, ne ulazi u dokument za sud bez usvajanja, ni kao prepisan tekst."""
    k, b, pid, doks, st = predlog
    p = U.predlog(k, A, st["id"])
    pog = _stavka_sa(p, "sud odbio")
    d = U.dokument(k, A, st["id"])
    assert d["tekst"] == "" and d["procesne_tacke"] == {} and d["provera_izvora"] == "NIJE_IZVRSENA_SERVEROM"
    assert all(s["odluka"] is None for s in d["stavke"])
    # usvojene samo tačne stavke → pogrešna nije u tekstu
    for s in ("S-01", "S-02", "S-04"):
        assert U.stavka(k, A, d["id"], s).status_code == 200
    assert U.tacke(k, A, d["id"]).status_code == 200
    t = U.sacuvan(k, A, d["id"])
    assert "sud odbio" not in t["tekst"] and TACNA in t["tekst"] and STAV in t["tekst"]
    # advokat PREPIŠE pogrešnu stavku u tekst (mimo usvajanja) → odobrenje odbijeno, ništa nije odobreno
    r = k.patch(f"/api/staging/{d['id']}/tekst", json={"tekst": t["tekst"] + "\n\n" + pog["tekst"]}, headers=A)
    assert r.status_code == 200
    r = U.odobri(k, A, d["id"])
    assert r.status_code == 409 and any(pog["id"] in x for x in r.json()["detail"]["razlozi"]), r.text
    assert U.sacuvan(k, A, d["id"])["odobreno"] is None
    # izričito usvajanje JE moguće (advokat odlučuje) — zapis kaže „usvojio advokat“, nikad „izvor potvrđuje“
    k.patch(f"/api/staging/{d['id']}/tekst", json={"tekst": t["tekst"]}, headers=A)
    assert U.stavka(k, A, d["id"], pog["id"]).status_code == 200
    r = U.odobri(k, A, d["id"])
    assert r.status_code == 200, r.text
    red = next(s for s in b.tabele["staging_memory"] if s["id"] == d["id"])
    z = next(x for x in red["quality_detail"]["usvajanje"]["stavke"] if x["id"] == pog["id"])
    assert z["odluka"] == "USVOJENO" and z["by"] == "uid-A" and z["sha256"] == pog["sha256"]
    assert "VERIFIED" not in json.dumps(red["quality_detail"], ensure_ascii=False)


@treba_ocr
def test_bez_usvajanja_i_odobrenja_nema_dokumenta_za_sud(predlog):
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    assert k.post(f"/api/staging/{d['id']}/docx", headers=A).status_code == 409                 # nije odobren
    assert U.tacke(k, A, d["id"]).status_code == 200
    r = U.odobri(k, A, d["id"])
    assert r.status_code == 409 and "Dokument za sud je prazan." in r.json()["detail"]["razlozi"]     # nema usvojenog teksta
    assert U.stavka(k, A, d["id"], "S-02").status_code == 200
    # bez tela / tuđ sha (stari klijent, „odobri“ naslepo) → 409
    assert k.post(f"/api/staging/{d['id']}/approve", headers=A).status_code == 409
    assert U.odobri(k, A, d["id"], sha="0" * 64).status_code == 409
    assert U.sacuvan(k, A, d["id"])["odobreno"] is None
    assert k.post(f"/api/staging/{d['id']}/docx", headers=A).status_code == 409


@treba_ocr
def test_procesne_tacke_odlucuje_samo_advokat_i_sve_su_obavezne(predlog):
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    U.stavka(k, A, d["id"], "S-02")
    # bez ijedne odluke → odobrenje odbijeno, sa spiskom tačaka
    r = U.odobri(k, A, d["id"])
    assert r.status_code == 409 and any("Procesne tačke bez vaše odluke" in x for x in r.json()["detail"]["razlozi"])
    for lose in ({"NEPOSTOJECA": {"odluka": "NEPOZNATO"}}, {"ROK": {"odluka": "MOZDA"}},
                 {"ROK": {"odluka": "POTVRDJENO", "tekst": "  "}}, {"ROK": {"odluka": "NEPOZNATO", "izvori": ["DOK-99"]}}):
        assert U.tacke(k, A, d["id"], lose).status_code == 422, lose
    # delimično: sedam tačaka → i dalje 409; osma → 200
    sedam = {kk: v for kk, v in U.SVE_NEPOZNATO.items() if kk != "UPLATA"}
    assert U.tacke(k, A, d["id"], sedam).status_code == 200
    assert U.odobri(k, A, d["id"]).status_code == 409
    r = U.tacke(k, A, d["id"], {"UPLATA": {"odluka": "ISPRAVLJENO", "tekst": "U spisu nema dokaza o uplati predujma.",
                                           "izvori": ["DOK-07"]}})
    assert r.status_code == 200 and r.json()["procesne_tacke"]["UPLATA"]["by"] == "uid-A"
    assert U.odobri(k, A, d["id"]).status_code == 200


@treba_ocr
def test_odbacivanje_ne_brise_drugi_sadrzaj_i_izmena_posle_odobrenja_ne_nasledjuje_odobrenje(predlog):
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    assert U.dokument(k, A, st["id"])["id"] == d["id"]                                     # ponovljen zahtev: isti
    for s in ("S-02", "S-04"):
        U.stavka(k, A, d["id"], s)
    assert U.stavka(k, A, d["id"], "S-02").status_code == 200                              # ponovljeno: bez dupliranja
    assert U.stavka(k, A, d["id"], "S-03", "ODBACENO").status_code == 200
    assert U.stavka(k, A, d["id"], "S-02", "ODBACENO").status_code == 409                  # usvojena → izmenom teksta
    t = U.sacuvan(k, A, d["id"])
    assert t["tekst"] == TACNA + "\n\n" + STAV and t["tekst"].count(TACNA) == 1
    assert {s["id"]: s["odluka"] for s in t["stavke"]}["S-03"] == "ODBACENO"
    U.tacke(k, A, d["id"])
    assert U.odobri(k, A, d["id"]).status_code == 200
    assert U.odobri(k, A, d["id"]).json()["poruka"].startswith("Ovaj dokument je već obrađen")    # dvostruki klik
    v1 = U.sacuvan(k, A, d["id"])
    # posle odobrenja: tekst i odluke se ne menjaju
    assert k.patch(f"/api/staging/{d['id']}/tekst", json={"tekst": "Novo."}, headers=A).status_code == 409
    assert U.stavka(k, A, d["id"], "S-01").status_code == 409
    assert U.tacke(k, A, d["id"]).status_code == 409
    # nova verzija: isti tekst, BEZ odobrenja i bez odluka o tačkama; v1 ostaje izvezen tačno kakav je odobren
    d2 = U.dokument(k, A, st["id"])
    assert d2["id"] != d["id"] and d2["verzija"] == 2 and d2["prethodna_verzija_id"] == d["id"]
    assert d2["status"] == "pending" and d2["odobreno"] is None and d2["procesne_tacke"] == {} and d2["tekst"] == v1["tekst"]
    assert k.post(f"/api/staging/{d2['id']}/docx", headers=A).status_code == 409
    assert k.patch(f"/api/staging/{d2['id']}/tekst", json={"tekst": v1["tekst"] + "\n\nDodato."}, headers=A).status_code == 200
    r1 = k.post(f"/api/staging/{d['id']}/docx", headers=A)
    assert r1.status_code == 200 and "Dodato." not in "\n".join(U.docx_pasusi(r1.content))
    assert U.dokument(k, A, st["id"])["id"] == d2["id"]                                     # verzija na čekanju se vraća


@treba_ocr
def test_docx_je_tacno_odobren_tekst_bez_naslova_i_podnozja_sistema(predlog):
    k, b, pid, doks, st = predlog
    dok, d = U.ceo_tok(k, A, st["id"], ["S-01", "S-02", "S-04"])
    assert d.status_code == 200 and d.headers["content-disposition"] == 'attachment; filename="Dokument_za_sud.docx"'
    pasusi = U.docx_pasusi(d.content)
    assert [p for p in pasusi if p.strip()] == [r for r in dok["tekst"].split("\n") if r.strip()]
    assert "NACRT IZ SPISA" not in "\n".join(pasusi) and "Dokument za sud" not in "\n".join(pasusi)
    assert U.docx_podnozje(d.content).strip() == ""
    # sačuvan tekst promenjen mimo rute (npr. ručno u bazi) → sha ne odgovara odobrenom → izvoz odbijen
    red = next(s for s in b.tabele["staging_memory"] if s["id"] == dok["id"])
    red["tekst"] = red["tekst"] + "\nPodmetnuto."
    assert k.post(f"/api/staging/{dok['id']}/docx", headers=A).status_code == 409


@treba_ocr
def test_tudj_korisnik_ne_vidi_ne_usvaja_ne_odobrava_ne_izvozi(predlog):
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    U.stavka(k, A, d["id"], "S-02")
    assert k.get(f"/api/staging/{d['id']}", headers=B).status_code == 404
    assert k.post(f"/api/staging/{st['id']}/dokument-za-sud", headers=B).status_code == 404
    assert k.post(f"/api/staging/{d['id']}/stavka", json={"stavka": "S-04", "odluka": "USVOJENO"}, headers=B).status_code == 404
    assert k.post(f"/api/staging/{d['id']}/procesne-tacke", json={"tacke": U.SVE_NEPOZNATO}, headers=B).status_code == 404
    assert k.patch(f"/api/staging/{d['id']}/tekst", json={"tekst": "A piše."}, headers=A).status_code == 200
    assert k.patch(f"/api/staging/{d['id']}/tekst", json={"tekst": "B piše."}, headers=B).status_code == 404
    U.tacke(k, A, d["id"])
    sha = U.sacuvan(k, A, d["id"])["sha256"]
    assert k.post(f"/api/staging/{d['id']}/approve", json={"sha256": sha}, headers=B).status_code == 404
    assert U.odobri(k, A, d["id"]).status_code == 200
    assert k.post(f"/api/staging/{d['id']}/docx", headers=B).status_code == 404


@treba_ocr
def test_poreklo_predloga_mora_biti_proverljivo(predlog):
    k, b, pid, doks, st = predlog
    red = next(s for s in b.tabele["staging_memory"] if s["id"] == st["id"])
    d = U.dokument(k, A, st["id"])
    # tip: usvajanje radi samo nad dokumentom za sud; dokument za sud nastaje samo iz predloga
    assert k.post(f"/api/staging/{st['id']}/stavka", json={"stavka": "S-01", "odluka": "USVOJENO"}, headers=A).status_code == 409
    assert k.post(f"/api/staging/{d['id']}/dokument-za-sud", headers=A).status_code == 409
    assert U.stavka(k, A, d["id"], "S-99").status_code == 404
    # tekst predloga promenjen mimo rute → usvajanje odbijeno (sha snimka)
    staro = red["tekst"]
    red["tekst"] = staro.replace("potpun i jasan", "potpun")
    assert U.stavka(k, A, d["id"], "S-02").status_code == 409
    red["tekst"] = staro
    assert U.stavka(k, A, d["id"], "S-02").status_code == 200
    # predlog izrađen pre kontrolisanog toka (bez snimka) → nema dokumenta za sud (ne označava se retroaktivno)
    qd = red["quality_detail"]
    red["quality_detail"] = {kk: v for kk, v in qd.items() if kk != "predlog"}
    assert k.post(f"/api/staging/{st['id']}/dokument-za-sud", headers=A).status_code == 409
    red["quality_detail"] = qd


@treba_ocr
def test_usvajanje_ne_naplacuje_ne_zove_model_i_ne_ide_u_znanje(predlog, monkeypatch):
    k, b, pid, doks, st = predlog
    from shared.usage import UsageService
    import routers.drafting as D
    import routers.multi_agent as MA
    dogadjaji = []

    async def _naplata(*a, **kw):
        dogadjaji.append("naplata")

    async def _promocija(supa, red):
        dogadjaji.append("promocija")
        return True
    monkeypatch.setattr(UsageService, "consume", staticmethod(_naplata))
    monkeypatch.setattr(D, "_promote_staged_draft_to_pinecone", _promocija)
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", lambda *a, **kw: dogadjaji.append("model"))
    vektori = len(b.vektori)
    dok, d = U.ceo_tok(k, A, st["id"], ["S-02"])
    assert d.status_code == 200 and dogadjaji == [] and len(b.vektori) == vektori
    # Law Brain: odobren dokument za sud i AI predlog NISU overeno znanje kancelarije
    from services import law_brain as LB
    predmet = {"id": pid, "user_id": "uid-A"}
    for sid in (st["id"], dok["id"]):
        red = next(s for s in b.tabele["staging_memory"] if s["id"] == sid)
        it = LB.artifact_item(red, predmet)
        assert it.trust_class == LB.AI_WORK_PRODUCT and not it.trusted and "INTERNE NAPOMENE" not in it.excerpt


# ── MIR001 FINAL RELEASE R1: izvor u internom panelu, ne u tekstu za sud ──────────────────────────────────────────
@treba_ocr
def test_r1_izvod_servera_u_dokumentu_bez_interne_oznake_a_pregled_je_zadrzava(predlog):
    """Izvod koji umeće server: u pregledu nosi DOK-07 (izvor za proveru), u dokument za sud ulazi isti doslovan izvod
    sa naslovom i datumom dokumenta, bez interne oznake spisa. Izvoz = tačno odobren tekst."""
    k, b, pid, doks, st = predlog
    p = U.predlog(k, A, st["id"])
    pog = _stavka_sa(p, "sud odbio")
    assert "(DOK-07, zapisnik sa rocista (sinteticki predmet), 15.07.2026.: „Sud prihvata predlog za dopunu vestacenja.“)" in pog["tekst"]
    assert "(zapisnik sa rocista (sinteticki predmet), 15.07.2026.: „Sud prihvata predlog za dopunu vestacenja.“)" in pog["tekst_za_dokument"]
    assert "DOK-" not in pog["tekst_za_dokument"] and pog["izvori"] == ["DOK-07"]
    assert all(s["sha256_za_dokument"] == UN.sha(s["tekst_za_dokument"]) for s in p["predlog"]["stavke"])
    dok, d = U.ceo_tok(k, A, st["id"], ["S-02", pog["id"]])
    assert d.status_code == 200 and "DOK-" not in dok["tekst"] and pog["tekst_za_dokument"] in dok["tekst"]
    pasusi = "\n".join(U.docx_pasusi(d.content))
    assert "DOK-" not in pasusi and "„Sud prihvata predlog za dopunu vestacenja.“" in pasusi
    # izvor ostaje dostupan za pregled (predlog nepromenjen) — zapis usvajanja nosi oba sha
    assert U.predlog(k, A, st["id"])["predlog"]["stavke"] == p["predlog"]["stavke"]
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == dok["id"])
    z = next(x for x in red["quality_detail"]["usvajanje"]["stavke"] if x["id"] == pog["id"])
    assert z["sha256"] == pog["sha256"] and z["sha256_za_dokument"] == pog["sha256_za_dokument"]


@treba_ocr
def test_r1_interna_oznaka_u_tekstu_zaustavlja_odobrenje_bez_brisanja(predlog):
    """DOK-nn koji je napisao AI (ili korisnik) se NE briše iz teksta; odobrenje se zaustavlja sa objašnjenjem koja je
    to oznaka, dok je advokat ne zameni. Korisnikov namerni citat ostaje."""
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    U.stavka(k, A, d["id"], "S-02")
    U.tacke(k, A, d["id"])
    sa = U.sacuvan(k, A, d["id"])["tekst"] + "\n\nTuzeni u izjasnjenju (DOK-06) osporava nalaz."
    assert k.patch(f"/api/staging/{d['id']}/tekst", json={"tekst": sa}, headers=A).status_code == 200
    r = U.odobri(k, A, d["id"])
    assert r.status_code == 409, r.text
    raz = " ".join(r.json()["detail"]["razlozi"])
    assert "internu oznaku spisa DOK-nn" in raz and "DOK-06 = 06 Izjasnjenje na nalaz vestaka.pdf" in raz
    assert U.sacuvan(k, A, d["id"])["tekst"] == sa                                     # ništa nije obrisano
    citat = "\n\nTuzeni u izjasnjenju od 01.07.2026. navodi: „nalaz je nepotpun“."
    assert k.patch(f"/api/staging/{d['id']}/tekst", json={"tekst": U.sacuvan(k, A, d["id"])["tekst"].replace(
        "\n\nTuzeni u izjasnjenju (DOK-06) osporava nalaz.", citat)}, headers=A).status_code == 200
    assert U.odobri(k, A, d["id"]).status_code == 200
    dx = k.post(f"/api/staging/{d['id']}/docx", headers=A)
    assert dx.status_code == 200 and "Tuzeni u izjasnjenju od 01.07.2026. navodi: „nalaz je nepotpun“." in U.docx_pasusi(dx.content)


@treba_ocr
def test_r1_odobren_tekst_sa_oznakom_se_ne_menja_pri_izvozu(predlog):
    """Dokument odobren pre R1 (tekst sadrži DOK-nn): izvoz ga NE menja niti „čisti“ — 409 sa putem (nova verzija);
    sačuvan i odobren tekst ostaje isti."""
    k, b, pid, doks, st = predlog
    dok, d = U.ceo_tok(k, A, st["id"], ["S-02"])
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == dok["id"])
    star = red["tekst"] + " (DOK-05)"                       # kao da je odobren starim pravilom
    red["tekst"] = star
    red["quality_detail"]["usvajanje"]["odobreno"]["sha256"] = UN.sha(star)
    r = k.post(f"/api/staging/{dok['id']}/docx", headers=A)
    assert r.status_code == 409 and "novu verziju" in r.json()["detail"] and "DOK-nn" in r.json()["detail"]
    assert red["tekst"] == star and red["status"] == "approved"


@treba_ocr
def test_r1_stari_zapis_predloga_se_ne_usvaja(predlog):
    """Predlog sa zapisom verzije 1 (bez teksta za dokument) se ne proglašava kompatibilnim: nema dokumenta za sud, nema
    daljeg usvajanja u već započetom dokumentu."""
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == st["id"])
    stari = dict(red["quality_detail"]["predlog"], verzija_ugovora=1)
    red["quality_detail"] = {**red["quality_detail"], "predlog": stari}
    assert U.stavka(k, A, d["id"], "S-02").status_code == 409
    assert k.post(f"/api/staging/{st['id']}/dokument-za-sud", headers=A).status_code in (200, 409)
    k.post(f"/api/staging/{d['id']}/reject", headers=A)
    r = k.post(f"/api/staging/{st['id']}/dokument-za-sud", headers=A)
    assert r.status_code == 409 and "pre pravila o izvorima" in r.json()["detail"]


@pytest.mark.parametrize("zapis", ["(dok-06)", "DOK 05", "ДОК-05", "DOK\u201105", "DOK\u201305", "DOK-00005", "Dok-5",
                                   "DOK-05a", "[[DOK-05]]", "DOK 05", "DOK.05", "DOK. 05"])
def test_r1_svaki_zapis_interne_oznake_blokira(zapis):
    """GATE-R1 N1: varijante zapisa interne oznake (mala slova uz crticu, razmak, ćirilica, Unicode crte, vodeće nule)
    zaustavljaju odobrenje kao i „DOK-05“ i svode se na oznaku iz spiska dokumenata."""
    assert UN.nedozvoljen_sadrzaj(f"Tuzeni navodi {zapis} da …"), zapis
    pr = {"dokumenti": [{"oznaka": "DOK-05", "naziv": "05 Nalaz.pdf"}, {"oznaka": "DOK-06", "naziv": "06 Izjasnjenje.pdf"}]}
    raz = " ".join(UN.razlozi_protiv_odobrenja(f"Tekst {zapis}.", {"procesne_tacke": U.SVE_NEPOZNATO}, pr))
    assert ("DOK-06 = 06 Izjasnjenje.pdf" if "6" in zapis else "DOK-05 = 05 Nalaz.pdf") in raz, raz
    assert UN.stavke(f"Stavka {zapis}.")[0]["izvori"] == (["DOK-06"] if "6" in zapis else ["DOK-05"])


@pytest.mark.parametrize("tekst", ["Tuzeni ne placa dok 15 dana ne prodje.", "Dokaz 5 je priložen.", "DOKAZ-12", "dokument 12",
                                   "Sve dok-a nema.", "kodok-3"])
def test_r1_obicne_reci_nisu_interna_oznaka(tekst):
    assert not UN.nedozvoljen_sadrzaj(tekst) and UN.oznake_u(tekst) == []


@treba_ocr
def test_r1_pad_zapisa_predloga_pre_naplate(nacrt, monkeypatch):
    """GATE-R1 N5: zapis predloga nastaje PRE naplate — njegov pad ne naplaćuje i ne upisuje ništa."""
    k, b, pid, doks, snimljeno = nacrt
    _model(monkeypatch, snimljeno)
    from shared.usage import UsageService
    naplate = []

    async def _naplata(*a, **kw):
        naplate.append(1)
    monkeypatch.setattr(UsageService, "consume", staticmethod(_naplata))

    def _pad(*a, **kw):
        raise ValueError("stavke se ne poklapaju")
    monkeypatch.setattr(UN, "snimak_predloga", _pad)
    r = k.post("/api/agents/run", json={"agent": "drafting", "task": "Sastavi podnesak tuzioca.", "predmet_id": pid}, headers=A)
    assert r.status_code == 502 and "Ništa nije naplaćeno" in r.json()["detail"]
    assert naplate == [] and _nacrti(b, pid) == []


def test_r1_snimak_ima_dve_verzije_iste_strukture():
    from shared import nacrt_za_sud as NZ
    stanje = {"dogadjaji": [{"id": "PS-01", "oznaka": "DOK-07", "izvod": "Sud prihvata predlog.", "datum_dokumenta": "2026-07-15",
                             "vrsta_dokumenta": {"naslov": "ZAPISNIK SA ROCISTA"}, "akter": "SUD", "vrsta": "SUD_PRIHVATA"}]}
    pr = NZ.predlog("Uvod.\n\nSud je odlucio [[PS-01]].\n\nOznaka [[PS-99]].", stanje)
    sn = UN.snimak_predloga(pr["tekst"], stanje, [], pr["tekst_za_dokument"])
    assert sn["verzija_ugovora"] == UN.VERZIJA_UGOVORA == 2
    assert [s["tekst_za_dokument"] for s in sn["stavke"]] == [
        "Uvod.", "Sud je odlucio (zapisnik sa rocista, 15.07.2026.: „Sud prihvata predlog.“).", "Oznaka [[PS-99 NE POSTOJI]]."]
    assert sn["stavke"][1]["tekst"] == "Sud je odlucio (DOK-07, zapisnik sa rocista, 15.07.2026.: „Sud prihvata predlog.“)."
    assert UN.nedozvoljen_sadrzaj(sn["stavke"][2]["tekst_za_dokument"])               # nepostojeća oznaka i dalje blokira
    assert UN.nedozvoljen_sadrzaj("Vidi DOK-12.") and not UN.nedozvoljen_sadrzaj("Vidi dokument 12 (DOKAZ-12).")


def test_uslovna_izmena_odbija_zastareo_tekst_i_reviziju():
    """Trka: izmena dokumenta za sud važi samo nad tekstom i revizijom koji su pročitani."""
    import asyncio
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    import routers.drafting as D
    supa = MagicMock()
    lanac = supa.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.eq
    lanac.return_value.execute.return_value = types.SimpleNamespace(data=[])
    with pytest.raises(HTTPException) as e:
        asyncio.run(D._uslovno_azuriraj_dokument(supa, {"id": "x", "tekst": "staro", "quality_detail": {"usvajanje_rev": 4}},
                                                 "uid", {"tekst": "novo"}))
    assert e.value.status_code == 409
    assert lanac.call_args.args == ("quality_detail->>usvajanje_rev", "4")
    upisano = supa.table.return_value.update.call_args.args[0]
    assert upisano["quality_detail"]["usvajanje_rev"] == 5


def _paralelno_pre_upisa(monkeypatch, b, did, izmena):
    """Emulira paralelan zahtev koji završi IZMEĐU čitanja i upisa: pri prvoj proveri odobrenja red u bazi dobija
    novu odluku i novu reviziju (kao da ga je upisao drugi zahtev kroz istu rutu)."""
    orig = UN.razlozi_protiv_odobrenja
    stanje = {"jednom": False}

    def _r(tekst, usv, pr):
        if not stanje["jednom"]:
            stanje["jednom"] = True
            red = next(x for x in b.tabele["staging_memory"] if x["id"] == did)
            qd = dict(red["quality_detail"])
            izmena(qd)
            qd["usvajanje_rev"] = int(qd.get("usvajanje_rev") or 0) + 1
            red["quality_detail"] = qd
        return orig(tekst, usv, pr)
    monkeypatch.setattr(UN, "razlozi_protiv_odobrenja", _r)


@treba_ocr
def test_trka_odobrenje_ne_brise_paralelnu_ispravku_procesne_tacke(predlog, monkeypatch):
    """GATE-01 B1: odluka o tački upisana dok traje odobrenje ne sme da nestane; odobrenje tada pada (409)."""
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    U.stavka(k, A, d["id"], "S-02")
    U.tacke(k, A, d["id"])
    ispravka = {"odluka": "ISPRAVLJENO", "tekst": "Sud je PRIHVATIO dopunu (DOK-07).", "izvori": ["DOK-07"],
                "by": "uid-A", "at": "x"}

    def _izmena(qd):
        u = dict(qd["usvajanje"])
        u["procesne_tacke"] = {**u["procesne_tacke"], "ODLUKE_SUDA": ispravka}
        qd["usvajanje"] = u
    _paralelno_pre_upisa(monkeypatch, b, d["id"], _izmena)
    r = U.odobri(k, A, d["id"])
    assert r.status_code == 409, r.text
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == d["id"])
    assert red["status"] == "pending" and red["quality_detail"]["usvajanje"]["procesne_tacke"]["ODLUKE_SUDA"] == ispravka
    # advokat vidi novo stanje i odobrava ga svesno
    assert U.odobri(k, A, d["id"]).status_code == 200
    assert next(x for x in b.tabele["staging_memory"] if x["id"] == d["id"])["quality_detail"]["usvajanje"][
        "procesne_tacke"]["ODLUKE_SUDA"]["odluka"] == "ISPRAVLJENO"


@treba_ocr
def test_trka_izmena_teksta_ne_brise_paralelnu_odluku_o_tacki(predlog, monkeypatch):
    """PATCH teksta: između čitanja reda i upisa (računanje ocene kvaliteta) paralelno je upisana odluka o tački →
    PATCH pada (409), odluka ostaje."""
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    U.stavka(k, A, d["id"], "S-02")
    import services.quality_gate as QG
    orig = QG.evaluate_draft_quality

    async def _ocena(tekst, tip):
        red = next(x for x in b.tabele["staging_memory"] if x["id"] == d["id"])
        qd = dict(red["quality_detail"])
        qd["usvajanje"] = {**qd["usvajanje"], "procesne_tacke": {"ROK": {"odluka": "NEPOZNATO", "tekst": ""}}}
        qd["usvajanje_rev"] = int(qd.get("usvajanje_rev") or 0) + 1
        red["quality_detail"] = qd
        return await orig(tekst, tip)
    monkeypatch.setattr(QG, "evaluate_draft_quality", _ocena)
    r = k.patch(f"/api/staging/{d['id']}/tekst", json={"tekst": "Nov tekst advokata."}, headers=A)
    assert r.status_code == 409, r.text
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == d["id"])
    assert red["quality_detail"]["usvajanje"]["procesne_tacke"]["ROK"]["odluka"] == "NEPOZNATO" and red["tekst"] == TACNA


@treba_ocr
def test_odobrenje_trazi_reviziju_koju_je_advokat_video(predlog):
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    U.stavka(k, A, d["id"], "S-02")
    U.tacke(k, A, d["id"])
    stara = U.sacuvan(k, A, d["id"])["rev"]
    # u drugom prozoru advokat menja odluku o tački (tekst isti) → odobrenje sa starom revizijom pada
    assert U.tacke(k, A, d["id"], {"ROK": {"odluka": "POTVRDJENO", "tekst": "Rok nije određen u spisu."}}).status_code == 200
    assert U.odobri(k, A, d["id"], rev=stara).status_code == 409
    assert k.post(f"/api/staging/{d['id']}/approve", json={"sha256": U.sacuvan(k, A, d["id"])["sha256"]},
                  headers=A).status_code == 409                                               # bez revizije
    assert U.odobri(k, A, d["id"]).status_code == 200


@treba_ocr
def test_odbacen_predlog_i_odobren_dokument_su_zakljucani(predlog):
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    U.stavka(k, A, d["id"], "S-02")
    U.tacke(k, A, d["id"])
    assert U.odobri(k, A, d["id"]).status_code == 200
    # GATE-01 N4: odobren dokument za sud se ne odbija naknadno; DOCX ostaje izvoziv
    assert k.post(f"/api/staging/{d['id']}/reject", headers=A).status_code == 409
    assert k.post(f"/api/staging/{d['id']}/docx", headers=A).status_code == 200
    # GATE-01 N3: posle odbacivanja AI predloga nema daljeg usvajanja ni odobrenja iz njega
    d2 = U.dokument(k, A, st["id"])
    assert k.post(f"/api/staging/{st['id']}/reject", headers=A).status_code == 200
    assert U.stavka(k, A, d2["id"], "S-04").status_code == 409
    assert U.tacke(k, A, d2["id"]).status_code == 409
    assert U.odobri(k, A, d2["id"]).status_code == 409


@treba_ocr
def test_poreklo_iz_drugog_predmeta_se_odbija(predlog):
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == d["id"])
    red["predmet_id"] = "drugi-predmet"
    assert U.stavka(k, A, d["id"], "S-02").status_code == 409
    red["predmet_id"] = pid
    assert U.stavka(k, A, d["id"], "S-02").status_code == 200


@treba_ocr
def test_dupli_zahtev_za_dokument_ostavlja_jednu_verziju_na_cekanju(predlog, monkeypatch):
    """GATE-01 N5: dva paralelna zahteva (oba prođu proveru „nema verzije na čekanju“) → ostaje jedna."""
    k, b, pid, doks, st = predlog
    import routers.drafting as D
    prvi = U.dokument(k, A, st["id"])
    # drugi zahtev „ne vidi“ prvi (emulacija trke): filter verzija na čekanju pri proveri vraća prazno jednom
    orig = D._usvajanje
    stanje = {"n": 0}

    def _slepo(red):
        u = orig(red)
        if red and red.get("id") == prvi["id"] and stanje["n"] == 0:
            stanje["n"] += 1
            return {}
        return u
    monkeypatch.setattr(D, "_usvajanje", _slepo)
    drugi = U.dokument(k, A, st["id"])
    monkeypatch.setattr(D, "_usvajanje", orig)
    cekaju = [x for x in b.tabele["staging_memory"] if x.get("tip") == "dokument_za_sud" and x.get("status") == "pending"]
    assert drugi["id"] == prvi["id"] and len(cekaju) == 1
    # GATE-01 N-c: ostaje PRVI (radni) red sa svojim sadržajem; obrisan je samo novi, netaknut red
    assert cekaju[0]["id"] == prvi["id"]
    U.stavka(k, A, prvi["id"], "S-02")
    monkeypatch.setattr(D, "_usvajanje", _slepo)
    stanje["n"] = 0
    treci = U.dokument(k, A, st["id"])
    monkeypatch.setattr(D, "_usvajanje", orig)
    ostao = [x for x in b.tabele["staging_memory"] if x.get("tip") == "dokument_za_sud" and x.get("status") == "pending"]
    assert treci["id"] == prvi["id"] and [x["id"] for x in ostao] == [prvi["id"]] and TACNA in ostao[0]["tekst"]


@treba_ocr
def test_trka_odbijanje_ne_prepisuje_odobren_dokument(predlog, monkeypatch):
    """GATE-01 N-a: odbijanje pročita „na čekanju“, a odobrenje završi pre upisa odbijanja → odbijanje 409."""
    k, b, pid, doks, st = predlog
    d = U.dokument(k, A, st["id"])
    U.stavka(k, A, d["id"], "S-02")
    U.tacke(k, A, d["id"])
    assert U.odobri(k, A, d["id"]).status_code == 200
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == d["id"])
    import routers.drafting as D
    orig = D._get_supa

    class _Pogled:                                     # prvo čitanje reda vidi stanje PRE odobrenja (kao u trci)
        def __init__(self, supa):
            self.supa, self.prvi = supa, True

        def table(self, ime):
            t = self.supa.table(ime)
            if ime == "staging_memory" and self.prvi:
                self.prvi = False
                staro = {**red, "status": "pending"}
                return types.SimpleNamespace(select=lambda *a, **kw: types.SimpleNamespace(
                    eq=lambda *a: types.SimpleNamespace(eq=lambda *a: types.SimpleNamespace(
                        maybe_single=lambda: types.SimpleNamespace(execute=lambda: types.SimpleNamespace(data=staro))))))
            return t
    pogled = _Pogled(orig())
    monkeypatch.setattr(D, "_get_supa", lambda: pogled)
    assert k.post(f"/api/staging/{d['id']}/reject", headers=A).status_code == 409
    monkeypatch.setattr(D, "_get_supa", orig)
    assert red["status"] == "approved" and k.post(f"/api/staging/{d['id']}/docx", headers=A).status_code == 200


def test_law_brain_izvod_bez_internih_napomena():
    from services import law_brain as LB
    from shared.nacrt_za_sud import GRANICA
    red = {"id": "s1", "user_id": "u", "predmet_id": "p", "tip": "nacrt_iz_spisa", "status": "pending",
           "is_lawyer_approved": False, "tekst": "Kratak predlog.\n\n" + GRANICA + "\nINTERNO TAJNO"}
    it = LB.artifact_item(red, {"id": "p", "user_id": "u"})
    assert it.trust_class == LB.AI_WORK_PRODUCT and "INTERNO TAJNO" not in it.excerpt and "Kratak predlog." in it.excerpt
    odobren = {**red, "id": "s2", "tip": "dokument_za_sud", "status": "approved", "is_lawyer_approved": True,
               "approved_at": "2026-10-24T10:00:00Z", "tekst": "Usvojen tekst."}
    it2 = LB.artifact_item(odobren, {"id": "p", "user_id": "u"})
    assert it2.trust_class == LB.AI_WORK_PRODUCT and not it2.trusted and "LAWYER_ADOPTED" in it2.lineage


def test_stavke_su_strukturne_a_razlozi_ne_tumace_tekst():
    assert [s["tekst"] for s in UN.stavke("A\n\nB\nC")] == ["A", "B\nC"]
    assert [s["tekst"] for s in UN.stavke("A\nB")] == ["A", "B"]
    pr = {"stavke": UN.stavke("Kratko.\n\n" + "Duga AI stavka koja ima dovoljno znakova da se traži doslovno u tekstu dokumenta.")}
    sve = {"procesne_tacke": U.SVE_NEPOZNATO, "stavke": []}
    assert UN.razlozi_protiv_odobrenja("Kratko.", sve, pr) == []                         # kratka stavka (zaglavlje)
    assert len(UN.razlozi_protiv_odobrenja(pr["stavke"][1]["tekst"], sve, pr)) == 1
    # isti sadržaj, ali sud „odbija“ umesto „prihvata“ — server ne tumači: nema razloga ni za ni protiv
    assert UN.razlozi_protiv_odobrenja("Sud je odbio dopunu veštačenja.", sve, pr) == []
    for natpis in ("[PROVERITI: adresa]", "[IZOSTAVLJENO I-1: x]", "[[PS-03]]", "═══ VINDEX — INTERNE NAPOMENE x"):
        assert UN.nedozvoljen_sadrzaj("Tekst " + natpis), natpis
