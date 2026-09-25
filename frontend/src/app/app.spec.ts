import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';
import { texte } from './testing';

describe('App (mise en page)', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('rappelle en permanence le statut « usage interne, lecture seule, sans authentification »', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(texte(el.querySelector('.bandeau'))).toContain(
      'Usage interne — lecture seule, sans authentification',
    );
  });

  it('propose les 4 pages, et les fonctionnalités à venir mènent à la feuille de route', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    const liens = [...el.querySelectorAll<HTMLAnchorElement>('.menu__lien')];
    expect(liens.slice(0, 4).map(texte)).toEqual([
      'Tableau de bord',
      'Consultations',
      'Suivi de la collecte',
      'Feuille de route',
    ]);

    const aVenir = liens.filter((a) => a.classList.contains('menu__lien--a-venir'));
    expect(aVenir.map((a) => texte(a))).toEqual([
      'Alertes Bientôt',
      'Suivi commercial Bientôt',
      'Analyse IA Bientôt',
    ]);
    expect(aVenir.map((a) => a.getAttribute('href'))).toEqual([
      '/feuille-de-route#phase-3',
      '/feuille-de-route#phase-3',
      '/feuille-de-route#phase-4',
    ]);
  });
});
