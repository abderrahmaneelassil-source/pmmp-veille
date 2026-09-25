import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, of, throwError } from 'rxjs';
import { ApiErreur } from '../core/api-erreur';
import { API_BASE, DernierRun, Sante } from '../core/api.types';

@Injectable({ providedIn: 'root' })
export class CollecteService {
  private readonly http = inject(HttpClient);

  /**
   * GET /health. En 503, l'API répond { api: "ok", base: "indisponible" } : c'est un
   * état de santé à afficher, pas une panne de l'API. Il est donc renvoyé comme une
   * réponse normale. Seule une API injoignable reste une erreur.
   */
  sante(): Observable<Sante> {
    return this.http.get<Sante>(`${API_BASE}/health`).pipe(
      catchError((e: unknown) => {
        if (e instanceof ApiErreur && e.type === 'base_indisponible' && estSante(e.corps)) {
          return of(e.corps);
        }
        return throwError(() => e);
      }),
    );
  }

  dernierRun(): Observable<DernierRun> {
    return this.http.get<DernierRun>(`${API_BASE}/collecte/dernier-run`);
  }
}

function estSante(corps: unknown): corps is Sante {
  return typeof corps === 'object' && corps !== null && 'api' in corps && 'base' in corps;
}
