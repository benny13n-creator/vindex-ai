# -*- coding: utf-8 -*-
"""
Governance Wave 4 — životni ciklus patch-a i istinitost zastavice.

CENTRALNO PITANJE SPRINTA

„Može li AI zahtev ili odgovor zaobići governance sloj a da sistem to ne zna?"

Do Wave 4 odgovor je bio **DA**, i to ne hipotetički:

`shared/ai_client.py` je na neuspeh uvoza SDK klasa logovao grešku i postavljao
`_guard_patched = True`, pa se vraćao. Aplikacija bi se podigla bez ijednog
prompt guard-a, bez Response Firewall-a, bez provenance-a i bez timeout-a — a
jedina promenljiva koja opisuje stanje tvrdila bi da je patch primenjen. Wave 2
je izmerio da tu zastavicu **niko ne čita** van internog idempotency check-a,
pa nijedan health check to nije mogao da razlikuje.

Jedna promenljiva je nosila dve različite tvrdnje: „pokušano" i „aktivno".

ŠTA JE PROMENJENO

  `_guard_patched`  → i dalje znači „ne pokušavaj ponovo" (idempotencija)
  `_guard_active`   → NOVA, nosi istinu: kontrole se stvarno izvršavaju
  `governance_status()` → jedina javna tvrdnja
  `/api/version.governance` → izlaže je spolja

Misija je izričito tražila: „Ako pronađeš bilo kakav `_guard_patched = True` pre
stvarnog uspeha patch-a, dokaži posledicu testom. Ne prihvataj 'u praksi se to
neće desiti'." Ovaj fajl je taj dokaz.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def svez_modul(monkeypatch):
    """Sveža kopija `shared.ai_client` sa resetovanim globalnim stanjem.

    VRAĆA I SDK METODE, NE SAMO ZASTAVICE — i to nije opreznost nego ispravka
    stvarnog kvara koji je ovaj fajl proizveo.

    `_patch_prompt_guard` je idempotentan preko `_guard_patched`. Prva verzija
    ovog fixture-a resetovala je samo zastavice, pa je ponovni poziv patch-ovao
    VEĆ PATCH-OVANE klase: `_orig_create` bi postao već-obavijen `_guarded_create`,
    a wrapper bi se ugnezdio u samog sebe. Efekat se prelivao na kasnije testove
    u istoj sesiji i oborio je dva nevezana testa u
    `tests/test_uploaded_doc_api.py` — koji su do tada bili zeleni.

    Zato se snima i vraća kompletno stanje: zastavice, sačuvani originali, i
    same metode na SDK klasama.

    WAVE 9 (C2): fixture više NE zna interne detalje modula. Umesto ručnog
    vraćanja četiri klase (i zaboravljanja pete — audio, i šeste — otrovanih
    `openai.OpenAI` konstruktora, koje je Wave 9 uveo), poziva se
    `ac._uninstall_prompt_guard()`, produkciona funkcija koja je jedini vlasnik
    znanja o tome šta je sve instalirano. Snimak ispod ostaje kao POJAS I
    TREGERI: posle deinstalacije se vraća stanje koje je zateklo test sesiju
    (conftest uvozi `api`, pa je patch već instaliran kad ovaj fajl počne).
    """
    import shared.ai_client as ac
    from openai.resources.audio.speech import AsyncSpeech, Speech
    from openai.resources.audio.transcriptions import AsyncTranscriptions, Transcriptions
    from openai.resources.chat.completions.completions import (
        AsyncCompletions, Completions,
    )
    from openai.resources.embeddings import AsyncEmbeddings, Embeddings

    snimak = {
        "zastavice": (ac._guard_patched, ac._guard_active, ac._guard_failure_reason),
        "originali": (ac._orig_create, ac._orig_acreate, ac._orig_embed, ac._orig_aembed),
        # AUDIO se snima od Wave 9: `_uninstall_prompt_guard()` vraća i audio
        # klase (S2-1 grana), pa fixture koji vraća samo chat+embeddings ostavlja
        # audio TRAJNO nepatch-ovan za ostatak sesije. Izmereno, ne pretpostavljeno:
        # tri testa u `tests/test_sprint2_governance.py` su pala baš tako.
        "audio_originali": (ac._orig_stt, ac._orig_astt, ac._orig_tts, ac._orig_atts),
        "metode": (
            Completions.create, AsyncCompletions.create,
            Embeddings.create, AsyncEmbeddings.create,
        ),
        "audio_metode": (
            Transcriptions.create, AsyncTranscriptions.create,
            Speech.create, AsyncSpeech.create,
        ),
    }

    ac._guard_patched = False
    ac._guard_active = False
    ac._guard_failure_reason = None
    yield ac

    # Kanonska deinstalacija — vraća i chat, i embeddings, i audio, i eventualnu
    # fail-closed branu nad `openai.OpenAI`/`AsyncOpenAI`/Azure parnjacima.
    ac._uninstall_prompt_guard()

    ac._guard_patched, ac._guard_active, ac._guard_failure_reason = snimak["zastavice"]
    ac._orig_create, ac._orig_acreate, ac._orig_embed, ac._orig_aembed = snimak["originali"]
    ac._orig_stt, ac._orig_astt, ac._orig_tts, ac._orig_atts = snimak["audio_originali"]
    (Completions.create, AsyncCompletions.create,
     Embeddings.create, AsyncEmbeddings.create) = snimak["metode"]
    (Transcriptions.create, AsyncTranscriptions.create,
     Speech.create, AsyncSpeech.create) = snimak["audio_metode"]


# ─── 1. ISTINITOST ZASTAVICE ────────────────────────────────────────────────

def test_a_pre_patcha_governance_nije_aktivan(svez_modul):
    s = svez_modul.governance_status()
    assert s["attempted"] is False
    assert s["active"] is False


def test_b_posle_uspesnog_patcha_je_aktivan(svez_modul):
    svez_modul._patch_prompt_guard()
    s = svez_modul.governance_status()
    assert s["attempted"] is True
    assert s["active"] is True, "uspešan patch se ne prijavljuje kao aktivan"
    assert s["failure_reason"] is None


def test_c_NEUSPEH_PATCHA_NE_SME_da_izgleda_kao_uspeh(svez_modul, monkeypatch):
    """Srž Wave 4.

    Simulira se tačno ono što je ranije proizvodilo tihu rupu: uvoz SDK klasa
    pukne. Pre popravke bi `_guard_patched` bio True i ništa ne bi odalo da
    kontrole ne rade.
    """
    import builtins
    pravi_import = builtins.__import__

    def _pukni(ime, *a, **k):
        if ime == "openai.resources.chat.completions.completions":
            raise ImportError("simulirani pad SDK-a")
        return pravi_import(ime, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _pukni)
    svez_modul._patch_prompt_guard()

    s = svez_modul.governance_status()
    assert s["attempted"] is True, "idempotencija je izgubljena — patch bi se ponavljao"
    assert s["active"] is False, (
        "NEUSPEH PATCH-a SE PRIJAVLJUJE KAO USPEH. Aplikacija radi bez prompt "
        "guard-a i bez Response Firewall-a, a status tvrdi da je sve u redu — "
        "tačno rupa zbog koje Wave 4 postoji."
    )
    assert s["failure_reason"], "neuspeh bez razloga se ne može dijagnostikovati"
    assert "import" in s["failure_reason"].lower()


def test_d_idempotencija_je_ocuvana(svez_modul):
    """Drugi poziv ne sme ponovo da patch-uje (dvostruko obavijanje)."""
    svez_modul._patch_prompt_guard()
    prvi = svez_modul.governance_status()
    svez_modul._patch_prompt_guard()
    assert svez_modul.governance_status() == prvi


# ─── 2. IZLAGANJE — zastavica koju niko ne čita ne postoji ─────────────────

def test_e_api_version_objavljuje_stvarno_stanje():
    """Wave 2 je izmerio da `_guard_patched` niko ne čita van samog modula.

    Istinita zastavica koju nijedan endpoint ne izlaže i dalje bi bila
    nevidljiva na produkciji. Ovo dokazuje da je vidljiva.
    """
    import api
    odgovor = api.api_version()
    assert "governance" in odgovor, "/api/version ne objavljuje stanje governance-a"
    gov = odgovor["governance"]
    for kljuc in ("attempted", "active", "failure_reason"):
        assert kljuc in gov, f"nedostaje `{kljuc}`"
    assert gov["active"] is True, (
        "u test procesu je patch primenjen (conftest uvozi api), pa `active` "
        "mora biti True — ako nije, ili patch ne radi ili status laže"
    )


def test_f_status_ne_izlaze_nista_osetljivo():
    """`/api/version` je javan. Status sme da nosi zastavice i ime klase greške,
    nikad putanje, ključeve ni sadržaj."""
    import shared.ai_client as ac
    s = ac.governance_status()
    tekst = repr(s).lower()
    for zabranjeno in ("sk-", "api_key", "supabase", "password", "token", "c:\\", "/home/"):
        assert zabranjeno not in tekst, f"status izlaže `{zabranjeno}`"


# ─── 3. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

def test_ng_status_stvarno_razlikuje_dva_stanja(svez_modul, monkeypatch):
    """Bez ovoga bi `test_c` prolazio i da `active` uvek vraća False.

    Meri se OBA smera u istom testu, nad istim svežim modulom.
    """
    assert svez_modul.governance_status()["active"] is False
    svez_modul._patch_prompt_guard()
    assert svez_modul.governance_status()["active"] is True


def test_ng_zastavice_nisu_ista_promenljiva(svez_modul, monkeypatch):
    """Dokaz da razdvajanje nije kozmetičko.

    Posle simuliranog neuspeha jedna mora biti True (pokušano), druga False
    (nije aktivno). Da su ista promenljiva, ovo je nemoguće.
    """
    import builtins
    pravi = builtins.__import__

    def _pukni(ime, *a, **k):
        if ime == "openai.resources.chat.completions.completions":
            raise ImportError("pad")
        return pravi(ime, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _pukni)
    svez_modul._patch_prompt_guard()
    s = svez_modul.governance_status()
    assert s["attempted"] != s["active"], (
        "`attempted` i `active` imaju istu vrednost posle neuspeha — "
        "razdvajanje je poništeno i rupa je vraćena"
    )


# ─── 4. WAVE 9 (C2) — ŽIVOTNI CIKLUS PATCH-A ───────────────────────────────
#
# Wave 4 je razdvojio zastavice. Wave 9 stabilizuje SAM CIKLUS, jer je upravo
# on jednom već proizveo kvar van svog fajla: fixture je resetovao zastavice
# ali ne i SDK metode, pa je drugi `_patch_prompt_guard()` obavio VEĆ OBAVIJENE
# klase — `_orig_create` je postao već-obavijen `_guarded_create`, wrapper se
# ugnezdio u samog sebe i oborio dva zelena testa u
# `tests/test_uploaded_doc_api.py`.
#
# Dve mere, obe merene ispod:
#   1. `_uninstall_prompt_guard()` — produkcioni modul zna da se deinstalira,
#      pa fixture ne mora da poznaje njegove interne detalje.
#   2. `_vindex_guarded` marker — ugnežđivanje je nemoguće ČAK I ako neko
#      zaobiđe zastavicu (tj. tačno ono što je fixture radio).

def _lazni_odgovor(model="gpt-4o"):
    from unittest.mock import MagicMock
    r = MagicMock()
    r.usage = None
    r.model = model
    poruka = MagicMock()
    poruka.content = "Rok je 15 dana."
    poruka.tool_calls = None
    izbor = MagicMock()
    izbor.message = poruka
    r.choices = [izbor]
    return r


def _postavi_dno_lanca(ac, monkeypatch) -> dict:
    """Postavlja lažni provajder na DNO lanca i vraća brojač njegovih poziva.

    Mora se pozvati PRE eventualnog drugog `_patch_prompt_guard()`: ugnežđivanje
    živi upravo u `_orig_create`, pa test koji ga zameni POSLE ugnežđivanja
    briše baš ono što meri.
    """
    import security.ai_forensics as forensics

    brojac = {"n": 0}

    def _detektor(self, *a, **k):
        brojac["n"] += 1
        return _lazni_odgovor()

    async def _bez_provenance(**kwargs):
        return None

    monkeypatch.setattr(forensics, "log_provenance_from_wrapper", _bez_provenance)
    monkeypatch.setattr(ac, "_orig_create", _detektor, raising=False)
    return brojac


def _jedan_logicki_poziv():
    import openai
    openai.OpenAI(api_key="sk-fake").chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": "Rok za žalbu?"}],
    )


def _broj_poziva_originala(ac, monkeypatch) -> int:
    """Koliko puta se `_orig_create` pozove za JEDAN logički SDK poziv.

    Mora biti tačno 1. Više znači da je wrapper ugnežđen u samog sebe — tada se
    svaki AI poziv duplira (dvostruka naplata provajderu), a i guard i firewall
    se izvršavaju dva puta nad istim sadržajem.
    """
    brojac = _postavi_dno_lanca(ac, monkeypatch)
    _jedan_logicki_poziv()
    return brojac["n"]


def test_w9_a_svez_proces_pa_uspesan_patch(svez_modul, monkeypatch):
    """Osnovni ciklus: pre patch-a ništa, posle patch-a jedan sloj."""
    assert svez_modul.governance_status()["active"] is False
    svez_modul._patch_prompt_guard()
    assert svez_modul.governance_status()["active"] is True
    assert _broj_poziva_originala(svez_modul, monkeypatch) == 1


def test_w9_b_DVOSTRUKI_patch_NE_UGNEZDJUJE_wrapper(svez_modul, monkeypatch):
    """Srž C2, i jedini test koji bi uhvatio stvarni kvar iz prethodnog sprinta.

    Zastavica se NAMERNO zaobilazi (`_guard_patched = False`) — to je tačno
    ono što je fixture radio. Bez strukturne zaštite (`_vindex_guarded`) drugi
    patch bi obavio već obavijene klase i `_orig_create` bi se pozvao dvaput.
    """
    svez_modul._patch_prompt_guard()
    # Dno lanca se postavlja PRE drugog patch-a — inače bi zamena `_orig_create`
    # obrisala upravo ugnežđivanje koje test traži.
    brojac = _postavi_dno_lanca(svez_modul, monkeypatch)
    prvi_orig = svez_modul._orig_create

    svez_modul._guard_patched = False        # zaobilaženje zastavice
    svez_modul._patch_prompt_guard()

    assert svez_modul._orig_create is prvi_orig, (
        "`_orig_create` je prepisan već-obavijenim wrapperom — sledeći poziv "
        "ulazi u samog sebe (u praksi: RecursionError na svakom AI pozivu)"
    )
    _jedan_logicki_poziv()
    assert brojac["n"] == 1, (
        "jedan logički poziv nije stigao do provajdera tačno jednom — "
        "wrapper je ugnežđen"
    )


def test_w9_c_deinstalacija_vraca_originalne_metode(svez_modul):
    """Modul koji zna da se instalira mora znati i da se deinstalira."""
    from openai.resources.chat.completions.completions import (
        AsyncCompletions, Completions,
    )
    from openai.resources.embeddings import AsyncEmbeddings, Embeddings

    svez_modul._patch_prompt_guard()
    assert getattr(Completions.create, "_vindex_guarded", False) is True

    svez_modul._uninstall_prompt_guard()

    for klasa in (Completions, AsyncCompletions, Embeddings, AsyncEmbeddings):
        assert getattr(klasa.create, "_vindex_guarded", False) is False, (
            f"{klasa.__name__}.create je ostao obavijen posle deinstalacije"
        )
    s = svez_modul.governance_status()
    assert s["attempted"] is False and s["active"] is False
    assert svez_modul._orig_create is None


def test_w9_d_deinstalacija_pa_ponovna_instalacija(svez_modul, monkeypatch):
    """Redosled A→B→A: teardown pa setup ne sme da ostavi ugnežđen sloj."""
    svez_modul._patch_prompt_guard()
    svez_modul._uninstall_prompt_guard()
    svez_modul._patch_prompt_guard()

    assert svez_modul.governance_status()["active"] is True
    assert _broj_poziva_originala(svez_modul, monkeypatch) == 1


def test_w9_e_deinstalacija_bez_prethodne_instalacije_je_bezbedna(svez_modul):
    """Teardown mora biti bezuslovno pozivljiv — inače svaki fixture mora da
    zna da li je setup uspeo, što je upravo znanje koje ne sme da nosi."""
    svez_modul._uninstall_prompt_guard()  # ne sme da digne
    assert svez_modul.governance_status()["active"] is False


def test_w9_f_retry_posle_neuspeha_daje_aktivan_guard(svez_modul, monkeypatch):
    """Neuspeh ne sme trajno da zaključa mogućnost oporavka."""
    import builtins
    pravi = builtins.__import__

    def _pukni(ime, *a, **k):
        if ime == "openai.resources.chat.completions.completions":
            raise ImportError("pad")
        return pravi(ime, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _pukni)
    svez_modul._patch_prompt_guard()
    assert svez_modul.governance_status()["active"] is False
    assert svez_modul.governance_status()["ai_blocked"] is True

    monkeypatch.undo()
    svez_modul._guard_patched = False
    svez_modul._patch_prompt_guard()

    s = svez_modul.governance_status()
    assert s["active"] is True
    assert s["ai_blocked"] is False, (
        "fail-closed brana je ostala i posle uspešnog patch-a — AI je mrtav "
        "bez razloga"
    )


def test_w9_g_deinstalacija_sklanja_i_fail_closed_branu(svez_modul, monkeypatch):
    """Teardown mora da počisti SVE što je setup mogao da instalira.

    Ovo je nova verzija istog propusta: fixture koji vrati četiri SDK metode
    ali ne i otrovane `openai.OpenAI` konstruktore ostavlja ceo naredni deo
    sesije bez ijednog AI poziva.
    """
    import builtins
    import openai
    pravi = builtins.__import__

    def _pukni(ime, *a, **k):
        if ime == "openai.resources.chat.completions.completions":
            raise ImportError("pad")
        return pravi(ime, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _pukni)
    svez_modul._patch_prompt_guard()
    with pytest.raises(svez_modul.GovernanceUnavailable):
        openai.OpenAI(api_key="sk-fake")

    monkeypatch.undo()
    svez_modul._uninstall_prompt_guard()

    openai.OpenAI(api_key="sk-fake")  # ne sme da digne
    assert svez_modul.governance_status()["ai_blocked"] is False


def test_w9_h_redosled_B_pa_A_deinstalacija_pre_instalacije(svez_modul, monkeypatch):
    """Obrnut redosled (B→A): deinstalacija na svežem modulu, pa instalacija."""
    svez_modul._uninstall_prompt_guard()
    svez_modul._patch_prompt_guard()
    assert svez_modul.governance_status()["active"] is True
    assert _broj_poziva_originala(svez_modul, monkeypatch) == 1
