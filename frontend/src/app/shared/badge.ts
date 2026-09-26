import { Component, input } from '@angular/core';
import { Libelle } from '../core/libelles';

/** Pastille de statut. Seul endroit, avec les alertes, où la couleur porte un sens. */
@Component({
  selector: 'app-badge',
  template: `<span class="badge badge--{{ info().ton }}">{{ info().libelle }}</span>`,
})
export class Badge {
  readonly info = input.required<Libelle>();
}
