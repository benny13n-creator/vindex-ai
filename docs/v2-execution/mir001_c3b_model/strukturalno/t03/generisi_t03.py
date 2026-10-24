# -*- coding: utf-8 -*-
"""MIR001 C3b STRUCTURAL TASK-03 — generisanje izlaza za slepu ocenu (PREREGISTRACIJA.md).

Stvarna ruta `POST /api/agents/run` (savetnik `drafting`, uz predmet), stvaran gpt-4o (`_pozovi_nacrt_api` nije
zamenjen), kapija, pregled i DOCX sa pregleda. Zamenjeni su samo baza u memoriji, pravna baza, ocena kvaliteta i naplata.
Ključ se čita iz `.env` i ne ispisuje. Jedan test = jedan nov spis i jedan nacrt.

Pokretanje iz korena repozitorijuma (OCR okruženje uključeno):
  python -X utf8 -m pytest -p tests.conftest -p no:randomly -p no:cacheprovider -q \
      docs/v2-execution/mir001_c3b_model/strukturalno/t03/generisi_t03.py
T03_SUVO=1 → model je zamenjen zamenikom (provera prijema varijanti, bez poziva API-ja).
T03_SAMO=A,C1 → samo ti scenariji; T03_N → broj po scenariju (podrazumevano 10).
"""
import asyncio
import copy
import io
import json
import os
import re
import types

import pytest

from tests import mir001_golden_case as gc
from tests.test_mir001_t02_prijem_spisa import primi_spis
from tests.test_osb002_solo_tok import A, solo  # noqa: F401

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "izlazi")
ZAHTEV = ("Sastavi podnesak tuzioca za rociste zakazano za 18.11.2026. kojim se izjasnjava na nalaz i misljenje vestaka "
          "(DOK-05), na izjasnjenje tuzenog (DOK-06) i o stanju postupka.")
SUD, BROJ = gc.SUD, gc.BROJ
SUVO = os.environ.get("T03_SUVO") == "1"
N = int(os.environ.get("T03_N", "10"))


def _dok(oznaka, ime, strana, datum, redovi, vrsta="podnesak", skeniran=False):
    return {"oznaka": oznaka, "ime": ime, "vrsta": vrsta, "strana": strana, "datum": datum, "skeniran": skeniran,
            "redovi": redovi}


def _zameni_07(doks, zamene):
    d7 = next(d for d in doks if d["oznaka"] == "DOK-07")
    for staro, novo in zamene:
        i = d7["redovi"].index(staro)
        if novo is None:
            d7["redovi"].pop(i)
        else:
            d7["redovi"][i] = novo
    return doks


NALOG_DNEVNIK = "Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana."
PRIHVATA = "Sud prihvata predlog za dopunu vestacenja."
PREDUJAM_8_OD_PRIJEMA = ("Sud nalaze tuziocu da u roku od 8 dana od prijema zapisnika uplati predujam za dopunu "
                         "vestacenja u iznosu od 60.000 dinara.")


