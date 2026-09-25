import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { BehaviorSubject, combineLatest, map, switchMap } from 'rxjs';
import { Consultation, Modification } from '../../core/api.types';
import { CHARGEMENT, suivre } from '../../core/chargement';
import { dateHeure } from '../../core/format';
import { DateCourtePipe, DateHeurePipe, DelaiRestantPipe } from '../../core/format.pipes';
import {
  STATUT_CONSULTATION,
  libelleChamp,
  libelleDceStatut,
  libelleStatut,
  libelleTypeEvenement,
  ouiNon,
} from '../../core/libelles';
import { ConsultationsService } from '../../services/consultations.service';
import { DerniereRecherche } from '../../services/derniere-recherche.service';
import { Badge } from '../../shared/badge';
import { Chargement, Erreur } from '../../shared/etats';

/** Champs dont les valeurs d'historique sont des dates ISO (history.py : to_text). */
const CHAMPS_DATE = new Set(['date_limite_depot', 'date_publication']);

/**
 * Les liens viennent de pages collectées sur un site externe : seuls http(s) sont
 * rendus cliquables (Angular neutralise déjà « javascript: », ceci est une seconde barrière).
 */
export function lienSur(url: string | null | undefined): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null;
}

@Component({
  selector: 'app-consultation-detail',
  imports: [RouterLink, Badge, Chargement, Erreur, DateCourtePipe, DateHeurePipe, DelaiRestantPipe],
  templateUrl: './consultation-detail.html',
})
export class ConsultationDetail {
  private readonly route = inject(ActivatedRoute);
  private readonly service = inject(ConsultationsService);
  protected readonly retour = inject(DerniereRecherche).parametres;
  private readonly rechargement = new BehaviorSubject<void>(undefined);

  private readonly cle$ = this.route.paramMap.pipe(
    map((p) => ({ org: p.get('org') ?? '', ref: p.get('ref') ?? '' })),
  );
  protected readonly cle = toSignal(this.cle$, { requireSync: true });

  protected readonly consultation = toSignal(
    combineLatest([this.cle$, this.rechargement]).pipe(
      switchMap(([{ org, ref }]) => suivre(this.service.detail(org, ref))),
    ),
    { initialValue: CHARGEMENT },
  );
  protected readonly historique = toSignal(
    combineLatest([this.cle$, this.rechargement]).pipe(
      switchMap(([{ org, ref }]) => suivre(this.service.historique(org, ref))),
    ),
    { initialValue: CHARGEMENT },
  );

  protected recharger(): void {
    this.rechargement.next();
  }

  protected statut(c: Consultation) {
    return libelleStatut(STATUT_CONSULTATION, c.statut);
  }
  protected typeEvenement(m: Modification) {
    return libelleTypeEvenement(m.type_evenement);
  }
  protected champ(m: Modification): string {
    return libelleChamp(m.champ);
  }
  protected valeur(m: Modification, v: string | null): string {
    if (v === null || v === '') {
      return '(vide)';
    }
    return CHAMPS_DATE.has(m.champ) ? dateHeure(v) : v;
  }
  protected dce(c: Consultation): string {
    return libelleDceStatut(c.dce_statut);
  }
  protected ouiNon(v: boolean | null): string {
    return ouiNon(v);
  }
  protected lien(url: string | null | undefined): string | null {
    return lienSur(url);
  }
}
