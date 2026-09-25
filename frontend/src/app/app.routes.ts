import { Routes } from '@angular/router';

const SUFFIXE = ' — Veille PMMP';

export const routes: Routes = [
  {
    path: '**',
    title: 'Page introuvable' + SUFFIXE,
    loadComponent: () => import('./pages/page-introuvable').then((m) => m.PageIntrouvable),
  },
];
