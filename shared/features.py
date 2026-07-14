# -*- coding: utf-8 -*-
"""
Vindex AI — shared/features.py

Centralna Feature Matrix — JEDINI izvor istine o tome koja tarifa/addon
otključava koju funkciju platforme. Nijedan endpoint ne sme sam da odlučuje
"da li je ovo PRO funkcija" — svaki poziva PermissionService.require(FEATURE_X),
a PermissionService čita ODAVDE.

Mapiranje je izvedeno iz docs/ENTITLEMENT_AUDIT_PHASE1.md §2 (kompletna analiza
celog projekta, 104 routera + api.py + klijenti/ modul) i founder-ove eksplicitne
filozofije tarifa:
  BASIC        — samo imenovanih 8 stvari, upoznavanje platforme, minimalni krediti
  PROFESSIONAL — glavni proizvod, ~85-90% vrednosti platforme, gotovo sve AI
  ENTERPRISE   — Professional + tim/RBAC/audit/administracija, NE "Professional sa
                 više kredita"
  ADDON        — Digitalna imovina & Usklađenost, NIKAD deo tarife, zaseban proizvod
                 (samostalno 79€/mes ili dodatak 39€/mes uz Professional/Enterprise)

Ne menjati ovaj fajl bez ažuriranja docs/ENTITLEMENT_AUDIT_PHASE1.md tabele.
"""
from __future__ import annotations

# ─── Tier hijerarhija ──────────────────────────────────────────────────────────
BASIC = "basic"
PROFESSIONAL = "professional"
ENTERPRISE = "enterprise"

TIER_ORDER: dict[str, int] = {BASIC: 0, PROFESSIONAL: 1, ENTERPRISE: 2}

# ─── Addon identifikatori (profiles.addons niz) ───────────────────────────────
ADDON_DIGITAL_ASSETS = "digital_assets"                    # 39€/mes dodatak uz postojeću tarifu
ADDON_DIGITAL_ASSETS_STANDALONE = "digital_assets_standalone"  # 79€/mes samostalno

# ─── FEATURE_* konstante ───────────────────────────────────────────────────────
# Grupa: Dnevni rad (BASIC)
FEATURE_PREDMETI_CRUD          = "predmeti_crud"            # api.py — kreiranje/lista/detalj/izmena predmeta
FEATURE_KLIJENTI_CRUD          = "klijenti_crud"             # klijenti/router.py — CRUD, ne uključuje AI intake wizard
FEATURE_DOKUMENTI_BASIC        = "dokumenti_basic"           # upload/pregled dokumenta (bez AI analize)
FEATURE_ROKOVI                 = "rokovi"                    # kalendar.py, rocista.py, rokovi_lanac.py
FEATURE_FINANSIJE              = "finansije"                 # billing.py, billing_reports.py
FEATURE_CRM                    = "crm"                       # search.py, komentari.py, saradnja.py osnovno
FEATURE_AI_PRAVNA_PITANJA      = "ai_pravna_pitanja"          # api.py /api/pitanje, /api/pitanje/stream
FEATURE_SUDSKA_PRAKSA          = "sudska_praksa"              # praksa.py osnovna pretraga

