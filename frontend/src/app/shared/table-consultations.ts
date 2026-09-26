import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ConsultationResume } from '../core/api.types';
import { DateHeurePipe, DelaiRestantPipe } from '../core/format.pipes';
import { STATUT_CONSULTATION, libelleStatut } from '../core/libelles';
import { Badge } from './badge';

/** Tableau dense des consultations (liste et tableau de bord). */
@Component({
  selector: 'app-table-consultations',
  imports: [RouterLink, Badge, DateHeurePipe, DelaiRestantPipe],
  template: `
    <div class="table-conteneur">
      <table class="table">
        <thead>
          <tr>
            <th scope="col" class="col-date">Date limite</th>
            <th scope="col">Objet</th>
            <th scope="col" class="col-acheteur">Acheteur</th>
            @if (!compact()) {
              <th scope="col" class="col-categorie">Catégorie</th>
            }
            <th scope="col" class="col-statut">Statut</th>
          </tr>
        </thead>
        <tbody>
          @for (c of consultations(); track c.org_acronyme + '/' + c.ref_consultation) {
            <tr>
              <td class="col-date">
                <span class="nowrap">{{ c.date_limite_depot | dateHeure }}</span>
                <span class="texte-discret">{{ c.date_limite_depot | delaiRestant }}</span>
              </td>
              <td>
                <a
                  class="lien-objet"
                  [routerLink]="['/consultations', c.org_acronyme, c.ref_consultation]"
                  >{{ c.objet }}</a
                >
                @if (c.reference) {
                  <span class="texte-discret">Réf. {{ c.reference }}</span>
                }
              </td>
              <td class="col-acheteur">{{ c.acheteur }}</td>
              @if (!compact()) {
                <td class="col-categorie">{{ c.categorie ?? '—' }}</td>
              }
              <td class="col-statut"><app-badge [info]="statut(c.statut)" /></td>
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
})
export class TableConsultations {
  readonly consultations = input.required<ConsultationResume[]>();
  /** Version courte (tableau de bord) : sans la colonne catégorie. */
  readonly compact = input(false);

  protected statut(valeur: string) {
    return libelleStatut(STATUT_CONSULTATION, valeur);
  }
}
