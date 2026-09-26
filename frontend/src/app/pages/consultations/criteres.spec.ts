import { convertToParamMap } from '@angular/router';
import {
  CRITERES_VIDES,
  lireCriteres,
  nbFiltresAvances,
  normaliser,
  versFiltresApi,
  versParametresUrl,
} from './criteres';

describe('critères de recherche', () => {
  it("lit l'URL et ignore les valeurs invalides (lien modifié à la main)", () => {
    const c = lireCriteres(
      convertToParamMap({
        q: '  tiznit ',
        champ: 'autre',
        statut: 'bidon',
        du: '2026-02-30',
        taille: '7',
        page: '-2',
      }),
    );
    expect(c).toEqual({ ...CRITERES_VIDES, texte: 'tiznit' });
  });

  it("traduit exactement vers les paramètres de l'API", () => {
    const c = {
      ...CRITERES_VIDES,
      champ: 'categorie' as const,
      texte: 'travaux',
      statut: 'en_cours' as const,
      taille: 50,
      page: 3,
    };
    expect(versFiltresApi(c)).toEqual({
      categorie: 'travaux',
      statut: 'en_cours',
      limit: 50,
      offset: 100,
    });
    expect(versFiltresApi(CRITERES_VIDES)).toEqual({ limit: 20, offset: 0 });
  });

  it("rend la date de fin inclusive : l'API exclut sa borne, on envoie le lendemain", () => {
    const filtres = versFiltresApi({ ...CRITERES_VIDES, du: '2026-11-01', au: '2026-11-05' });
    expect(filtres.date_limite_apres).toBe('2026-11-01');
    expect(filtres.date_limite_avant).toBe('2026-11-06');
  });

  it("garde des URL courtes et fait l'aller-retour URL ↔ critères sans perte", () => {
    expect(versParametresUrl(CRITERES_VIDES)).toEqual({
      q: null,
      champ: null,
      statut: null,
      du: null,
      au: null,
      taille: null,
      page: null,
    });
    const c = {
      ...CRITERES_VIDES,
      champ: 'categorie' as const,
      texte: 'services',
      du: '2026-10-01',
      taille: 100,
      page: 2,
    };
    const url = Object.fromEntries(
      Object.entries(versParametresUrl(c)).filter(([, v]) => v !== null),
    );
    expect(lireCriteres(convertToParamMap(url))).toEqual(c);
  });

  it("garde le champ « catégorie » dans l'URL même sans texte saisi", () => {
    expect(versParametresUrl({ ...CRITERES_VIDES, champ: 'categorie' })['champ']).toBe('categorie');
  });

  it('compte les filtres avancés actifs', () => {
    expect(nbFiltresAvances(CRITERES_VIDES)).toBe(0);
    expect(
      nbFiltresAvances({ ...CRITERES_VIDES, statut: 'cloture', au: '2026-12-01', taille: 50 }),
    ).toBe(3);
  });

  it('normalise pour le filtre local : casse et accents ignorés', () => {
    expect(normaliser('Électricité')).toBe('electricite');
    expect(normaliser('MÉDICAMENTS').includes(normaliser('medicament'))).toBe(true);
  });
});
