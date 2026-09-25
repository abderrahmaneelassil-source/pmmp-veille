import { Component, input, output } from '@angular/core';
import { ApiErreur, COMMANDE_API } from '../core/api-erreur';

@Component({
  selector: 'app-chargement',
  template: `
    <div class="chargement" role="status" aria-live="polite">
      <span class="chargement__roue" aria-hidden="true"></span>
      {{ texte() }}
    </div>
  `,
})
export class Chargement {
  readonly texte = input('Chargement…');
}

/** Message d'erreur d'appel à l'API, identique sur toutes les pages. */
@Component({
  selector: 'app-erreur',
  template: `
    <div class="alerte alerte--danger" role="alert">
      <p class="alerte__titre">{{ titre() }}</p>
      <p>{{ erreur().message }}</p>
      @if (erreur().type === 'api_injoignable') {
        <p class="alerte__aide">
          Commande à lancer depuis le dossier du projet :
          <code>{{ commande }}</code>
        </p>
      }
      <button type="button" class="bouton bouton--secondaire" (click)="reessayer.emit()">
        Réessayer
      </button>
    </div>
  `,
})
export class Erreur {
  readonly erreur = input.required<ApiErreur>();
  readonly titre = input('Données indisponibles');
  readonly reessayer = output<void>();
  protected readonly commande = COMMANDE_API;
}
