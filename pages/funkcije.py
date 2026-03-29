import os
import certifi
import streamlit as st

os.environ["SSL_CERT_FILE"] = certifi.where()

st.set_page_config(
    page_title="Funkcije — Vindex AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;900&family=DM+Sans:wght@300;400;500;600&display=swap');

* { box-sizing: border-box; }

.stApp {
    background: linear-gradient(135deg, #040a16 0%, #060f23 50%, #04081a 100%);
    font-family: 'DM Sans', sans-serif;
}

div[data-testid="stAppViewContainer"],
div[data-testid="stHeader"] {
    background: transparent !important;
}

.block-container {
    max-width: 1100px !important;
    padding: 2rem 2rem 4rem 2rem !important;
}

section[data-testid="stSidebar"] {
    display: none;
}

.vx-nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.2rem 1.4rem;
    border-bottom: 1px solid rgba(255,255,255,0.18);
    margin-bottom: 4rem;
    background: rgba(4,10,22,0.85);
    backdrop-filter: blur(16px);
    border-radius: 12px;
}

.vx-logo {
    font-family: 'Playfair Display', serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: #fff;
    text-decoration: none;
}

.vx-logo span {
    color: #3b9eff;
}

.vx-nav-links {
    display: flex;
    gap: 2rem;
    align-items: center;
}

.vx-nav-link {
    color: rgba(255,255,255,0.80);
    font-size: 0.875rem;
    font-weight: 600;
    text-decoration: none;
}

.vx-nav-cta {
    background: #3b9eff;
    color: #fff !important;
    padding: 0.5rem 1.2rem;
    border-radius: 6px;
}

.page-hero {
    text-align: center;
    margin-bottom: 4rem;
}

.page-badge {
    display: inline-block;
    padding: 0.35rem 0.9rem;
    border: 1px solid rgba(59,158,255,0.35);
    border-radius: 999px;
    background: rgba(59,158,255,0.08);
    color: #7dc4ff;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: 1.2rem;
}

.page-title {
    font-family: 'Playfair Display', serif;
    font-size: 3rem;
    font-weight: 900;
    color: #fff;
    line-height: 1.1;
    margin-bottom: 1rem;
}

.page-title em {
    color: #3b9eff;
    font-style: italic;
}

.page-sub {
    font-size: 1.05rem;
    color: rgba(255,255,255,0.55);
    max-width: 600px;
    margin: 0 auto;
    line-height: 1.7;
}

.func-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1.5rem;
    margin-bottom: 4rem;
}

.func-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 20px;
    padding: 2rem;
    transition: all 0.3s;
    position: relative;
    overflow: hidden;
}

.func-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, rgba(59,158,255,0.6), transparent);
}

.func-card:hover {
    border-color: rgba(59,158,255,0.25);
    background: rgba(59,158,255,0.05);
    transform: translateY(-3px);
    box-shadow: 0 20px 50px rgba(0,0,0,0.3);
}

.func-icon {
    font-size: 2rem;
    margin-bottom: 1rem;
}

.func-badge {
    display: inline-block;
    padding: 0.2rem 0.7rem;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin-bottom: 0.8rem;
}

.func-badge.active {
    background: rgba(34,197,94,0.12);
    border: 1px solid rgba(34,197,94,0.3);
    color: #4ade80;
}

.func-badge.coming {
    background: rgba(250,204,21,0.12);
    border: 1px solid rgba(250,204,21,0.3);
    color: #fbbf24;
}

.func-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.4rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 0.8rem;
}

.func-desc {
    font-size: 0.88rem;
    color: rgba(255,255,255,0.55);
    line-height: 1.75;
    margin-bottom: 1.2rem;
}