# Grupa: AI Radni prostor / Case Intelligence (PROFESSIONAL)
FEATURE_CASE_DNA               = "case_dna"                  # case_dna.py — Case Genome
FEATURE_CASE_INTELLIGENCE      = "case_intelligence"          # case_intelligence.py
FEATURE_CASE_COMMANDER         = "case_commander"             # case_commander.py
FEATURE_CASE_PIPELINE          = "case_pipeline"              # case_pipeline.py
FEATURE_CIO                    = "cio"                       # cio.py — Chief Intelligence Officer dnevni sken
FEATURE_CLIENT_TWIN            = "client_twin"                # client_twin.py
FEATURE_CONFIDENCE_AUDIT       = "confidence_audit"           # confidence_audit.py
FEATURE_CONFLICT_CHECK         = "conflict_check"             # conflict_check.py
FEATURE_CORRECTIONS            = "corrections"                # corrections.py
FEATURE_CROSS_DOC              = "cross_doc"                  # cross_doc.py
FEATURE_DECISION_REPLAY        = "decision_replay"            # decision_replay.py
FEATURE_DOCUMENT_ANALYSIS      = "document_analysis"          # dokument.py — analiza, pitanje, rokovi extraction
FEATURE_DOCUMENT_TEMPLATES     = "document_templates"         # doc_templates.py
FEATURE_DRAFTING               = "drafting"                   # drafting.py — nacrt, podnesak, sazmi, playbook
FEATURE_EVIDENCE                = "evidence"                   # evidence.py — Evidence Vault
FEATURE_EVIDENCE_GRAPH         = "evidence_graph"             # evidence_graph.py
FEATURE_FIRM_MEMORY             = "firm_memory"                 # firm_memory.py — Law Firm Brain
FEATURE_HEALTH_INDEX            = "health_index"                # health_index.py
FEATURE_HEARING_PREP            = "hearing_prep"                # hearing_cc.py
FEATURE_INTAKE_AI               = "intake_ai"                   # intake.py — AI ekstrakcija (osnovni intake CRUD ostaje deo predmeti_crud)
FEATURE_KNOWLEDGE_BASE          = "knowledge_base"               # knowledge_base.py
FEATURE_KNOWLEDGE_GRAPH         = "knowledge_graph"              # knowledge_graph.py
FEATURE_KNOWLEDGE_HYGIENE       = "knowledge_hygiene"            # knowledge_hygiene.py
FEATURE_KNOWLEDGE_TRANSFER      = "knowledge_transfer"           # knowledge_transfer.py
FEATURE_LEARNING                = "learning"                     # learning.py — Lessons Learned, Firm DNA
FEATURE_MATTER_INTEL            = "matter_intel"                 # matter_intel.py
FEATURE_MEMORY_GRAPH            = "memory_graph"                 # memory_graph.py
FEATURE_MORNING_BRIEFING        = "morning_briefing"             # morning_briefing.py
FEATURE_MULTI_AGENT             = "multi_agent"                  # multi_agent.py — Tim savetnika
FEATURE_OBLASTI                 = "oblasti"                      # oblasti.py — specijalizovana pravna Q&A
FEATURE_OUTCOME_INTEL           = "outcome_intel"                 # outcome_intel.py
FEATURE_PRECEDENTI              = "precedenti"                   # precedenti.py
FEATURE_STRATEGIJA              = "strategija"                   # strategija.py — Red Team, Litigation Sim, AI Judge...
FEATURE_STRATEGY_SIMULATOR      = "strategy_simulator"            # strategy_simulator.py
FEATURE_STYLE_CHECKER           = "style_checker"                 # style_checker.py
FEATURE_VINDEX_MEMORY           = "vindex_memory"                 # vindex_memory.py
FEATURE_VOICE                   = "voice"                        # voice.py — Whisper/TTS/glasovna komanda
FEATURE_ZADACI_AI               = "zadaci_ai"                    # zadaci.py /ai-analiziraj (osnovni CRUD je slobodan svima)
FEATURE_ZASTARELOST_GUARDIAN    = "zastarelost_guardian"          # zastarelost.py Guardian (kalkulatori ostaju javni)
FEATURE_ZAKON_MONITORING        = "zakon_monitoring"              # zakon_monitoring.py impact_analiza
FEATURE_REGION_AI               = "region_ai"                    # region.py /ai-savet
FEATURE_PROCENA                 = "procena"                      # api.py /api/procena
FEATURE_PREDMET_UPLOAD_AI       = "predmet_upload_ai"             # api.py /api/predmeti/{id}/upload (3 GPT poziva)
FEATURE_PREDMET_AI_PREPORUKA    = "predmet_ai_preporuka"          # api.py /api/predmeti/{id}/ai-preporuka
FEATURE_PREDMET_WORKSPACE_AI    = "predmet_workspace_ai"          # api.py /api/predmeti/{id}/workspace cockpit summary

# Grupa: Enterprise (tim, administracija, audit)
FEATURE_KANCELARIJA_TEAM        = "kancelarija_team"              # kancelarija.py — pozivanje/uklanjanje članova (seat-limited)
FEATURE_ENTERPRISE_DELEGACIJA   = "enterprise_delegacija"          # enterprise.py — statistike/kapacitet/delegiraj
FEATURE_KLIJENTI_AUDIT_LOG      = "klijenti_audit_log"             # klijenti/router.py GET /audit (već PARTNER-only)
FEATURE_API_EXTERNAL            = "api_external"                  # export.py — eksterni API ključevi

# Grupa: Digitalna imovina & Usklađenost (ADDON — nikad deo tarife)
FEATURE_DIGITAL_ASSETS          = "digital_assets"                # web3.py, wallet_provenance.py, source_of_funds.py, csv_import.py

