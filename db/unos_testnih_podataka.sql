BEGIN;

-- Ocisti podatke (ako ponovno pokreces)
TRUNCATE TABLE uplata RESTART IDENTITY CASCADE;
TRUNCATE TABLE status_ugovora_povijest RESTART IDENTITY CASCADE;
TRUNCATE TABLE ugovor_najma RESTART IDENTITY CASCADE;
TRUNCATE TABLE nekretnina RESTART IDENTITY CASCADE;
TRUNCATE TABLE korisnik RESTART IDENTITY CASCADE;

-- Korisnici
INSERT INTO korisnik (ime, prezime, email, tip_korisnika) VALUES
('Ivan', 'Ivic', 'ivan.ivic@gmail.com', 'najmodavac'),
('Marko', 'Maric', 'marko.maric@gmail.com', 'najmoprimac'),
('Ana', 'Anic', 'ana.anic@gmail.com', 'oboje');

-- Nekretnine (vlasnici: Ivan=1, Ana=3)
INSERT INTO nekretnina (adresa, tip_nekretnine, povrsina, vlasnik_id) VALUES
('Zagrebacka 10, Zagreb', 'stan', 55.00, 1),
('Ribarska 5, Split', 'kuca', 120.00, 3);

-- Ugovori (trigger automatski upisuje pocetni status AKTIVAN u status_ugovora_povijest)
INSERT INTO ugovor_najma (nekretnina_id, najmoprimac_id, datum_pocetka, datum_zavrsetka, mjesecna_najamnina, polog, napomena) VALUES
(1, 2, DATE '2025-12-01', DATE '2026-11-30', 650.00, 650.00, 'Ugovor na 12 mjeseci.'),
(2, 2, DATE '2025-01-01', DATE '2025-12-31', 900.00, 900.00, 'Ugovor istekao (za test osvjezavanja).');

-- Uplate (razdoblje = prvi dan mjeseca)
INSERT INTO uplata (ugovor_id, iznos, datum_uplate, razdoblje) VALUES
(1, 650.00, DATE '2025-12-05', DATE '2025-12-01'),
(1, 650.00, DATE '2026-01-05', DATE '2026-01-01'),
(1, 650.00, DATE '2026-02-05', DATE '2026-02-01'),
(2, 900.00, DATE '2025-12-02', DATE '2025-12-01');

COMMIT;
