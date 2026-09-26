import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-page-introuvable',
  imports: [RouterLink],
  template: `
    <section class="carte page-erreur">
      <h1>Page introuvable</h1>
      <p>Cette adresse ne correspond à aucune page de l'application.</p>
      <a class="bouton" routerLink="/">Retour au tableau de bord</a>
    </section>
  `,
})
export class PageIntrouvable {}
