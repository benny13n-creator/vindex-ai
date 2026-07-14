# -*- coding: utf-8 -*-
"""
Vindex AI — shared/features.py

SAMO simbolički FEATURE_* identifikatori — string konstante koje endpoint
importuje da izbegne magic string typo greške. NIKAKVA POLITIKA (tarifa,
addon, krediti, limiti) se ne drži ovde — sve to živi u feature_registry
tabeli (migracija 064) i čita se preko shared/feature_registry.py, koje
PermissionService i UsageService koriste.

Zašto: cena/tarifa/limit funkcije mora biti promenljiva bez deploy-a koda
(Admin Feature Console). Ako bi FEATURE_TIER/FEATURE_ADDON/krediti bili
ovde kao Python dict, svaka promena cene tražila bi novi commit — tačno
ono što ne želimo (founder-ova eksplicitna odluka).

Dodavanje nove funkcije: 1) dodaj FEATURE_X konstantu ovde, 2) dodaj red u
feature_registry tabeli (migracija ili Admin Console), 3) endpoint zove
PermissionService.require(FEATURE_X) + UsageService.consume(...FEATURE_X).
Ako feature_key postoji ovde ali nema red u bazi, FeatureRegistry baca
grešku pri prvom pristupu — namerno glasno, ne tiho.
"""
from __future__ import annotations

# ─── Dnevni rad (BASIC) ─────────────────────────────────────────────────────
FEATURE_PREDMETI_CRUD           = "predmeti_crud"
FEATURE_KLIJENTI_CRUD           = "klijenti_crud"
FEATURE_DOKUMENTI_BASIC         = "dokumenti_basic"
FEATURE_ROKOVI                  = "rokovi"
FEATURE_FINANSIJE               = "finansije"
FEATURE_CRM                     = "crm"
FEATURE_AI_PRAVNA_PITANJA       = "ai_pravna_pitanja"
FEATURE_SUDSKA_PRAKSA           = "sudska_praksa"

# ─── AI Radni prostor / Case Intelligence (PROFESSIONAL) ───────────────────
FEATURE_CASE_DNA                = "case_dna"
FEATURE_CASE_INTELLIGENCE       = "case_intelligence"
FEATURE_CASE_COMMANDER          = "case_commander"
FEATURE_CASE_PIPELINE           = "case_pipeline"
FEATURE_CIO                     = "cio"
FEATURE_CLIENT_TWIN             = "client_twin"
FEATURE_CONFIDENCE_AUDIT        = "confidence_audit"
FEATURE_CONFLICT_CHECK          = "conflict_check"
FEATURE_CORRECTIONS             = "corrections"
FEATURE_CROSS_DOC               = "cross_doc"
FEATURE_DECISION_REPLAY         = "decision_replay"
FEATURE_DOCUMENT_ANALYSIS       = "document_analysis"
FEATURE_DOCUMENT_TEMPLATES      = "document_templates"
FEATURE_DRAFTING                = "drafting"
FEATURE_EVIDENCE                = "evidence"
FEATURE_EVIDENCE_GRAPH          = "evidence_graph"
FEATURE_FIRM_MEMORY             = "firm_memory"
FEATURE_HEALTH_INDEX            = "health_index"
FEATURE_HEARING_PREP            = "hearing_prep"
FEATURE_INTAKE_AI               = "intake_ai"
FEATURE_INTERNI_STAVOVI         = "interni_stavovi"
FEATURE_KNOWLEDGE_BASE          = "knowledge_base"
FEATURE_KNOWLEDGE_GRAPH         = "knowledge_graph"
FEATURE_KNOWLEDGE_HYGIENE       = "knowledge_hygiene"
FEATURE_KNOWLEDGE_TRANSFER      = "knowledge_transfer"
FEATURE_LEARNING                = "learning"
FEATURE_MATTER_INTEL            = "matter_intel"
FEATURE_MEMORY_GRAPH            = "memory_graph"
FEATURE_MORNING_BRIEFING        = "morning_briefing"
FEATURE_MULTI_AGENT             = "multi_agent"
FEATURE_OBLASTI                 = "oblasti"
FEATURE_OUTCOME_INTEL           = "outcome_intel"
FEATURE_PRECEDENTI              = "precedenti"
FEATURE_PROFITABILNOST_AI       = "profitabilnost_ai"
FEATURE_STRATEGIJA              = "strategija"
FEATURE_STRATEGY_SIMULATOR      = "strategy_simulator"
FEATURE_STYLE_CHECKER           = "style_checker"
FEATURE_COURT_PREDICTOR         = "court_predictor"
FEATURE_COPILOT                 = "copilot"
FEATURE_VINDEX_MEMORY           = "vindex_memory"
FEATURE_VOICE                   = "voice"
FEATURE_ZADACI_AI               = "zadaci_ai"
FEATURE_ZASTARELOST_GUARDIAN    = "zastarelost_guardian"
FEATURE_ZAKON_MONITORING        = "zakon_monitoring"
FEATURE_REGION_AI               = "region_ai"
FEATURE_PROCENA                 = "procena"
FEATURE_PREDMET_UPLOAD_AI       = "predmet_upload_ai"
FEATURE_PREDMET_AI_PREPORUKA    = "predmet_ai_preporuka"
FEATURE_PREDMET_WORKSPACE_AI    = "predmet_workspace_ai"

# ─── Enterprise (tim, administracija, audit) ────────────────────────────────
FEATURE_KANCELARIJA_TEAM        = "kancelarija_team"
FEATURE_ENTERPRISE_DELEGACIJA   = "enterprise_delegacija"
FEATURE_KLIJENTI_AUDIT_LOG      = "klijenti_audit_log"
FEATURE_API_EXTERNAL            = "api_external"

# ─── Digitalna imovina & Usklađenost (ADDON — nikad deo tarife) ────────────
# Granularno po alatu (ne jedan blanket feature) — svaki ima sopstvenu cenu
# u Registry-ju, tačno kako je founder tražio (npr. Source of Funds != OFAC).
FEATURE_DA_REGULATORY_REVIEW    = "da_regulatory_review"     # ZDI/MiCA pretraga, compliance check, MiCA score, license check, CARF jurisdikcije, CSV import
FEATURE_DA_DUE_DILIGENCE        = "da_due_diligence"          # Documentation Health Score
FEATURE_DA_WALLET_RISK          = "da_wallet_risk_assessment" # OFAC screening + Wallet Provenance
FEATURE_DA_SOURCE_OF_FUNDS      = "da_source_of_funds"        # PDF Dossier
FEATURE_DA_SMART_CONTRACT       = "da_smart_contract"         # Pametni ugovor — pravna analiza (najskuplji alat)
FEATURE_DA_WHITEPAPER           = "da_whitepaper_analysis"    # AI analiza projekta
FEATURE_DA_AML_AUDIT            = "da_aml_audit"              # AML/KYC revizija
FEATURE_DA_REPORTING_SIMULATOR  = "da_reporting_simulator"    # Exchange Reporting Simulator

ALL_DIGITAL_ASSET_FEATURES = (
    FEATURE_DA_REGULATORY_REVIEW, FEATURE_DA_DUE_DILIGENCE, FEATURE_DA_WALLET_RISK,
    FEATURE_DA_SOURCE_OF_FUNDS, FEATURE_DA_SMART_CONTRACT, FEATURE_DA_WHITEPAPER,
    FEATURE_DA_AML_AUDIT, FEATURE_DA_REPORTING_SIMULATOR,
)
