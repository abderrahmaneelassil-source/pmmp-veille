import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

interface EntreeMenu {
  libelle: string;
  lien: string;
  exact?: boolean;
}

interface EntreeAVenir {
  libelle: string;
  ancre: string;
}

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
})
export class App {
  protected readonly menu: EntreeMenu[] = [
    { libelle: 'Tableau de bord', lien: '/', exact: true },
    { libelle: 'Consultations', lien: '/consultations' },
    { libelle: 'Suivi de la collecte', lien: '/collecte' },
    { libelle: 'Feuille de route', lien: '/feuille-de-route' },
  ];

  /** Fonctionnalités prévues : menant à la feuille de route, pas à une fausse page. */
  protected readonly aVenir: EntreeAVenir[] = [
    { libelle: 'Alertes', ancre: 'phase-3' },
    { libelle: 'Suivi commercial', ancre: 'phase-3' },
    { libelle: 'Analyse IA', ancre: 'phase-4' },
  ];
}
