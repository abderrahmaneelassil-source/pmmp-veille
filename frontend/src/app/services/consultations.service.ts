import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  API_BASE,
  Consultation,
  Modification,
  PageConsultations,
  StatutConsultation,
} from '../core/api.types';

/** Paramètres de GET /consultations, exactement ceux de l'API (api/main.py). */
export interface FiltresConsultations {
  categorie?: string;
  acheteur?: string;
  statut?: StatutConsultation;
  /** Date limite postérieure ou égale (AAAA-MM-JJ = minuit, heure du Maroc). */
  date_limite_apres?: string;
  /** Date limite strictement antérieure. */
  date_limite_avant?: string;
  limit?: number;
  offset?: number;
}

@Injectable({ providedIn: 'root' })
export class ConsultationsService {
  private readonly http = inject(HttpClient);

  lister(filtres: FiltresConsultations = {}): Observable<PageConsultations> {
    let params = new HttpParams();
    for (const [cle, valeur] of Object.entries(filtres)) {
      if (valeur !== undefined && valeur !== null && valeur !== '') {
        params = params.set(cle, String(valeur));
      }
    }
    return this.http.get<PageConsultations>(`${API_BASE}/consultations`, { params });
  }

  detail(org: string, ref: string): Observable<Consultation> {
    return this.http.get<Consultation>(chemin(org, ref));
  }

  historique(org: string, ref: string): Observable<Modification[]> {
    return this.http.get<Modification[]>(`${chemin(org, ref)}/historique`);
  }
}

function chemin(org: string, ref: string): string {
  return `${API_BASE}/consultations/${encodeURIComponent(org)}/${encodeURIComponent(ref)}`;
}
