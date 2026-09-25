import {
  dateCourte,
  dateHeure,
  delaiRestant,
  depuis,
  duree,
  estDateJour,
  lendemain,
  plusAncienQue,
} from './format';

describe('format', () => {
  it("affiche l'heure du Maroc telle que l'API l'écrit, sans reconversion par le navigateur", () => {
    // Valeurs réelles de pmmp_veille : décalage UTC+0 (« Z ») depuis fin septembre 2026,
    // UTC+1 avant. Dans les deux cas, les chiffres sont l'heure locale du Maroc.
    expect(dateHeure('2026-11-05T10:00:00Z')).toBe('5 nov. 2026, 10:00');
    expect(dateHeure('2026-08-24T00:00:00+01:00')).toBe('24 août 2026, 00:00');
    expect(dateHeure('2026-09-25T16:30:46.235373Z')).toBe('25 sept. 2026, 16:30');
    expect(dateCourte('2026-11-05T10:00:00Z')).toBe('5 nov. 2026');
    // Valeurs d'historique écrites par le collecteur (history.py : isoformat()).
    expect(dateHeure('2026-10-20T10:00:00+01:00')).toBe('20 oct. 2026, 10:00');
  });

  it('gère les dates absentes ou illisibles sans planter', () => {
    expect(dateCourte(null)).toBe('—');
    expect(dateHeure(undefined)).toBe('—');
    expect(dateHeure('pas une date')).toBe('pas une date');
    expect(delaiRestant(null)).toBe('');
  });

  it('calcule le délai restant avant la date limite', () => {
    const maintenant = new Date('2026-09-26T10:00:00Z');
    expect(delaiRestant('2026-11-05T10:00:00Z', maintenant)).toBe('dans 40 j');
    expect(delaiRestant('2026-09-26T15:30:00Z', maintenant)).toBe('dans 5 h');
    expect(delaiRestant('2026-09-26T10:20:00Z', maintenant)).toBe("dans moins d'1 h");
    expect(delaiRestant('2026-09-25T10:00:00Z', maintenant)).toBe('échue');
  });

  it("calcule le temps écoulé et détecte l'absence de run réussi depuis 24 h", () => {
    const maintenant = new Date('2026-09-26T10:00:00Z');
    expect(depuis('2026-09-26T07:00:00Z', maintenant)).toBe('il y a 3 h');
    expect(depuis('2026-09-24T10:00:00Z', maintenant)).toBe('il y a 2 j');
    expect(plusAncienQue('2026-09-25T09:00:00Z', 24, maintenant)).toBe(true);
    expect(plusAncienQue('2026-09-25T11:00:00Z', 24, maintenant)).toBe(false);
    expect(plusAncienQue(null, 24, maintenant)).toBe(true);
  });

  it('formate les durées de run', () => {
    expect(duree(null)).toBe('—');
    expect(duree(42)).toBe('42 s');
    expect(duree(87)).toBe('1 min 27 s');
    expect(duree(3720)).toBe('1 h 2 min');
  });

  it('valide les dates AAAA-MM-JJ et calcule le lendemain sans effet de fuseau', () => {
    expect(estDateJour('2026-10-01')).toBe(true);
    expect(estDateJour('2026-02-30')).toBe(false);
    expect(estDateJour('01/10/2026')).toBe(false);
    expect(estDateJour(null)).toBe(false);
    expect(lendemain('2026-10-01')).toBe('2026-10-02');
    expect(lendemain('2026-12-31')).toBe('2027-01-01');
    expect(lendemain('2028-02-28')).toBe('2028-02-29');
  });
});
