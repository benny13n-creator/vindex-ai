-- Migration 012: SMS/WhatsApp notifikacije (Twilio)
-- Tabela čuva broj telefona i preference korisnika za SMS podsetnike.

CREATE TABLE IF NOT EXISTS korisnik_sms_profil (
    id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     uuid NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    email       text,
    telefon     text NOT NULL,           -- E.164 format, npr. +381601234567
    whatsapp    boolean NOT NULL DEFAULT false,
    aktivan     boolean NOT NULL DEFAULT true,
    created_at  timestamptz DEFAULT now(),
    updated_at  timestamptz DEFAULT now()
);

-- RLS
ALTER TABLE korisnik_sms_profil ENABLE ROW LEVEL SECURITY;

CREATE POLICY "korisnik vidi samo svoj profil"
    ON korisnik_sms_profil FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "korisnik upisuje samo svoj profil"
    ON korisnik_sms_profil FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "korisnik menja samo svoj profil"
    ON korisnik_sms_profil FOR UPDATE
    USING (auth.uid() = user_id);

-- updated_at automatski
CREATE OR REPLACE FUNCTION set_updated_at_sms()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sms_updated_at ON korisnik_sms_profil;
CREATE TRIGGER trg_sms_updated_at
    BEFORE UPDATE ON korisnik_sms_profil
    FOR EACH ROW EXECUTE FUNCTION set_updated_at_sms();
