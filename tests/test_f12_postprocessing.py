# -*- coding: utf-8 -*-
"""
F12 deterministic post-processing — unit tests (no live API).

T1  — _sc_detect_lock_without_exit: True for SimpleStaking-style code
T2  — _sc_detect_lock_without_exit: False for plain ERC-20-style code (no false positive)
T3  — offchain_zavisnosti placeholder injected when GPT returns empty list
T4  — offchain_zavisnosti placeholder injected when GPT omits the field
T5  — anonimnost_ucesnika AML/KYC note appended when indikator == "DA"
T6  — anonimnost_ucesnika AML/KYC note NOT duplicated if already present
T7  — lock-without-exit risk appended when GPT misses it (is_lock_without_exit=True)
T8  — lock-without-exit risk NOT appended when GPT already included it
T9  — lock-without-exit risk NOT appended when is_lock_without_exit=False
TM1 — _sc_detect_unrestricted_mint: True for onlyOwner mint without supply cap
TM2 — _sc_detect_unrestricted_mint: False for contract with no mint function
TM3 — _sc_detect_unrestricted_mint: False for capped token (MAX_SUPPLY present)
TM4 — unrestricted-mint risk appended when GPT misses it (is_unrestricted_mint=True)
TM5 — unrestricted-mint risk NOT duplicated when GPT already included it
TM6 — unrestricted-mint risk NOT added when is_unrestricted_mint=False
"""

