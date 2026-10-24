# -*- coding: utf-8 -*-
"""VCR002 Release Closure — FIX 2: oporavak plaćenog niza savetnika posle pada radnika.

Reprodukcija (stvarna ruta `/api/agents/pipeline`, stvaran `shared/idempotency.py` middleware, T06 harness): radnik
umire POSLE prvog plaćenog koraka, a PRE nego što trajni zahtev bude završen.

Šta merenje pokazuje o POSTOJEĆOJ trajnoj infrastrukturi:
  * red idempotencije ostaje IN_PROGRESS (nema lažnog „završeno“) — ispravno;
  * isti ključ dobija 409 IN_PROGRESS zauvek — nema puta do već plaćenog rada;
  * izlaz plaćenog koraka nije upisan NIGDE (nijedna tabela ga ne sadrži) — isporučen rad nije prepoznatljiv;
  * naplata je red bez veze sa zahtevom ili korakom — ne može se uskladiti;
  * nova radnja advokata (novi ključ) ponovo plaća isti korak.
Bez nove trajne evidencije koraka (nova šema = posebno odobrenje) oporavak se ne može učiniti bezbednim, pa je ulaz
za niz u V2 ISKLJUČEN (`frontend-v2-ng/index.html`), a pojedinačni i paralelni rad ostaju. Ovi testovi su dokaz za tu
odluku i padaju ako se ponašanje promeni — tada se ulaz može ponovo razmotriti.
"""
import json
import re
import uuid
from pathlib import Path

from tests.test_vcr002_t06_niz_savetnika import _niz, niz  # noqa: F401
from tests.nacrt_json_zamena import kao_json

KOREN = Path(__file__).resolve().parent.parent
PLACENI_IZLAZ = "ISTRAZIVANJE-KORAK-1: placen rad koji se ne sme izgubiti"


class _Pad(BaseException):
    """Smrt radnika: ne hvata je nijedan `except Exception`."""


def _ubij_posle_prvog_koraka(st, monkeypatch):
    import routers.multi_agent as MA
    pravi = MA._pozovi_agent_api

    def _model(client, system, user_msg):
        agent = next(a for a, c in MA._AGENTS.items() if c["system"] == system)
        if agent == "litigation":
            raise _Pad("radnik je umro tokom drugog koraka")
        return pravi(client, system, user_msg)
    monkeypatch.setattr(MA, "_pozovi_agent_api", _model)
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", kao_json(_model, bez_pravila=True))     # C3b: nacrt iz spisa = JSON
    st["odgovori"]["research"] = PLACENI_IZLAZ


def _pokreni_uz_pad(k, telo, kljuc):
    try:
        r = _niz(k, telo, kljuc=kljuc)
    except _Pad:
        return None
    return r


TELO = {"opis": "Pripremi odgovor na tužbu za naknadu štete.", "predmet_id": "pred-A-1",
        "pipeline": ["research", "litigation", "drafting"]}


def test_pad_posle_placenog_koraka_red_ostaje_u_toku_bez_laznog_zavrsetka(niz, monkeypatch):
    k, b, st = niz
    _ubij_posle_prvog_koraka(st, monkeypatch)
    kljuc = str(uuid.uuid4())
    r = _pokreni_uz_pad(k, TELO, kljuc)
    assert r is None or r.status_code >= 500
    assert st["naplate"] == [("uid-A", "multi_agent", None)]            # prvi korak JE naplaćen
    [red] = [z for z in b.tabele["v2_mutation_idempotency"] if z["idempotency_key"] == kljuc]
    assert red["state"] == "IN_PROGRESS" and not red.get("response_payload_enc")
    # isti ključ: iskren 409 „ishod nepoznat“, model se ne zove, ništa se ne naplaćuje
    pozivi = len(st["pozivi"])
    r2 = _niz(k, TELO, kljuc=kljuc)
    assert r2.status_code == 409 and r2.json()["kod"] == "IDEMPOTENCY_IN_PROGRESS"
    assert len(st["pozivi"]) == pozivi and len(st["naplate"]) == 1


def test_placen_izlaz_nije_nigde_trajno_zabelezen_pa_oporavak_nije_moguc(niz, monkeypatch):
    k, b, st = niz
    _ubij_posle_prvog_koraka(st, monkeypatch)
    _pokreni_uz_pad(k, TELO, str(uuid.uuid4()))
    sve = json.dumps(b.tabele, ensure_ascii=False, default=str)
    assert PLACENI_IZLAZ not in sve, "izlaz koraka je sada trajno zabeležen — preispitati isključenje niza u V2"


def test_nova_radnja_posle_pada_ponovo_placa_isti_korak(niz, monkeypatch):
    k, b, st = niz
    _ubij_posle_prvog_koraka(st, monkeypatch)
    _pokreni_uz_pad(k, TELO, str(uuid.uuid4()))
    _pokreni_uz_pad(k, TELO, str(uuid.uuid4()))
    istrazivanja = [a for a, _ in st["pozivi"] if a == "research"]
    assert len(istrazivanja) == 2 and len(st["naplate"]) == 2           # isti plaćeni korak, dva puta


def test_v2_ne_nudi_niz_dok_oporavak_nije_bezbedan():
    html = (KOREN / "frontend-v2-ng" / "index.html").read_text(encoding="utf-8")
    opcije = dict(re.findall(r'<option value="(\w+)"([^>]*)>', html[html.index('id="ag-nacin"'):][:800]))
    assert "disabled" in opcije["niz"], "ulaz za niz savetnika u V2 mora ostati isključen"
    assert "disabled" not in opcije["pojedinacno"] and "disabled" not in opcije["paralelno"]
    js = (KOREN / "frontend-v2-ng" / "src" / "agenti-predmeta.js").read_text(encoding="utf-8")
    assert re.search(r"niz: \{ iskljucen: true,", js), "katalog savetnika ne sme ponovo da uključi niz"
    assert "op.disabled = !!NACINI[n].iskljucen ||" in js
