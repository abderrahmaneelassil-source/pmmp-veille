import { Component, computed, input, output } from '@angular/core';
import { DernierRun, Sante } from '../core/api.types';
import { Etat } from '../core/chargement';
import { plusAncienQue } from '../core/format';
import { DateHeurePipe, DepuisPipe, DureePipe } from '../core/format.pipes';
import {
  LEGENDE_RUN,
  STATUT_RUN,
  libelleErreurRun,
  libelleMode,
  resumerRaison,
  libelleStatut,
} from '../core/libelles';
import { Badge } from './badge';
import { Chargement, Erreur } from './etats';

/** Au-delà, l'absence de run réussi signale une panne silencieuse (db/schema.sql). */
const SEUIL_PANNE_HEURES = 24;

/** Contenu de GET /collecte/dernier-run (tableau de bord et page Suivi de la collecte). */
@Component({
  selector: 'app-resume-run',
  imports: [Badge, DateHeurePipe, DepuisPipe, DureePipe],
  template: `
    @if (donnees().dernier_run; as run) {
      <div class="ligne-titre">
        <app-badge [info]="statutRun(run.statut)" />
        <span class="texte-discret">Run n° {{ run.id }}</span>
      </div>
      <dl class="infos">
        <div>
          <dt>Déclenchement</dt>
          <dd>
            {{
              run.force
                ? 'Test manuel (--force, run plafonné)'
                : 'Run normal (tâche planifiée ou lancement dans la fenêtre horaire)'
            }}
          </dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd>{{ mode(run.mode) }}</dd>
        </div>
        <div>
          <dt>Début</dt>
          <dd>
            {{ run.demarre_le | dateHeure }}
            <span class="texte-discret">{{ run.demarre_le | depuis }}</span>
          </dd>
        </div>
        <div>
          <dt>Fin</dt>
          <dd>{{ run.termine_le ? (run.termine_le | dateHeure) : 'Non terminé' }}</dd>
        </div>
        <div>
          <dt>Durée</dt>
          <dd>{{ run.duree_secondes | duree }}</dd>
        </div>
        <div>
          <dt>Raison de fin</dt>
          <dd>{{ raison().resume }}</dd>
        </div>
        <div>
          <dt>Pages de liste lues</dt>
          <dd>{{ run.nb_pages ?? '—' }}</dd>
        </div>
        <div>
          <dt>Consultations enregistrées ou mises à jour</dt>
          <dd>{{ run.nb_consultations ?? '—' }}</dd>
        </div>
        <div>
          <dt>Écartées (données invalides)</dt>
          <dd>{{ run.nb_ecartees ?? '—' }}</dd>
        </div>
      </dl>
      @if (raison().detail; as detail) {
        <details class="repli repli--technique">
          <summary>Détail technique de l'arrêt</summary>
          <p class="texte-technique">{{ detail }}</p>
        </details>
      }
      @if (erreurs().length) {
        <div class="alerte alerte--attention">
          <p class="alerte__titre">Erreurs comptées pendant ce run</p>
          <ul class="liste-simple">
            @for (e of erreurs(); track e.cle) {
              <li>
                {{ e.libelle }} : <strong>{{ e.nombre }}</strong>
              </li>
            }
          </ul>
        </div>
      } @else {
        <p class="texte-discret">Aucune erreur comptée pendant ce run.</p>
      }
      @if (run.statut !== 'succes') {
        <p>
          Dernier run réussi :
          @if (donnees().dernier_succes_le) {
            <strong>{{ donnees().dernier_succes_le | dateHeure }}</strong>
            <span class="texte-discret">{{ donnees().dernier_succes_le | depuis }}</span>
          } @else {
            <strong>aucun</strong>
          }
        </p>
      }
      @if (panneSilencieuse()) {
        <div class="alerte alerte--danger" role="alert">
          Aucun run réussi depuis plus de 24 h : vérifier la tâche planifiée « PMMP-Veille » et le
          log du dernier run (storage/logs).
        </div>
      }
    } @else {
      <p class="vide">
        Aucun run enregistré : le collecteur n'a encore jamais tourné sur cette base.
      </p>
    }
  `,
})
export class ResumeRun {
  readonly donnees = input.required<DernierRun>();

