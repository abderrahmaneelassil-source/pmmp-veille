import { Component } from '@angular/core';

type Avancement = 'disponible' | 'prevu';

interface Element {
  titre: string;
  detail: string;
  avancement: Avancement;
}

interface Phase {
  id: string;
  titre: string;
  objectif: string;
  elements: Element[];
}

/** Contenu de la feuille de route du projet (Phases 3 et 4), repris tel quel. */
export const PHASES: readonly Phase[] = [
  {
    id: 'phase-3',
    titre: 'Phase 3 — Moteur de recherche',
    objectif: 'Rendre les données consultables : recherche, filtres, alertes.',
    elements: [
      {
        titre: 'Recherche plein texte français/arabe',
        detail: 'Le portail est bilingue.',
        avancement: 'prevu',
      },
      {
        titre: 'Recherche sémantique',
        detail: "Les intitulés varient beaucoup d'un acheteur à l'autre.",
        avancement: 'prevu',
      },
      {
        titre: 'Filtres : catégorie, acheteur, date limite, statut',
        detail: 'Disponibles dans la page Consultations.',
        avancement: 'disponible',
      },
      {
        titre: 'Filtres : lieu, réservation PME, réponse électronique',
        detail: 'Ces champs ne sont pas encore filtrables côté API.',
        avancement: 'prevu',
      },
      {
        titre: 'Alertes',
        detail: 'Recherches sauvegardées, résumé par email.',
        avancement: 'prevu',
      },
      {
        titre: 'Suivi commercial',
        detail: 'À qualifier / go / en préparation / déposé / résultat.',
        avancement: 'prevu',
      },
    ],
  },
  {
    id: 'phase-4',
    titre: 'Phase 4 — Analyse par IA',
    objectif:
      "Utiliser l'IA seulement là où elle apporte de la valeur, sur les dossiers présélectionnés.",
    elements: [
      {
        titre: 'Tri par score de pertinence',
        detail: 'Modèle léger + règles.',
        avancement: 'prevu',
      },
      {
        titre: 'Analyse des DCE',
        detail: 'Extraction structurée des exigences, cautions, délais.',
        avancement: 'prevu',
      },
      {
        titre: 'Go/no-go',
        detail: "Confrontation aux capacités de l'entreprise.",
        avancement: 'prevu',
      },
      {
        titre: 'Aide à la réponse',
        detail: 'Premier jet de mémoire technique.',
        avancement: 'prevu',
      },
    ],
  },
];

@Component({
  selector: 'app-feuille-de-route',
  template: `
    <header class="entete-page">
      <h1>Feuille de route</h1>
      <p class="texte-discret">
        Ce qui est disponible aujourd'hui et ce qui est prévu pour la suite du projet.
      </p>
    </header>

    @for (phase of phases; track phase.id) {
      <section class="carte" [id]="phase.id">
        <h2>{{ phase.titre }}</h2>
        <p class="objectif">{{ phase.objectif }}</p>
        <ul class="feuille-route">
          @for (e of phase.elements; track e.titre) {
            <li class="feuille-route__element">
              <span class="etat-avancement etat-avancement--{{ e.avancement }}">
                {{ e.avancement === 'disponible' ? '✅ Disponible dès cette version' : '🔜 Prévu' }}
              </span>
              <div>
                <p class="feuille-route__titre">{{ e.titre }}</p>
                <p class="texte-discret">{{ e.detail }}</p>
              </div>
            </li>
          }
        </ul>
      </section>
    }
  `,
})
export class FeuilleDeRoute {
  protected readonly phases = PHASES;
}
