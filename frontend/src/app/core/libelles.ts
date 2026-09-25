/**
 * Libellés français des valeurs techniques renvoyées par l'API.
 * Source de chaque liste : le code du collecteur (cité en commentaire). Une valeur
 * absente de ces listes est affichée telle quelle, jamais masquée.
 */

/** Tonalité visuelle d'un badge (voir styles.css, .badge--*). */
export type Ton = 'succes' | 'attention' | 'danger' | 'neutre' | 'info';

export interface Libelle {
  libelle: string;
  ton: Ton;
}

// db/schema.sql : CHECK consultations.statut
export const STATUT_CONSULTATION: Record<string, Libelle> = {
  en_cours: { libelle: 'En cours', ton: 'succes' },
  reporte: { libelle: 'Reportée', ton: 'attention' },
  annule: { libelle: 'Annulée', ton: 'danger' },
  cloture: { libelle: 'Clôturée', ton: 'neutre' },
};

// db/schema.sql : CHECK collecte_runs.statut
export const STATUT_RUN: Record<string, Libelle> = {
  succes: { libelle: 'Succès', ton: 'succes' },
  partiel: { libelle: 'Partiel', ton: 'attention' },
  echec: { libelle: 'Échec', ton: 'danger' },
  refuse: { libelle: 'Refusé', ton: 'neutre' },
  en_cours: { libelle: 'En cours', ton: 'info' },
};

export function libelleStatut(table: Record<string, Libelle>, valeur: string): Libelle {
  return table[valeur] ?? { libelle: valeur, ton: 'neutre' };
}

export interface LigneLegende {
  statut: string | null;
  code: string;
  signification: string;
}

/**
 * Statut enregistré en base ↔ code de sortie du collecteur (LastTaskResult de la tâche
 * planifiée). Source : EXIT_CODES (extensions.py) et __main__.py.
 */
export const LEGENDE_RUN: readonly LigneLegende[] = [
  { statut: 'succes', code: '0', signification: 'Run terminé normalement.' },
  {
    statut: 'echec',
    code: '1',
    signification:
      'Run arrêté sur erreur : arrêt de sécurité, aucune consultation extraite, erreurs de base, ou run interrompu (PC éteint, processus arrêté) détecté au run suivant.',
  },
  {
    statut: 'refuse',
    code: '2',
    signification:
      'Lancé hors de la fenêtre horaire autorisée : aucune requête envoyée au portail.',
  },
  {
    statut: 'partiel',
    code: '3',
    signification:
      'Arrêté par la fin de la fenêtre horaire : collecte incomplète, reprise au run suivant.',
  },
  {
    statut: null,
    code: '4',
    signification:
      "Un autre run était déjà en cours : refusé avant de démarrer. Ce cas n'est pas enregistré en base et n'apparaît donc jamais ici.",
  },
  {
    statut: 'en_cours',
    code: '—',
    signification: "Run en cours d'exécution (pas encore de code de sortie).",
  },
];

// extensions.py (run_status, spider_closed) et middlewares.py (REASON_*)
const RAISONS_RUN: Record<string, string> = {
  finished: 'Terminé normalement',
  circuit_breaker: "Arrêt de sécurité : trop d'erreurs ou de lenteurs consécutives du portail",
  refus_hors_fenetre: 'Refusé : hors de la fenêtre horaire autorisée',
  fin_fenetre_horaire: 'Arrêté : fin de la fenêtre horaire',
  aucune_consultation_extraite: 'Aucune consultation extraite de la liste',
  erreurs_base: "Erreurs d'enregistrement en base",
};

export function libelleRaison(raison: string | null): string {
  if (!raison) {
    return '—';
  }
  return RAISONS_RUN[raison] ?? raison;
}

// Compteurs pmmp/*_errors (spiders/pmmp.py, pipelines.py), sans le préfixe « pmmp/ »
const ERREURS_RUN: Record<string, string> = {
  listing_errors: 'Pages de liste en erreur',
  pagination_errors: 'Erreurs de pagination',
  parse_errors: "Erreurs d'extraction",
  detail_errors: 'Fiches détail en erreur',
  dce_errors: 'DCE en erreur',
  db_errors: 'Erreurs de base de données',
};

export function libelleErreurRun(cle: string): string {
  return ERREURS_RUN[cle] ?? cle;
}

export function libelleMode(mode: string): string {
  if (mode === 'prod') {
    return 'Production';
  }
  if (mode === 'test') {
    return 'Test';
  }
  return mode;
}

// db/schema.sql : CHECK historique_modifications.type_evenement
const TYPES_EVENEMENT: Record<string, Libelle> = {
  rectificatif: { libelle: 'Rectificatif', ton: 'info' },
  report_date: { libelle: 'Report de date', ton: 'attention' },
  annulation: { libelle: 'Annulation', ton: 'danger' },
  resultat: { libelle: 'Résultat publié', ton: 'succes' },
  autre: { libelle: 'Autre', ton: 'neutre' },
};

export function libelleTypeEvenement(type: string): Libelle {
  return libelleStatut(TYPES_EVENEMENT, type);
}

// history.py : TRACKED_FIELDS
const CHAMPS: Record<string, string> = {
  statut: 'Statut',
  date_limite_depot: 'Date limite de dépôt',
  objet: 'Objet',
  resultat: 'Résultat',
  reference: 'Référence',
  acheteur: 'Acheteur',
  categorie: 'Catégorie',
  lieu_execution: "Lieu d'exécution",
  reservation_pme: 'Réservé aux PME',
  reponse_electronique: 'Réponse électronique',
  date_publication: 'Date de publication',
};

export function libelleChamp(champ: string): string {
  return CHAMPS[champ] ?? champ;
}

// spiders/pmmp.py : valeurs de dce_statut
const DCE_STATUTS: Record<string, string> = {
  telecharge: 'Téléchargé',
  deja_present: 'Déjà téléchargé',
  aucun_lien: 'Aucun lien DCE sur la fiche',
  page_intermediaire: "Page intermédiaire (conditions d'utilisation) : non téléchargé",
  captcha: 'Bloqué par un captcha : non téléchargé',
  echec: 'Échec du téléchargement',
  echec_fiche_detail: 'Fiche détail en erreur',
  desactive: 'Téléchargement désactivé',
};

export function libelleDceStatut(statut: string | null): string {
  if (!statut) {
    return '—';
  }
  return DCE_STATUTS[statut] ?? statut;
}

export function ouiNon(valeur: boolean | null): string {
  if (valeur === null) {
    return 'Non précisé';
  }
  return valeur ? 'Oui' : 'Non';
}
