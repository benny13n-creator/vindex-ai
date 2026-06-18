-- Migration 015: Add tuzilac, tuzeni, rizik, vrednost_spora columns to predmeti
-- Run in Supabase SQL Editor

ALTER TABLE public.predmeti
  ADD COLUMN IF NOT EXISTS tuzilac       TEXT,
  ADD COLUMN IF NOT EXISTS tuzeni        TEXT,
  ADD COLUMN IF NOT EXISTS rizik         TEXT,
  ADD COLUMN IF NOT EXISTS vrednost_spora TEXT;
