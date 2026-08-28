-- 118 — predmet_dokazi.izvor_snage
--
-- Provenijencija odluke o dokaznoj snazi. `snaga` govori KOLIKA je snaga;
-- ova kolona govori DA LI je iko o njoj odlucio. Kolona `snaga` je
-- NOT NULL DEFAULT 'srednja', pa njena vrednost nikad ne dokazuje da je
-- procena izvrsena.
--
-- Nullable i bez DEFAULT-a namerno: postojeci redovi nemaju zapis o tome kako
-- je `snaga` nastala i taj podatak se ne moze rekonstruisati. NULL se cita
-- kao "nije poznato", a citaoci ga broje kao NEPROCENJENO (fail-closed).
--
-- Bez backfill-a, bez UPDATE, bez okidaca, bez CHECK-a: vokabular drzi
-- shared/evidence_write.py::IZVORI, jedini pisac ove kolone.

ALTER TABLE predmet_dokazi
  ADD COLUMN IF NOT EXISTS izvor_snage TEXT;

COMMENT ON COLUMN predmet_dokazi.izvor_snage IS
  'Provenijencija odluke o `snaga`. covek = pozivalac je eksplicitno poslao vrednost. dc005 = tvrdnja je nadjena u izvornom dokumentu i iz toga je izvedena snaga `jaka`. podrazumevano = nijedna procena nije izvrsena, ukljucujuci ishod u kome je DC-005 pretrazio dokument i tvrdnju nije nasao. NULL = provenijencija nije poznata; broji se kao neprocenjeno.';