import sys, os

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ["VINDEX_CACHE_BYPASS"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_stashed = sys.modules.pop("api", None)
import api as _api
del sys.modules["api"]
if _stashed is not None:
    sys.modules["api"] = _stashed

# ── Fixtures ──────────────────────────────────────────────────────────────────

SIMPLE_STAKING = """
pragma solidity ^0.8.0;
contract SimpleStaking {
    address public owner;
    uint256 public lockPeriod = 30 days;
    mapping(address => uint256) public stakes;
    mapping(address => uint256) public lockUntil;

    modifier onlyOwner() { require(msg.sender == owner); _; }

    function stake(uint256 amount) external {
        stakes[msg.sender] += amount;
        lockUntil[msg.sender] = block.timestamp + lockPeriod;
    }

    function withdraw() external {
        require(block.timestamp >= lockUntil[msg.sender], "Locked");
        uint256 amount = stakes[msg.sender];
        stakes[msg.sender] = 0;
        payable(msg.sender).transfer(amount);
    }

    function setLockPeriod(uint256 newPeriod) external onlyOwner {
        lockPeriod = newPeriod;
    }
}
"""

ERC20_SIMPLE = """
pragma solidity ^0.8.0;
contract SimpleToken {
    mapping(address => uint256) public balances;
    uint256 public totalSupply;

    function transfer(address to, uint256 amount) external {
        require(balances[msg.sender] >= amount);
        balances[msg.sender] -= amount;
        balances[to] += amount;
    }

    function mint(address to, uint256 amount) external {
        balances[to] += amount;
        totalSupply += amount;
    }
}
"""

# onlyOwner modifier before {, no supply cap → TM1 True
UNRESTRICTED_OWNER_MINT = """
pragma solidity ^0.8.0;
contract UnrestrictedToken {
    address public owner;
    mapping(address => uint256) public balanceOf;
    uint256 public totalSupply;

    modifier onlyOwner() { require(msg.sender == owner, "Not owner"); _; }
    constructor() { owner = msg.sender; }

    function mint(address to, uint256 amount) external onlyOwner {
        totalSupply += amount;
        balanceOf[to] += amount;
    }
}
"""

# has MAX_SUPPLY cap → TM3 False
CAPPED_TOKEN = """
pragma solidity ^0.8.0;
contract CappedToken {
    address public owner;
    uint256 public totalSupply;
    uint256 public constant MAX_SUPPLY = 1000000;
    mapping(address => uint256) public balanceOf;

    constructor() { owner = msg.sender; }

    function mint(address to, uint256 amount) external {
        require(msg.sender == owner, "Not owner");
        require(totalSupply + amount <= MAX_SUPPLY, "Exceeds max supply");
        totalSupply += amount;
        balanceOf[to] += amount;
    }
}
"""


def _make_result(offchain=None, anon_indikator="DA", anon_obr="Korisnici su anonimni.", rizici=None):
    r = {
        "pravni_indikatori": {
            "anonimnost_ucesnika": {
                "indikator": anon_indikator,
                "obrazlozenje": anon_obr,
            }
        },
        "pravni_rizici": rizici if rizici is not None else [],
    }
    if offchain is not None:
        r["offchain_zavisnosti"] = offchain
    return r


def _run_postprocessing(result: dict, is_lock: bool, is_mint: bool = False) -> dict:
    """Replicate all post-processing steps from the endpoint."""
    # Step 1
    if not result.get("offchain_zavisnosti"):
        result["offchain_zavisnosti"] = [_api._DEFAULT_OFFCHAIN_PLACEHOLDER]
    # Step 2
    anon = result.get("pravni_indikatori", {}).get("anonimnost_ucesnika", {})
    if isinstance(anon, dict):
        obr = anon.get("obrazlozenje", "")
        if _api._AML_KYC_NAPOMENA.strip() not in obr:
            anon["obrazlozenje"] = obr.rstrip(".") + "." + _api._AML_KYC_NAPOMENA
    # Step 5
    if is_lock:
        existing = result.get("pravni_rizici", [])
        already = any(
            "povraćaj" in r.get("rizik", "").lower()
            or "povracaj" in r.get("rizik", "").lower()
            or "prevremen" in r.get("rizik", "").lower()
            for r in existing
        )
        if not already:
            result["pravni_rizici"] = existing + [_api._LOCK_WITHOUT_EXIT_RISK]
    # Step 6
    if is_mint:
        existing = result.get("pravni_rizici", [])
        already = any(
            "mint" in r.get("rizik", "").lower()
            or "emisij" in r.get("rizik", "").lower()
            or "emitova" in r.get("rizik", "").lower()
            for r in existing
        )
        if not already:
            result["pravni_rizici"] = existing + [_api._UNRESTRICTED_MINT_RISK]
    return result


# ── T1/T2: heuristic ─────────────────────────────────────────────────────────

def test_t1_detect_lock_without_exit_true():
    assert _api._sc_detect_lock_without_exit(SIMPLE_STAKING) is True


def test_t2_detect_lock_without_exit_false_for_erc20():
    assert _api._sc_detect_lock_without_exit(ERC20_SIMPLE) is False


# ── T3/T4: offchain placeholder ───────────────────────────────────────────────

def test_t3_offchain_injected_when_empty_list():
    result = _run_postprocessing(_make_result(offchain=[]), False)
    assert result["offchain_zavisnosti"] == [_api._DEFAULT_OFFCHAIN_PLACEHOLDER]


def test_t4_offchain_injected_when_field_missing():
    result = _run_postprocessing(_make_result(offchain=None), False)
    assert result["offchain_zavisnosti"] == [_api._DEFAULT_OFFCHAIN_PLACEHOLDER]


# ── T5/T6: AML/KYC note ──────────────────────────────────────────────────────

def test_t5_aml_note_appended():
    result = _run_postprocessing(_make_result(anon_indikator="DA", anon_obr="Korisnici su anonimni."), False)
    obr = result["pravni_indikatori"]["anonimnost_ucesnika"]["obrazlozenje"]
    assert _api._AML_KYC_NAPOMENA.strip() in obr


def test_t5b_aml_note_appended_for_ne():
    result = _run_postprocessing(_make_result(anon_indikator="NE", anon_obr="Nema posebnih mehanizama anonimnosti."), False)
    obr = result["pravni_indikatori"]["anonimnost_ucesnika"]["obrazlozenje"]
    assert _api._AML_KYC_NAPOMENA.strip() in obr


def test_t5c_aml_note_appended_for_nedovoljno():
    result = _run_postprocessing(_make_result(anon_indikator="NEDOVOLJNO PODATAKA", anon_obr="Nedovoljno podataka za procenu."), False)
    obr = result["pravni_indikatori"]["anonimnost_ucesnika"]["obrazlozenje"]
    assert _api._AML_KYC_NAPOMENA.strip() in obr


def test_t6_aml_note_not_duplicated():
    already = "Korisnici su anonimni." + _api._AML_KYC_NAPOMENA
    result = _run_postprocessing(_make_result(anon_indikator="DA", anon_obr=already), False)
    obr = result["pravni_indikatori"]["anonimnost_ucesnika"]["obrazlozenje"]
    assert obr.count(_api._AML_KYC_NAPOMENA.strip()) == 1


# ── T7/T8/T9: lock-without-exit risk ─────────────────────────────────────────

def test_t7_lock_risk_appended_when_missing():
    result = _run_postprocessing(_make_result(rizici=[{"rizik": "Centralizovana kontrola.", "ozbiljnost": "VISOK", "obrazlozenje": "..."}]), True)
    rizici = [r["rizik"] for r in result["pravni_rizici"]]
    assert any("prevremeni povraćaj" in r.lower() or "prevremen" in r.lower() for r in rizici)


def test_t8_lock_risk_not_duplicated_when_gpt_included():
    existing = [{"rizik": "Ne postoji mehanizam za prevremeni povraćaj sredstava.", "ozbiljnost": "VISOK", "obrazlozenje": "..."}]
    result = _run_postprocessing(_make_result(rizici=existing), True)
    count = sum(1 for r in result["pravni_rizici"] if "prevremen" in r.get("rizik", "").lower())
    assert count == 1


def test_t9_lock_risk_not_added_for_non_lock_contract():
    result = _run_postprocessing(_make_result(rizici=[]), False)
    assert not any("prevremen" in r.get("rizik", "").lower() for r in result["pravni_rizici"])


# ── TM1/TM2/TM3: unrestricted-mint heuristic ─────────────────────────────────

def test_tm1_detect_unrestricted_mint_true_for_onlyowner_mint():
    assert _api._sc_detect_unrestricted_mint(UNRESTRICTED_OWNER_MINT) is True


def test_tm2_detect_unrestricted_mint_false_for_no_mint():
    assert _api._sc_detect_unrestricted_mint(SIMPLE_STAKING) is False


def test_tm3_detect_unrestricted_mint_false_for_capped_token():
    assert _api._sc_detect_unrestricted_mint(CAPPED_TOKEN) is False


# ── TM4/TM5/TM6: unrestricted-mint post-processing ───────────────────────────

def test_tm4_mint_risk_appended_when_missing():
    result = _run_postprocessing(_make_result(rizici=[{"rizik": "Centralizovana kontrola.", "ozbiljnost": "VISOK", "obrazlozenje": "..."}]), False, is_mint=True)
    rizici = [r["rizik"] for r in result["pravni_rizici"]]
    assert any("mint" in r.lower() or "emitova" in r.lower() for r in rizici)


def test_tm5_mint_risk_not_duplicated_when_gpt_included():
    existing = [{"rizik": "Vlasnik može emitovati neograničen broj tokena.", "ozbiljnost": "VISOK", "obrazlozenje": "..."}]
    result = _run_postprocessing(_make_result(rizici=existing), False, is_mint=True)
    count = sum(1 for r in result["pravni_rizici"] if "emitova" in r.get("rizik", "").lower() or "mint" in r.get("rizik", "").lower())
    assert count == 1


def test_tm6_mint_risk_not_added_when_is_mint_false():
    result = _run_postprocessing(_make_result(rizici=[]), False, is_mint=False)
    assert not any(
        "mint" in r.get("rizik", "").lower() or "emitova" in r.get("rizik", "").lower()
        for r in result["pravni_rizici"]
    )
