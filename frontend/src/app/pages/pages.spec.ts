import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { apiErreurInterceptor } from '../core/api-erreur';
import { dernierRun, page, resume, texte } from '../testing';
import { FeuilleDeRoute } from './feuille-de-route';
import { SuiviCollecte } from './suivi-collecte';
import { TableauDeBord } from './tableau-de-bord';

describe('pages Tableau de bord, Suivi de la collecte, Feuille de route', () => {
  let controle: HttpTestingController;
  let harness: RouterTestingHarness;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: '', component: TableauDeBord },
          { path: 'collecte', component: SuiviCollecte },
          { path: 'feuille-de-route', component: FeuilleDeRoute },
        ]),
        provideHttpClient(withInterceptors([apiErreurInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    controle = TestBed.inject(HttpTestingController);
    harness = await RouterTestingHarness.create();
  });

  afterEach(() => controle.verify());

  async function rendu(): Promise<HTMLElement> {
    await harness.fixture.whenStable();
    return harness.routeNativeElement as HTMLElement;
  }

  it('tableau de bord : trois appels seulement, avec les 5 prochaines échéances en cours', async () => {
    await harness.navigateByUrl('/');
    const echeances = controle.expectOne((r) => r.url === '/api/consultations');
    expect(echeances.request.params.get('statut')).toBe('en_cours');
    expect(echeances.request.params.get('limit')).toBe('5');
    echeances.flush(page([resume('1'), resume('2')], 20, 0, 5));
    controle
      .expectOne('/api/health')
      .flush({ api: 'ok', base: 'ok', base_de_donnees: 'pmmp_veille', lecture_seule: true });
    controle.expectOne('/api/collecte/dernier-run').flush(dernierRun());

    const el = await rendu();
    expect(texte(el)).toContain('2 plus proches sur 20 consultations en cours');
    expect(texte(el)).toContain('Test manuel (--force, run plafonné)');
    expect(texte(el)).toContain('1 min 27 s');
    expect(texte(el)).toContain('Base de données : connectée pmmp_veille');
    expect(texte(el.querySelector('details'))).toContain('Code de sortie');
  });

  it('tableau de bord : état « aucun run » et base indisponible (503 de /health)', async () => {
    await harness.navigateByUrl('/');
    controle.expectOne((r) => r.url === '/api/consultations').flush(page([]));
    controle
      .expectOne('/api/health')
      .flush({ api: 'ok', base: 'indisponible' }, { status: 503, statusText: 'x' });
    controle
      .expectOne('/api/collecte/dernier-run')
      .flush({ dernier_run: null, dernier_succes_le: null });

    const el = await rendu();
    expect(texte(el)).toContain("Aucun run enregistré : le collecteur n'a encore jamais tourné");
    expect(texte(el)).toContain('Base de données : indisponible');
    expect(texte(el)).toContain('Aucune consultation en cours.');
  });

  it('suivi de la collecte : run en échec, erreurs comptées et date du dernier succès', async () => {
    await harness.navigateByUrl('/collecte');
    controle.expectOne('/api/collecte/dernier-run').flush(
      dernierRun(
        {
          statut: 'echec',
          raison: 'circuit_breaker',
          erreurs: { detail_errors: 3, db_errors: 0 },
        },
        '2026-09-24T06:45:00Z',
      ),
    );
    controle
      .expectOne('/api/health')
      .flush({ api: 'ok', base: 'ok', base_de_donnees: 'pmmp_veille', lecture_seule: true });

    const el = await rendu();
    expect(texte(el)).toContain(
      "Arrêt de sécurité : trop d'erreurs ou de lenteurs consécutives du portail",
    );
    expect(texte(el)).toContain('Fiches détail en erreur : 3');
    expect(texte(el)).not.toContain('Erreurs de base de données'); // compteur à 0 : non affiché
    expect(texte(el)).toContain('Dernier run réussi');
    expect(texte(el)).toContain('Aucun run réussi depuis plus de 24 h');
    expect(el.querySelectorAll('.table--legende tbody tr').length).toBe(6);
  });

  it('suivi de la collecte : API arrêtée → message et commande de lancement, sans page cassée', async () => {
    await harness.navigateByUrl('/collecte');
    controle
      .expectOne('/api/collecte/dernier-run')
      .flush(null, { status: 502, statusText: 'Bad Gateway' });
    controle.expectOne('/api/health').flush(null, { status: 502, statusText: 'Bad Gateway' });

    const el = await rendu();
    expect(texte(el)).toContain('API injoignable');
    expect(texte(el)).toContain('python -m uvicorn api.main:app --host 127.0.0.1 --port 8000');
    expect(texte(el)).toContain('storage/logs');
    expect(el.querySelectorAll('.table--legende tbody tr').length).toBe(6); // la légende reste lisible
  });

  it('feuille de route : phases 3 et 4, sans appel API', async () => {
    await harness.navigateByUrl('/feuille-de-route');
    const el = await rendu();
    expect([...el.querySelectorAll('h2')].map(texte)).toEqual([
      'Phase 3 — Moteur de recherche',
      'Phase 4 — Analyse par IA',
    ]);
    expect(el.querySelectorAll('.etat-avancement--disponible').length).toBe(1);
    expect(el.querySelectorAll('.etat-avancement--prevu').length).toBe(9);
    expect(el.querySelector('#phase-4')).not.toBeNull();
  });
});