.func-list {
    list-style: none;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.func-list li {
    font-size: 0.82rem;
    color: rgba(255,255,255,0.65);
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
}

.func-list li::before {
    content: '→';
    color: #3b9eff;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 1px;
}

.vx-footer {
    border-top: 1px solid rgba(255,255,255,0.07);
    padding-top: 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.vx-footer-logo {
    font-family: 'Playfair Display', serif;
    font-size: 1.1rem;
    font-weight: 700;
    color: rgba(255,255,255,0.6);
}

.vx-footer-logo span {
    color: #3b9eff;
}

.vx-footer-note {
    font-size: 0.75rem;
    color: rgba(255,255,255,0.3);
    text-align: right;
    line-height: 1.6;
}

@media (max-width: 900px) {
    .func-grid {
        grid-template-columns: 1fr;
    }

    .vx-nav,
    .vx-footer {
        flex-direction: column;
        gap: 1rem;
        text-align: center;
    }

    .vx-nav-links {
        flex-wrap: wrap;
        justify-content: center;
        gap: 1rem;
    }

    .page-title {
        font-size: 2.2rem;
    }
}
</style>
""",
    unsafe_allow_html=True,
)

# NAV
st.markdown(
    """
<div class="vx-nav">
    <a href="/" class="vx-logo">Vindex<span>AI</span></a>
    <div class="vx-nav-links">
        <a class="vx-nav-link" href="/funkcije">Funkcije</a>
        <a class="vx-nav-link" href="/paketi">Paketi</a>
        <a class="vx-nav-link" href="/o_nama">O nama</a>
        <a class="vx-nav-link vx-nav-cta" href="/">Počni besplatno</a>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# HERO
st.markdown(
    """
<div class="page-hero">
    <div class="page-badge">⚖ Mogućnosti platforme</div>
    <div class="page-title">
        Sve što advokat<br><em>treba.</em>
    </div>
    <div class="page-sub">
        Vindex AI kombinuje preciznost pravne baze sa brzinom veštačke inteligencije —
        sve u jednom alatu dizajniranom za svakodnevnu pravnu praksu.
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# FUNKCIJE
st.markdown(
    """
<div class="func-grid">

    <div class="func-card">
        <div class="func-icon">🔍</div>
        <div class="func-badge active">✓ Dostupno</div>
        <div class="func-title">Pravno istraživanje</div>
        <div class="func-desc">
            Postavljate pitanje na prirodnom jeziku — Vindex AI pretražuje
            13.600+ pravnih odredbi iz 66 zakona i vraća tačan član,
            doslovan citat i pravnu kvalifikaciju za sekunde.
        </div>
        <ul class="func-list">
            <li>Pretraga po svim oblastima prava</li>
            <li>Tačan zakon i broj člana</li>
            <li>Doslovan citat iz važećeg teksta</li>
            <li>Ocena pouzdanosti odgovora</li>
            <li>Postupanje u praksi za advokata</li>
        </ul>
    </div>

    <div class="func-card">
        <div class="func-icon">📄</div>
        <div class="func-badge active">✓ Dostupno</div>
        <div class="func-title">Generisanje dokumenata</div>
        <div class="func-desc">
            Opišite slučaj i izaberite vrstu podneska — agent generiše
            strukturiran nacrt tužbe, žalbe, ugovora ili drugog akta,
            zasnovan na važećim zakonskim odredbama.
        </div>
        <ul class="func-list">
            <li>Tužba za naknadu štete</li>
            <li>Otkaz ugovora o radu</li>
            <li>Ugovor o delu i uslugama</li>
            <li>Žalba na prvostepenu presudu</li>
            <li>Prilagođavanje na osnovu činjenica slučaja</li>
        </ul>
    </div>

    <div class="func-card">
        <div class="func-icon">⚖️</div>
        <div class="func-badge active">✓ Dostupno</div>
        <div class="func-title">Analiza ugovora</div>
        <div class="func-desc">
            Nalepite tekst ugovora ili drugog pravnog akta —
            agent identifikuje sporne klauzule, pravne rizike
            i odredbe koje zahtevaju posebnu pažnju.
        </div>
        <ul class="func-list">
            <li>Identifikacija rizičnih klauzula</li>
            <li>Provera usklađenosti sa zakonom</li>
            <li>Analiza ugovornih obaveza</li>
            <li>Preporuke za izmenu spornih odredbi</li>
        </ul>
    </div>

    <div class="func-card">
        <div class="func-icon">🏛️</div>
        <div class="func-badge coming">⏳ Uskoro</div>
        <div class="func-title">Pretraga sudske prakse</div>
        <div class="func-desc">
            Pretraga relevantnih presuda Vrhovnog i Apelacionih sudova
            po pravnom pitanju, zakonu ili broju predmeta —
            direktna primena sudske prakse u konkretnom slučaju.
        </div>
        <ul class="func-list">
            <li>Baza presuda srpskih sudova</li>
            <li>Pretraga po pravnom pitanju</li>
            <li>Analiza konzistentnosti sudske prakse</li>
            <li>Citiranje presuda u podnesku</li>
        </ul>
    </div>

</div>
""",
    unsafe_allow_html=True,
)

# FOOTER
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