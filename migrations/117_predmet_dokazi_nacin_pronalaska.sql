-- Migration 117: predmet_dokazi.nacin_pronalaska — kako je tvrdnja pronađena u izvoru
-- Run in Supabase SQL Editor
--
-- IMPLEMENTATION TASK 002A (2026-08-28). Odobreno u TASK-u 002B kao jedina
-- minimalna implementaciona granica.
--
-- PROBLEM KOJI ZATVARA:
-- `lociraj_tvrdnju` ima dva puta pronalaska (doslovan substring i
-- whitespace-normalizovano pretraživanje sa proporcionalnim mapiranjem), a oba
-- su do sada upisivala ISTE četiri grounding kolone (migracija 080) bez ikakve
-- oznake. Iz skladištenih podataka se posle nije moglo utvrditi da li je span
-- doslovno proverljiv ili samo približno lociran.
--
-- SEMANTIKA — tačno tri vrednosti, bez četvrte i bez `None` kao vrednosti:
--   'egzaktan'       tekst_dokumenta[start_offset:end_offset] == pronađena proba,
--                    DOSLOVNO, bez ikakve normalizacije pri poređenju
--   'normalizovan'   span je lociran, ali gornja jednakost NE važi
--                    (npr. poklapanje se razlikuje po veličini slova ili je
--                    offset dobijen proporcionalnim mapiranjem)
--   'nije_pronadjen' nijedan postojeći metod nije našao lokaciju;
--                    start_offset i end_offset su NULL
--
-- Način se određuje ISKLJUČIVO proverom te invarijante nad rezultatom, ne time
-- koja je grana koda uspela. Nijedna nova normalizacija nije uvedena.
--
-- ŠTA OVA MIGRACIJA NAMERNO NE RADI:
--   * ne uvodi status (verified/candidate/unverified/unverifiable)
--   * ne dira `snaga`, `identitet`, grounding kolone ni `dokument_id`
--   * ne uvodi UNIQUE, FK, NOT NULL, DEFAULT, trigger, funkciju ni generated column
--   * ne radi backfill — 12 postojećih redova ostaje sa NULL
--
-- NULL znači: način pronalaska nije zabeležen za taj red. Očekivano je za redove
-- nastale pre uvođenja ove kolone, ali može nastati i kasnije, kada upis pređe
-- na dozvoljeni degradirani fallback (shared/evidence_write.py::_insert_sa_fallback).
-- NULL zato NE dokazuje da migracija 117 nije izvršena.

ALTER TABLE public.predmet_dokazi
  ADD COLUMN IF NOT EXISTS nacin_pronalaska TEXT;

COMMENT ON COLUMN public.predmet_dokazi.nacin_pronalaska IS
  'Kako je tvrdnja pronadjena u izvornom tekstu: egzaktan (tekst[start:end] == proba, doslovno) | normalizovan (lociran, ali ta jednakost NE vazi) | nije_pronadjen (start/end su NULL). Odredjuje se proverom invarijante, ne granom koda. NULL znaci da nacin nije zabelezen za taj red -- ocekivano pre migracije 117, ali moguce i kasnije pri degradiranom upisu.';
