import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import {
  BehaviorSubject,
  combineLatest,
  debounceTime,
  distinctUntilChanged,
  filter,
  map,
  scan,
  switchMap,
} from 'rxjs';
import { PageConsultations, STATUTS_CONSULTATION } from '../../core/api.types';
import { CHARGEMENT, Etat, suivre } from '../../core/chargement';
import { STATUT_CONSULTATION } from '../../core/libelles';
import { ConsultationsService } from '../../services/consultations.service';
import { DerniereRecherche } from '../../services/derniere-recherche.service';
import { Chargement, Erreur } from '../../shared/etats';
import { TableConsultations } from '../../shared/table-consultations';
import {
  ChampRecherche,
  Criteres,
  TAILLES_PAGE,
  lireCriteres,
  nbFiltresAvances,
  normaliser,
  versFiltresApi,
  versParametresUrl,
} from './criteres';

/** Délai de frappe avant d'interroger l'API. */
export const DELAI_RECHERCHE_MS = 300;

export const AIDE_RECHERCHE_AVANCEE =
  'Bientôt : recherche plein texte français/arabe et recherche sémantique (Phase 3 de la ' +
  'feuille de route). Elle nécessite des évolutions côté collecteur non encore réalisées.';

interface Vue {
  etat: Etat<PageConsultations>;
  /** Derniers résultats affichés, gardés à l'écran (estompés) pendant le chargement suivant. */
  precedent: PageConsultations | null;
}

@Component({
  selector: 'app-liste-consultations',
  imports: [ReactiveFormsModule, Chargement, Erreur, TableConsultations],
  templateUrl: './liste-consultations.html',
})
export class ListeConsultations {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly service = inject(ConsultationsService);
  private readonly derniereRecherche = inject(DerniereRecherche);
  private readonly rechargement = new BehaviorSubject<void>(undefined);

  private readonly criteres$ = this.route.queryParamMap.pipe(
    map(lireCriteres),
    distinctUntilChanged((a, b) => JSON.stringify(a) === JSON.stringify(b)),
  );
  protected readonly criteres = toSignal(this.criteres$, { requireSync: true });

  protected readonly vue = toSignal(
    combineLatest([this.criteres$, this.rechargement]).pipe(
      switchMap(([c]) => suivre(this.service.lister(versFiltresApi(c)))),
      scan(
        (avant: Vue, etat: Etat<PageConsultations>): Vue => ({
          etat,
          precedent:
            etat.etat === 'ok' ? etat.donnees : etat.etat === 'erreur' ? null : avant.precedent,
        }),
        { etat: CHARGEMENT, precedent: null },
      ),
    ),
    { initialValue: { etat: CHARGEMENT, precedent: null } as Vue },
  );

  protected readonly texte = new FormControl('', { nonNullable: true });
  /** Dernier texte envoyé dans l'URL par la frappe (voir le constructeur). */
  private texteEnvoye = '';

  protected readonly filtreObjet = signal('');
  protected readonly panneauOuvert = signal(false);

  protected readonly statuts = STATUTS_CONSULTATION.map((s) => ({
    valeur: s,
    libelle: STATUT_CONSULTATION[s].libelle,
  }));
  protected readonly tailles = TAILLES_PAGE;
  protected readonly aideAvancee = AIDE_RECHERCHE_AVANCEE;
  protected readonly nbAvances = computed(() => nbFiltresAvances(this.criteres()));
  protected readonly datesIncoherentes = computed(() => {
    const { du, au } = this.criteres();
    return du !== null && au !== null && du > au;
  });

  /** Résultats de la page courante, filtrés localement sur l'objet si demandé. */
  protected readonly lignes = computed(() => {
    const vue = this.vue();
    const page = vue.etat.etat === 'ok' ? vue.etat.donnees : vue.precedent;
    const filtre = normaliser(this.filtreObjet().trim());
    const resultats = page?.resultats ?? [];
    return filtre ? resultats.filter((c) => normaliser(c.objet).includes(filtre)) : resultats;
  });

  protected readonly pagination = computed(() => {
    const vue = this.vue();
    if (vue.etat.etat !== 'ok') {
      return null;
    }
    const { total, offset, resultats } = vue.etat.donnees;
    const { page, taille } = this.criteres();
    return {
      total,
      debut: resultats.length ? offset + 1 : 0,
      fin: offset + resultats.length,
      page,
      nbPages: Math.max(1, Math.ceil(total / taille)),
    };
  });

  constructor() {
    const initiaux = this.criteres();
    this.texte.setValue(initiaux.texte, { emitEvent: false });
    this.texteEnvoye = initiaux.texte;
    this.panneauOuvert.set(nbFiltresAvances(initiaux) > 0);

    // Frappe → URL, après DELAI_RECHERCHE_MS sans frappe (une requête, pas une par caractère).
    this.texte.valueChanges
      .pipe(
        debounceTime(DELAI_RECHERCHE_MS),
        map((t) => t.trim()),
        // Comparé à l'URL actuelle, pas à la frappe précédente : après un retour arrière,
        // retaper le même texte doit relancer la recherche.
        filter((t) => t !== this.criteres().texte),
        takeUntilDestroyed(),
      )
      .subscribe((t) => this.rechercher(t));

    // URL → champ de saisie, seulement si l'URL a changé pour une autre raison que la
    // frappe (bouton Précédent, réinitialisation) : sinon, une lettre tapée pendant la
    // navigation serait effacée.
    this.criteres$.pipe(takeUntilDestroyed()).subscribe((c) => {
      if (c.texte !== this.texteEnvoye) {
        this.texteEnvoye = c.texte;
        this.texte.setValue(c.texte, { emitEvent: false });
      }
      this.filtreObjet.set('');
      this.derniereRecherche.parametres.set(versParametresUrl(c));
    });
  }

  protected rechercher(texte = this.texte.value.trim()): void {
    this.texteEnvoye = texte;
    this.appliquer({ texte, page: 1 }, true);
  }

  protected changerChamp(champ: string): void {
    this.appliquer({ champ: champ === 'categorie' ? 'categorie' : 'acheteur', page: 1 });
  }

  protected changerStatut(valeur: string): void {
    const statut = STATUTS_CONSULTATION.find((s) => s === valeur) ?? null;
    this.appliquer({ statut, page: 1 });
  }

  protected changerDate(borne: 'du' | 'au', valeur: string): void {
    this.appliquer({ [borne]: valeur || null, page: 1 });
  }

  protected changerTaille(valeur: string): void {
    this.appliquer({ taille: Number(valeur), page: 1 });
  }

  protected allerPage(page: number): void {
    this.appliquer({ page });
  }

  protected reinitialiser(): void {
    this.router.navigate([], { relativeTo: this.route, queryParams: {} });
  }

  protected recharger(): void {
    this.rechargement.next();
  }

  protected placeholder(champ: ChampRecherche): string {
    return champ === 'acheteur'
      ? "Nom de l'acheteur, ex. : commune, direction, office…"
      : 'Catégorie, ex. : travaux, fournitures, services';
  }

  private appliquer(changement: Partial<Criteres>, remplacer = false): void {
    const criteres = { ...this.criteres(), ...changement };
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: versParametresUrl(criteres),
      replaceUrl: remplacer,
    });
  }
}
