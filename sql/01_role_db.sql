-- Create role and database (run as superuser like postgres)
-- Adjust password before running in production
CREATE ROLE tracker LOGIN PASSWORD 'changeme' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE tracker OWNER tracker ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE tracker TO tracker;

-- Optional extension(s)
-- \c tracker
-- CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
