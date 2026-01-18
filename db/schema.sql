BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;

DROP VIEW IF EXISTS v_aktivni_ugovori;
DROP VIEW IF EXISTS v_trenutni_status_ugovora;
DROP VIEW IF EXISTS v_svi_ugovori;

DROP TRIGGER IF EXISTS uplata_validacija ON uplata;
DROP TRIGGER IF EXISTS ugovor_insert_pocetni_status ON ugovor_najma;

DROP FUNCTION IF EXISTS osvjezi_status_isteklih_ugovora();
DROP FUNCTION IF EXISTS postavi_status_ugovora(bigint, text, date);
DROP FUNCTION IF EXISTS trg_ugovor_pocetni_status();
DROP FUNCTION IF EXISTS trg_uplata_validacija();

DROP TABLE IF EXISTS uplata;
DROP TABLE IF EXISTS status_ugovora_povijest;
DROP TABLE IF EXISTS ugovor_najma;
DROP TABLE IF EXISTS nekretnina;
DROP TABLE IF EXISTS korisnik;

CREATE TABLE korisnik (
  korisnik_id     BIGSERIAL PRIMARY KEY,
  ime             TEXT NOT NULL,
  prezime         TEXT NOT NULL,
  email           TEXT NOT NULL UNIQUE,
  tip_korisnika   TEXT NOT NULL,
  datum_kreiranja TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_tip_korisnika CHECK (tip_korisnika IN ('VLASNIK', 'NAJMOPRIMAC', 'OBOJE'))
);

CREATE TABLE nekretnina (
  nekretnina_id   BIGSERIAL PRIMARY KEY,
  vlasnik_id      BIGINT NOT NULL REFERENCES korisnik(korisnik_id) ON DELETE RESTRICT,
  adresa          TEXT NOT NULL,
  tip_nekretnine  TEXT NOT NULL,
  povrsina        NUMERIC(10,2) NOT NULL,
  datum_kreiranja TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_tip_nekretnine CHECK (tip_nekretnine IN ('stan', 'kuca', 'poslovni_prostor', 'ostalo')),
  CONSTRAINT ck_povrsina CHECK (povrsina > 0)
);

CREATE INDEX idx_nekretnina_vlasnik_id ON nekretnina(vlasnik_id);

CREATE TABLE ugovor_najma (
  ugovor_id         BIGSERIAL PRIMARY KEY,
  nekretnina_id     BIGINT NOT NULL REFERENCES nekretnina(nekretnina_id) ON DELETE RESTRICT,
  najmoprimac_id    BIGINT NOT NULL REFERENCES korisnik(korisnik_id) ON DELETE RESTRICT,
  datum_pocetka     DATE NOT NULL,
  datum_zavrsetka   DATE NOT NULL,
  mjesecna_najamnina NUMERIC(12,2) NOT NULL,
  polog             NUMERIC(12,2) NOT NULL DEFAULT 0,
  napomena          TEXT,
  datum_kreiranja   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_datumi_ugovora CHECK (datum_zavrsetka > datum_pocetka),
  CONSTRAINT ck_najamnina CHECK (mjesecna_najamnina >= 0),
  CONSTRAINT ck_polog CHECK (polog >= 0)
);

CREATE INDEX idx_ugovor_nekretnina_id ON ugovor_najma(nekretnina_id);
CREATE INDEX idx_ugovor_najmoprimac_id ON ugovor_najma(najmoprimac_id);

CREATE TABLE status_ugovora_povijest (
  status_id   BIGSERIAL PRIMARY KEY,
  ugovor_id   BIGINT NOT NULL REFERENCES ugovor_najma(ugovor_id) ON DELETE CASCADE,
  status      TEXT NOT NULL,
  vrijedi_od  DATE NOT NULL,
  vrijedi_do  DATE,
  CONSTRAINT ck_status CHECK (status IN ('AKTIVAN', 'RASKINUT', 'ISTEKAO')),
  CONSTRAINT ck_status_period CHECK (vrijedi_do IS NULL OR vrijedi_do >= vrijedi_od)
);

CREATE INDEX idx_status_ugovor_id ON status_ugovora_povijest(ugovor_id);
CREATE INDEX idx_status_vrijedi_od ON status_ugovora_povijest(vrijedi_od);

ALTER TABLE status_ugovora_povijest
  ADD CONSTRAINT ex_status_bez_preklapanja
  EXCLUDE USING gist (
    ugovor_id WITH =,
    daterange(vrijedi_od, COALESCE(vrijedi_do, 'infinity'::date), '[)') WITH &&
  );

CREATE TABLE uplata (
  uplata_id     BIGSERIAL PRIMARY KEY,
  ugovor_id     BIGINT NOT NULL REFERENCES ugovor_najma(ugovor_id) ON DELETE CASCADE,
  datum_uplate  DATE NOT NULL DEFAULT CURRENT_DATE,
  iznos         NUMERIC(12,2) NOT NULL,
  razdoblje_od  DATE NOT NULL,
  razdoblje_do  DATE NOT NULL,
  napomena      TEXT,
  CONSTRAINT ck_iznos_uplate CHECK (iznos > 0),
  CONSTRAINT ck_razdoblje_uplate CHECK (razdoblje_do >= razdoblje_od)
);

