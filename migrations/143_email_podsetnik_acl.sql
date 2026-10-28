-- 143: Ograniči pristup tabelama podsetnika samo na serversku ulogu.
-- U 142 su kreirane tabele sa uključenim RLS-om i bez politika.
-- Supabase podrazumevane privilegije su ipak dodelile ALL rolama anon i authenticated,
-- uključujući TRUNCATE, koji nije ograničen RLS-om.
-- Ovaj REVOKE ne menja service_role pristup niti bilo koji podatak.
-- Primenjeno na VindexAI produkciju kao Supabase migracija
-- 20261028201800_email_podsetnik_143_revoke_anon_authenticated.
REVOKE ALL PRIVILEGES ON
  public.email_podsetnik_dogadjaj,
  public.email_podsetnik_pokretanje
FROM anon, authenticated;
