-- Schéma du moteur de veille PMMP (TACHFIR)
-- Base créée en UTF-8 (voir README) ; toutes les dates sont en timestamptz
-- et affichées dans le fuseau Africa/Casablanca.
-- Idempotent : peut être rejoué sans effacer les données.

SET client_encoding = 'UTF8';
SET TIME ZONE 'Africa/Casablanca';

-- ---------------------------------------------------------------------------
-- Journal des exécutions : permet de détecter une panne silencieuse
-- (ex. aucun run 'succes' depuis plus de 24 h).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collecte_runs (
    id                BIGSERIAL PRIMARY KEY,
    demarre_le        timestamptz NOT NULL DEFAULT now(),
    termine_le        timestamptz,
    statut            text NOT NULL DEFAULT 'en_cours'
                      CHECK (statut IN ('en_cours', 'succes', 'partiel', 'echec', 'refuse')),
    raison            text,                 -- raison de fermeture Scrapy / circuit breaker
    force             boolean NOT NULL DEFAULT false,  -- lancé avec --force (test manuel)
    mode              text NOT NULL,        -- prod | test
    nb_pages          integer,
    nb_consultations  integer,              -- items insérés/mis à jour
    nb_ecartees       integer,              -- items rejetés par la validation
    stats             jsonb                 -- statistiques Scrapy complètes
);

-- ---------------------------------------------------------------------------
-- État courant de chaque consultation (un appel d'offres = une ligne)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consultations (
    id                    BIGSERIAL PRIMARY KEY,
    -- Clé naturelle : paramètres orgAcronyme et refConsultation des URL du portail
    org_acronyme          text NOT NULL,
    ref_consultation      text NOT NULL,
    reference             text,             -- référence affichée (ex. "12/2026/AOO")
    objet                 text NOT NULL,    -- arabe et/ou français
    acheteur              text NOT NULL,
    categorie             text,             -- Travaux / Fournitures / Services
    type_procedure        text,
    lieu_execution        text,
    date_publication      timestamptz,
    date_limite_depot     timestamptz NOT NULL,
    reservation_pme       boolean,          -- NULL = information absente de la page
    reponse_electronique  boolean,          -- true = réponse électronique exigée
    statut                text NOT NULL DEFAULT 'en_cours'
                          CHECK (statut IN ('en_cours', 'cloture', 'annule', 'reporte')),
    resultat              text,             -- attributaire / résultat s'il est publié
    url_detail            text NOT NULL,
    dce_urls              text[] NOT NULL DEFAULT '{}',
    dce_paths             text[] NOT NULL DEFAULT '{}',  -- chemins sur disque, jamais de blob
    dce_statut            text,             -- telecharge, deja_present, aucun_lien, page_intermediaire, captcha, echec...
    raw_html_detail_path  text,             -- dernière fiche détail archivée
    premiere_vue_le       timestamptz NOT NULL DEFAULT now(),
    derniere_vue_le       timestamptz NOT NULL DEFAULT now(),
    mis_a_jour_le         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT consultations_cle_naturelle UNIQUE (org_acronyme, ref_consultation)
);

CREATE INDEX IF NOT EXISTS consultations_date_limite_idx ON consultations (date_limite_depot);
CREATE INDEX IF NOT EXISTS consultations_statut_idx ON consultations (statut);

-- ---------------------------------------------------------------------------
-- Historique des versions : une ligne par champ modifié entre deux collectes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historique_modifications (
    id               BIGSERIAL PRIMARY KEY,
    consultation_id  bigint NOT NULL REFERENCES consultations(id) ON DELETE CASCADE,
    champ            text NOT NULL,
    ancienne_valeur  text,
    nouvelle_valeur  text,
    type_evenement   text NOT NULL
                     CHECK (type_evenement IN ('rectificatif', 'report_date', 'annulation', 'resultat', 'autre')),
    detecte_le       timestamptz NOT NULL DEFAULT now(),
    run_id           bigint REFERENCES collecte_runs(id)
);

CREATE INDEX IF NOT EXISTS historique_consultation_idx ON historique_modifications (consultation_id, detecte_le);

-- Supervision : dernier run réussi (à surveiller depuis un outil externe)
CREATE OR REPLACE VIEW v_dernier_run_reussi AS
SELECT max(termine_le) AS termine_le,
       now() - max(termine_le) AS anciennete
FROM collecte_runs
WHERE statut = 'succes';
