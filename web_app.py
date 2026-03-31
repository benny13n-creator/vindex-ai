import os
import base64
from pathlib import Path

import certifi
import streamlit as st
from rag_engine import answer_question

from pathlib import Path

VECTOR_STORE_DIR = Path("vector_store")


os.environ["SSL_CERT_FILE"] = certifi.where()

st.set_page_config(
    page_title="Vindex AI — Pravni asistent",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "page" not in st.session_state:
    st.session_state.page = "home"

BACKGROUND_IMAGE = "assets/lady_justice.jpg"


def image_to_base64(path_str):
    path = Path(path_str)
    if not path.exists():
        return ""
    try:
        return base64.b64encode(path.read_bytes()).decode()
    except Exception:
        return ""


bg_base64 = image_to_base64(BACKGROUND_IMAGE)

if bg_base64:
    bg_css = f"""
background:
linear-gradient(135deg, rgba(4,10,22,0.92) 0%, rgba(6,15,35,0.85) 100%),
url("data:image/jpeg;base64,{bg_base64}");
background-size: cover;
background-position: center;
background-attachment: fixed;
"""
else:
    bg_css = "background: linear-gradient(135deg, #040a16 0%, #060f23 50%, #04081a 100%);"

st.markdown(
    f"""
<style>
.vx-response-text {{
    line-height: 1.45;
    padding: 10px 14px;
}}

.vx-response-text p {{
    margin: 6px 0;
}}

.vx-response-text li {{
    margin: 4px 0;
}}

.vx-response-text ul, 
.vx-response-text ol {{
    margin: 6px 0;
    padding-left: 18px;
}}

.vx-response-text br {{
    display: block;
    margin: 4px 0;
}}



@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;900&family=DM+Sans:wght@300;400;500;600&display=swap');

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

.stApp {{
    {bg_css}
    font-family: 'DM Sans', sans-serif;
}}

div[data-testid="stAppViewContainer"],
div[data-testid="stHeader"] {{ background: transparent !important; }}

.block-container {{
    max-width: 1280px !important;
    padding: 1rem 2rem 4rem 2rem !important;
}}

section[data-testid="stSidebar"] {{ display: none; }}

/* ── NAV ── */
.vx-nav {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.2rem 1.8rem;
    background: rgba(4,10,22,0.85);
    border: 1px solid rgba(255,255,255,0.12);
    backdrop-filter: blur(16px);
    border-radius: 14px;
    margin-bottom: 3rem;
}}

.vx-logo {{
    font-family: 'Playfair Display', serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: #fff;
}}

.vx-logo span {{ color: #3b9eff; }}

/* ── GLOBALNA GLAVNA DUGMAD ── */
.stButton > button {{
    background: linear-gradient(135deg, #2b8fff, #1a6fd4) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.75rem 1.5rem !important;
    font-size: 0.9rem !important;
    font-weight: 700 !important;
    width: 100% !important;
    box-shadow: 0 8px 24px rgba(43,143,255,0.3) !important;
    margin-top: 0.5rem !important;
    transition: all 0.2s !important;
}}

.stButton > button:hover {{
    transform: translateY(-1px) !important;
    box-shadow: 0 12px 32px rgba(43,143,255,0.4) !important;
}}

/* ── NAVBAR: prva 4 dugmeta vrati na staro ── */
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(1) .stButton > button,
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton > button,
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(3) .stButton > button,
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(4) .stButton > button {{
    background: transparent !important;
    color: rgba(255,255,255,0.80) !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.4rem 0.9rem !important;
    font-size: 0.875rem !important;
    font-weight: 600 !important;
    box-shadow: none !important;
    width: auto !important;
    margin-top: 0 !important;
}}

div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(1) .stButton > button:hover,
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton > button:hover,
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(3) .stButton > button:hover,
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(4) .stButton > button:hover {{
    background: rgba(255,255,255,0.08) !important;
    color: #fff !important;
    box-shadow: none !important;
    transform: none !important;
}}

/* ── NAVBAR: samo 'Počni besplatno' ostaje plavo i poravnato ── */
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(5) .stButton > button {{
    background: linear-gradient(135deg, #2b8fff, #1a6fd4) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.4rem 1.1rem !important;
    font-size: 0.875rem !important;
    font-weight: 700 !important;
    width: auto !important;
    margin-top: -8px !important;
    box-shadow: 0 4px 16px rgba(43,143,255,0.4) !important;
    line-height: 1.2 !important;
 }}

  /* FIX ALIGN CTA */
div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(5) {{
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}}

div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(5) > div {{
    margin-top: 0 !important;
    padding-top: 0 !important;
}}

div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(5) .stButton {{
    margin-top: 0 !important;
}}

div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stHorizontalBlock"] > div:nth-child(5) .stButton > button:hover {{
    background: linear-gradient(135deg, #3b9eff, #2b8fff) !important;
    box-shadow: 0 6px 20px rgba(43,143,255,0.5) !important;
    transform: translateY(-1px) !important;
}}

/* ── INPUTS - TAMNO SIVA SA CRNIM SLOVIMA ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {{
    background: rgba(200,210,230,0.92) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 10px !important;
    color: #1a1a2e !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    padding: 0.75rem 1rem !important;
}}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {{
    border-color: rgba(59,158,255,0.6) !important;
    box-shadow: 0 0 0 3px rgba(59,158,255,0.12) !important;
    background: rgba(210,220,240,0.95) !important;
}}

.stTextInput > div > div > input::placeholder,
.stTextArea > div > div > textarea::placeholder {{
    color: rgba(50,60,100,0.6) !important;
}}

label[data-testid="stWidgetLabel"] p {{
    color: rgba(255,255,255,0.55) !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
}}

/* ── SELECTBOX ── */
.stSelectbox > div > div {{
    background: rgba(200,210,230,0.92) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 10px !important;
    color: #1a1a2e !important;
}}

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0 !important;
    background: rgba(255,255,255,0.04) !important;
    border-radius: 10px !important;
    padding: 4px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    margin-bottom: 1.4rem !important;
}}

.stTabs [data-baseweb="tab"] {{
    background: transparent !important;
    border-radius: 7px !important;
    color: rgba(255,255,255,0.5) !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    padding: 0.5rem 1rem !important;
    border: none !important;
}}

.stTabs [aria-selected="true"] {{
    background: rgba(59,158,255,0.15) !important;
    color: #7dc4ff !important;
    border: none !important;
}}

/* ── TOGGLE ── */
div[data-testid="stToggle"] {{
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.20) !important;
    border-radius: 10px !important;
    padding: 0.5rem 1rem !important;
}}

div[data-testid="stToggle"] label {{
    color: rgba(255,255,255,0.90) !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
}}

/* ── RESPONSE ── */
.vx-response {{
    margin-top: 1.4rem;
    background: rgba(59,158,255,0.05);
    border: 1px solid rgba(59,158,255,0.18);
    border-radius: 14px;
    padding: 1.4rem;
}}

.vx-response-label {{
    font-size: 0.7rem;
    font-weight: 700;
    color: #3b9eff;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.8rem;
}}

.vx-response-text {{
    color: rgba(255,255,255,0.88);
    font-size: 0.88rem;
    line-height: 1.75;
    white-space: pre-wrap;
}}

/* ── HERO ── */
.vx-hero-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.9rem;
    border: 1px solid rgba(59,158,255,0.35);
    border-radius: 999px;
    background: rgba(59,158,255,0.08);
    color: #7dc4ff;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: 1.4rem;
}}

.vx-hero-badge::before {{
    content: '';
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #3b9eff;
    animation: pulse 2s infinite;
}}

@keyframes pulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.4; transform: scale(0.8); }}
}}

.vx-hero-title {{
    font-family: 'Playfair Display', serif;
    font-size: 3.6rem;
    font-weight: 900;
    line-height: 1.05;
    letter-spacing: -0.03em;
    color: #fff;
    margin-bottom: 1.2rem;
}}

.vx-hero-title em {{ font-style: italic; color: #3b9eff; }}

.vx-hero-sub {{
    font-size: 1.05rem;
    line-height: 1.75;
    color: rgba(255,255,255,0.62);
    margin-bottom: 2rem;
    max-width: 480px;
}}

/* ── PANEL ── */
.vx-panel {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 20px;
    padding: 2rem;
    backdrop-filter: blur(24px);
    box-shadow: 0 32px 80px rgba(0,0,0,0.4);
}}

.vx-panel-title {{
    font-family: 'Playfair Display', serif;
    font-size: 1.3rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 0.4rem;
}}

.vx-panel-sub {{
    font-size: 0.82rem;
    color: rgba(255,255,255,0.4);
    margin-bottom: 1.6rem;
}}

/* ── FEATURES ── */
.vx-features {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.2rem;
    margin-bottom: 3rem;
}}

.vx-feature {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 1.6rem;
    transition: all 0.3s;
}}

.vx-feature:hover {{
    border-color: rgba(59,158,255,0.2);
    background: rgba(59,158,255,0.04);
}}

.vx-feature-icon {{ font-size: 1.4rem; margin-bottom: 0.9rem; }}

.vx-feature-title {{
    font-family: 'Playfair Display', serif;
    font-size: 1rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 0.5rem;
}}

.vx-feature-text {{
    font-size: 0.82rem;
    color: rgba(255,255,255,0.5);
    line-height: 1.65;
}}

/* ── PRICING ── */
.vx-plan {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 20px;
    padding: 2rem;
    position: relative;
    transition: all 0.3s;
}}

.vx-plan:hover {{
    border-color: rgba(59,158,255,0.25);
    transform: translateY(-3px);
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}}

.vx-plan.featured {{
    background: rgba(59,158,255,0.07);
    border-color: rgba(59,158,255,0.35);
    box-shadow: 0 0 0 1px rgba(59,158,255,0.15), 0 24px 60px rgba(59,158,255,0.12);
}}

.vx-plan-badge {{
    position: absolute;
    top: -1px; left: 50%;
    transform: translateX(-50%);
    background: linear-gradient(135deg, #2b8fff, #1a6fd4);
    color: #fff;
    font-size: 0.68rem;
    font-weight: 800;
    padding: 0.3rem 1rem;
    border-radius: 0 0 8px 8px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}}

.vx-plan-name {{
    font-size: 0.75rem;
    font-weight: 700;
    color: rgba(255,255,255,0.45);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.8rem;
    margin-top: 0.8rem;
}}

.vx-plan-price {{
    font-family: 'Playfair Display', serif;
    font-size: 2.8rem;
    font-weight: 900;
    color: #fff;
    line-height: 1;
    margin-bottom: 0.3rem;
}}

.vx-plan-price span {{
    font-family: 'DM Sans', sans-serif;
    font-size: 1rem;
    font-weight: 400;
    color: rgba(255,255,255,0.4);
}}

.vx-plan-desc {{
    font-size: 0.8rem;
    color: rgba(255,255,255,0.4);
    margin-bottom: 1.4rem;
    padding-bottom: 1.4rem;
    border-bottom: 1px solid rgba(255,255,255,0.07);
}}

.vx-plan-features {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
    margin-bottom: 1.6rem;
    padding-left: 0;
}}

.vx-plan-features li {{
    font-size: 0.82rem;
    color: rgba(255,255,255,0.65);
    display: flex;
    align-items: center;
    gap: 0.6rem;
}}

.vx-plan-features li::before {{
    content: '✓';
    color: #3b9eff;
    font-weight: 700;
    font-size: 0.75rem;
    flex-shrink: 0;
}}

/* ── LOADING ── */
.vx-loading {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 1rem;
    color: rgba(255,255,255,0.5);
    font-size: 0.85rem;
}}

.vx-dot {{
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #3b9eff;
    animation: vx-bounce 1.2s infinite;
}}

.vx-dot:nth-child(2) {{ animation-delay: 0.2s; }}
.vx-dot:nth-child(3) {{ animation-delay: 0.4s; }}

@keyframes vx-bounce {{
    0%, 100% {{ transform: translateY(0); opacity: 0.4; }}
    50% {{ transform: translateY(-5px); opacity: 1; }}
}}

/* ── FOOTER ── */
.vx-footer {{
    border-top: 1px solid rgba(255,255,255,0.07);
    padding-top: 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 3rem;
}}

.vx-footer-logo {{
    font-family: 'Playfair Display', serif;
    font-size: 1.1rem;
    font-weight: 700;
    color: rgba(255,255,255,0.6);
}}

.vx-footer-logo span {{ color: #3b9eff; }}

.vx-footer-note {{
    font-size: 0.75rem;
    color: rgba(255,255,255,0.3);
    max-width: 420px;
    text-align: right;
    line-height: 1.6;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ═══════════════════════════════════
# NAVIGATION
# ═══════════════════════════════════

st.markdown('<div class="vx-nav">', unsafe_allow_html=True)
nav_l, nav_r = st.columns([1, 3], vertical_alignment="center")

with nav_l:
    st.markdown('<div class="vx-logo">Vindex<span>AI</span></div>', unsafe_allow_html=True)

with nav_r:
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1.4], vertical_alignment="center")

    with c1:
        if st.button("Početna", key="nav_home"):
            st.session_state.page = "home"
            st.rerun()

    with c2:
        if st.button("Funkcije", key="nav_func"):
            st.session_state.page = "funkcije"
            st.rerun()

    with c3:
        if st.button("Paketi", key="nav_paketi"):
            st.session_state.page = "paketi"
            st.rerun()

    with c4:
        if st.button("O nama", key="nav_onama"):
            st.session_state.page = "o_nama"
            st.rerun()

    with c5:
        if st.button("✦ Počni besplatno", key="nav_cta"):
            st.session_state.page = "home"
            st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════
# PAGE: HOME
# ═══════════════════════════════════

if st.session_state.page == "home":
    col_left, col_right = st.columns([1.1, 1], gap="large")

    with col_left:
        st.markdown(
            """
<div style="padding-top: 1rem;">
    <div class="vx-hero-badge">⚖ AI pravni asistent za Srbiju</div>
    <div class="vx-hero-title">
        Pravo na dohvat<br><em>ruke.</em>
    </div>
    <div class="vx-hero-sub">
        Tačan zakon, relevantan član i praktično tumačenje — za sekunde.
        Vindex AI je dizajniran za advokate koji cene brzinu i preciznost.
    </div>
</div>
""",
            unsafe_allow_html=True,
        )

    with col_right:
        st.markdown('<div class="vx-panel">', unsafe_allow_html=True)
        st.markdown(
            """
<div class="vx-panel-title">Postavi pravno pitanje</div>
<div class="vx-panel-sub">Koristite prirodan jezik — ne treba vam znanje baze podataka</div>
""",
            unsafe_allow_html=True,
        )

        tab1, tab2, tab3 = st.tabs(["Pravno pitanje", "Nacrt podneska", "Analiza dokumenta"])

        with tab1:
            pitanje = st.text_area(
                "pitanje",
                placeholder="Npr. Koji su uslovi za naknadu nematerijalne štete i kako sud određuje visinu naknade?",
                height=110,
                key="pitanje_input",
                label_visibility="collapsed",
            )
            st.markdown('<div class="main-btn">', unsafe_allow_html=True)
            dugme = st.button("Dobij odgovor V3→", key="btn_odgovor", use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

            if dugme:
                if pitanje and pitanje.strip():
                    with st.spinner(""):
                        st.markdown(
                            """
<div class="vx-loading">
    <div class="vx-dot"></div><div class="vx-dot"></div><div class="vx-dot"></div>
    <span>Pretragujem pravnu bazu...</span>
</div>
""",
                            unsafe_allow_html=True,
                        )
                        odgovor = answer_question(pitanje)
                    st.markdown(
                        f"""
<div class="vx-response">
    <div class="vx-response-label">⚖ Odgovor</div>
    <div class="vx-response-text">{odgovor}</div>
</div>
""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.warning("Unesite pravno pitanje.")

        with tab2:
            st.markdown(
                """
<div style="margin-bottom:0.8rem;">
    <div style="font-size:0.78rem;font-weight:700;color:#3b9eff;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;">Nacrt podneska</div>
    <div style="font-size:0.82rem;color:rgba(255,255,255,0.5);">Opišite slučaj i vrstu podneska — agent generiše nacrt na osnovu važećih propisa.</div>
</div>
""",
                unsafe_allow_html=True,
            )

            vrsta = st.selectbox(
                "vrsta",
                ["Tužba za naknadu štete", "Otkaz ugovora o radu", "Ugovor o delu", "Žalba na presudu", "Drugo"],
                key="vrsta_podneska",
                label_visibility="collapsed",
            )
            opis = st.text_area(
                "opis",
                placeholder="Opišite činjenice slučaja...",
                height=120,
                key="nacrt_input",
                label_visibility="collapsed",
            )

            st.markdown('<div class="main-btn">', unsafe_allow_html=True)
            dugme_nacrt = st.button("Generiši nacrt →", key="btn_nacrt", use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

            if dugme_nacrt:
                if opis and opis.strip():
                    with st.spinner(""):
                        st.markdown(
                            """<div class="vx-loading"><div class="vx-dot"></div><div class="vx-dot"></div><div class="vx-dot"></div><span>Generišem nacrt...</span></div>""",
                            unsafe_allow_html=True,
                        )
                        nacrt = answer_question(f"Sastavi {vrsta} na osnovu sledećih činjenica: {opis}")

                    nacrt_html = "<p>" + nacrt.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"

                    st.markdown(
                        f"""
<div class="vx-response">
    <div class="vx-response-label">📄 Nacrt podneska</div>
    <div class="vx-response-text">{nacrt_html}</div>
</div>
""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.warning("Unesite opis slučaja.")

        with tab3:
            st.markdown(
                """
<div style="margin-bottom:0.8rem;">
    <div style="font-size:0.78rem;font-weight:700;color:#3b9eff;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;">Analiza dokumenta</div>
    <div style="font-size:0.82rem;color:rgba(255,255,255,0.5);">Nalepite tekst dokumenta — agent identifikuje pravne rizike i sporne odredbe.</div>
</div>
""",
                unsafe_allow_html=True,
            )

            tekst_doc = st.text_area(
                "tekst",
                placeholder="Nalepite tekst ugovora, presude ili drugog pravnog akta...",
                height=150,
                key="dokument_input",
                label_visibility="collapsed",
            )
            pitanje_doc = st.text_input(
                "pitanje_doc",
                placeholder="Npr. Da li postoje sporne klauzule?",
                key="pitanje_dokument",
                label_visibility="collapsed",
            )

            st.markdown('<div class="main-btn">', unsafe_allow_html=True)
            dugme_analiza = st.button("Analiziraj dokument →", key="btn_analiza", use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

            if dugme_analiza:
                if tekst_doc and tekst_doc.strip():
                    with st.spinner(""):
                        st.markdown(
                            """<div class="vx-loading"><div class="vx-dot"></div><div class="vx-dot"></div><div class="vx-dot"></div><span>Analiziram dokument...</span></div>""",
                            unsafe_allow_html=True,
                        )
                        p = pitanje_doc if pitanje_doc else "Identifikuj pravne rizike i sporne odredbe."
                        analiza = answer_question(f"{p}\n\nTEKST DOKUMENTA:\n{tekst_doc[:3000]}")
                    st.markdown(
                        f'<div class="vx-response"><div class="vx-response-label">🔎 Analiza dokumenta</div><div class="vx-response-text">{"<p>" + analiza.replace("\\n\\n", "</p><p>").replace("\\n", "<br>") + "</p>"}</div></div>',
                        unsafe_allow_html=True,
                        )
                else:
                    st.warning("Nalepite tekst dokumenta.")

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── STATS ──
    st.markdown(
        """
<div style="text-align:center;margin-bottom:3rem;padding:2rem;background:rgba(255,255,255,0.02);border-radius:20px;border:1px solid rgba(255,255,255,0.06);">
    <div style="font-size:0.72rem;font-weight:700;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:1.5rem;">Napravljeno za srpske pravnike</div>
    <div style="display:flex;justify-content:center;gap:4rem;flex-wrap:wrap;">
        <div style="text-align:center;">
            <div style="font-family:'Playfair Display',serif;font-size:2.4rem;font-weight:900;color:#fff;">13.600+</div>
            <div style="font-size:0.78rem;color:rgba(255,255,255,0.4);margin-top:4px;">Pravnih odredbi</div>
        </div>
        <div style="text-align:center;">
            <div style="font-family:'Playfair Display',serif;font-size:2.4rem;font-weight:900;color:#fff;">65+</div>
            <div style="font-size:0.78rem;color:rgba(255,255,255,0.4);margin-top:4px;">Zakona u bazi</div>
        </div>
        <div style="text-align:center;">
            <div style="font-family:'Playfair Display',serif;font-size:2.4rem;font-weight:900;color:#3b9eff;">&lt;10s</div>
            <div style="font-size:0.78rem;color:rgba(255,255,255,0.4);margin-top:4px;">Prosečan odgovor</div>
        </div>
        <div style="text-align:center;">
            <div style="font-family:'Playfair Display',serif;font-size:2.4rem;font-weight:900;color:#4ade80;">100%</div>
            <div style="font-size:0.78rem;color:rgba(255,255,255,0.4);margin-top:4px;">Srpsko pravo</div>
        </div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # ── FEATURES ──
    st.markdown(
        """
<div class="vx-features">
    <div class="vx-feature">
        <div class="vx-feature-icon">🎯</div>
        <div class="vx-feature-title">Tačan zakon i član</div>
        <div class="vx-feature-text">Ne pretražuješ ručno kroz stotine stranica. Dobijaš tačan član i citat iz zakona za sekunde.</div>
    </div>
    <div class="vx-feature">
        <div class="vx-feature-icon">⚡</div>
        <div class="vx-feature-title">Praktično tumačenje</div>
        <div class="vx-feature-text">Ne samo norma — jasno objašnjenje kako se odredba primenjuje u stvarnom predmetu.</div>
    </div>
    <div class="vx-feature">
        <div class="vx-feature-icon">🔒</div>
        <div class="vx-feature-title">Pouzdanost na prvom mestu</div>
        <div class="vx-feature-text">Svaki odgovor nosi ocenu pouzdanosti. Bolje nepotpun tačan odgovor nego lažna sigurnost.</div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # ── ZA ADVOKATE I KANCELARIJE ──
    h1, h2 = st.columns([1.2, 1], gap="large")

    with h1:
        st.markdown(
            """
<div style="background:linear-gradient(135deg,rgba(59,158,255,0.08),rgba(59,158,255,0.03));border:1px solid rgba(59,158,255,0.2);border-radius:24px;padding:2.5rem;margin-bottom:2rem;">
    <div style="font-family:'Playfair Display',serif;font-size:1.8rem;font-weight:800;color:#fff;margin-bottom:1rem;">Za advokate i kancelarije</div>
    <div style="font-size:0.92rem;color:rgba(255,255,255,0.65);line-height:1.8;margin-bottom:1.5rem;">
        Vindex AI je zamišljen kao radni alat za svakodnevna pravna pitanja,
        izradu podnesaka i analizu dokumenata — sa fokusom na jasnoću,
        brzinu i praktičnu primenu.
    </div>
    <div style="display:flex;flex-direction:column;gap:0.6rem;">
        <div style="font-size:0.88rem;color:rgba(255,255,255,0.8);">⚡ <strong style="color:#fff;">10 sekundi</strong> do relevantnog zakona i člana</div>
        <div style="font-size:0.88rem;color:rgba(255,255,255,0.8);">📄 <strong style="color:#fff;">3 režima rada</strong> za svakodnevnu praksu</div>
        <div style="font-size:0.88rem;color:rgba(255,255,255,0.8);">🎁 <strong style="color:#fff;">7 dana besplatno</strong> za testiranje na realnom predmetu</div>
    </div>
</div>
""",
            unsafe_allow_html=True,
        )

    with h2:
        st.markdown(
            """
<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:24px;padding:2.5rem;margin-bottom:2rem;">
    <div style="font-family:'Playfair Display',serif;font-size:1.8rem;font-weight:800;color:#fff;margin-bottom:1rem;">Vindex AI vs ChatGPT</div>
    <div style="font-size:0.82rem;color:rgba(255,255,255,0.4);margin-bottom:1.2rem;">Zašto generički AI nije dovoljan</div>
    <div style="display:flex;flex-direction:column;gap:0.5rem;">
        <div style="display:flex;align-items:center;gap:0.8rem;font-size:0.82rem;">
            <span style="color:#4ade80;font-weight:700;">✓</span>
            <span style="color:rgba(255,255,255,0.75);">Treniran isključivo na srpskim zakonima</span>
        </div>
        <div style="display:flex;align-items:center;gap:0.8rem;font-size:0.82rem;">
            <span style="color:#4ade80;font-weight:700;">✓</span>
            <span style="color:rgba(255,255,255,0.75);">Citira tačan zakon i broj člana</span>
        </div>
        <div style="display:flex;align-items:center;gap:0.8rem;font-size:0.82rem;">
            <span style="color:#4ade80;font-weight:700;">✓</span>
            <span style="color:rgba(255,255,255,0.75);">Ocena pouzdanosti svakog odgovora</span>
        </div>
        <div style="display:flex;align-items:center;gap:0.8rem;font-size:0.82rem;">
            <span style="color:#4ade80;font-weight:700;">✓</span>
            <span style="color:rgba(255,255,255,0.75);">Nikad ne izmišlja zakone</span>
        </div>
        <div style="display:flex;align-items:center;gap:0.8rem;font-size:0.82rem;">
            <span style="color:#4ade80;font-weight:700;">✓</span>
            <span style="color:rgba(255,255,255,0.75);">Pravna terminologija srpskog prava</span>
        </div>
    </div>
</div>
""",
            unsafe_allow_html=True,
        )

# ═══════════════════════════════════
# PAGE: FUNKCIJE
# ═══════════════════════════════════

elif st.session_state.page == "funkcije":
    st.markdown(
        """
<div style="margin-bottom:2rem;">
    <div style="display:inline-block;padding:0.35rem 0.9rem;border:1px solid rgba(59,158,255,0.35);border-radius:999px;background:rgba(59,158,255,0.08);color:#7dc4ff;font-size:0.78rem;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;margin-bottom:1.2rem;">⚖ Mogućnosti platforme</div>
    <div style="font-family:'Playfair Display',serif;font-size:3rem;font-weight:900;color:#fff;line-height:1.1;margin-bottom:1rem;">Sve što advokat<br><em style='color:#3b9eff;font-style:italic;'>treba.</em></div>
    <div style="font-size:1.05rem;color:rgba(255,255,255,0.6);line-height:1.75;max-width:700px;">
        Vindex AI kombinuje preciznost pravne baze sa brzinom veštačke inteligencije — sve u jednom alatu dizajniranom za svakodnevnu pravnu praksu.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    CARD = "background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);border-radius:20px;padding:2rem;margin-bottom:1.5rem;position:relative;overflow:hidden;"
    BADGE_OK = "display:inline-block;padding:0.2rem 0.7rem;border-radius:999px;font-size:0.68rem;font-weight:700;margin-bottom:0.8rem;background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.3);color:#4ade80;"
    BADGE_SOON = "display:inline-block;padding:0.2rem 0.7rem;border-radius:999px;font-size:0.68rem;font-weight:700;margin-bottom:0.8rem;background:rgba(250,204,21,0.12);border:1px solid rgba(250,204,21,0.3);color:#fbbf24;"
    TITLE = "font-family:'Playfair Display',serif;font-size:1.4rem;font-weight:700;color:#fff;margin-bottom:0.8rem;"
    DESC = "font-size:0.88rem;color:rgba(255,255,255,0.55);line-height:1.75;margin-bottom:1.2rem;"
    LI = "font-size:0.82rem;color:rgba(255,255,255,0.65);margin-bottom:0.4rem;padding-left:1.2rem;"

    f1, f2 = st.columns(2, gap="medium")

    with f1:
        st.markdown(
            f"""
<div style="{CARD}">
    <div style="font-size:2rem;margin-bottom:1rem;">🔍</div>
    <div style="{BADGE_OK}">✓ Dostupno</div>
    <div style="{TITLE}">Pravno istraživanje</div>
    <div style="{DESC}">Postavljate pitanje na prirodnom jeziku — Vindex AI pretražuje 13.600+ pravnih odredbi iz 65 zakona i vraća tačan član, doslovan citat i pravnu kvalifikaciju za sekunde.</div>
    <div style="{LI}">→ &nbsp;Pretraga po svim oblastima prava</div>
    <div style="{LI}">→ &nbsp;Tačan zakon i broj člana</div>
    <div style="{LI}">→ &nbsp;Doslovan citat iz važećeg teksta</div>
    <div style="{LI}">→ &nbsp;Ocena pouzdanosti odgovora</div>
</div>
<div style="{CARD}">
    <div style="font-size:2rem;margin-bottom:1rem;">⚖️</div>
    <div style="{BADGE_OK}">✓ Dostupno</div>
    <div style="{TITLE}">Analiza ugovora</div>
    <div style="{DESC}">Nalepite tekst ugovora ili drugog pravnog akta — agent identifikuje sporne klauzule, pravne rizike i odredbe koje zahtevaju posebnu pažnju.</div>
    <div style="{LI}">→ &nbsp;Identifikacija rizičnih klauzula</div>
    <div style="{LI}">→ &nbsp;Provera usklađenosti sa zakonom</div>
    <div style="{LI}">→ &nbsp;Preporuke za izmenu spornih odredbi</div>
</div>
""",
            unsafe_allow_html=True,
        )

    with f2:
        st.markdown(
            f"""
<div style="{CARD}">
    <div style="font-size:2rem;margin-bottom:1rem;">📄</div>
    <div style="{BADGE_OK}">✓ Dostupno</div>
    <div style="{TITLE}">Generisanje dokumenata</div>
    <div style="{DESC}">Opišite slučaj i izaberite vrstu podneska — agent generiše strukturiran nacrt tužbe, žalbe, ugovora ili drugog akta.</div>
    <div style="{LI}">→ &nbsp;Tužba za naknadu štete</div>
    <div style="{LI}">→ &nbsp;Otkaz ugovora o radu</div>
    <div style="{LI}">→ &nbsp;Ugovor o delu i uslugama</div>
    <div style="{LI}">→ &nbsp;Žalba na prvostepenu presudu</div>
</div>
<div style="{CARD}">
    <div style="font-size:2rem;margin-bottom:1rem;">🏛️</div>
    <div style="{BADGE_SOON}">⏳ Uskoro</div>
    <div style="{TITLE}">Pretraga sudske prakse</div>
    <div style="{DESC}">Pretraga relevantnih presuda Vrhovnog i Apelacionih sudova po pravnom pitanju, zakonu ili broju predmeta.</div>
    <div style="{LI}">→ &nbsp;Baza presuda srpskih sudova</div>
    <div style="{LI}">→ &nbsp;Pretraga po pravnom pitanju</div>
    <div style="{LI}">→ &nbsp;Citiranje presuda u podnesku</div>
</div>
""",
            unsafe_allow_html=True,
        )

# ═══════════════════════════════════
# PAGE: PAKETI
# ═══════════════════════════════════

elif st.session_state.page == "paketi":
    st.markdown(
        """
<div style="margin-bottom:3rem;text-align:center;">
    <div style="display:inline-block;padding:0.35rem 0.9rem;border:1px solid rgba(59,158,255,0.35);border-radius:999px;background:rgba(59,158,255,0.08);color:#7dc4ff;font-size:0.78rem;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;margin-bottom:1.2rem;">💼 Cenovnik</div>
    <div style="font-family:'Playfair Display',serif;font-size:3rem;font-weight:900;color:#fff;line-height:1.1;margin-bottom:1rem;">Jednostavno i<br><em style='color:#3b9eff;font-style:italic;'>transparentno.</em></div>
    <div style="font-size:1rem;color:rgba(255,255,255,0.5);">Počni besplatno. Nadogradi kada si spreman.</div>
</div>
""",
        unsafe_allow_html=True,
    )

    col_tog1, col_tog2, col_tog3 = st.columns([1, 1.2, 1])
    with col_tog2:
        godisnji = st.toggle("Godišnja naplata  ·  uštedi 20%", value=False, key="godisnji_toggle")

    if godisnji:
        basic_price, pro_price, period = "39€", "79€", "/mes · godišnje"
    else:
        basic_price, pro_price, period = "49€", "99€", "/mesečno"

    p1, p2, p3 = st.columns(3, gap="medium")

    with p1:
        st.markdown(
            f"""
<div class="vx-plan">
    <div class="vx-plan-name">Basic</div>
    <div class="vx-plan-price">{basic_price} <span>{period}</span></div>
    <div class="vx-plan-desc">Za individualne advokate koji žele brze odgovore bez složene pretrage.</div>
    <ul class="vx-plan-features">
        <li>Do 50 pitanja mesečno</li>
        <li>Pretraga svih zakona u bazi</li>
        <li>Ocena pouzdanosti odgovora</li>
        <li>7 dana besplatno · bez obaveze</li>
    </ul>
    <button class="vx-plan-btn">Počni besplatno</button>
</div>
""",
            unsafe_allow_html=True,
        )

    with p2:
        st.markdown(
            f"""
<div class="vx-plan featured">
    <div class="vx-plan-badge">Najpopularniji</div>
    <div class="vx-plan-name">Pro</div>
    <div class="vx-plan-price">{pro_price} <span>{period}</span></div>
    <div style="display:inline-block;background:rgba(250,204,21,0.12);border:1px solid rgba(250,204,21,0.3);color:#fbbf24;font-size:0.72rem;font-weight:700;padding:0.25rem 0.75rem;border-radius:999px;margin-bottom:0.8rem;">⏳ Uskoro dostupno — optimizacija u toku</div>
    <div class="vx-plan-desc">Za aktivne advokate i kancelarije kojima je brzina konkurentska prednost.</div>
    <ul class="vx-plan-features">
        <li>Neograničena pitanja</li>
        <li>Nacrt podnesaka (uskoro)</li>
        <li>Analiza dokumenata (uskoro)</li>
        <li>Istorija svih pretraga</li>
        <li>Prioritetna podrška</li>
    </ul>
    <button class="vx-plan-btn featured-btn">Počni besplatno</button>
</div>
""",
            unsafe_allow_html=True,
        )

    with p3:
        st.markdown(
            """
<div class="vx-plan">
    <div class="vx-plan-name">Firm</div>
    <div class="vx-plan-price">Custom</div>
    <div class="vx-plan-desc">Za advokatske kancelarije sa više korisnika i specifičnim potrebama.</div>
    <ul class="vx-plan-features">
        <li>Više korisničkih naloga</li>
        <li>Prilagođen onboarding</li>
        <li>Integracija sa internim sistemima</li>
        <li>SLA i dedikovana podrška</li>
    </ul>
    <button class="vx-plan-btn">Kontaktiraj nas</button>
</div>
""",
            unsafe_allow_html=True,
        )

# ═══════════════════════════════════
# PAGE: O NAMA
# ═══════════════════════════════════

elif st.session_state.page == "o_nama":
    st.markdown(
        """
<div style="display:inline-block;padding:0.35rem 0.9rem;border:1px solid rgba(59,158,255,0.35);border-radius:999px;background:rgba(59,158,255,0.08);color:#7dc4ff;font-size:0.78rem;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;margin-bottom:1.2rem;">⚖ Naša priča</div>
<div style="font-family:'Playfair Display',serif;font-size:3rem;font-weight:900;color:#fff;line-height:1.1;margin-bottom:1.5rem;">Zašto smo<br><em style='color:#3b9eff;font-style:italic;'>napravili Vindex AI.</em></div>

<div style="font-size:1.05rem;color:rgba(255,255,255,0.72);line-height:1.85;margin-bottom:1.5rem;max-width:750px;">
    Svaki advokat u Srbiji zna kako izgleda taj trenutak — klijent čeka odgovor, predmet je pod rokovima, a vi provodite dragoceno vreme prelistavajući stranice zakona koji bi trebalo da znate napamet.
</div>

<div style="font-size:1.05rem;color:rgba(255,255,255,0.72);line-height:1.85;margin-bottom:1.5rem;max-width:750px;">
    <strong style="color:#fff;">Vindex AI je nastao iz jednog jednostavnog uverenja:</strong> advokat treba da razmišlja o strategiji predmeta, a ne da ručno pretražuje propise. Istraživanje zakona treba da traje sekunde, ne sate.
</div>

<div style="font-size:1.05rem;color:rgba(255,255,255,0.72);line-height:1.85;margin-bottom:1.5rem;max-width:750px;">
    Izgradili smo sistem koji je treniran isključivo na srpskim zakonima, koji citira tačan član i daje preciznu pravnu kvalifikaciju — bez halucinacija, bez generičkih odgovora.
</div>

<div style="font-size:1.05rem;color:rgba(255,255,255,0.72);line-height:1.85;margin-bottom:3rem;max-width:750px;">
    Naš cilj nije da zameni advokata. <strong style="color:#fff;">Naš cilj je da ga oslobodi.</strong>
</div>

<hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:2rem 0;">
<div style="font-size:0.72rem;font-weight:700;color:#3b9eff;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.6rem;">Naše vrednosti</div>
<div style="font-family:'Playfair Display',serif;font-size:1.8rem;font-weight:800;color:#fff;margin-bottom:1.5rem;">Na čemu gradimo.</div>
""",
        unsafe_allow_html=True,
    )

    VC = "background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:1.6rem;text-align:center;"
    VT = "font-family:'Playfair Display',serif;font-size:1rem;font-weight:700;color:#fff;margin-bottom:0.5rem;"
    VX = "font-size:0.82rem;color:rgba(255,255,255,0.5);line-height:1.65;"

    v1, v2, v3 = st.columns(3, gap="medium")
    with v1:
        st.markdown(
            f'<div style="{VC}"><div style="font-size:1.8rem;margin-bottom:0.8rem;">🎯</div><div style="{VT}">Preciznost iznad svega</div><div style="{VX}">Bolje nepotpun tačan odgovor nego kompletan ali netačan.</div></div>',
            unsafe_allow_html=True,
        )
    with v2:
        st.markdown(
            f'<div style="{VC}"><div style="font-size:1.8rem;margin-bottom:0.8rem;">⚡</div><div style="{VT}">Brzina koja se meri</div><div style="{VX}">Odgovor za manje od 10 sekundi. 13.600+ odredbi trenutno.</div></div>',
            unsafe_allow_html=True,
        )
    with v3:
        st.markdown(
            f'<div style="{VC}"><div style="font-size:1.8rem;margin-bottom:0.8rem;">🔒</div><div style="{VT}">Transparentnost</div><div style="{VX}">Uvek navodimo izvor, zakon i član. Nikad ne nagađamo.</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        """
<hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:2.5rem 0;">
<div style="font-size:0.72rem;font-weight:700;color:#3b9eff;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.6rem;">Kontakt</div>
<div style="font-family:'Playfair Display',serif;font-size:1.8rem;font-weight:800;color:#fff;margin-bottom:1rem;">Stupite u kontakt.</div>
<div style="background:rgba(59,158,255,0.06);border:1px solid rgba(59,158,255,0.2);border-radius:16px;padding:2rem;max-width:600px;">
    <div style="font-size:0.9rem;color:rgba(255,255,255,0.65);line-height:2;">
        <strong style="color:#fff;">Vindex AI</strong> je u fazi beta testiranja.<br>
        Ako ste advokat i želite da testirate platformu besplatno — pišite nam.<br><br>
        <strong style="color:#fff;">Email:</strong> info@vindexai.rs<br>
        <strong style="color:#fff;">Dostupnost:</strong> Pon — Pet, 09:00 — 17:00<br>
        <strong style="color:#fff;">Beta program:</strong> 7 dana besplatno, bez obaveze
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════
# FOOTER
# ═══════════════════════════════════

st.markdown(
    """
<div class="vx-footer">
    <div class="vx-footer-logo">Vindex<span>AI</span></div>
    <div class="vx-footer-note">
        Vindex AI ne zamenjuje profesionalno pravno rasuđivanje advokata.<br>
        Namenjen je kao alat za ubrzanje istraživanja, analize i pripreme.
    </div>
</div>
""",
    unsafe_allow_html=True,
)