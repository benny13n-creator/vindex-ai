# -*- coding: utf-8 -*-
"""
F12 system-prompt hardening — static checks (no live API needed).

T1 — offchain_zavisnosti has embedded placeholder comment
T2 — aml_kyc block present; anonimnost_ucesnika present for post-processing
T3 — pravni_rizici has lock-period rule comment
T4 — removed abstract blocks are gone
T5 — new sections present: pravni_sazetak, administrativna_ovlascenja, centralizacija,
     klasifikacija_tokena, faktori_za/faktori_protiv, regulatorna_relevantnost with razlog_aktivacije
"""

import sys, os

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ["VINDEX_CACHE_BYPASS"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.web3 import _SC_SYSTEM_PROMPT as PROMPT


def test_t1_offchain_embedded_default():
    assert "nikad prazan niz []" in PROMPT
    assert "Nema identifikovanih eksplicitnih off-chain zavisnosti u dostavljenom kodu" in PROMPT
    assert "frontend, deployment proces" in PROMPT


def test_t2_aml_kyc_block_and_anonimnost_present():
    # new dedicated aml_kyc block
    assert '"aml_kyc"' in PROMPT
    assert "nivo_rizika" in PROMPT
    assert "AML obaveze se tipično procenjuju na nivou platforme" in PROMPT
    # anonimnost_ucesnika still present (required by post-processing Step 2)
    assert "anonimnost_ucesnika" in PROMPT


def test_t3_lock_period_risk_example():
    assert "Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim okolnostima." in PROMPT
    assert "lock period" in PROMPT
    assert "kompromitacije ključa" in PROMPT


def test_t4_removed_abstract_blocks():
    assert "OBAVEZNA PROVERA RIZIKA" not in PROMPT
    assert "INSTRUKCIJE ZA SPECIFIČNA POLJA" not in PROMPT
    assert "Jednostrana izmena parametara" not in PROMPT
    # old "MORA završiti rečenicom" instruction removed (post-processing handles it)
    assert "obrazlozenje MORA završiti rečenicom" not in PROMPT


def test_t5_new_sections_present():
    assert '"pravni_sazetak"' in PROMPT
    assert '"administrativna_ovlascenja"' in PROMPT
    assert '"centralizacija"' in PROMPT
    assert '"klasifikacija_tokena"' in PROMPT
    assert "faktori_za" in PROMPT
    assert "faktori_protiv" in PROMPT
    assert "razlog_aktivacije" in PROMPT
    assert "moguci_pravni_dogadjaji" in PROMPT
    assert "PRIORITET RIZIKA" in PROMPT
