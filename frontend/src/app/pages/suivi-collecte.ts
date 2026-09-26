import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { BehaviorSubject, switchMap } from 'rxjs';
import { CHARGEMENT, suivre } from '../core/chargement';
import { CollecteService } from '../services/collecte.service';
import { CarteSante, LegendeRun, ResumeRun } from '../shared/collecte';
import { Chargement, Erreur } from '../shared/etats';

@Component({
  selector: 'app-suivi-collecte',
  imports: [CarteSante, LegendeRun, ResumeRun, Chargement, Erreur],
  template: `
    <header class="entete-page">
      <h1>Suivi de la collecte</h1>
      <p class="texte-discret">
        Le collecteur et l'API sont deux programmes indépendants : le collecteur peut tourner même
        quand l'API est arrêtée. Cette page affiche ce que le collecteur a enregistré en base.
      </p>
    </header>

    <div class="grille-cartes">
      <section class="carte">
        <h2>Dernier run</h2>
        @let run = dernierRun();
        @if (run.etat === 'chargement') {
          <app-chargement />
        } @else if (run.etat === 'erreur') {
          <app-erreur
            [erreur]="run.erreur"
            titre="État de la collecte indisponible"
            (reessayer)="recharger()"
          />
          <p class="texte-discret">
            Sans l'API, l'état de la collecte reste lisible dans le log du run
            (storage/logs/run_&lt;date&gt;.log) et dans le Planificateur de tâches (tâche
            PMMP-Veille).
          </p>
        } @else {
          <app-resume-run [donnees]="run.donnees" />
        }
      </section>

      <section class="carte">
        <h2>Santé de l'API et de la base</h2>
        <app-sante [etat]="sante()" (reessayer)="recharger()" />
      </section>
    </div>

    <section class="carte">
      <h2>Légende des statuts de run</h2>
      <app-legende-run />
    </section>
  `,
})
export class SuiviCollecte {
  private readonly collecte = inject(CollecteService);
  private readonly rechargement = new BehaviorSubject<void>(undefined);

  protected readonly dernierRun = toSignal(
    this.rechargement.pipe(switchMap(() => suivre(this.collecte.dernierRun()))),
    { initialValue: CHARGEMENT },
  );
  protected readonly sante = toSignal(
    this.rechargement.pipe(switchMap(() => suivre(this.collecte.sante()))),
    { initialValue: CHARGEMENT },
  );

  protected recharger(): void {
    this.rechargement.next();
  }
}