  protected readonly erreurs = computed(() =>
    Object.entries(this.donnees().dernier_run?.erreurs ?? {})
      .filter(([, nombre]) => nombre > 0)
      .map(([cle, nombre]) => ({ cle, nombre, libelle: libelleErreurRun(cle) })),
  );

  protected readonly raison = computed(() =>
    resumerRaison(this.donnees().dernier_run?.raison ?? null),
  );

  protected readonly panneSilencieuse = computed(
    () =>
      this.donnees().dernier_run !== null &&
      plusAncienQue(this.donnees().dernier_succes_le, SEUIL_PANNE_HEURES),
  );

  protected statutRun(statut: string) {
    return libelleStatut(STATUT_RUN, statut);
  }
  protected mode(mode: string) {
    return libelleMode(mode);
  }
}

/** Correspondance statut en base ↔ code de sortie du collecteur. */
@Component({
  selector: 'app-legende-run',
  imports: [Badge],
  template: `
    <table class="table table--legende">
      <thead>
        <tr>
          <th scope="col">Statut affiché</th>
          <th scope="col">Code de sortie</th>
          <th scope="col">Signification</th>
        </tr>
      </thead>
      <tbody>
        @for (l of legende; track l.code) {
          <tr>
            <td>
              @if (l.statut) {
                <app-badge [info]="statutRun(l.statut)" />
              } @else {
                <span class="texte-discret">Non enregistré</span>
              }
            </td>
            <td>
              <code>{{ l.code }}</code>
            </td>
            <td>{{ l.signification }}</td>
          </tr>
        }
      </tbody>
    </table>
    <p class="texte-discret">
      Le code de sortie est celui du processus du collecteur : c'est le « Dernier résultat » de la
      tâche planifiée Windows (LastTaskResult).
    </p>
  `,
})
export class LegendeRun {
  protected readonly legende = LEGENDE_RUN;
  protected statutRun(statut: string) {
    return libelleStatut(STATUT_RUN, statut);
  }
}

/** Contenu de GET /health, y compris quand l'API ou la base ne répond pas. */
@Component({
  selector: 'app-sante',
  imports: [Chargement, Erreur],
  template: `
    @let e = etat();
    @if (e.etat === 'chargement') {
      <app-chargement texte="Vérification…" />
    } @else if (e.etat === 'erreur') {
      <app-erreur [erreur]="e.erreur" titre="API injoignable" (reessayer)="reessayer.emit()" />
    } @else {
      <ul class="liste-sante">
        <li class="indicateur indicateur--ok">
          <span class="point" aria-hidden="true"></span>API : opérationnelle
        </li>
        @if (e.donnees.base === 'ok') {
          <li class="indicateur indicateur--ok">
            <span class="point" aria-hidden="true"></span>Base de données : connectée
            @if (e.donnees.base_de_donnees) {
              <code>{{ e.donnees.base_de_donnees }}</code>
            }
          </li>
          <li
            class="indicateur"
            [class.indicateur--ok]="e.donnees.lecture_seule"
            [class.indicateur--ko]="!e.donnees.lecture_seule"
          >
            <span class="point" aria-hidden="true"></span>Session en lecture seule :
            {{ e.donnees.lecture_seule ? 'oui' : 'non' }}
          </li>
        } @else {
          <li class="indicateur indicateur--ko">
            <span class="point" aria-hidden="true"></span>Base de données : indisponible
          </li>
        }
      </ul>
      @if (e.donnees.base !== 'ok') {
        <p class="texte-discret">
          L'API tourne, mais ne peut pas lire PostgreSQL : vérifier que le service PostgreSQL est
          démarré et que PMMP_DATABASE_URL (.env) est correct.
        </p>
      }
    }
  `,
})
export class CarteSante {
  readonly etat = input.required<Etat<Sante>>();
  readonly reessayer = output<void>();
}
