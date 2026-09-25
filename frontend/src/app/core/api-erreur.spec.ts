import {
  HttpClient,
  HttpErrorResponse,
  provideHttpClient,
  withInterceptors,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ApiErreur, COMMANDE_API, apiErreurInterceptor, versApiErreur } from './api-erreur';

function reponse(status: number, error: unknown = null): HttpErrorResponse {
  return new HttpErrorResponse({ status, error, url: '/api/x' });
}

describe('traduction des erreurs HTTP', () => {
  it('API arrêtée (0, ou 502 renvoyé par le proxy de ng serve) → « API injoignable »', () => {
    for (const status of [0, 502, 504]) {
      const e = versApiErreur(reponse(status));
      expect(e.type).toBe('api_injoignable');
      expect(e.message).toContain("L'API ne répond pas");
      // La commande est affichée une seule fois, par le composant Erreur (voir pages.spec.ts).
      expect(e.message).not.toContain(COMMANDE_API);
    }
  });

  it('503 → base indisponible, en gardant le corps (utile pour /health)', () => {
    const e = versApiErreur(reponse(503, { api: 'ok', base: 'indisponible' }));
    expect(e.type).toBe('base_indisponible');
    expect(e.message).toContain('base de données est indisponible');
    expect(e.corps).toEqual({ api: 'ok', base: 'indisponible' });
  });

  it('404, 422 et 500 → messages distincts en français', () => {
    expect(versApiErreur(reponse(404)).type).toBe('introuvable');
    expect(versApiErreur(reponse(422)).type).toBe('parametres');
    const e500 = versApiErreur(reponse(500));
    expect(e500.type).toBe('serveur');
    expect(e500.message).toContain('code 500');
  });
});

describe('apiErreurInterceptor', () => {
  let http: HttpClient;
  let controle: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([apiErreurInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    controle = TestBed.inject(HttpTestingController);
  });

  afterEach(() => controle.verify());

  it("transforme l'erreur d'un appel /api en ApiErreur", () => {
    let recue: unknown;
    http.get('/api/consultations').subscribe({ error: (e: unknown) => (recue = e) });
    controle
      .expectOne('/api/consultations')
      .flush({ detail: 'Base de données indisponible' }, { status: 503, statusText: 'x' });
    expect(recue).toBeInstanceOf(ApiErreur);
    expect((recue as ApiErreur).type).toBe('base_indisponible');
  });

  it("ne touche pas aux requêtes hors de l'API", () => {
    let recue: unknown;
    http.get('/autre').subscribe({ error: (e: unknown) => (recue = e) });
    controle.expectOne('/autre').flush(null, { status: 500, statusText: 'x' });
    expect(recue).toBeInstanceOf(HttpErrorResponse);
  });
});
