-- Rôles PostgreSQL du collecteur PMMP (moindre privilège). Idempotent.
--
-- pmmp     : propriétaire de la base et des tables, SANS connexion possible. Sert
--            uniquement à faire évoluer le schéma (voir README §4.4).
-- pmmp_app : compte utilisé par le collecteur (PMMP_DATABASE_URL). Il lit, insère
--            et met à jour les données du projet, rien d'autre : ni DELETE, ni
--            TRUNCATE, ni CREATE, et aucune autre base.
--
-- À exécuter en superutilisateur, connecté à pmmp_veille, APRÈS db/schema.sql.
-- Le mot de passe de pmmp_app est lu dans la variable d'environnement
-- PMMP_APP_PASSWORD : il n'est jamais écrit dans ce fichier ni sur la ligne de commande.
--
--   PowerShell : $env:PMMP_APP_PASSWORD = "<mot de passe fort>"
--                psql -U postgres -h localhost -d pmmp_veille -f db/roles.sql
--                Remove-Item Env:PMMP_APP_PASSWORD
--
-- ATTENTION (serveur partagé) : la section « aucune autre base » retire le droit de
-- connexion accordé par défaut à PUBLIC sur TOUTES les autres bases du serveur. Les
-- autres applications doivent alors avoir un GRANT CONNECT explicite.

\set ON_ERROR_STOP on

SELECT current_database() = 'pmmp_veille' AS bonne_base \gset
\if :bonne_base
\else
  DO $$ BEGIN RAISE EXCEPTION 'Exécuter ce script connecté à la base pmmp_veille (-d pmmp_veille)'; END $$;
\endif

\getenv app_password PMMP_APP_PASSWORD
\if :{?app_password}
\else
  DO $$ BEGIN RAISE EXCEPTION 'Variable d''environnement PMMP_APP_PASSWORD non définie'; END $$;
\endif

-- --- Comptes --------------------------------------------------------------------
SELECT 'CREATE ROLE pmmp NOLOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pmmp') \gexec
SELECT 'CREATE ROLE pmmp_app' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pmmp_app') \gexec

ALTER ROLE pmmp_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT
    CONNECTION LIMIT 10 PASSWORD :'app_password';
-- Ancien compte applicatif : plus aucune connexion, mot de passe supprimé.
ALTER ROLE pmmp NOLOGIN PASSWORD NULL;

-- --- Accès à la base pmmp_veille uniquement ------------------------------------------
REVOKE ALL ON DATABASE pmmp_veille FROM PUBLIC;
GRANT CONNECT ON DATABASE pmmp_veille TO pmmp_app;
-- Aucune autre base : PUBLIC (et donc pmmp_app) perd le droit de connexion ailleurs.
SELECT format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', datname)
FROM pg_database WHERE datname <> 'pmmp_veille' AND datallowconn \gexec

-- --- Données du projet -----------------------------------------------------------
REVOKE CREATE ON SCHEMA public FROM PUBLIC;  -- déjà le cas depuis PostgreSQL 15
GRANT USAGE ON SCHEMA public TO pmmp_app;
GRANT SELECT, INSERT, UPDATE ON consultations, historique_modifications, collecte_runs TO pmmp_app;
GRANT SELECT ON v_dernier_run_reussi TO pmmp_app;
GRANT USAGE, SELECT ON SEQUENCE consultations_id_seq, historique_modifications_id_seq, collecte_runs_id_seq
    TO pmmp_app;
-- Tables et séquences ajoutées plus tard par pmmp : mêmes droits automatiquement.
ALTER DEFAULT PRIVILEGES FOR ROLE pmmp IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO pmmp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE pmmp IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO pmmp_app;

\echo 'Rôles appliqués : pmmp (propriétaire, NOLOGIN), pmmp_app (application).'
