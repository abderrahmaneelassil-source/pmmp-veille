import { ParamMap, Params } from '@angular/router';
import { STATUTS_CONSULTATION, StatutConsultation } from '../../core/api.types';
import { estDateJour, lendemain } from '../../core/format';
import { FiltresConsultations } from '../../services/consultations.service';

/** Les deux seuls champs filtrables côté API (texte « contient », casse ignorée). */
export type ChampRecherche = 'acheteur' | 'categorie';

export const TAILLES_PAGE = [10, 20, 50, 100, 200] as const;
export const TAILLE_DEFAUT = 20;

/**
 * Critères de la page Consultations. Ils vivent dans l'URL (?q=…&champ=…) : une
 * recherche se partage par lien et le bouton « Précédent » du navigateur fonctionne.
 */
export interface Criteres {
  champ: ChampRecherche;
  texte: string;
  statut: StatutConsultation | null;
  /** Date limite à partir de ce jour inclus (AAAA-MM-JJ). */
  du: string | null;
  /** Date limite jusqu'à ce jour inclus (AAAA-MM-JJ). */
  au: string | null;
  taille: number;
  page: number;
}

export const CRITERES_VIDES: Criteres = {
  champ: 'acheteur',
  texte: '',
  statut: null,
  du: null,
  au: null,
  taille: TAILLE_DEFAUT,
  page: 1,
};

/** Lit les critères de l'URL. Une valeur invalide (lien modifié à la main) est ignorée. */
export function lireCriteres(p: ParamMap): Criteres {
  const statut = p.get('statut');
  const taille = Number(p.get('taille'));
  const page = Number(p.get('page'));
  return {
    champ: p.get('champ') === 'categorie' ? 'categorie' : 'acheteur',
    texte: (p.get('q') ?? '').trim(),
    statut: STATUTS_CONSULTATION.includes(statut as StatutConsultation)
      ? (statut as StatutConsultation)
      : null,
    du: estDateJour(p.get('du')) ? p.get('du') : null,
    au: estDateJour(p.get('au')) ? p.get('au') : null,
    taille: (TAILLES_PAGE as readonly number[]).includes(taille) ? taille : TAILLE_DEFAUT,
    page: Number.isInteger(page) && page >= 1 ? page : 1,
  };
}

/** Paramètres d'URL ; les valeurs par défaut sont omises pour garder des liens courts. */
export function versParametresUrl(c: Criteres): Params {
  return {
    q: c.texte || null,
    // Gardé même sans texte : le sélecteur doit rester sur le champ choisi avant la frappe.
    champ: c.champ !== 'acheteur' ? c.champ : null,
    statut: c.statut,
    du: c.du,
    au: c.au,
    taille: c.taille !== TAILLE_DEFAUT ? c.taille : null,
    page: c.page > 1 ? c.page : null,
  };
}

/** Traduction exacte vers GET /consultations (api/main.py). */
export function versFiltresApi(c: Criteres): FiltresConsultations {
  const filtres: FiltresConsultations = {
    limit: c.taille,
    offset: (c.page - 1) * c.taille,
  };
  if (c.texte) {
    filtres[c.champ] = c.texte;
  }
  if (c.statut) {
    filtres.statut = c.statut;
  }
  if (c.du) {
    filtres.date_limite_apres = c.du; // >= minuit du jour choisi (heure du Maroc)
  }
  if (c.au) {
    // L'API exclut sa borne (date_limite_avant strict) : pour inclure toute la journée
    // choisie, on envoie le lendemain à minuit.
    filtres.date_limite_avant = lendemain(c.au);
  }
  return filtres;
}

/** Nombre de filtres avancés actifs (pour le libellé du panneau). */
export function nbFiltresAvances(c: Criteres): number {
  return [c.statut, c.du, c.au, c.taille !== TAILLE_DEFAUT ? c.taille : null].filter(
    (v) => v !== null,
  ).length;
}

/**
 * Filtre local sur l'objet, limité aux résultats déjà affichés : casse et accents
 * ignorés (« electricite » trouve « Électricité »).
 */
export function normaliser(texte: string): string {
  return texte.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}
