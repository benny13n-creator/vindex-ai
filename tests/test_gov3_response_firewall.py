# -*- coding: utf-8 -*-
"""
Governance Wave 3 — Response Firewall: dokaz izvršavanja.

PRAVILO IZNAD SVIH

Test koji može biti zelen dok je kontrola mrtva nije test. Zato se ovde ni na
jednom mestu ne tvrdi „`response_firewall` postoji" — svaka tvrdnja ide kroz
STVARNI SDK poziv i meri šta se vrati pozivaocu.

ZAŠTO JE OVO POUZDANO
`shared/ai_client.py::_patch_prompt_guard` zamenjuje metodu SDK KLASE. Testovi
ispod prave običan `openai.OpenAI(...)` klijent i zovu
`client.chat.completions.create(...)` — isto što radi bilo koji od 91
produkcionog pozivaoca. `_orig_create` se zamenjuje lažnim provajderom, pa
nijedan bajt ne odlazi na mrežu.

ŠTA FIREWALL NE POKRIVA — testirano kao granica, ne prećutano
  - `services/voice_orchestrator.py` (sirov WSS) — ne prolazi kroz SDK
  - `app/services/retrieve.py::_cohere_rerank` (drugi SDK)
  - embeddings i audio (nemaju chat oblik) — v. `test_gov2_runtime_interception.py`
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from security.response_firewall import (  # noqa: E402
    ALLOW, BLOCK, ESCALATE, ResponseBlocked, Verdict,
    enforce, inspect_chat_response,
)

_PITANJE = [{"role": "user", "content": "Koji je rok za žalbu na presudu?"}]


@pytest.fixture(scope="module", autouse=True)
def patched():
    import shared.ai_client as ac
    ac._patch_openai_module()
    ac._patch_prompt_guard()
    return ac


def _odgovor(sadrzaj="Rok je 15 dana.", *, choices=True, tool_calls=None, model="gpt-4o"):
    r = MagicMock()
    r.usage = None
    r.model = model
    if not choices:
        r.choices = []
        return r
    poruka = MagicMock()
    poruka.content = sadrzaj
    poruka.tool_calls = tool_calls
    izbor = MagicMock()
    izbor.message = poruka
    r.choices = [izbor]
    return r


def _pozovi(odgovor, **kwargs):
    """Pravi SDK poziv sa lažnim provajderom. Vraća ono što dobije POZIVALAC."""
    import openai
    import shared.ai_client as ac
    with patch.object(ac, "_orig_create", lambda self, *a, **k: odgovor):
        klijent = openai.OpenAI(api_key="sk-fake")
        return klijent.chat.completions.create(
            model="gpt-4o", messages=_PITANJE, **kwargs
        )


# ─── 1. IZVRŠAVANJE KROZ STVARNI SDK POZIV ──────────────────────────────────

def test_a_ispravan_odgovor_stize_do_pozivaoca():
    """Pozitivna kontrola. Bez nje bi svaki BLOCK test prolazio vakuumski."""
    ocekivan = _odgovor("Rok za žalbu je 15 dana od dostavljanja.")
    dobijen = _pozovi(ocekivan)
    assert dobijen is ocekivan
    assert dobijen.choices[0].message.content.startswith("Rok za žalbu")


@pytest.mark.parametrize("opis,odg", [
    ("prazna lista izbora", _odgovor(choices=False)),
    ("sadržaj None bez tool_calls", _odgovor(None)),
    ("prazan string", _odgovor("   ")),
])
def test_b_pokvaren_odgovor_NE_STIZE_do_pozivaoca(opis, odg):
    """Srž firewall-a: pokvaren odgovor mora pući, ne stići kao sadržaj.

    Prazan odgovor koji stigne advokatu izgleda kao „nema šta da se kaže o ovom
    predmetu". Greška je iskrenija od praznine.
    """
    with pytest.raises(ResponseBlocked) as e:
        _pozovi(odg)
    assert e.value.razlozi, f"{opis}: blokada bez navedenog razloga"


def test_c_trazen_json_a_odgovor_nije_json_JE_BLOKIRAN():
    """Provera koja hvata VEĆ DOKAZAN defekt ovog repozitorijuma.

    `strategija.py:641` na neuspeh parsiranja vraća
    `{"error":..., "raw": raw[:300], "confidence":"NISKA"}`, i taj dict se
    `json.dumps`-uje u akumulirani `kontekst` — pa fragment pokvarenog odgovora
    postaje „analiza prethodnog koraka" za svih 5 narednih koraka
    (nalaz C-01, `docs/beta_war/BETA_TRUTH_MATRIX.md`).

    Sada takav odgovor ne stiže ni do te grane.
    """
    with pytest.raises(ResponseBlocked) as e:
        _pozovi(_odgovor("Evo analize: ovo nije JSON."),
                response_format={"type": "json_object"})
    assert "JSON" in " ".join(e.value.razlozi)


def test_ng_validan_json_prolazi():
    """Negativna kontrola za `test_c`.

    Bez ovoga bi `test_c` prolazio i da firewall blokira SVAKI odgovor kad je
    tražen JSON — što bi oborilo desetine produkcionih putanja.
    """
    payload = json.dumps({"confidence": "SREDNJA", "summary": "ok"})
    dobijen = _pozovi(_odgovor(payload), response_format={"type": "json_object"})
    assert json.loads(dobijen.choices[0].message.content)["confidence"] == "SREDNJA"


def test_d_tool_calls_bez_sadrzaja_PROLAZE():
    """Odgovor sa pozivom alata legitimno nema tekst.

    Da ovo nije izuzeto, firewall bi oborio jedinu tool-capable putanju u
    sistemu.
    """
    dobijen = _pozovi(_odgovor(None, tool_calls=[MagicMock()]))
    assert dobijen.choices[0].message.tool_calls


# ─── 2. FAIL-CLOSED ─────────────────────────────────────────────────────────

def test_e_greska_u_samoj_proveri_ZATVARA(monkeypatch):
    """Najvažnija odluka u ugovoru.

    Ako firewall ne može da odluči, odgovor nije pregledan — a nepregledan
    odgovor se ne sme predstaviti kao pregledan. Domet ove odluke je 91
    putanja, zato je površina provera deterministička i minimalna.
    """
    import security.response_firewall as fw

    def _pukni(*a, **k):
        raise RuntimeError("provera pukla")

    monkeypatch.setattr(fw, "inspect_chat_response", _pukni)
    with pytest.raises(ResponseBlocked) as e:
        fw.enforce(_odgovor(), operation="test")
    assert "nije uspela" in str(e.value)


def test_ng_fail_closed_nije_uvek_blokada():
    """Kontrola za `test_e`: bez greške isti put propušta."""
    odg = _odgovor()
    assert enforce(odg, operation="test", correlation_id="c", user_id="u") is odg


# ─── 3. DEGRADACIJA JE VIDLJIVA, NE TIHA ────────────────────────────────────

def test_f_nedostatak_identiteta_je_ESCALATE_a_ne_blokada():
    """Postoje legitimne putanje bez korisnika (cron, background agenti).

    Njih ne treba obarati — ali se ne sme ni prećutati, jer bez identiteta
    zapis o pozivu ne može da se pripiše nikome.
    """
    v = inspect_chat_response(_odgovor(), operation="cron", model="gpt-4o")
    assert v.decision == ESCALATE
    assert v.allowed is True
    assert any("correlation_id" in d for d in v.degradacije)
    assert any("user_id" in d for d in v.degradacije)


def test_g_pun_identitet_daje_ALLOW():
    v = inspect_chat_response(
        _odgovor(), operation="op", model="gpt-4o",
        correlation_id="c-1", user_id="u-1",
    )
    assert v.decision == ALLOW
    assert not v.degradacije


def test_h_stream_objekat_je_ESCALATE_ne_LAZNO_ALLOW():
    """Streaming odgovor nema `choices` — firewall ne vidi sadržaj.

    Ne sme se prijaviti kao pregledan. `ESCALATE` je istina: prošao je, ali
    nije proveren. Danas u produkciji nema `stream=True` ni na jednoj AI
    putanji (izmereno u Wave 2), pa je ovo ugovor za budućnost, ne živa grana.
    """
    stream = MagicMock()
    stream.choices = None
    v = inspect_chat_response(stream, operation="stream")
    assert v.decision == ESCALATE
    assert v.allowed is True
    assert any("nije pregledan" in d for d in v.degradacije)


# ─── 4. NEGATIVNA KONTROLA NAD SAMIM TESTOM ────────────────────────────────

def test_ng_lazni_provajder_se_stvarno_koristi():
    """Dokaz da testovi iznad mere firewall, a ne mrežnu grešku.

    Da `_orig_create` nije zamenjen, poziv bi pao na autentifikaciji sa
    `sk-fake` i svaki `pytest.raises` bi „prolazio" iz pogrešnog razloga.
    """
    marker = _odgovor("MARKER-PROVAJDERA-8891")
    dobijen = _pozovi(marker)
    assert dobijen.choices[0].message.content == "MARKER-PROVAJDERA-8891"
