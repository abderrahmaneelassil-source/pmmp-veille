/**
 * Formatage des dates et durées.
 *
 * L'heure affichée est l'heure « murale » écrite par l'API, SANS reconversion par le
 * navigateur. L'API (PostgreSQL, session en Africa/Casablanca) renvoie déjà l'heure du
 * Maroc : dans "2026-11-05T10:00:00Z", 10:00 est l'heure locale et « Z » le décalage en
 * vigueur. Reconvertir dans le navigateur dépendrait de SA base de fuseaux : mesuré le
 * 26/09/2026, Node (ICU tz 2026a) place le Maroc en UTC+1 le 5/11/2026 et afficherait
 * 11:00, alors que PostgreSQL et Python (tzdata 2026.4) le placent en UTC+0 (10:00).
 * Les calculs de durée (délai restant, ancienneté) utilisent, eux, l'instant exact.
 */

const MOIS = [
  'janv.',
  'févr.',
  'mars',
  'avr.',
  'mai',
  'juin',
  'juil.',
  'août',
  'sept.',
  'oct.',
  'nov.',
  'déc.',
];
const HEURE_MURALE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;

interface Murale {
  annee: string;
  mois: number;
  jour: number;
  heure: string | null;
}

function murale(iso: string | null | undefined): Murale | null {
  const m = iso ? HEURE_MURALE.exec(iso) : null;
  if (!m || +m[2] < 1 || +m[2] > 12) {
    return null;
  }
  return { annee: m[1], mois: +m[2], jour: +m[3], heure: m[4] ? `${m[4]}:${m[5]}` : null };
}

function lire(iso: string | null | undefined): Date | null {
  if (!iso) {
    return null;
  }
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** « 5 nov. 2026 » ; « — » si absente ; la chaîne brute si illisible. */
export function dateCourte(iso: string | null | undefined): string {
  const m = murale(iso);
  return m ? `${m.jour} ${MOIS[m.mois - 1]} ${m.annee}` : (iso ?? '—');
}

/** « 5 nov. 2026, 10:00 » : heure du Maroc, telle que renvoyée par l'API. */
export function dateHeure(iso: string | null | undefined): string {
  const m = murale(iso);
  if (!m) {
    return iso ?? '—';
  }
  const date = `${m.jour} ${MOIS[m.mois - 1]} ${m.annee}`;
  return m.heure ? `${date}, ${m.heure}` : date;
}

/** Temps restant avant une date limite : « dans 40 j », « dans 5 h », « échue ». */
export function delaiRestant(
  iso: string | null | undefined,
  maintenant: Date = new Date(),
): string {
  const d = lire(iso);
  if (!d) {
    return '';
  }
  const heures = (d.getTime() - maintenant.getTime()) / 3_600_000;
  if (heures < 0) {
    return 'échue';
  }
  if (heures < 1) {
    return "dans moins d'1 h";
  }
  if (heures < 24) {
    return `dans ${Math.floor(heures)} h`;
  }
  return `dans ${Math.floor(heures / 24)} j`;
}

/** 87 → « 1 min 27 s » ; 3720 → « 1 h 2 min ». */
export function duree(secondes: number | null | undefined): string {
  if (secondes === null || secondes === undefined) {
    return '—';
  }
  if (secondes < 60) {
    return `${secondes} s`;
  }
  if (secondes < 3600) {
    return `${Math.floor(secondes / 60)} min ${secondes % 60} s`;
  }
  return `${Math.floor(secondes / 3600)} h ${Math.floor((secondes % 3600) / 60)} min`;
}

const DATE_ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Vrai pour une date de calendrier valide au format AAAA-MM-JJ (celui des <input type="date">). */
export function estDateJour(valeur: string | null | undefined): valeur is string {
  const m = valeur ? DATE_ISO.exec(valeur) : null;
  if (!m) {
    return false;
  }
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
}

/** « 2026-12-31 » → « 2027-01-01 ». Calcul en UTC : aucun effet de fuseau ni d'heure d'été. */
export function lendemain(jour: string): string {
  const m = DATE_ISO.exec(jour);
  if (!m) {
    throw new Error(`Date invalide : ${jour}`);
  }
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3] + 1));
  return d.toISOString().slice(0, 10);
}

/** Temps écoulé depuis une date passée : « il y a 3 h », « il y a 2 j ». */
export function depuis(iso: string | null | undefined, maintenant: Date = new Date()): string {
  const d = lire(iso);
  if (!d) {
    return '';
  }
  const minutes = Math.max(0, (maintenant.getTime() - d.getTime()) / 60_000);
  if (minutes < 1) {
    return "il y a moins d'1 min";
  }
  if (minutes < 60) {
    return `il y a ${Math.floor(minutes)} min`;
  }
  if (minutes < 60 * 24) {
    return `il y a ${Math.floor(minutes / 60)} h`;
  }
  return `il y a ${Math.floor(minutes / (60 * 24))} j`;
}

/** Vrai si la date est plus ancienne que `heures` (ou absente). */
export function plusAncienQue(
  iso: string | null | undefined,
  heures: number,
  maintenant: Date = new Date(),
): boolean {
  const d = lire(iso);
  return !d || maintenant.getTime() - d.getTime() > heures * 3_600_000;
}
