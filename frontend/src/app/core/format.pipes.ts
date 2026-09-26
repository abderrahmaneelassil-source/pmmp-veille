import { Pipe, PipeTransform } from '@angular/core';
import { dateCourte, dateHeure, delaiRestant, depuis, duree } from './format';

@Pipe({ name: 'dateCourte' })
export class DateCourtePipe implements PipeTransform {
  transform(iso: string | null | undefined): string {
    return dateCourte(iso);
  }
}

@Pipe({ name: 'dateHeure' })
export class DateHeurePipe implements PipeTransform {
  transform(iso: string | null | undefined): string {
    return dateHeure(iso);
  }
}

@Pipe({ name: 'delaiRestant' })
export class DelaiRestantPipe implements PipeTransform {
  transform(iso: string | null | undefined): string {
    return delaiRestant(iso);
  }
}

@Pipe({ name: 'duree' })
export class DureePipe implements PipeTransform {
  transform(secondes: number | null | undefined): string {
    return duree(secondes);
  }
}

@Pipe({ name: 'depuis' })
export class DepuisPipe implements PipeTransform {
  transform(iso: string | null | undefined): string {
    return depuis(iso);
  }
}
