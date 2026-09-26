import { resumerRaison } from './libelles';

// Raison réelle du run n°3 (26/09/2026), telle qu'enregistrée par le circuit breaker.
const RAISON_26_09 =
  '3 problèmes consécutifs : DownloadFailedError sur https://www.marchespublics.gov.ma/?page=entreprise.' +
  'EntrepriseDetailsConsultation&refConsultation=1040903&orgAcronyme=d4q&code=&retraits : [<twisted.python.' +
  'failure.Failure twisted.internet.error.ConnectionLost: Connection to the other side was lost in a ' +
  'non-clean fashion: Connection lost.>] | DownloadFailedError sur https://www.marchespublics.gov.ma/?page=' +
  'entreprise.EntrepriseDetailsConsultation&refConsultation=1040813&orgAcronyme=z7x&code=&retraits : ' +
  '[<twisted.python.failure.Failure twisted.internet.error.ConnectionLost: Connection lost.>]';

describe('resumerRaison', () => {
  it("résume l'arrêt du circuit breaker et garde le détail technique à part", () => {
    const r = resumerRaison(RAISON_26_09);
    expect(r.resume).toBe(
      'Arrêt de sécurité : 3 problèmes consécutifs sur le portail (connexion coupée par le site)',
    );
    expect(r.detail).toBe(RAISON_26_09);
  });

  it('reconnaît les autres causes du circuit breaker', () => {
    expect(
      resumerRaison('3 problèmes consécutifs : HTTP 503 sur https://x | HTTP 502 sur https://y')
        .resume,
    ).toContain('erreurs du serveur (HTTP 5xx)');
    expect(
      resumerRaison('3 problèmes consécutifs : réponse lente (21.0s > 15s) sur https://x').resume,
    ).toContain('réponses trop lentes');
    expect(
      resumerRaison('HTTP 429 sur https://x : le site refuse ou limite nos requêtes').resume,
    ).toBe('Arrêt immédiat : le site refuse ou limite nos requêtes (HTTP 429)');
  });

  it('traduit les codes connus sans détail, et raccourcit les textes longs inconnus', () => {
    expect(resumerRaison('finished')).toEqual({ resume: 'Terminé normalement', detail: null });
    expect(resumerRaison(null)).toEqual({ resume: '—', detail: null });
    expect(resumerRaison('interrompu : resté en_cours plus de 6 h').resume).toContain(
      'Run interrompu',
    );
    const long = 'x'.repeat(300);
    expect(resumerRaison(long)).toEqual({ resume: `${'x'.repeat(120)}…`, detail: long });
    expect(resumerRaison('raison courte inconnue')).toEqual({
      resume: 'raison courte inconnue',
      detail: null,
    });
  });
});