CREATE INDEX idx_uplata_ugovor_id ON uplata(ugovor_id);
CREATE INDEX idx_uplata_datum ON uplata(datum_uplate);

CREATE OR REPLACE FUNCTION postavi_status_ugovora(
  p_ugovor_id BIGINT,
  p_status TEXT,
  p_vrijedi_od DATE DEFAULT CURRENT_DATE
) RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
  v_trenutni_od DATE;
BEGIN
  SELECT vrijedi_od
    INTO v_trenutni_od
  FROM status_ugovora_povijest
  WHERE ugovor_id = p_ugovor_id
    AND vrijedi_do IS NULL
  ORDER BY vrijedi_od DESC
  LIMIT 1;

  IF v_trenutni_od IS NOT NULL AND p_vrijedi_od < v_trenutni_od THEN
    RAISE EXCEPTION 'Neispravan datum promjene statusa (%, trenutni vrijedi_od=%)', p_vrijedi_od, v_trenutni_od;
  END IF;

  UPDATE status_ugovora_povijest
  SET vrijedi_do = p_vrijedi_od
  WHERE ugovor_id = p_ugovor_id
    AND vrijedi_do IS NULL;

  INSERT INTO status_ugovora_povijest(ugovor_id, status, vrijedi_od, vrijedi_do)
  VALUES (p_ugovor_id, p_status, p_vrijedi_od, NULL);
END;
$$;

CREATE OR REPLACE FUNCTION trg_ugovor_pocetni_status()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM postavi_status_ugovora(NEW.ugovor_id, 'AKTIVAN', NEW.datum_pocetka);
  RETURN NEW;
END;
$$;

CREATE TRIGGER ugovor_insert_pocetni_status
AFTER INSERT ON ugovor_najma
FOR EACH ROW
EXECUTE FUNCTION trg_ugovor_pocetni_status();

CREATE OR REPLACE FUNCTION osvjezi_status_isteklih_ugovora()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
  r RECORD;
  v_broj INTEGER := 0;
  v_datum_promjene DATE;
BEGIN
  FOR r IN
    SELECT u.ugovor_id, u.datum_zavrsetka
    FROM ugovor_najma u
    JOIN status_ugovora_povijest s
      ON s.ugovor_id = u.ugovor_id
     AND s.vrijedi_do IS NULL
     AND s.status = 'AKTIVAN'
    WHERE u.datum_zavrsetka < CURRENT_DATE
  LOOP
    v_datum_promjene := r.datum_zavrsetka;
    PERFORM postavi_status_ugovora(r.ugovor_id, 'ISTEKAO', v_datum_promjene);
    v_broj := v_broj + 1;
  END LOOP;

  RETURN v_broj;
END;
$$;

CREATE OR REPLACE FUNCTION trg_uplata_validacija()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  v_pocetak DATE;
  v_kraj DATE;
BEGIN
  SELECT datum_pocetka, datum_zavrsetka
  INTO v_pocetak, v_kraj
  FROM ugovor_najma
  WHERE ugovor_id = NEW.ugovor_id;

  IF v_pocetak IS NULL THEN
    RAISE EXCEPTION 'Ugovor ne postoji (ugovor_id=%)', NEW.ugovor_id;
  END IF;

  IF NEW.razdoblje_od < v_pocetak OR NEW.razdoblje_do > v_kraj THEN
    RAISE EXCEPTION 'Razdoblje uplate (% - %) izvan trajanja ugovora (% - %)',
      NEW.razdoblje_od, NEW.razdoblje_do, v_pocetak, v_kraj;
  END IF;

  IF NEW.razdoblje_do < NEW.razdoblje_od THEN
    RAISE EXCEPTION 'Neispravno razdoblje uplate (% - %)', NEW.razdoblje_od, NEW.razdoblje_do;
  END IF;

  RETURN NEW;
END;
$$;

CREATE TRIGGER uplata_validacija
BEFORE INSERT OR UPDATE ON uplata
FOR EACH ROW
EXECUTE FUNCTION trg_uplata_validacija();

CREATE VIEW v_trenutni_status_ugovora AS
SELECT s.ugovor_id, s.status, s.vrijedi_od, s.vrijedi_do
FROM status_ugovora_povijest s
WHERE s.vrijedi_do IS NULL;

CREATE VIEW v_svi_ugovori AS
SELECT
  u.ugovor_id,
  u.nekretnina_id,
  n.adresa,
  u.najmoprimac_id,
  k.ime || ' ' || k.prezime AS najmoprimac,
  u.datum_pocetka,
  u.datum_zavrsetka,
  u.mjesecna_najamnina,
  u.polog,
  ts.status AS trenutni_status
FROM ugovor_najma u
JOIN nekretnina n ON n.nekretnina_id = u.nekretnina_id
JOIN korisnik k ON k.korisnik_id = u.najmoprimac_id
LEFT JOIN v_trenutni_status_ugovora ts ON ts.ugovor_id = u.ugovor_id;

CREATE VIEW v_aktivni_ugovori AS
SELECT *
FROM v_svi_ugovori
WHERE trenutni_status = 'AKTIVAN';

COMMIT;