# ─── Feature → minimalna tarifa ────────────────────────────────────────────────
# Feature koje NISU ovde a jesu u FEATURE_* listi iznad = greška, mora biti mapirano.
FEATURE_TIER: dict[str, str] = {
    # Basic
    FEATURE_PREDMETI_CRUD: BASIC,
    FEATURE_KLIJENTI_CRUD: BASIC,
    FEATURE_DOKUMENTI_BASIC: BASIC,
    FEATURE_ROKOVI: BASIC,
    FEATURE_FINANSIJE: BASIC,
    FEATURE_CRM: BASIC,
    FEATURE_AI_PRAVNA_PITANJA: BASIC,
    FEATURE_SUDSKA_PRAKSA: BASIC,

    # Professional
    FEATURE_CASE_DNA: PROFESSIONAL,
    FEATURE_CASE_INTELLIGENCE: PROFESSIONAL,
    FEATURE_CASE_COMMANDER: PROFESSIONAL,
    FEATURE_CASE_PIPELINE: PROFESSIONAL,
    FEATURE_CIO: PROFESSIONAL,
    FEATURE_CLIENT_TWIN: PROFESSIONAL,
    FEATURE_CONFIDENCE_AUDIT: PROFESSIONAL,
    FEATURE_CONFLICT_CHECK: PROFESSIONAL,
    FEATURE_CORRECTIONS: PROFESSIONAL,
    FEATURE_CROSS_DOC: PROFESSIONAL,
    FEATURE_DECISION_REPLAY: PROFESSIONAL,
    FEATURE_DOCUMENT_ANALYSIS: PROFESSIONAL,
    FEATURE_DOCUMENT_TEMPLATES: PROFESSIONAL,
    FEATURE_DRAFTING: PROFESSIONAL,
    FEATURE_EVIDENCE: PROFESSIONAL,
    FEATURE_EVIDENCE_GRAPH: PROFESSIONAL,
    FEATURE_FIRM_MEMORY: PROFESSIONAL,
    FEATURE_HEALTH_INDEX: PROFESSIONAL,
    FEATURE_HEARING_PREP: PROFESSIONAL,
    FEATURE_INTAKE_AI: PROFESSIONAL,
    FEATURE_KNOWLEDGE_BASE: PROFESSIONAL,
    FEATURE_KNOWLEDGE_GRAPH: PROFESSIONAL,
    FEATURE_KNOWLEDGE_HYGIENE: PROFESSIONAL,
    FEATURE_KNOWLEDGE_TRANSFER: PROFESSIONAL,
    FEATURE_LEARNING: PROFESSIONAL,
    FEATURE_MATTER_INTEL: PROFESSIONAL,
    FEATURE_MEMORY_GRAPH: PROFESSIONAL,
    FEATURE_MORNING_BRIEFING: PROFESSIONAL,
    FEATURE_MULTI_AGENT: PROFESSIONAL,
    FEATURE_OBLASTI: PROFESSIONAL,
    FEATURE_OUTCOME_INTEL: PROFESSIONAL,
    FEATURE_PRECEDENTI: PROFESSIONAL,
    FEATURE_STRATEGIJA: PROFESSIONAL,
    FEATURE_STRATEGY_SIMULATOR: PROFESSIONAL,
    FEATURE_STYLE_CHECKER: PROFESSIONAL,
    FEATURE_VINDEX_MEMORY: PROFESSIONAL,
    FEATURE_VOICE: PROFESSIONAL,
    FEATURE_ZADACI_AI: PROFESSIONAL,
    FEATURE_ZASTARELOST_GUARDIAN: PROFESSIONAL,
    FEATURE_ZAKON_MONITORING: PROFESSIONAL,
    FEATURE_REGION_AI: PROFESSIONAL,
    FEATURE_PROCENA: PROFESSIONAL,
    FEATURE_PREDMET_UPLOAD_AI: PROFESSIONAL,
    FEATURE_PREDMET_AI_PREPORUKA: PROFESSIONAL,
    FEATURE_PREDMET_WORKSPACE_AI: PROFESSIONAL,

    # Enterprise
    FEATURE_KANCELARIJA_TEAM: ENTERPRISE,
    FEATURE_ENTERPRISE_DELEGACIJA: ENTERPRISE,
    FEATURE_KLIJENTI_AUDIT_LOG: ENTERPRISE,
    FEATURE_API_EXTERNAL: ENTERPRISE,
}

# ─── Feature → addon (Digitalna imovina — nezavisno od subscription_type) ─────
# Prihvata BILO KOJI od dva addon-a (standalone pokriva i "dodatak" upotrebu).
FEATURE_ADDON: dict[str, tuple[str, ...]] = {
    FEATURE_DIGITAL_ASSETS: (ADDON_DIGITAL_ASSETS, ADDON_DIGITAL_ASSETS_STANDALONE),
}


def tier_satisfies(user_tier: str, required_tier: str) -> bool:
    """True ako user_tier >= required_tier po hijerarhiji basic < professional < enterprise."""
    return TIER_ORDER.get(user_tier, -1) >= TIER_ORDER.get(required_tier, 999)


def has_addon(user_addons: list[str], feature: str) -> bool:
    accepted = FEATURE_ADDON.get(feature)
    if not accepted:
        return False
    return any(a in (user_addons or []) for a in accepted)
