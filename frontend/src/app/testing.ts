/** Jeux de données des tests, au format exact de l'API (valeurs issues de pmmp_veille). */
import {
  Consultation,
  ConsultationResume,
  DernierRun,
  Modification,
  PageConsultations,
} from './core/api.types';

export function resume(ref: string, extra: Partial<ConsultationResume> = {}): ConsultationResume {
  return {
    org_acronyme: 'o8p',
    ref_consultation: ref,
    reference: 'AO13/2026',
    objet: 'TRAVAUX DE PROTECTION DU LITTORAL DE SALE -PHASE 1',
    acheteur: "M3 / DPETLER - DIRECTION PROVINCIALE DE L'EQUIPEMENT DE RABAT",
    categorie: 'Travaux',
    type_procedure: "Appel d'offres ouvert | Sur offre de prix",
    lieu_execution: 'SALE SALE',
    date_publication: '2026-09-22T00:00:00Z',
    date_limite_depot: '2026-11-05T10:00:00Z',
    statut: 'en_cours',
    url_detail:
      'https://www.marchespublics.gov.ma/?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1037543&orgAcronyme=o8p',
    ...extra,
  };
}

export function page(
  resultats: ConsultationResume[],
  total = resultats.length,
  offset = 0,
  limit = 20,
): PageConsultations {
  return { total, limit, offset, resultats };
}

export function consultation(extra: Partial<Consultation> = {}): Consultation {
  return {
    ...resume('1037543'),
    reservation_pme: null,
    reponse_electronique: true,
    resultat: null,
    dce_urls: [
      'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDemandeTelechargementDce&refConsultation=1037543&orgAcronyme=o8p',
    ],
    dce_statut: 'page_intermediaire',
    premiere_vue_le: '2026-09-25T16:30:34Z',
    derniere_vue_le: '2026-09-25T16:30:34Z',
    mis_a_jour_le: '2026-09-25T16:30:34Z',
    ...extra,
  };
}

export const MODIFICATIONS: Modification[] = [
  {
    champ: 'date_limite_depot',
    ancienne_valeur: '2026-10-20T10:00:00+01:00',
    nouvelle_valeur: '2026-11-05T10:00:00+00:00',
    type_evenement: 'report_date',
    detecte_le: '2026-09-24T06:30:00Z',
    run_id: 1,
  },
  {
    champ: 'objet',
    ancienne_valeur: 'Travaux',
    nouvelle_valeur: 'Travaux — تهيئة',
    type_evenement: 'rectificatif',
    detecte_le: '2026-09-24T06:31:00Z',
    run_id: 1,
  },
];

export function dernierRun(
  extra: Partial<NonNullable<DernierRun['dernier_run']>> = {},
  succes: string | null = null,
): DernierRun {
  const run = {
    id: 2,
    statut: 'succes',
    mode: 'prod',
    force: true,
    demarre_le: '2026-09-25T16:29:19Z',
    termine_le: '2026-09-25T16:30:46Z',
    duree_secondes: 87,
    raison: 'finished',
    nb_pages: 2,
    nb_consultations: 10,
    nb_ecartees: 0,
    erreurs: {},
    ...extra,
  };
  return { dernier_run: run, dernier_succes_le: succes ?? run.termine_le };
}

/**
 * Texte visible d'un élément, espaces normalisés. Un espace sépare les cellules de
 * tableau et les couples libellé/valeur (dt/dd), comme à l'écran.
 */
export function texte(el: Element | null | undefined): string {
  if (!el) {
    return '';
  }
  const copie = el.cloneNode(true) as Element;
  copie.querySelectorAll('dt, dd, td, th, li, p, h1, h2').forEach((e) => e.append(' '));
  return (copie.textContent ?? '').replace(/\s+/g, ' ').trim();
}
