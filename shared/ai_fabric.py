# -*- coding: utf-8 -*-
"""
Vindex AI — shared/ai_fabric.py

PROVIDER FABRIC V1 — kanonski ugovor između Vindexa i AI provajdera.

ZAŠTO OVAJ SLOJ POSTOJI
Do sada je Vindex zvao OpenAI SDK direktno sa 99 mesta u 59 fajlova. Governance
je bila obezbeđena monkey-patchom nad `openai.Completions.create`
(shared/ai_client.py::_patch_prompt_guard) -- pokrivenost je strukturna i radi,
ali važi ISKLJUČIVO za taj jedan SDK. Dodavanje drugog provajdera dalo bi nula
governance-a besplatno.

Ovaj modul uvodi provider-neutralnu granicu:

    caller -> AIRequest -> Gateway -> Registry -> ProviderAdapter -> AIResponse

`shared/case_context.py` ostaje source of truth i NIJE menjan: kanonski kontekst
je običan dict sa `context_field(source, owner, refresh)` provenance-om, dakle
već je provider-agnostičan. Fabric ga prosleđuje netaknutog; pretvaranje u
provider-specifičan oblik dešava se ISKLJUČIVO unutar adaptera.

ŠTA OVAJ MODUL NAMERNO NE RADI
- ne dira postojeće OpenAI pozive (legacy put ostaje netaknut i funkcionalan)
- ne duplira `_patch_prompt_guard` (legacy zaštita ostaje na svom mestu)
- ne uvodi LangChain/LiteLLM
- ne bira model "pametno" -- rutiranje je determinističko i konfiguraciono
- ne pravi DB migraciju (telemetrija ide kroz postojeći audit/provenance sloj)

MODEL ID-EVI SE NE IZMIŠLJAJU
Podrazumevani OpenAI model je `gpt-4o-mini`, jer je to model koji ovaj
repozitorijum stvarno koristi na 59 pozivnih mesta (`gpt-4o` na 54). Anthropic i
Gemini podrazumevani modeli MORAJU doći iz okruženja -- bez ključa i bez
`*_MODEL` promenljive adapter odbija poziv umesto da pogađa ID.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger("vindex.ai_fabric")


# ─── Capabilities ─────────────────────────────────────────────────────────────

class Capability(str, Enum):
    TEXT_GENERATION   = "text_generation"
    STRUCTURED_OUTPUT = "structured_output"
    VISION            = "vision"
    EMBEDDINGS        = "embeddings"
    STREAMING         = "streaming"


# ─── Normalizovane greške ─────────────────────────────────────────────────────
# Gateway NIKAD ne pušta sirov SDK izuzetak u domen. Svaki provajder mapira
# svoje greške u ove klase; domen barata jednim skupom.

class AIError(Exception):
    """Bazna klasa. `provider` je uvek poznat, `retryable` vodi retry politiku."""

    retryable: bool = False

    def __init__(self, message: str, provider: str = "?", model: str = "?"):
        super().__init__(message)
        self.provider = provider
        self.model = model


class AIAuthenticationError(AIError):     retryable = False
class AIRateLimitError(AIError):          retryable = True
class AITimeoutError(AIError):            retryable = True
class AIUnavailableError(AIError):        retryable = True
class AIInvalidRequestError(AIError):     retryable = False
class AIUnsupportedCapabilityError(AIError): retryable = False
class AIProviderError(AIError):           retryable = False
class AIMalformedResponseError(AIError):  retryable = False


# ─── Kanonski ugovor ──────────────────────────────────────────────────────────

@dataclass
class AIRequest:
    """Jedini oblik u kome domen izražava AI poziv.

    `case_context` je kanonski dict iz shared/case_context.py -- prosleđuje se
    netaknut i adapter ga serijalizuje po svojim pravilima. Identitet
    (`user_id`, `predmet_id`) NIKAD ne sme doći iz request payload-a; pozivalac
    ga prosleđuje iz autentifikovanog konteksta, isto kao svuda u Vindexu.
    """
    task:              str
    prompt:            str
    system:            Optional[str] = None
    case_context:      Optional[dict] = None
    schema:            Optional[dict] = None      # structured output
    temperature:       Optional[float] = None
    max_tokens:        Optional[int] = None
    timeout_s:         float = 60.0
    provider:          Optional[str] = None       # eksplicitan override
    model:             Optional[str] = None       # eksplicitan override
    correlation_id:    Optional[str] = None
    user_id:           Optional[str] = None
    predmet_id:        Optional[str] = None
    feature:           Optional[str] = None
    metadata:          dict = field(default_factory=dict)

    def required_capabilities(self) -> set[Capability]:
        caps = {Capability.TEXT_GENERATION}
        if self.schema:
            caps.add(Capability.STRUCTURED_OUTPUT)
        return caps


@dataclass
class AIResponse:
    """Normalizovan odgovor. Nijedan SDK objekat ne izlazi iz adaptera.

    `raw_meta` nosi SAMO bezbedne skalare (finish reason, provider request id) --
    nikad sirov response objekat, nikad zaglavlja, nikad ključeve.
    """
    provider:            str
    model:               str
    text:                str
    structured:          Optional[dict] = None
    finish_reason:       Optional[str] = None
    input_tokens:        Optional[int] = None
    output_tokens:       Optional[int] = None
    latency_ms:          int = 0
    correlation_id:      Optional[str] = None
    provider_request_id: Optional[str] = None
    task:                Optional[str] = None
    raw_meta:            dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> Optional[int]:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)


# ─── Cross-model verification seam (dormant) ──────────────────────────────────
# Ugovor postoji da bi sledeći sprint mogao da implementira A -> B kritiku bez
# redizajna. Namerno BEZ implementacije: verifikacija koja ne radi ništa gora je
# od nepostojeće, jer stvara lažan osećaj pokrivenosti.

class Agreement(str, Enum):
    AGREEMENT    = "agreement"
    DISAGREEMENT = "disagreement"
    INCONCLUSIVE = "inconclusive"


@dataclass
class VerificationRequest:
    primary:            AIResponse
    secondary_provider: str
    criteria:           Optional[str] = None
    correlation_id:     Optional[str] = None


@dataclass
class VerificationResult:
    agreement:  Agreement
    primary:    AIResponse
    secondary:  Optional[AIResponse] = None
    notes:      Optional[str] = None


# ─── Provider adapter protokol ────────────────────────────────────────────────

@runtime_checkable
class ProviderAdapter(Protocol):
    name: str

    def supports(self, capability: Capability) -> bool: ...
    def is_configured(self) -> bool: ...
    def default_model(self) -> Optional[str]: ...
    def generate(self, request: AIRequest) -> AIResponse: ...


class _BaseAdapter:
    """Zajedničko: serijalizacija kanonskog konteksta i capability guard.

    Serijalizacija je namerno ovde a ne u case_context-u: kanonski kontekst se
    NE prilagođava nijednom provajderu (Hard Rule 1).
    """
    name = "base"
    _caps: set[Capability] = set()

    def supports(self, capability: Capability) -> bool:
        return capability in self._caps

    def _require_caps(self, request: AIRequest) -> None:
        missing = request.required_capabilities() - self._caps
        if missing:
            raise AIUnsupportedCapabilityError(
                f"{self.name} ne podržava: {sorted(c.value for c in missing)}",
                provider=self.name,
            )

    @staticmethod
    def render_context(case_context: Optional[dict]) -> str:
        """Kanonski dict -> tekst, uz očuvanje provenance oznaka.

        `shared/case_context.py::context_field` pakuje vrednosti kao
        {"value":..., "source":..., "owner":..., "refresh":...}. Provenance se
        NE odbacuje -- `source` ide uz vrednost da bi model mogao da razlikuje
        utvrđenu činjenicu od izvedene.
        """
        if not case_context:
            return ""
        lines: list[str] = []
        for key, val in case_context.items():
            if isinstance(val, dict) and "value" in val:
                src = val.get("source")
                suffix = f"  [izvor: {src}]" if src else ""
                lines.append(f"- {key}: {val['value']}{suffix}")
            else:
                lines.append(f"- {key}: {val}")
        return "\n".join(lines)

    def _compose(self, request: AIRequest) -> str:
        ctx = self.render_context(request.case_context)
        return f"KONTEKST PREDMETA:\n{ctx}\n\n{request.prompt}" if ctx else request.prompt


# ─── OpenAI ───────────────────────────────────────────────────────────────────

class OpenAIProvider(_BaseAdapter):
    """Podrazumevani model je `gpt-4o-mini` -- model koji repozitorijum stvarno
    koristi na 59 pozivnih mesta. Azure varijanta se ne dira: legacy
    `_patch_openai_module` i dalje zamenjuje klasu ako su Azure env promenljive
    postavljene, pa ovaj adapter automatski nasleđuje taj deployment.
    """
    name = "openai"
    _caps = {Capability.TEXT_GENERATION, Capability.STRUCTURED_OUTPUT,
             Capability.VISION, Capability.EMBEDDINGS, Capability.STREAMING}

    def is_configured(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_KEY"))

    def default_model(self) -> Optional[str]:
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def generate(self, request: AIRequest) -> AIResponse:
        self._require_caps(request)
        model = request.model or self.default_model()
        t0 = time.monotonic()
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            msgs = ([{"role": "system", "content": request.system}] if request.system else [])
            msgs.append({"role": "user", "content": self._compose(request)})
            kw: dict[str, Any] = {"model": model, "messages": msgs, "timeout": request.timeout_s}
            if request.temperature is not None:
                kw["temperature"] = request.temperature
            if request.max_tokens is not None:
                kw["max_tokens"] = request.max_tokens
            if request.schema:
                kw["response_format"] = {"type": "json_object"}
            r = client.chat.completions.create(**kw)
        except Exception as exc:
            raise _normalize(exc, self.name, model) from exc

        try:
            choice = r.choices[0]
            usage = getattr(r, "usage", None)
            return AIResponse(
                provider=self.name, model=getattr(r, "model", model) or model,
                text=choice.message.content or "",
                finish_reason=getattr(choice, "finish_reason", None),
                input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                latency_ms=int((time.monotonic() - t0) * 1000),
                correlation_id=request.correlation_id,
                provider_request_id=getattr(r, "id", None),
                task=request.task,
            )
        except Exception as exc:
            raise AIMalformedResponseError(str(exc), provider=self.name, model=model) from exc


# ─── Anthropic ────────────────────────────────────────────────────────────────

class AnthropicProvider(_BaseAdapter):
    """Model MORA doći iz `ANTHROPIC_MODEL` -- adapter ne pogađa ID."""
    name = "anthropic"
    _caps = {Capability.TEXT_GENERATION, Capability.STRUCTURED_OUTPUT,
             Capability.VISION, Capability.STREAMING}

    def is_configured(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

    def default_model(self) -> Optional[str]:
        return os.getenv("ANTHROPIC_MODEL") or None

    def generate(self, request: AIRequest) -> AIResponse:
        self._require_caps(request)
        model = request.model or self.default_model()
        if not model:
            raise AIInvalidRequestError(
                "ANTHROPIC_MODEL nije postavljen i model nije prosleđen -- "
                "model ID se ne pogađa.", provider=self.name)
        t0 = time.monotonic()
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            kw: dict[str, Any] = {
                "model": model,
                "max_tokens": request.max_tokens or 4096,
                "messages": [{"role": "user", "content": self._compose(request)}],
                "timeout": request.timeout_s,
            }
            if request.system:
                kw["system"] = request.system          # Anthropic: system je top-level
            if request.temperature is not None:
                kw["temperature"] = request.temperature
            r = client.messages.create(**kw)
        except Exception as exc:
            raise _normalize(exc, self.name, model) from exc

        try:
            parts = [b.text for b in (r.content or []) if getattr(b, "type", None) == "text"]
            usage = getattr(r, "usage", None)
            return AIResponse(
                provider=self.name, model=getattr(r, "model", model) or model,
                text="".join(parts),
                finish_reason=getattr(r, "stop_reason", None),
                input_tokens=getattr(usage, "input_tokens", None) if usage else None,
                output_tokens=getattr(usage, "output_tokens", None) if usage else None,
                latency_ms=int((time.monotonic() - t0) * 1000),
                correlation_id=request.correlation_id,
                provider_request_id=getattr(r, "id", None),
                task=request.task,
            )
        except Exception as exc:
            raise AIMalformedResponseError(str(exc), provider=self.name, model=model) from exc


# ─── Gemini ───────────────────────────────────────────────────────────────────

class GeminiProvider(_BaseAdapter):
    """Model MORA doći iz `GEMINI_MODEL` -- adapter ne pogađa ID."""
    name = "gemini"
    _caps = {Capability.TEXT_GENERATION, Capability.STRUCTURED_OUTPUT,
             Capability.VISION, Capability.EMBEDDINGS}

    def is_configured(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

    def default_model(self) -> Optional[str]:
        return os.getenv("GEMINI_MODEL") or None

    def generate(self, request: AIRequest) -> AIResponse:
        self._require_caps(request)
        model = request.model or self.default_model()
        if not model:
            raise AIInvalidRequestError(
                "GEMINI_MODEL nije postavljen i model nije prosleđen -- "
                "model ID se ne pogađa.", provider=self.name)
        t0 = time.monotonic()
        try:
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
            gm = genai.GenerativeModel(
                model_name=model,
                system_instruction=request.system,   # Gemini: system je konstruktorski
            )
            cfg: dict[str, Any] = {}
            if request.temperature is not None:
                cfg["temperature"] = request.temperature
            if request.max_tokens is not None:
                cfg["max_output_tokens"] = request.max_tokens
            if request.schema:
                cfg["response_mime_type"] = "application/json"
            r = gm.generate_content(
                self._compose(request),
                generation_config=cfg or None,
                request_options={"timeout": request.timeout_s},
            )
        except Exception as exc:
            raise _normalize(exc, self.name, model) from exc

        try:
            um = getattr(r, "usage_metadata", None)
            cand = (getattr(r, "candidates", None) or [None])[0]
            return AIResponse(
                provider=self.name, model=model,
                text=getattr(r, "text", "") or "",
                finish_reason=str(getattr(cand, "finish_reason", "")) or None,
                input_tokens=getattr(um, "prompt_token_count", None) if um else None,
                output_tokens=getattr(um, "candidates_token_count", None) if um else None,
                latency_ms=int((time.monotonic() - t0) * 1000),
                correlation_id=request.correlation_id,
                task=request.task,
            )
        except Exception as exc:
            raise AIMalformedResponseError(str(exc), provider=self.name, model=model) from exc


# ─── Normalizacija grešaka ────────────────────────────────────────────────────

def _normalize(exc: Exception, provider: str, model: str) -> AIError:
    """Sirov SDK izuzetak -> Vindex klasa. Poruka se skraćuje na 300 znakova da
    dugačka tela odgovora ne bi ulazila u logove."""
    if isinstance(exc, AIError):
        return exc
    name = type(exc).__name__.lower()
    msg = str(exc)[:300]
    if "authentic" in name or "permission" in name:
        return AIAuthenticationError(msg, provider, model)
    if "ratelimit" in name or "resourceexhausted" in name:
        return AIRateLimitError(msg, provider, model)
    if "timeout" in name or "deadline" in name:
        return AITimeoutError(msg, provider, model)
    if "connection" in name or "unavailable" in name or "internalserver" in name:
        return AIUnavailableError(msg, provider, model)
    if "badrequest" in name or "invalid" in name:
        return AIInvalidRequestError(msg, provider, model)
    return AIProviderError(msg, provider, model)


# ─── Registry + determinističko rutiranje ─────────────────────────────────────

@dataclass
class TaskPolicy:
    preferred_provider: str
    preferred_model:    Optional[str] = None
    allowed_fallbacks:  tuple[str, ...] = ()
    timeout_s:          float = 60.0


# Podrazumevana politika: SVE ide na OpenAI, bez fallback-a. Ovo je namerno --
# fallback na provajdera koji nikad nije validiran za pravni sadržaj bio bi
# tiha promena kvaliteta rezultata. Fallback se uključuje eksplicitno.
DEFAULT_POLICIES: dict[str, TaskPolicy] = {
    "legal_reasoning":     TaskPolicy("openai"),
    "document_extraction": TaskPolicy("openai"),
    "summarization":       TaskPolicy("openai"),
    "drafting":            TaskPolicy("openai"),
    "classification":      TaskPolicy("openai"),
    "verification":        TaskPolicy("openai"),
}


class ProviderRegistry:
    def __init__(self, adapters: Optional[list] = None,
                 policies: Optional[dict[str, TaskPolicy]] = None):
        self._adapters = {a.name: a for a in (adapters or
                          [OpenAIProvider(), AnthropicProvider(), GeminiProvider()])}
        self._policies = dict(policies or DEFAULT_POLICIES)

    def names(self) -> list[str]:
        return sorted(self._adapters)

    def get(self, name: str):
        if name not in self._adapters:
            raise AIInvalidRequestError(f"Nepoznat provajder: {name}", provider=name)
        return self._adapters[name]

    def policy(self, task: str) -> TaskPolicy:
        return self._policies.get(task, TaskPolicy("openai"))

    def health(self, name: str) -> dict:
        """Nikad ne pravi naplativ poziv -- samo provera konfiguracije."""
        a = self.get(name)
        return {"provider": name, "configured": a.is_configured(),
                "default_model": a.default_model(),
                "capabilities": sorted(c.value for c in a._caps)}

    def resolve(self, request: AIRequest):
        """Determinističko: eksplicitan override -> task politika -> fallback.

        Fallback se koristi SAMO ako je politika eksplicitno navela i ako je
        kandidat konfigurisan i capability-kompatibilan.
        """
        if request.provider:
            return self.get(request.provider)
        pol = self.policy(request.task)
        need = request.required_capabilities()
        for cand in (pol.preferred_provider, *pol.allowed_fallbacks):
            a = self._adapters.get(cand)
            if a and a.is_configured() and not (need - a._caps):
                return a
        primary = self.get(pol.preferred_provider)
        if not primary.is_configured():
            raise AIUnavailableError(
                f"Provajder '{primary.name}' nije konfigurisan i nema dozvoljenog fallback-a.",
                provider=primary.name)
        return primary


# ─── Gateway — jedina ulazna tačka ────────────────────────────────────────────

MAX_PROMPT_CHARS = int(os.getenv("AI_FABRIC_MAX_PROMPT_CHARS", "400000"))


class GovernanceRejection(AIInvalidRequestError):
    """Kapija je odbila zahtev PRE nego što je provajder dodirnut.

    Nasleđuje AIInvalidRequestError da bi domen imao jedan skup grešaka --
    pozivalac ne mora da zna da li je odbio Vindex ili provajder.
    """


def _govern_request(request: AIRequest) -> AIRequest:
    """Provider-neutralna ULAZNA kapija. Radi PRE registry-ja i adaptera.

    Namerno NE duplira `_patch_prompt_guard`: taj monkey-patch ostaje legacy
    safety net za 99 nemigriranih poziva. Ovde je isti ugovor izražen na
    domenskom nivou, tako da važi za SVAKI provajder, ne samo za OpenAI SDK.
    """
    if not request.task or not str(request.task).strip():
        raise GovernanceRejection("AIRequest.task je obavezan -- bez njega nema "
                                  "ni rutiranja ni upotrebljive telemetrije.")
    if not request.prompt or not str(request.prompt).strip():
        raise GovernanceRejection("Prazan prompt se ne šalje provajderu.", )
    if len(request.prompt) > MAX_PROMPT_CHARS:
        raise GovernanceRejection(
            f"Prompt {len(request.prompt)} znakova prelazi granicu "
            f"{MAX_PROMPT_CHARS} -- odbijeno pre naplativog poziva.")
    if request.timeout_s <= 0:
        raise GovernanceRejection("timeout_s mora biti pozitivan.")

    # Identity provenance: `user_id` je ovde SAMO za trag. Fabric ga nikad ne
    # koristi kao ovlašćenje -- autorizacija je već obavljena u ruteru, isto kao
    # u ostatku Vindexa. Ova provera hvata format, ne pravo pristupa.
    if request.user_id is not None and not isinstance(request.user_id, str):
        raise GovernanceRejection("user_id mora biti string ako je prisutan.")

    # Postojeći prompt guard iz security sloja -- REUSE, ne nova implementacija.
    try:
        from security.prompt_guard import sanitize_prompt  # type: ignore
        request.prompt = sanitize_prompt(request.prompt)
    except ImportError:
        pass
    return request


class AIGateway:
    """caller -> governance -> registry -> adapter -> normalizovan odgovor.

    Governance je provider-neutralna i stoji PRE adaptera, pa novi kanonski put
    ne zavisi od monkey-patch mehanizma. Korelacija i audit koriste POSTOJEĆU
    Vindex infrastrukturu (`shared.ai_provenance`, `shared.audit_immutable`) --
    bez druge korelacione šeme i bez DB migracije (Hard Rules 12 i 20).
    """

    def __init__(self, registry: Optional[ProviderRegistry] = None):
        self.registry = registry or ProviderRegistry()

    def _correlate(self, request: AIRequest) -> AIRequest:
        if request.correlation_id is None:
            try:
                from shared.ai_provenance import current_correlation_id
                request.correlation_id = current_correlation_id()
            except Exception:
                request.correlation_id = None
        return request

    def generate(self, request: AIRequest, shadow: Optional[str] = None) -> AIResponse:
        request = self._correlate(_govern_request(request))
        adapter = self.registry.resolve(request)
        pol = self.registry.policy(request.task)
        if request.timeout_s == 60.0 and pol.timeout_s != 60.0:
            request.timeout_s = pol.timeout_s
        if request.model is None and request.provider is None and pol.preferred_model:
            request.model = pol.preferred_model

        try:
            response = adapter.generate(request)
        except AIError as err:
            self._telemetry(request, None, err)
            raise
        self._telemetry(request, response, None)

        # Shadow ide POSLE primarnog i njegov ishod se odbacuje. Ne može da
        # promeni ono što je pozivalac dobio -- primarni `response` je već
        # izračunat i vraća se bez obzira na shadow.
        shadow_name = shadow or os.getenv("AI_FABRIC_SHADOW_PROVIDER") or None
        if shadow_name and shadow_name != response.provider:
            self._run_shadow(request, shadow_name)
        return response

    def _run_shadow(self, request: AIRequest, shadow_name: str) -> None:
        """Nikad ne diže i nikad ne vraća vrednost -- struktura garantuje da
        shadow ne može uticati na primarni rezultat (test to zaključava)."""
        try:
            sh = self.registry.get(shadow_name)
            if not sh.is_configured():
                return
            shadow_req = replace(
                request,
                provider=shadow_name, model=None,
                timeout_s=min(request.timeout_s, float(os.getenv("AI_FABRIC_SHADOW_TIMEOUT_S", "20"))),
            )
            sh_resp = sh.generate(shadow_req)
            self._telemetry(shadow_req, sh_resp, None, mode="shadow")
        except Exception as exc:
            logger.info("[AI_FABRIC] shadow=%s neuspeh (ignorisano): %s",
                        shadow_name, str(exc)[:200])

    def _telemetry(self, request: AIRequest, response: Optional[AIResponse],
                   error: Optional[AIError], mode: str = "gateway") -> None:
        """Best-effort, kao svaki audit put u Vindexu -- otkaz telemetrije ne
        sme oboriti AI poziv koji je uspeo.

        `mode` razdvaja novi kanonski put (`gateway`) od shadow-a; legacy pozivi
        nemaju ovaj marker, pa su dva puta razlučiva u logu i auditu.
        """
        provider = response.provider if response else (error.provider if error else "?")
        model = response.model if response else (error.model if error else "?")
        try:
            logger.info(
                "[AI_FABRIC] mode=%s task=%s provider=%s model=%s ok=%s in=%s out=%s ms=%s corr=%s",
                mode, request.task, provider, model, error is None,
                response.input_tokens if response else None,
                response.output_tokens if response else None,
                response.latency_ms if response else None,
                request.correlation_id,
            )
        except Exception:
            pass
        self._audit(request, response, error, mode, provider, model)

    def _audit(self, request: AIRequest, response: Optional[AIResponse],
               error: Optional[AIError], mode: str, provider: str, model: str) -> None:
        """Upis u POSTOJEĆI `audit_immutable` preko postojećeg `log_action`.

        Bez nove tabele i bez migracije: `metadata` je već `jsonb`, a
        `correlation_id` se auto-izvodi ako ga ne prosledimo. Akcija
        `ai_fabric_call` mora biti u AUDITABLE_ACTIONS -- ako nije, log_action
        tiho vrati None, pa ovaj poziv ostaje bezopasan dok se registruje.

        METADATA NE SME NOSITI SADRŽAJ: ni prompt ni odgovor ne ulaze u
        append-only ledger. Samo ko/šta/koliko.
        """
        try:
            import asyncio
            from shared.audit_immutable import log_action_sync
            meta = {
                "mode": mode, "task": request.task, "provider": provider, "model": model,
                "ok": error is None,
                "latency_ms": response.latency_ms if response else None,
                "input_tokens": response.input_tokens if response else None,
                "output_tokens": response.output_tokens if response else None,
                "provider_request_id": response.provider_request_id if response else None,
                "error_class": type(error).__name__ if error else None,
                "feature": request.feature,
            }
            log_action_sync(
                "ai_fabric_call",
                user_id=request.user_id,
                resource_type="predmet" if request.predmet_id else "ai_call",
                resource_id=request.predmet_id,
                metadata={k: v for k, v in meta.items() if v is not None},
                correlation_id=request.correlation_id,
            )
        except Exception as exc:
            logger.debug("[AI_FABRIC] audit upis preskočen: %s", str(exc)[:200])


_gateway: Optional[AIGateway] = None


def get_gateway() -> AIGateway:
    global _gateway
    if _gateway is None:
        _gateway = AIGateway()
    return _gateway
