# -*- coding: utf-8 -*-
"""
Vindex AI — security/agent_isolation.py

Izolacija AI agenata — princip najmanjih privilegija za svaki AI agent.

Svaki agent je "mikro-zaposleni" sa tačno definisanim setom dozvola.
Ni jedan agent ne može pristupiti resursima izvan svog skupa dozvola.

Principe inspirisano: OWASP LLM Top 10, LLM09 — Overreliance
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger("vindex.security.agent_isolation")


@dataclass(frozen=True)
class AgentProfile:
    """Profil jednog AI agenta sa tačno definisanim dozvolama."""
    name: str
    description: str
    allowed_resources: frozenset[str]    # Koji Supabase resursi su dozvoljeni
    allowed_actions: frozenset[str]      # Koje akcije su dozvoljene
    max_documents: int = 10              # Max broj dokumenata u kontekstu
    can_write_db: bool = False           # Sme li pisati u bazu
    can_call_external_api: bool = False  # Sme li zvati eksterne API-je
    can_see_billing: bool = False        # Sme li videti billing podatke
    can_see_user_management: bool = False # Sme li videti upravljanje korisnicima

    def allows_resource(self, resource: str) -> bool:
        return resource in self.allowed_resources or "*" in self.allowed_resources

    def allows_action(self, action: str) -> bool:
        return action in self.allowed_actions or "*" in self.allowed_actions


# ─── Definicije agenata ───────────────────────────────────────────────────────

AGENT_PROFILES: dict[str, AgentProfile] = {

    "copilot": AgentProfile(
        name="copilot",
        description="Pravni AI asistent — odgovara na pitanja iz srpskog prava",
        allowed_resources=frozenset({"laws", "court_decisions", "predmeti", "dokumenti"}),
        allowed_actions=frozenset({"read", "ai_query"}),
        max_documents=10,
        can_write_db=False,
        can_call_external_api=False,
    ),

    "analiza": AgentProfile(
        name="analiza",
        description="Kompletna pravna analiza predmeta — 6-koračni pipeline",
        allowed_resources=frozenset({"laws", "court_decisions", "predmeti", "dokumenti", "predmet_beleske"}),
        allowed_actions=frozenset({"read", "ai_query", "ai_analyze"}),
        max_documents=15,
        can_write_db=True,    # Upisuje analizu u predmet_istorija
        can_call_external_api=False,
    ),

    "briefing": AgentProfile(
        name="briefing",
        description="Jutarnji brifing — pregled predmeta i rokova za danas",
        allowed_resources=frozenset({"predmeti", "rokovi", "klijenti"}),
        allowed_actions=frozenset({"read", "ai_summarize"}),
        max_documents=5,
        can_write_db=False,
        can_call_external_api=False,
        can_see_billing=False,   # Eksplicitno zabranjeno
        can_see_user_management=False,
    ),

    "memory": AgentProfile(
        name="memory",
        description="Vindex Memory — praćenje pravnih stavova i precedenata kancelarije",
        allowed_resources=frozenset({"predmeti", "predmet_beleske", "predmet_istorija"}),
        allowed_actions=frozenset({"read", "ai_query", "write_memory"}),
        max_documents=8,
        can_write_db=True,    # Upisuje memorijske zapise
        can_call_external_api=False,
    ),

    "commander": AgentProfile(
        name="commander",
        description="Case Commander — taktičko upravljanje predmetima",
        allowed_resources=frozenset({"predmeti", "rokovi", "dokumenti", "klijenti"}),
        allowed_actions=frozenset({"read", "write", "ai_plan"}),
        max_documents=10,
        can_write_db=True,
        can_call_external_api=False,
    ),

    "drafting": AgentProfile(
        name="drafting",
        description="Pisanje pravnih podnesaka i dokumenata",
        allowed_resources=frozenset({"predmeti", "dokumenti", "laws", "templates"}),
        allowed_actions=frozenset({"read", "ai_draft"}),
        max_documents=8,
        can_write_db=True,    # Čuva nacrt
        can_call_external_api=False,
    ),

    "simulator": AgentProfile(
        name="simulator",
        description="Simulacija ishoda predmeta",
        allowed_resources=frozenset({"predmeti", "laws", "court_decisions"}),
        allowed_actions=frozenset({"read", "ai_simulate"}),
        max_documents=12,
        can_write_db=False,
        can_call_external_api=False,
    ),

    "twin": AgentProfile(
        name="twin",
        description="Digital Twin klijenta — profil i preferencije",
        allowed_resources=frozenset({"klijenti", "predmeti"}),
        allowed_actions=frozenset({"read", "ai_profile"}),
        max_documents=5,
        can_write_db=False,
        can_see_billing=False,
        can_see_user_management=False,
    ),

    "discovery": AgentProfile(
        name="discovery",
        description="Pretraga i analiza dokumenata (eDiscovery)",
        allowed_resources=frozenset({"predmeti", "dokumenti"}),
        allowed_actions=frozenset({"read", "ai_search", "ai_analyze"}),
        max_documents=20,
        can_write_db=False,
        can_call_external_api=False,
    ),

    "knowledge": AgentProfile(
        name="knowledge",
        description="Baza znanja — samo javni pravni sadržaj",
        allowed_resources=frozenset({"laws", "court_decisions"}),
        allowed_actions=frozenset({"read", "ai_query"}),
        max_documents=10,
        can_write_db=False,
        can_call_external_api=False,
    ),

    "ccc": AgentProfile(
        name="ccc",
        description="Client Cost Calculator — kalkulacija troškova",
        allowed_resources=frozenset({"predmeti", "billing", "tarife"}),
        allowed_actions=frozenset({"read", "ai_calculate"}),
        max_documents=3,
        can_write_db=False,
        can_see_billing=True,
    ),
}

# Fallback profil za nepoznate agente — minimalne privilegije
_DEFAULT_PROFILE = AgentProfile(
    name="unknown",
    description="Nepoznati agent — minimalne privilegije",
    allowed_resources=frozenset(),
    allowed_actions=frozenset({"read"}),
    max_documents=3,
)


# ─── Javni API ────────────────────────────────────────────────────────────────

def get_agent_profile(agent_name: str) -> AgentProfile:
    """Vraća profil agenta, ili fallback profil za nepoznate agente."""
    profile = AGENT_PROFILES.get(agent_name)
    if not profile:
        logger.warning("[AGENT_ISOLATION] Nepoznati agent: %r — primenjujem restriktivan fallback", agent_name)
        return _DEFAULT_PROFILE
    return profile


def check_agent_access(
    agent_name: str,
    resource: str,
    action: str = "read",
    raise_on_denied: bool = True,
) -> bool:
    """
    Proverava da li agent sme da pristupi resursu.

    Args:
        agent_name: Ime agenta (npr. "briefing", "memory")
        resource:   Tip resursa (npr. "billing", "predmeti")
        action:     Akcija (npr. "read", "write")
        raise_on_denied: Baci 403 ako je pristup odbijen

    Returns:
        True ako je pristup dozvoljen, False inače
        (ili diže HTTPException ako raise_on_denied=True)
    """
    profile = get_agent_profile(agent_name)
    allowed = profile.allows_resource(resource) and profile.allows_action(action)

    if not allowed:
        logger.warning(
            "[AGENT_ISOLATION] ODBIJEN pristup: agent=%s resource=%s action=%s",
            agent_name, resource, action,
        )
        if raise_on_denied:
            raise HTTPException(
                status_code=403,
                detail=f"Agent '{agent_name}' nema dozvolu za pristup resursu '{resource}'.",
            )
        return False

    logger.debug("[AGENT_ISOLATION] DOZVOLJEN: agent=%s resource=%s action=%s", agent_name, resource, action)
    return True


def validate_documents_for_agent(
    agent_name: str,
    documents: list,
) -> list:
    """
    Ograničava broj dokumenata u kontekstu prema profilu agenta.
    Sprečava memory exhaustion i preveliki token spend.
    """
    profile = get_agent_profile(agent_name)
    if len(documents) > profile.max_documents:
        logger.info(
            "[AGENT_ISOLATION] agent=%s skraćuje kontekst %d → %d dokumenata",
            agent_name, len(documents), profile.max_documents,
        )
        return documents[:profile.max_documents]
    return documents


def get_agent_permissions_summary() -> dict:
    """Vraća pregled dozvola svih agenata — za admin pregled."""
    return {
        name: {
            "resources": sorted(p.allowed_resources),
            "actions":   sorted(p.allowed_actions),
            "max_docs":  p.max_documents,
            "can_write": p.can_write_db,
            "can_external_api": p.can_call_external_api,
            "can_billing": p.can_see_billing,
        }
        for name, p in AGENT_PROFILES.items()
    }