def spis(sc):
    d = copy.deepcopy(gc.DOKUMENTI)
    bez07 = [x for x in d if x["oznaka"] != "DOK-07"]
    if sc == "A":
        return d
    if sc == "C1":
        return d + [_dok("DOK-08", "08 Podnesak tuzenog.pdf", "tuzeni", "2026-09-05", [
            SUD, f"Broj predmeta: {BROJ}", "PODNESAK TUZENOG (SINTETICKI PREDMET)",
            "Tuzeni odustaje od predloga za dopunu vestacenja.", "Tuzeni navodi da gradjevinski dnevnik nije sacuvan.",
            "Datum podneska: 05.09.2026. godine."])]
    if sc == "C2":
        return bez07 + [_dok("DOK-07", "07 Podnesak tuzenog.pdf", "tuzeni", "2026-07-20", [
            SUD, f"Broj predmeta: {BROJ}", "PODNESAK TUZENOG (SINTETICKI PREDMET)",
            "Tuzeni navodi da je na rocistu odrzanom 15.07.2026. godine raspravljano o njegovom predlogu za dopunu vestacenja.",
            "Tuzeni ponavlja predlog za dopunu vestacenja.", "Datum podneska: 20.07.2026. godine."])]
    if sc == "H2":
        return _zameni_07(d, [(NALOG_DNEVNIK, PREDUJAM_8_OD_PRIJEMA)])
    if sc == "B":
        return bez07
    if sc == "H1":
        return _zameni_07(d, [(PRIHVATA, "Sud odbija predlog tuzenog za dopunu vestacenja."), (NALOG_DNEVNIK, None)])
    if sc == "N1":
        return bez07 + [_dok("DOK-07", "07 Zapisnik sa rocista.pdf", "sud", "2026-07-15",
                             ["ZAPISNIK SA ROCISTA"], vrsta="zapisnik", skeniran=True)]
    if sc == "N2":
        return d + [_dok("DOK-08", "08 Zapisnik sa rocista.pdf", "sud", "2026-09-10", [
            SUD, f"Broj predmeta: {BROJ}", "ZAPISNIK SA ROCISTA (SINTETICKI PREDMET)",
            "Rociste odrzano dana 10.09.2026. godine.", "Sud odbija predlog tuzenog za dopunu vestacenja.",
            "Sledece rociste zakazano je za 18.11.2026. godine."], vrsta="zapisnik")]
    if sc == "N3":
        return _zameni_07(d, [(NALOG_DNEVNIK, PREDUJAM_8_OD_PRIJEMA)]) + [
            _dok("DOK-08", "08 Podnesak tuzioca.pdf", "tuzilac", "2026-07-20", [
                SUD, f"Broj predmeta: {BROJ}", "PODNESAK TUZIOCA (SINTETICKI PREDMET)",
                "Tuzilac navodi da je uplatio predujam za dopunu vestacenja.", "Datum podneska: 20.07.2026. godine."]),
            _dok("DOK-09", "09 Dopis suda.pdf", "sud", "2026-09-01", [
                SUD, f"Broj predmeta: {BROJ}", "OBAVESTENJE SUDA (SINTETICKI PREDMET)",
                "Sud konstatuje da dokaz o uplati predujma za dopunu vestacenja nije dostavljen.",
                "Datum: 01.09.2026. godine."], vrsta="dopis")]
    if sc == "N4":
        return _zameni_07(d, [(NALOG_DNEVNIK, "Sud nalaze tuziocu da uplati predujam za dopunu vestacenja u iznosu od "
                                              "60.000 dinara u roku od 8 dana.")])
    raise ValueError(sc)


SCENARIJI = ["A", "C1", "C2", "H2", "B", "H1", "N1", "N2", "N3", "N4"]
_SAMO = os.environ.get("T03_SAMO")
if _SAMO:
    SCENARIJI = [s for s in SCENARIJI if s in _SAMO.split(",")]


def _kljuc_iz_env():
    for red in open(os.environ.get("VINDEX_ENV_FILE", ".env"), encoding="utf-8"):
        if red.startswith("OPENAI_API_KEY="):
            return red.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENAI_API_KEY nije u .env")


@pytest.fixture
def okruzenje(solo, monkeypatch):
    k, b = solo
    import app.services.retrieve as R
    import routers.case_dna as cd
    import routers.evidence as ev
    import routers.multi_agent as MA
    import services.quality_gate as QG
    import shared.usage as US
    from tests.test_mir001_t03_kontinuitet import _klasifikuj
    from tests.test_mir001_t04_savetnik_spis import _genome_bez_narativa
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome_bez_narativa(b.genome_pozivi))
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _klasifikuj)

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free", "krediti": 1}

    async def _stanje(uid, email):
        return 100
    naplate, pozivi, greske_modela = [], [], []
    b.greske_modela = greske_modela

    async def _consume(*a, **kw):
        naplate.append(1)

    async def _kvalitet(tekst, tip):
        return {"confidence_score": 0.5, "detail": {}}
    monkeypatch.setattr(US, "get_policy", _politika)
    monkeypatch.setattr(US.UsageService, "balance", staticmethod(_stanje))
    monkeypatch.setattr(US.UsageService, "consume", staticmethod(_consume))
    monkeypatch.setattr(R, "retrieve_documents", lambda *a, **kw: ([], {}))
    monkeypatch.setattr(QG, "evaluate_draft_quality", _kvalitet)
    pravi = MA._pozovi_nacrt_api

    def _brojac(client, system, user_msg):
        pozivi.append(user_msg)  # poruka modelu se čuva samo za dijagnozu izvršioca (ne ide označivačima)
        if SUVO:
            from tests.nacrt_json_zamena import kao_json
            return kao_json(lambda c, s, u: types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content="Tuzilac ostaje pri zahtevu."))]))(client, system, user_msg)
        import socket
        from tests import ns005_harness as H
        cuvar = socket.socket.connect
        try:
            # ns005 harness zabranjuje spoljnu mrežu za ceo proces; otvara se samo za trajanje stvarnog poziva modela
            socket.socket.connect = H._orig_connect
            resp = pravi(client, system, user_msg)
            b.sirovo = [resp.choices[0].message.content, resp.choices[0].finish_reason]
            return resp
        except BaseException as e:  # samo vrsta i status, nikad poruka (može sadržati deo ključa)
            greske_modela.append(f"{type(e).__name__} {getattr(e, 'status_code', '')} uzrok={type(e.__cause__).__name__}:{type(getattr(e.__cause__, '__cause__', None)).__name__}".strip())
            raise
        finally:
            socket.socket.connect = cuvar
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", _brojac)
    if not SUVO:
        monkeypatch.setenv("OPENAI_API_KEY", _kljuc_iz_env())
    b.odlozeni, b.sirovo = [], None

    class _Asyncio:
        def __getattr__(self, ime):
            return getattr(asyncio, ime)

        def create_task(self, coro):
            b.odlozeni.append(coro)
    monkeypatch.setattr(MA, "asyncio", _Asyncio())
    b.podrazumevano.setdefault("staging_memory", {}).update({"status": "pending", "is_lawyer_approved": False,
                                                            "pinecone_indexed": False, "quality_detail": {}, "naziv": ""})
    return k, b, naplate, pozivi


