/**
 * Types des réponses de l'API, alignés champ par champ sur api/schemas.py.
 * Les dates arrivent en chaînes ISO 8601 avec décalage (ex. "2026-11-05T10:00:00Z").
 */

/**
 * Préfixe de toutes les requêtes vers l'API. En développement, le proxy de `ng serve`
 * (proxy.conf.json) renvoie /api/... vers http://127.0.0.1:8000/... : pas de CORS à gérer.
 */
export const API_BASE = '/api';

/** Valeurs du CHECK consultations.statut (db/schema.sql). */
export type StatutConsultation = 'en_cours' | 'cloture' | 'annule' | 'reporte';
export const STATUTS_CONSULTATION: readonly StatutConsultation[] = [
  'en_cours',
  'cloture',
  'annule',
  'reporte',
];

/** Valeurs du CHECK collecte_runs.statut (db/schema.sql). */
export type StatutRun = 'en_cours' | 'succes' | 'partiel' | 'echec' | 'refuse';

export interface Sante {
  api: string;
  base: string;
  base_de_donnees?: string | null;
  lecture_seule?: boolean | null;
}

export interface ConsultationResume {
  org_acronyme: string;
  ref_consultation: string;
  reference: string | null;
  objet: string;
  acheteur: string;
  categorie: string | null;
  type_procedure: string | null;
  lieu_execution: string | null;
  date_publication: string | null;
  date_limite_depot: string;
  statut: string;
  url_detail: string;
}

export interface Consultation extends ConsultationResume {
  reservation_pme: boolean | null;
  reponse_electronique: boolean | null;
  resultat: string | null;
  dce_urls: string[];
  dce_statut: string | null;
  premiere_vue_le: string;
  derniere_vue_le: string;
  mis_a_jour_le: string;
}

export interface PageConsultations {
  total: number;
  limit: number;
  offset: number;
  resultats: ConsultationResume[];
}

export interface Modification {
  champ: string;
  ancienne_valeur: string | null;
  nouvelle_valeur: string | null;
  type_evenement: string;
  detecte_le: string;
  run_id: number | null;
}

export interface Run {
  id: number;
  statut: string;
  mode: string;
  force: boolean;
  demarre_le: string;
  termine_le: string | null;
  duree_secondes: number | null;
  raison: string | null;
  nb_pages: number | null;
  nb_consultations: number | null;
  nb_ecartees: number | null;
  /** Compteurs pmmp/*_errors du run, sans le préfixe (ex. { detail_errors: 2 }). */
  erreurs: Record<string, number>;
}

export interface DernierRun {
  /** null : le collecteur n'a encore jamais tourné. */
  dernier_run: Run | null;
  dernier_succes_le: string | null;
}
