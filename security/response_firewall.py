# -*- coding: utf-8 -*-
"""
Vindex AI — security/response_firewall.py

CANONICAL RESPONSE FIREWALL V1 (Governance Wave 3)

ZAŠTO POSTOJI

Wave 2 je izmerio da izlazna governance kontrola pokriva 2 od 93 produkcione AI
putanje. Ulazna strana je pokrivena od SEC-003 (`security/prompt_guard.py`,
podignut monkey-patch-om nad SDK klasama). Izlazna nije postojala kao sloj —
pretraga za `response_firewall`/`output_guard`/`sanitize_response` davala je
nula pogodaka.

GDE STOJI, I ZAŠTO BAŠ TU

Ne kao 93 pojedinačna poziva. `shared/ai_client.py::_patch_prompt_guard`
zamenjuje metode na SAMIM SDK KLASAMA (`Completions.create`,
`AsyncCompletions.create`). Posledica koja je merena, ne pretpostavljena: i
direktan `client.chat.completions.create(...)` iz bilo kog fajla prolazi kroz
wrapper, jer je zamenjena metoda klase, ne pozivno mesto. To je jedina tačka u
ovoj arhitekturi kroz koju se ne može proći slučajno.

Firewall se zove na `ai_client.py` odmah posle povratka provajdera, na istom
mestu gde `_capture_chat_provenance` već hvata odgovor.

ŠTA OVO **NE** POKRIVA — i to je deo ugovora, ne propust

  - `services/voice_orchestrator.py` — sirov WebSocket ka OpenAI Realtime.
    Ne prolazi kroz SDK uopšte, pa ga patch fizički ne vidi.
  - `app/services/retrieve.py::_cohere_rerank` — drugi SDK. Latentan u
    produkciji (paket nije u `requirements.txt`), ali arhitektonski van dosega.

Te dve putanje MOGU zaobići firewall. To je izmereno i prijavljeno, ne
zaokruženo naviše.

ODLUKA O FAIL-CLOSED I NJEN DOMET

Ugovor traži fail-closed. To znači da greška U SAMOM FIREWALL-u obara AI poziv.
Domet te odluke je 91 putanja — svaka. Zato je površina provera namerno
minimalna i isključivo deterministička: nema heuristike, nema modela koji
ocenjuje model, nema mrežnog poziva. Svaka provera je čitanje već postojećeg
objekta u memoriji.

Ako se ikad doda provera koja može da padne iz razloga nevezanog za sam
odgovor, fail-closed postaje neprihvatljiv i ugovor mora da se preispita —
ne da se tiho pretvori u `except: pass`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("vindex.response_firewall")

# ─── Ishodi ─────────────────────────────────────────────────────────────────
# Namerno tri, ne više. Svaki dodatni stanje traži pozivaoca koji zna šta sa
# njim da radi; stanje bez potrošača je dekoracija.
ALLOW = "ALLOW"        # odgovor sme dalje
BLOCK = "BLOCK"        # odgovor NE SME dalje; pozivalac diže izuzetak
ESCALATE = "ESCALATE"  # odgovor sme dalje, ali nosi oznaku degradiranog stanja


class ResponseBlocked(Exception):
    """Odgovor provajdera je odbijen na izlazu.

    Namerno NIJE podklasa `openai.APIError` — `shared/llm_retry.py` ponavlja
    samo provajderske greške, a ponavljanje odbijenog odgovora bi samo potrošilo
    novac na isti ishod.
    """

    def __init__(self, razlozi: list[str], operation: str = "", model: str = ""):
        self.razlozi = razlozi
        self.operation = operation
        self.model = model
        super().__init__(
            f"Odgovor modela je odbijen na izlazu ({operation or 'nepoznata operacija'}): "
            + "; ".join(razlozi)
        )


@dataclass
class Verdict:
    decision: str
    razlozi: list[str] = field(default_factory=list)
    degradacije: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision in (ALLOW, ESCALATE)


# ─── Pomoćne, čiste funkcije ────────────────────────────────────────────────

def _trazen_json(kwargs: dict) -> bool:
    rf = (kwargs or {}).get("response_format")
    if isinstance(rf, dict):
        return rf.get("type") in ("json_object", "json_schema")
    return False


def _izvuci_poruku(response: Any):
    izbori = getattr(response, "choices", None)
    if not izbori:
        return None, None
    prvi = izbori[0]
    poruka = getattr(prvi, "message", None)
    if poruka is None:
        return None, None
    return getattr(poruka, "content", None), getattr(poruka, "tool_calls", None)


# ─── Ugovor ─────────────────────────────────────────────────────────────────

def inspect_chat_response(
    response: Any,
    *,
    kwargs: Optional[dict] = None,
    operation: str = "",
    provider: str = "openai",
    model: str = "",
    correlation_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Verdict:
    """Deterministička provera odgovora chat-completion poziva.

    Vraća `Verdict`; NE diže izuzetak za odbijen odgovor — odluku o dizanju
    donosi pozivalac (`shared/ai_client.py`), da bi ista funkcija mogla da se
    koristi i za merenje bez posledica.

    Diže izuzetak samo ako je sama provera nemoguća — to je fail-closed grana i
    ona je namerna.
    """
    kwargs = kwargs or {}
    razlozi: list[str] = []
    degradacije: list[str] = []

    # ── 1. Integritet odgovora ──────────────────────────────────────────────
    if response is None:
        return Verdict(BLOCK, ["odgovor je None"])

    sadrzaj, tool_calls = _izvuci_poruku(response)

    if getattr(response, "choices", None) is None:
        # Streaming objekat nema `choices`. To NIJE greška — ali jeste stanje u
        # kome firewall ne vidi sadržaj, pa se ne sme prijaviti kao pregledan.
        return Verdict(ESCALATE, [], ["odgovor nije pregledan (stream ili nepoznat oblik)"])

    if not response.choices:
        return Verdict(BLOCK, ["provajder je vratio praznu listu izbora"])

    if sadrzaj is None and not tool_calls:
        # Prazan odgovor koji stigne do advokata izgleda kao „nema šta da se
        # kaže o ovom predmetu". Greška je iskrenija od praznine.
        return Verdict(BLOCK, ["odgovor nema ni sadržaj ni poziv alata"])

    if sadrzaj is not None and not isinstance(sadrzaj, str):
        return Verdict(BLOCK, [f"sadržaj nije string nego {type(sadrzaj).__name__}"])

    if sadrzaj is not None and not sadrzaj.strip() and not tool_calls:
        return Verdict(BLOCK, ["sadržaj je prazan string"])

    # ── 2. Ugovor o formatu ─────────────────────────────────────────────────
    # Ovo je jedina provera koja hvata VEĆ DOKAZAN defekt ovog repozitorijuma.
    # `strategija.py:641` na neuspeh parsiranja vraća
    # `{"error": ..., "raw": raw[:300], "confidence": "NISKA"}` i taj dict se
    # `json.dumps`-uje u akumulirani `kontekst`, pa fragment pokvarenog odgovora
    # postaje „analiza prethodnog koraka" za svih 5 narednih koraka
    # (nalaz C-01 u docs/beta_war/BETA_TRUTH_MATRIX.md).
    #
    # Kad je pozivalac izričito tražio JSON, odgovor koji nije JSON je pokvaren
    # odgovor — ne sadržaj o kome treba rezonovati.
    if _trazen_json(kwargs) and sadrzaj is not None:
        try:
            json.loads(sadrzaj)
        except (json.JSONDecodeError, ValueError):
            razlozi.append("tražen je JSON, a odgovor nije validan JSON")

    # ── 3. Governance metapodaci ────────────────────────────────────────────
    # Nedostatak identiteta NE obara odgovor — postoje legitimne putanje bez
    # korisnika (cron, background agenti). Ali se ne sme prećutati, jer bez
    # toga zapis o pozivu ne može da se pripiše nikome.
    if not model and not getattr(response, "model", None):
        degradacije.append("model nije poznat")
    if not correlation_id:
        degradacije.append("correlation_id nedostaje")
    if not user_id:
        degradacije.append("user_id nedostaje")

    if razlozi:
        return Verdict(BLOCK, razlozi, degradacije)
    if degradacije:
        return Verdict(ESCALATE, [], degradacije)
    return Verdict(ALLOW)


def enforce(
    response: Any,
    *,
    kwargs: Optional[dict] = None,
    operation: str = "",
    provider: str = "openai",
    model: str = "",
    correlation_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Any:
    """Primenjuje presudu. FAIL-CLOSED.

    Tri ishoda, svi eksplicitni:

      ALLOW     -> odgovor se vraća nepromenjen
      ESCALATE  -> odgovor se vraća, degradacija se loguje (ne prekida rad)
      BLOCK     -> `ResponseBlocked`

    Greška u samoj proveri takođe diže `ResponseBlocked`. To je namerno: ako
    firewall ne može da odluči, odgovor nije pregledan, a nepregledan odgovor
    se ne sme predstaviti kao pregledan. Ovo je jedina grana koja može oboriti
    poziv iz razloga koji nije sam odgovor — zato je površina provera držana na
    determinističkom minimumu.
    """
    try:
        v = inspect_chat_response(
            response, kwargs=kwargs, operation=operation, provider=provider,
            model=model, correlation_id=correlation_id, user_id=user_id,
        )
    except Exception as exc:
        logger.error("[RESP_FW] provera nije uspela (fail-closed): %s", exc)
        raise ResponseBlocked(
            [f"provera odgovora nije uspela: {type(exc).__name__}"], operation, model,
        ) from exc

    if v.decision == BLOCK:
        logger.warning(
            "[RESP_FW] BLOCK op=%s model=%s razlozi=%s",
            operation or "?", model or "?", "; ".join(v.razlozi),
        )
        raise ResponseBlocked(v.razlozi, operation, model)

    if v.degradacije:
        logger.info(
            "[RESP_FW] ESCALATE op=%s degradacije=%s",
            operation or "?", "; ".join(v.degradacije),
        )
    return response
