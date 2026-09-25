import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { API_BASE } from './api.types';

export type TypeErreur =
  'api_injoignable' | 'base_indisponible' | 'introuvable' | 'parametres' | 'serveur' | 'inconnue';

export const COMMANDE_API = 'python -m uvicorn api.main:app --host 127.0.0.1 --port 8000';

/** Erreur d'appel à l'API, traduite en message français (voir apiErreurInterceptor). */
export class ApiErreur extends Error {
  constructor(
    readonly type: TypeErreur,
    readonly statut: number,
    message: string,
    /** Corps JSON de la réponse, s'il y en a un (ex. /health en 503). */
    readonly corps: unknown = null,
  ) {
    super(message);
    this.name = 'ApiErreur';
  }
}

export function versApiErreur(e: HttpErrorResponse): ApiErreur {
  // 0 : requête bloquée ou serveur absent. 502/504 : le proxy de `ng serve` n'a pas
  // joint l'API (mesuré : API arrêtée → 502 Bad Gateway, corps vide).
  if (e.status === 0 || e.status === 502 || e.status === 504) {
    return new ApiErreur(
      'api_injoignable',
      e.status,
      // La commande de lancement (COMMANDE_API) est affichée à part, par le composant Erreur.
      "L'API ne répond pas (arrêtée, ou lancée sur un autre port que 8000).",
    );
  }
  if (e.status === 503) {
    return new ApiErreur(
      'base_indisponible',
      503,
      "L'API répond, mais la base de données est indisponible (PostgreSQL arrêté ou inaccessible).",
      e.error,
    );
  }
  if (e.status === 404) {
    return new ApiErreur('introuvable', 404, 'Élément introuvable.', e.error);
  }
  if (e.status === 422) {
    return new ApiErreur('parametres', 422, "Paramètres de recherche refusés par l'API.", e.error);
  }
  if (e.status >= 500) {
    return new ApiErreur(
      'serveur',
      e.status,
      `Erreur interne de l'API (code ${e.status}). Le détail est dans le terminal où tourne l'API.`,
    );
  }
  return new ApiErreur(
    'inconnue',
    e.status,
    `Erreur inattendue de l'API (code ${e.status}).`,
    e.error,
  );
}

/** Traduit toute erreur HTTP d'un appel à l'API en ApiErreur, au même endroit pour toute l'application. */
export const apiErreurInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(API_BASE)) {
    return next(req);
  }
  return next(req).pipe(
    catchError((e: unknown) =>
      throwError(() => (e instanceof HttpErrorResponse ? versApiErreur(e) : e)),
    ),
  );
};
