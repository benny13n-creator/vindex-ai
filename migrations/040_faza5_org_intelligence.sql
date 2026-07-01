-- ============================================================
-- Vindex AI — Faza 5: Organizational Intelligence Graph
-- 040_faza5_org_intelligence.sql
-- Style Consistency Checker + Knowledge Transfer System
-- ============================================================

-- ─── Style Consistency Checker ────────────────────────────────────────────────

-- Firminski stil profil (gradi se iz dokumenata)
CREATE TABLE IF NOT EXISTS style_profili (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL,
  naziv         TEXT NOT NULL DEFAULT 'Firminski profil',
  karakteristike JSONB DEFAULT '{}',
  -- karakteristike sadrzi: prosecna_duzina_recenice, gustina_pravnih_termina,
  --   formalni_stil_procenat, pasiv_aktiv_odnos, struktura_ocena, citiranje_ocena
  uzoraka       INT DEFAULT 0,
  aktivan       BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);

-- Analiza stila pojedinog dokumenta
CREATE TABLE IF NOT EXISTS style_analize (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL,
  predmet_id    UUID,
  dokument_naziv TEXT,
  skor          INT CHECK(skor BETWEEN 0 AND 100),
  rezultat      JSONB DEFAULT '{}',
  -- rezultat sadrzi: devijacije[], predlozi[], snage[], oblast_prava
  profile_id    UUID REFERENCES style_profili(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_style_analize_user ON style_analize(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_style_profili_user ON style_profili(user_id, aktivan);

-- ─── Knowledge Transfer System ────────────────────────────────────────────────

-- Profili znanja partnera/seniora
CREATE TABLE IF NOT EXISTS knowledge_profiles (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL,
  advokat_ime       TEXT NOT NULL,
  advokat_email     TEXT,
  oblasti_prava     TEXT[] DEFAULT '{}',
  top_argumenti     JSONB DEFAULT '[]',
  -- [{argument, uspesnost_procenat, kontekst, br_primena}]
  taktike           JSONB DEFAULT '[]',
  -- [{naziv, opis, kada_primeniti, primer_predmeta}]
  stil_komunikacije TEXT,
  napomene          TEXT,
  ukupno_predmeta   INT DEFAULT 0,
  win_rate          NUMERIC(5,2) DEFAULT 0,
  aktivan           BOOLEAN DEFAULT TRUE,
  created_at        TIMESTAMPTZ DEFAULT now(),
  updated_at        TIMESTAMPTZ DEFAULT now()
);

-- Upiti prema bazi znanja partnera
CREATE TABLE IF NOT EXISTS knowledge_upiti (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL,
  profile_id    UUID NOT NULL REFERENCES knowledge_profiles(id) ON DELETE CASCADE,
  upit          TEXT NOT NULL,
  odgovor       TEXT,
  kontekst      JSONB DEFAULT '{}',
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- Dokumenti iz kojih je znanje ekstraktovano
CREATE TABLE IF NOT EXISTS knowledge_izvori (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id    UUID NOT NULL REFERENCES knowledge_profiles(id) ON DELETE CASCADE,
  user_id       UUID NOT NULL,
  tip           TEXT NOT NULL CHECK(tip IN ('predmet_opis','podnesak','strategija','beleska','manuelni_unos')),
  sadrzaj       TEXT NOT NULL,
  oblast_prava  TEXT,
  ishod         TEXT,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_profiles_user ON knowledge_profiles(user_id, aktivan);
CREATE INDEX IF NOT EXISTS idx_knowledge_upiti_profile ON knowledge_upiti(profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_izvori_profile ON knowledge_izvori(profile_id, created_at DESC);

-- ─── Client Twin ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS client_twin_profili (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL,
  klijent_id    UUID NOT NULL,
  twin_profil   JSONB DEFAULT '{}',
  -- sadrzaj: risk_tolerance, komunikacioni_stil, finansijska_granica, donosi_odluke,
  --   churn_rizik, kljucni_okidaci, kljucne_vrednosti, upozorenja, preporuceni_pristup,
  --   poverenje_u_firmu, satisfakcija_procenat
  br_predmeta   INT DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, klijent_id)
);

CREATE INDEX IF NOT EXISTS idx_client_twin_user ON client_twin_profili(user_id, updated_at DESC);

-- RLS
ALTER TABLE style_profili ENABLE ROW LEVEL SECURITY;
ALTER TABLE style_analize ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_upiti ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_izvori ENABLE ROW LEVEL SECURITY;

CREATE POLICY style_profili_own ON style_profili USING (auth.uid() = user_id);
CREATE POLICY style_analize_own ON style_analize USING (auth.uid() = user_id);
CREATE POLICY knowledge_profiles_own ON knowledge_profiles USING (auth.uid() = user_id);
CREATE POLICY knowledge_upiti_own ON knowledge_upiti USING (auth.uid() = user_id);
CREATE POLICY knowledge_izvori_own ON knowledge_izvori USING (auth.uid() = user_id);

ALTER TABLE client_twin_profili ENABLE ROW LEVEL SECURITY;
CREATE POLICY client_twin_own ON client_twin_profili USING (auth.uid() = user_id);
