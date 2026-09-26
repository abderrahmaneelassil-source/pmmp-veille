import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { BehaviorSubject, switchMap } from 'rxjs';
import { CHARGEMENT, suivre } from '../core/chargement';
import { CollecteService } from '../services/collecte.service';
import { ConsultationsService } from '../services/consultations.service';
import { CarteSante, LegendeRun, ResumeRun } from '../shared/collecte';
import { Chargement, Erreur } from '../shared/etats';
import { TableConsultations } from '../shared/table-consultations';

const NB_ECHEANCES = 5;

/**
 * Page d'accueil : trois appels seulement (dernier run, santé, 5 échéances), l'API
 * n'acceptant que 3 connexions simultanées.
 */
@Component({
  selector: 'app-tableau-de-bord',
  imports: [RouterLink, CarteSante, LegendeRun, ResumeRun, Chargement, Erreur, TableConsultations],
  template: `
    <header class="entete-page">
      <h1>Tableau de bord</h1>
      <p class="texte-discret">État de la collecte et prochaines échéances.</p>
    </header>

    <div class="grille-cartes">
      <section class="carte">
        <h2>Dernière collecte</h2>
        @let run = dernierRun();
        @if (run.etat === 'chargement') {
          <app-chargement />
        } @else if (run.etat === 'erreur') {
          <app-erreur [erreur]="run.erreur" (reessayer)="recharger()" />
        } @else {
          <app-resume-run [donnees]="run.donnees" />
          <details class="repli">
            <summary>Légende des statuts</summary>
            <app-legende-run />
          </details>
        }
        <a routerLink="/collecte" class="lien-carte">Suivi détaillé de la collecte →</a>
      </section>

      <section class="carte">
        <h2>Santé</h2>
        <app-sante [etat]="sante()" (reessayer)="recharger()" />
      </section>
    </div>

    <section class="carte">
      <div class="ligne-titre ligne-titre--espacee">
        <h2>Prochaines échéances</h2>
        <a [routerLink]="['/consultations']" [queryParams]="{ statut: 'en_cours' }"
          >Toutes les consultations en cours →</a
        >
      </div>
      @let prochaines = echeances();
      @if (prochaines.etat === 'chargement') {
        <app-chargement />
      } @else if (prochaines.etat === 'erreur') {
        <app-erreur [erreur]="prochaines.erreur" (reessayer)="recharger()" />
      } @else if (prochaines.donnees.resultats.length === 0) {
        <p class="vide">Aucune consultation en cours.</p>
      } @else {
        <app-table-consultations [consultations]="prochaines.donnees.resultats" [compact]="true" />
        <p class="texte-discret">
          {{ prochaines.donnees.resultats.length }} plus proches sur
          {{ prochaines.donnees.total }} consultations en cours.
        </p>
      }
    </section>
  `,
})
export class TableauDeBord {
  private readonly collecte = inject(CollecteService);
  private readonly consultations = inject(ConsultationsService);
  private readonly rechargement = new BehaviorSubject<void>(undefined);

  protected readonly dernierRun = toSignal(
    this.rechargement.pipe(switchMap(() => suivre(this.collecte.dernierRun()))),
    { initialValue: CHARGEMENT },
  );
  protected readonly sante = toSignal(
    this.rechargement.pipe(switchMap(() => suivre(this.collecte.sante()))),
    { initialValue: CHARGEMENT },
  );
  protected readonly echeances = toSignal(
    this.rechargement.pipe(
      switchMap(() =>
        suivre(this.consultations.lister({ statut: 'en_cours', limit: NB_ECHEANCES })),
      ),
    ),
    { initialValue: CHARGEMENT },
  );

  protected recharger(): void {
    this.rechargement.next();
  }
}
