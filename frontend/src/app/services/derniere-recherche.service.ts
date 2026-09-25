import { Injectable, signal } from '@angular/core';
import { Params } from '@angular/router';

/** Mémorise la dernière recherche pour que « Retour à la liste » la restaure depuis une fiche. */
@Injectable({ providedIn: 'root' })
export class DerniereRecherche {
  readonly parametres = signal<Params>({});
}
