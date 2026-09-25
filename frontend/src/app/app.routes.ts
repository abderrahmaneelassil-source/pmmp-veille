import { Routes } from '@angular/router';

const SUFFIXE = ' — Veille PMMP';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: 'Tableau de bord' + SUFFIXE,
    loadComponent: () => import('./pages/tableau-de-bord').then((m) => m.TableauDeBord),
  },
  {
    path: 'consultations',
    title: 'Consultations' + SUFFIXE,
    loadComponent: () =>
      import('./pages/consultations/liste-consultations').then((m) => m.ListeConsultations),
  },
  {
    path: 'consultations/:org/:ref',
    title: 'Fiche consultation' + SUFFIXE,
    loadComponent: () =>
      import('./pages/consultation-detail/consultation-detail').then((m) => m.ConsultationDetail),
  },
  {
    path: 'collecte',
    title: 'Suivi de la collecte' + SUFFIXE,
    loadComponent: () => import('./pages/suivi-collecte').then((m) => m.SuiviCollecte),
  },
  {
    path: 'feuille-de-route',
    title: 'Feuille de route' + SUFFIXE,
    loadComponent: () => import('./pages/feuille-de-route').then((m) => m.FeuilleDeRoute),
  },
  {
    path: '**',
    title: 'Page introuvable' + SUFFIXE,
    loadComponent: () => import('./pages/page-introuvable').then((m) => m.PageIntrouvable),
  },
];
