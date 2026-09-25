import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ApiErreur, apiErreurInterceptor } from '../core/api-erreur';
import { Sante } from '../core/api.types';
import { CollecteService } from './collecte.service';
import { ConsultationsService } from './consultations.service';

describe('services API', () => {
  let controle: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([apiErreurInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    controle = TestBed.inject(HttpTestingController);
  });

  afterEach(() => controle.verify());

  it("ConsultationsService.lister n'envoie que les paramètres renseignés", () => {
    TestBed.inject(ConsultationsService)
      .lister({ acheteur: 'tiznit', categorie: '', statut: undefined, limit: 20, offset: 0 })
      .subscribe();
    const req = controle.expectOne((r) => r.url === '/api/consultations');
    expect(req.request.params.keys().sort()).toEqual(['acheteur', 'limit', 'offset']);
    expect(req.request.params.get('acheteur')).toBe('tiznit');
    req.flush({ total: 0, limit: 20, offset: 0, resultats: [] });
  });

  it('ConsultationsService encode la clé de la consultation dans le chemin', () => {
    const service = TestBed.inject(ConsultationsService);
    service.detail('o8p', '10/37').subscribe();
    service.historique('o8p', '1037543').subscribe();
    controle.expectOne('/api/consultations/o8p/10%2F37').flush({});
    controle.expectOne('/api/consultations/o8p/1037543/historique').flush([]);
  });

  it("CollecteService.sante renvoie l'état « base indisponible » du 503 comme une réponse", () => {
    let sante: Sante | undefined;
    TestBed.inject(CollecteService)
      .sante()
      .subscribe((s) => (sante = s));
    controle
      .expectOne('/api/health')
      .flush({ api: 'ok', base: 'indisponible' }, { status: 503, statusText: 'x' });
    expect(sante).toEqual({ api: 'ok', base: 'indisponible' });
  });

  it("CollecteService.sante laisse passer l'erreur si l'API est injoignable", () => {
    let erreur: unknown;
    TestBed.inject(CollecteService)
      .sante()
      .subscribe({ error: (e: unknown) => (erreur = e) });
    controle.expectOne('/api/health').flush(null, { status: 502, statusText: 'Bad Gateway' });
    expect((erreur as ApiErreur).type).toBe('api_injoignable');
  });
});
