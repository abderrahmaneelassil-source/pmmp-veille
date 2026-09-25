import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { apiErreurInterceptor } from '../../core/api-erreur';
import { MODIFICATIONS, consultation, texte } from '../../testing';
import { ConsultationDetail, lienSur } from './consultation-detail';

const URL_API = '/api/consultations/o8p/1037543';

describe('ConsultationDetail', () => {
  let controle: HttpTestingController;
  let harness: RouterTestingHarness;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([{ path: 'consultations/:org/:ref', component: ConsultationDetail }]),
        provideHttpClient(withInterceptors([apiErreurInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    controle = TestBed.inject(HttpTestingController);
    harness = await RouterTestingHarness.create();
  });

  afterEach(() => controle.verify());

  async function ouvrir(detail: object | null, historique: object | null): Promise<HTMLElement> {
    await harness.navigateByUrl('/consultations/o8p/1037543');
    const erreur404 = { status: 404, statusText: 'Not Found' };
    const d = controle.expectOne(URL_API);
    const h = controle.expectOne(`${URL_API}/historique`);
    detail
      ? d.flush(detail)
      : d.flush({ detail: 'Consultation introuvable : o8p/1037543' }, erreur404);
    historique
      ? h.flush(historique)
      : h.flush({ detail: 'Consultation introuvable : o8p/1037543' }, erreur404);
    await harness.fixture.whenStable();
    return harness.routeNativeElement as HTMLElement;
  }

  it('affiche tous les champs, les liens externes et le DCE', async () => {
    const el = await ouvrir(consultation(), []);
    expect(texte(el.querySelector('h1'))).toBe(
      'TRAVAUX DE PROTECTION DU LITTORAL DE SALE -PHASE 1',
    );
    expect(texte(el)).toContain("Page intermédiaire (conditions d'utilisation) : non téléchargé");
    expect(texte(el)).toContain('Réponse électronique exigée Oui');
    expect(texte(el)).toContain('Réservé aux PME Non précisé');

    const portail = [...el.querySelectorAll('a')].find((a) =>
      texte(a).startsWith('Ouvrir sur le portail'),
    );
    expect(portail?.getAttribute('href')).toContain('refConsultation=1037543');
    expect(portail?.getAttribute('target')).toBe('_blank');
    expect(portail?.getAttribute('rel')).toBe('noopener noreferrer');
    const dce = [...el.querySelectorAll('a')].find((a) => texte(a).startsWith('Lien DCE'));
    expect(dce?.getAttribute('target')).toBe('_blank');
  });

  it('présente un historique vide comme une information, pas une erreur', async () => {
    const el = await ouvrir(consultation(), []);
    expect(texte(el)).toContain('Aucune modification détectée depuis la première collecte');
    expect(el.querySelector('[role="alert"]')).toBeNull();
  });

  it("affiche l'historique en frise, de la plus ancienne à la plus récente", async () => {
    const el = await ouvrir(consultation(), MODIFICATIONS);
    const etapes = [...el.querySelectorAll('.frise__etape')].map(texte);
    expect(etapes.length).toBe(2);
    expect(etapes[0]).toContain('Report de date');
    expect(etapes[0]).toContain('Date limite de dépôt');
    expect(etapes[0]).toContain('run n° 1');
    expect(etapes[1]).toContain('Rectificatif');
    expect(etapes[1]).toContain('Travaux — تهيئة');
  });

  it('affiche une page « introuvable » conviviale sur un 404', async () => {
    const el = await ouvrir(null, null);
    expect(texte(el.querySelector('h1'))).toBe('Consultation introuvable');
    expect(texte(el)).toContain('o8p/1037543');
    const retour = [...el.querySelectorAll('a')].find(
      (a) => texte(a) === 'Retour à la liste des consultations',
    );
    expect(retour?.getAttribute('href')).toBe('/consultations');
  });

  it("n'affiche comme liens que les adresses http(s)", async () => {
    expect(lienSur('https://www.marchespublics.gov.ma/x')).toBe(
      'https://www.marchespublics.gov.ma/x',
    );
    expect(lienSur('javascript:alert(1)')).toBeNull();
    expect(lienSur(null)).toBeNull();
    const el = await ouvrir(
      consultation({ url_detail: 'javascript:alert(1)', dce_urls: ['javascript:alert(2)'] }),
      [],
    );
    expect(
      [...el.querySelectorAll('a')].some((a) =>
        (a.getAttribute('href') ?? '').includes('javascript'),
      ),
    ).toBe(false);
    expect(texte(el)).toContain('Lien non valide');
  });
});
