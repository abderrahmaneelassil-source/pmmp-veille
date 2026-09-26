import { Observable, catchError, map, of, startWith } from 'rxjs';
import { ApiErreur } from './api-erreur';

/** État d'un appel à l'API, tel qu'affiché par les pages. */
export type Etat<T> =
  { etat: 'chargement' } | { etat: 'ok'; donnees: T } | { etat: 'erreur'; erreur: ApiErreur };

export const CHARGEMENT: Etat<never> = { etat: 'chargement' };

/**
 * Transforme un appel en flux d'états : « chargement », puis « ok » ou « erreur ».
 * L'erreur est capturée ici : aucune erreur non gérée n'atteint la console.
 */
export function suivre<T>(appel: Observable<T>): Observable<Etat<T>> {
  return appel.pipe(
    map((donnees): Etat<T> => ({ etat: 'ok', donnees })),
    startWith(CHARGEMENT),
    catchError((e: unknown) =>
      of<Etat<T>>({
        etat: 'erreur',
        erreur:
          e instanceof ApiErreur
            ? e
            : new ApiErreur('inconnue', 0, "Erreur inattendue de l'application."),
      }),
    ),
  );
}
