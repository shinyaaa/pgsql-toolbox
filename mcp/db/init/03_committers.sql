-- Mark known PostgreSQL committers.
-- This file runs at DB init via docker-entrypoint-initdb.d, but the authors
-- table is empty at that point so the UPDATE is a no-op on first run.
-- Re-run manually after ingestion to flag committers:
--   docker compose exec db psql -U hackers -d pgsql_hackers \
--     -f /docker-entrypoint-initdb.d/03_committers.sql

UPDATE authors SET is_committer = TRUE
WHERE display_name IN (
    'Bruce Momjian',
    'Tom Lane',
    'Tatsuo Ishii',
    'Peter Eisentraut',
    'Joe Conway',
    'Álvaro Herrera',
    'Andrew Dunstan',
    'Magnus Hagander',
    'Heikki Linnakangas',
    'Robert Haas',
    'Jeff Davis',
    'Fujii Masao',
    'Noah Misch',
    'Andres Freund',
    'Dean Rasheed',
    'Alexander Korotkov',
    'Amit Kapila',
    'Tomas Vondra',
    'Michael Paquier',
    'Thomas Munro',
    'Peter Geoghegan',
    'Etsuro Fujita',
    'David Rowley',
    'Daniel Gustafsson',
    'John Naylor',
    'Nathan Bossart',
    'Amit Langote',
    'Masahiko Sawada',
    'Melanie Plageman',
    'Richard Guo',
    'Jacob Champion'
);