def _docx_tekst(k, sid):
    r = k.post(f"/api/staging/{sid}/docx", headers=A)
    if r.status_code != 200:
        return r.status_code, None, (r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text)
    import docx
    d = docx.Document(io.BytesIO(r.content))
    return 200, "\n".join(p.text for p in d.paragraphs), None


@pytest.mark.parametrize("i", range(N))
@pytest.mark.parametrize("sc", SCENARIJI)
def test_generisi(okruzenje, sc, i):
    from shared.nacrt_za_sud import GRANICA
    k, b, naplate, pozivi = okruzenje
    pid, doks, _ = primi_spis(k, b, dokumenti=spis(sc))
    r = k.post("/api/agents/run", json={"agent": "drafting", "task": ZAHTEV, "predmet_id": pid}, headers=A)
    zapis = {"scenarij": sc, "indeks": i, "suvo": SUVO, "status": r.status_code, "pozivi_modela": None, "naplate": None}
    o = r.json() if r.status_code == 200 else {"greska": r.text[:500]}
    zapis["odgovor_rute"] = {kl: o.get(kl) for kl in ("tekst_za_sud", "izostavljeno_iz_teksta_za_sud", "greska")}
    while b.odlozeni:
        asyncio.run(b.odlozeni.pop(0))
    st = [s for s in b.tabele["staging_memory"] if s.get("predmet_id") == pid]
    zapis["na_pregledu"] = len(st)
    if st:
        tekst = st[0]["tekst"]
        sud, interno = tekst.split(GRANICA, 1) if tekst.count(GRANICA) == 1 else (tekst, "")
        zapis["tekst_za_sud"], zapis["interno"] = sud.rstrip(), GRANICA + interno
        zapis["docx"] = dict(zip(("status", "tekst", "razlog"), _docx_tekst(k, st[0]["id"])))
        # simulirana ispravka advokata: redovi sa čuvarom mesta se uklanjaju, pa PATCH i ponovni izvoz
        ispravljen = "\n".join(red for red in sud.split("\n") if "[IZOSTAVLJENO" not in red).rstrip()
        zapis["ispravka_advokata"] = {"uklonjeno_redova": sud.count("[IZOSTAVLJENO")}
        p = k.patch(f"/api/staging/{st[0]['id']}/tekst", json={"tekst": ispravljen + "\n\n" + GRANICA + interno}, headers=A)
        zapis["ispravka_advokata"]["patch"] = p.status_code
        zapis["ispravka_advokata"]["docx"] = dict(zip(("status", "tekst", "razlog"), _docx_tekst(k, st[0]["id"])))
    zapis["pozivi_modela"], zapis["naplate"] = len(pozivi), len(naplate)
    zapis["poruka_modelu"] = pozivi[-1] if pozivi else None
    zapis["greske_modela"] = list(b.greske_modela)
    zapis["sirov_izlaz_modela"] = getattr(b, "sirovo", None)  # samo za dijagnozu izvršioca
    zapis["dokumenti_spisa"] = [{"oznaka": x["oznaka"], "ime": x["ime"], "tekst": gc.tekst(x)} for x in spis(sc)]
    os.makedirs(OUT, exist_ok=True)
    ime = f"{'SUVO_' if SUVO else ''}{sc}_{i:02d}.json"
    json.dump(zapis, open(os.path.join(OUT, ime), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    assert r.status_code in (200, 502), r.text[:300]
