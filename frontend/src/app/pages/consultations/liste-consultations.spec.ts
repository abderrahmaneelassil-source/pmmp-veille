import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { apiErreurInterceptor } from '../../core/api-erreur';
import { page, resume, texte } from '../../testing';
import {
  AIDE_RECHERCHE_AVANCEE,
  DELAI_RECHERCHE_MS,
  ListeConsultations,
} from './liste-consultations';

describe('ListeConsultations', () => {
  let controle: HttpTestingController;
  let harness: RouterTestingHarness;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([{ path: 'consultations', component: ListeConsultations }]),
        provideHttpClient(withInterceptors([apiErreurInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    controle = TestBed.inject(HttpTestingController);
    harness = await RouterTestingHarness.create();
  });

  afterEach(() => {
    vi.useRealTimers();
    controle.verify();
  });

  function requeteListe(): TestRequest {
    return controle.expectOne((r) => r.url === '/api/consultations');
  }

  async function afficher(): Promise<HTMLElement> {
    await harness.fixture.whenStable();
    return harness.routeNativeElement as HTMLElement;
  }

  it("envoie à l'API les critères lus dans l'URL, date de fin incluse", async () => {
    await harness.navigateByUrl(
      '/consultations?q=travaux&champ=categorie&statut=en_cours&du=2026-11-01&au=2026-11-05&page=2',
    );
    const req = requeteListe();
    const p = req.request.params;
    expect(p.get('categorie')).toBe('travaux');
    expect(p.has('acheteur')).toBe(false);
    expect(p.get('statut')).toBe('en_cours');
    expect(p.get('date_limite_apres')).toBe('2026-11-01');
    expect(p.get('date_limite_avant')).toBe('2026-11-06');
    expect(p.get('offset')).toBe('20');
    req.flush(page([resume('1')], 21, 20));

    const el = await afficher();
    expect(texte(el.querySelector('.resume-resultats'))).toBe('Résultats 21–21 sur 21');
    expect(texte(el.querySelector('.pagination'))).toContain('Page 2 sur 2');
    // Les filtres avancés actifs ouvrent le panneau et restent sélectionnés.
    expect((el.querySelector('#filtres-avances select') as HTMLSelectElement).value).toBe(
      'en_cours',
    );
  });

  it("n'interroge l'API qu'après 300 ms sans frappe, une seule fois", async () => {
    await harness.navigateByUrl('/consultations');
    requeteListe().flush(page([resume('1')]));
    const el = await afficher();

    vi.useFakeTimers();
    const champ = el.querySelector('input[type="search"]') as HTMLInputElement;
    for (const t of ['t', 'ti', 'tiz', 'tiznit']) {
      champ.value = t;
      champ.dispatchEvent(new Event('input'));
      vi.advanceTimersByTime(100);
    }
    controle.expectNone((r) => r.url === '/api/consultations');

    vi.advanceTimersByTime(DELAI_RECHERCHE_MS);
    vi.useRealTimers();
    await harness.fixture.whenStable();
    expect(TestBed.inject(Router).url).toBe('/consultations?q=tiznit');
    const req = requeteListe();
    expect(req.request.params.get('acheteur')).toBe('tiznit');
    expect(req.request.params.get('offset')).toBe('0');
    req.flush(page([]));
  });

  it('affiche un état vide explicite, avec réinitialisation', async () => {
    await harness.navigateByUrl('/consultations?q=introuvable');
    requeteListe().flush(page([]));
    const el = await afficher();
    expect(texte(el)).toContain('Aucune consultation ne correspond à ces critères.');
    expect(texte(el.querySelector('.vide button'))).toBe('Réinitialiser la recherche');
  });

  it("affiche l'erreur de base indisponible au lieu d'une page cassée", async () => {
    await harness.navigateByUrl('/consultations');
    requeteListe().flush(
      { detail: 'Base de données indisponible' },
      { status: 503, statusText: 'x' },
    );
    const el = await afficher();
    expect(texte(el.querySelector('[role="alert"]'))).toContain(
      'la base de données est indisponible',
    );
    expect(el.querySelector('table')).toBeNull();
  });

  it('propose la recherche avancée désactivée, avec son explication', async () => {
    await harness.navigateByUrl('/consultations');
    requeteListe().flush(page([resume('1')]));
    const el = await afficher();
    const bouton = [...el.querySelectorAll('button')].find((b) => texte(b) === 'Recherche avancée');
    expect(bouton?.disabled).toBe(true);
    expect(bouton?.parentElement?.getAttribute('data-infobulle')).toBe(AIDE_RECHERCHE_AVANCEE);
  });

  it("limite explicitement le filtre sur l'objet à la page affichée", async () => {
    await harness.navigateByUrl('/consultations');
    requeteListe().flush(
      page(
        [
          resume('1', { objet: 'Achat de médicaments' }),
          resume('2', { objet: 'Travaux de voirie' }),
        ],
        40,
      ),
    );
    const el = await afficher();
    expect(texte(el.querySelector('.filtre-local'))).toContain(
      'uniquement parmi les résultats affichés sur cette page',
    );

    const filtre = el.querySelector('.filtre-local input') as HTMLInputElement;
    filtre.value = 'medicament';
    filtre.dispatchEvent(new Event('input'));
    await harness.fixture.whenStable();
    expect(el.querySelectorAll('tbody tr').length).toBe(1);
    expect(texte(el)).toContain('Les autres pages ne sont pas filtrées.');
    controle.expectNone((r) => r.url === '/api/consultations'); // aucun appel API
  });
});
