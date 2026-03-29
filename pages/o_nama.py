import os
import certifi
import streamlit as st

os.environ["SSL_CERT_FILE"] = certifi.where()

st.set_page_config(
    page_title="O nama — Vindex AI",
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
    max-width: 900px !important;
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

.story-badge {
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

.story-title {
    font-family: 'Playfair Display', serif;
    font-size: 3rem;
    font-weight: 900;
    color: #fff;
    line-height: 1.1;
    margin-bottom: 1.5rem;
}

.story-title em {
    color: #3b9eff;
    font-style: italic;
}

.story-text {
    font-size: 1.05rem;
    color: rgba(255,255,255,0.72);
    line-height: 1.85;
    margin-bottom: 1.5rem;
}

.story-text strong {
    color: #fff;
}

.divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.08);
    margin: 3rem 0;
}

.values-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.2rem;
    margin: 2rem 0 3rem 0;
}

.value-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 1.6rem;
    text-align: center;
}

.value-icon {
    font-size: 1.8rem;
    margin-bottom: 0.8rem;
}

.value-title {
    font-family: 'Playfair Display', serif;
    font-size: 1rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 0.5rem;
}

.value-text {
    font-size: 0.82rem;
    color: rgba(255,255,255,0.5);
    line-height: 1.65;
}

.section-label {
    font-size: 0.72rem;
    font-weight: 700;
    color: #3b9eff;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.6rem;
}

.section-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.8rem;
    font-weight: 800;
    color: #fff;
    margin-bottom: 1rem;
}

.contact-card {
    background: rgba(59,158,255,0.06);
    border: 1px solid rgba(59,158,255,0.2);
    border-radius: 16px;
    padding: 2rem;
    margin-top: 1rem;
}

.contact-info {
    font-size: 0.9rem;
    color: rgba(255,255,255,0.65);
    line-height: 2;
}

.contact-info strong {
    color: #fff;
}

.vx-footer {
    border-top: 1px solid rgba(255,255,255,0.07);
    padding-top: 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 4rem;
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
    .values-grid {
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

    .story-title {
        font-size: 2.2rem;
    }

    .vx-footer-note {
        text-align: center;
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

# PRIČA
st.markdown(
    """
<div class="story-badge">⚖ Naša priča</div>

<div class="story-title">
    Zašto smo<br><em>napravili Vindex AI.</em>
</div>

<div class="story-text">
    Svaki advokat u Srbiji zna kako izgleda taj trenutak —
    klijent čeka odgovor, predmet je pod rokovima, a vi provodite
    dragoceno vreme prelistavajući stranice zakona koji bi trebalo
    da znate napamet.
</div>

<div class="story-text">
    <strong>Vindex AI je nastao iz jednog jednostavnog uverenja:</strong>
    advokat treba da razmišlja o strategiji predmeta,
    a ne da ručno pretražuje propise.
    Istraživanje zakona treba da traje sekunde, ne sate.
</div>

<div class="story-text">
    Izgradili smo sistem koji je treniran isključivo na srpskim zakonima,
    koji citira tačan član i daje preciznu pravnu kvalifikaciju —
    bez halucinacija, bez generičkih odgovora,
    bez ChatGPT stila koji ne razlikuje Zakon o radu od Porodičnog zakona.
</div>

<div class="story-text">
    Naš cilj nije da zameni advokata.
    <strong>Naš cilj je da ga oslobodi.</strong>
</div>

<hr class="divider">

<div class="section-label">Naše vrednosti</div>
<div class="section-title">Na čemu gradimo.</div>

<div class="values-grid">
    <div class="value-card">
        <div class="value-icon">🎯</div>
        <div class="value-title">Preciznost iznad svega</div>
        <div class="value-text">
            Bolje nepotpun tačan odgovor nego kompletan ali netačan.
            Svaki odgovor nosi ocenu pouzdanosti.
        </div>
    </div>

    <div class="value-card">
        <div class="value-icon">⚡</div>
        <div class="value-title">Brzina koja se meri</div>
        <div class="value-text">
            Odgovor za manje od 10 sekundi.
            13.600+ pravnih odredbi dostupno trenutno.
        </div>
    </div>

    <div class="value-card">
        <div class="value-icon">🔒</div>
        <div class="value-title">Transparentnost</div>
        <div class="value-text">
            Uvek navodimo izvor, zakon i član.
            Nikad ne nagađamo — uvek kažemo kada nešto ne znamo.
        </div>
    </div>
</div>

<hr class="divider">

<div class="section-label">Kontakt</div>
<div class="section-title">Stupite u kontakt.</div>

<div class="contact-card">
    <div class="contact-info">
        <strong>Vindex AI</strong> je u fazi beta testiranja.<br>
        Ako ste advokat i želite da testirate platformu besplatno,
        ili imate pitanja o saradnji — pišite nam.<br><br>
        <strong>Email:</strong> info@vindexai.rs<br>
        <strong>Dostupnost:</strong> Pon — Pet, 09:00 — 17:00<br>
        <strong>Beta program:</strong> 7 dana besplatno, bez obaveze
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