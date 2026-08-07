"""
Operation Iron Lawyer, Master Sprint 001 — regression coverage for the CRITICAL/HIGH real-bug
fixes made to the frontend (static/vindex.js, static/index.html, static/vindex.css).

There is no JS unit-test framework in this repo (frontend is a single vanilla-JS file with no
build step) and introducing one is out of scope for a UX-fix sprint. This suite instead asserts,
via plain text inspection, that each fixed bug's specific defect signature is gone and its fix is
present -- cheap, deterministic, and catches an accidental revert or copy-paste regression of the
exact lines this sprint changed. It does not (and cannot, without a browser) exercise runtime
behavior; see docs/ironlawyer/IRON_LAWYER_FINDINGS.md for what was verified by code-reading instead.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VINDEX_JS = (REPO_ROOT / "static" / "vindex.js").read_text(encoding="utf-8")
INDEX_HTML = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
VINDEX_CSS = (REPO_ROOT / "static" / "vindex.css").read_text(encoding="utf-8")


def test_vindex_js_is_syntactically_valid():
    """Guards every other fix in this file: a parse error would make the whole app fail to load."""
    import subprocess

    result = subprocess.run(
        ["node", "--check", str(REPO_ROOT / "static" / "vindex.js")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"static/vindex.js has a syntax error:\n{result.stderr}"


def test_smart_intake_finalize_includes_awaiting_review_docs():
    """Foxtrot F1 (CRITICAL): siFinalize() used to filter on status==='completed' only, silently
    dropping 'awaiting_review' docs from the created case (or no-op'ing the button entirely if
    ALL docs were awaiting_review, since _siRenderReview's filter already included them)."""
    assert "function siFinalize() {" in VINDEX_JS
    finalize_body = VINDEX_JS.split("function siFinalize() {", 1)[1][:600]
    assert "status === 'completed' || sf.status === 'awaiting_review'" in finalize_body
    assert "showToast('Nijedan dokument nije spreman" in finalize_body


def test_notification_priority_colors_match_backend_vocabulary():
    """Juliet F1 (CRITICAL): _PRIO_COLOR used stale keys (visoka/hitan/srednja/normalan/niska)
    that never matched notifications.py's actual urgent/high/normal/low/info vocabulary (renamed
    Program Omega Sprint 006) -- every notification silently got the dim default color."""
    # Both desktop dropdown and mobile sheet copies must use the corrected vocabulary.
    prio_color_blocks = []
    search_from = 0
    while True:
        idx = VINDEX_JS.find("var _PRIO_COLOR = {", search_from)
        if idx == -1:
            break
        prio_color_blocks.append(VINDEX_JS[idx : idx + 250])
        search_from = idx + 1
    assert len(prio_color_blocks) >= 2, "expected both notif_render() and mobNotifOtvori() _PRIO_COLOR maps"
    for block in prio_color_blocks:
        assert "urgent:" in block and "high:" in block and "normal:" in block
        assert "visoka:" not in block and "hitan:" not in block


def test_notification_read_state_persisted_to_server():
    """Juliet F2 (CRITICAL): read state was localStorage-only; the backend's own periodic
    regeneration deletes+reinserts unread rows with new ids, silently reverting a lawyer's
    'read' dismissal. notif_click/notif_markAllRead must now also call the PATCH endpoints."""
    notif_click_body = VINDEX_JS.split("function notif_click(el, id, predmetId) {", 1)[1][:700]
    assert "/notifications/'+encodeURIComponent(id)+'/read'" in notif_click_body
    assert "PATCH" in notif_click_body

    mark_all_body = VINDEX_JS.split("function notif_markAllRead() {", 1)[1][:400]
    assert "/notifications/read-all" in mark_all_body
    assert "PATCH" in mark_all_body


def test_copilot_chat_clears_on_case_switch():
    """Papa F2 (HIGH, real bug): _copilotHistory (the AI's own context) was already reset on
    case switch, but the visible #pred-copilot-messages transcript wasn't -- a lawyer saw the
    PREVIOUS case's messages on screen while new replies had no memory of them."""
    pred_select_body = VINDEX_JS.split("function pred_select(id) {", 1)[1][:700]
    assert "_copilotHistory = []" in pred_select_body
    assert "pred-copilot-messages" in pred_select_body


def test_evidence_classification_css_typo_fixed():
    """Kilo F4: CSS class name was 'evidence-tip-neklaFIkovan' (typo) while the JS always built
    'evidence-tip-neklaSIfikovan' -- the two never matched, so the 'needs review' color never
    applied to any unclassified document."""
    assert ".evidence-tip-neklafikovan" not in VINDEX_CSS
    assert ".evidence-tip-neklasifikovan" in VINDEX_CSS


def test_evidence_reclassify_control_always_rendered():
    """Kilo K3: the reclassify button used to disappear once ANY classification was assigned,
    making a wrong AI-assigned type permanently uncorrectable from the UI."""
    assert "tip === 'neklasifikovan' ? 'Klasifikuj' : 'Reklasifikuj'" in VINDEX_JS
    # The old code only emitted the button inside a conditional string-concat branch gated on
    # `tip === 'neklasifikovan' ? '<button ...>' : ''` -- that gating pattern must be gone.
    assert "'neklasifikovan' ? '<button onclick=\"evidence_reklasifikuj" not in VINDEX_JS


def test_predmeti_list_shows_error_on_fetch_failure():
    """Sierra S1 (HIGH): pred_load() used to silently `return`/no-op on fetch failure, leaving
    #pred-list (a <tbody>) blank with zero explanation, indistinguishable from a real empty case."""
    assert "function _predListError() {" in VINDEX_JS
    pred_load_body = VINDEX_JS.split("async function pred_load() {", 1)[1][:900]
    assert "_predListError()" in pred_load_body


def test_cmdk_search_distinguishes_failure_from_empty_results():
    """Sierra S3: a failed global search (network/5xx) used to render the identical 'Nema
    rezultata.' as a genuinely empty result set."""
    fetch_body = VINDEX_JS.split("async function _cmdkFetch(q) {", 1)[1][:900]
    assert "cmdkRender([], [], true)" in fetch_body
    render_sig = VINDEX_JS.split("function cmdkRender(items, nepotpuno, failed) {", 1)
    assert len(render_sig) == 2, "cmdkRender must accept a third 'failed' param"
    assert "Pretraga nije uspela" in render_sig[1][:1200]


def test_cmdk_search_includes_zadaci():
    """India I1 (HIGH): tasks (zadaci) had a fully working backend searcher but were invisible
    in the global Cmd+K palette -- excluded from _cmdkVrste, no icon, no filter pill."""
    assert "predmeti,klijenti,hronologija,beleske,dokumenti,billing,zadaci" in VINDEX_JS
    assert "data-vrste=\"zadaci\"" in INDEX_HTML


def test_dead_duplicate_search_button_removed():
    """India I3: #nav-search-btn was a permanently blank clickable button (its only child had
    display:none with nothing to ever un-hide it) duplicating the adjacent labeled search bar."""
    assert 'id="nav-search-btn"' not in INDEX_HTML


def test_portfolio_kancelarije_nav_gated_to_founders():
    """Alpha finding (HIGH): the internal Vindex SaaS-metrics nav item ('Portfolio kancelarije')
    was shown to every user regardless of role, dead-ending in an 'access denied' for non-founders."""
    assert 'id="tab-btn-pi-nav" style="display:none;"' in INDEX_HTML
    admin_ui_body = VINDEX_JS.split("function _updateAdminTabUI() {", 1)[1][:600]
    assert "tab-btn-pi-nav" in admin_ui_body


def test_breadcrumb_has_zadaci_label():
    """Alpha finding (MEDIUM): breadcrumb rendered the raw internal tab id 'zadaci-g' instead of
    a label, because _vxTabLabels had no entry for it."""
    assert "'zadaci-g':'Zadatci'" in VINDEX_JS


def test_case_reopen_available_from_detail_view():
    """Delta D3 (HIGH): reopening a closed case was only reachable via list bulk-select ->
    'Aktiviraj'; zero affordance existed on the case detail screen itself."""
    assert "async function pred_reopen(id) {" in VINDEX_JS
    assert "onclick=\"pred_reopen(" in VINDEX_JS


def test_dead_onboarding_modal_removed():
    """Romeo R1: a second, fully-built onboarding wizard (#onboard-overlay) was wired to a
    hardcoded no-op (onboard_show()), fully superseded by the live onboardingCheck() flow."""
    assert '<div id="onboard-overlay"' not in INDEX_HTML
    assert "function onboard_show()" not in VINDEX_JS
    assert "#onboard-overlay { display:none; }" not in VINDEX_CSS


def test_duplicate_dashboard_deadlines_panel_removed():
    """Echo E4 / Hotel H2: _kcPanelRokovi ('Današnji rokovi') independently recomputed the same
    'what's due today' data Workspace's 'Danas' bucket already shows, with no cross-reference --
    could visibly disagree with Workspace on the same screen."""
    assert "function _kcPanelRokovi(d) {" not in VINDEX_JS
    dash_render_grid = VINDEX_JS.split("_dashRender = function(d, bd, inboxData) {", 1)[1]
    assert "_kcPanelRokovi(d)" not in dash_render_grid.split("function _kcPanelAktivnosti")[0]


def test_dead_billing_fetch_removed_from_dashboard_load():
    """Hotel H5: /billing/pregled was fetched on every dashboard load; its result was never
    read anywhere in _dashRender."""
    dash_load_body = VINDEX_JS.split("async function dash_load(){", 1)[1][:900]
    assert "fetch(BASE_URL+'/billing/pregled'" not in dash_load_body


def test_sw_cache_bumped():
    """Standing convention: static/sw.js CACHE_NAME must increment whenever static/vindex.js
    changes, or returning users silently keep serving the stale cached bundle."""
    sw_js = (REPO_ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    assert 'const CACHE_NAME = "vindex-v95";' in sw_js
