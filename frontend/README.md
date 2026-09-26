# Interface web PMMP (Angular)

Interface de consultation des appels d'offres collectés : tableau de bord, recherche,
fiches détail avec historique, suivi de la collecte et feuille de route. Lecture seule :
elle ne fait qu'interroger l'API FastAPI du dossier `api/`.

Installation, lancement, tests et fonctionnement : voir **§13 du README principal**
(`../README.md`).

```powershell
npm install        # une fois
npm start          # ng serve : http://localhost:4200 (l'API doit tourner sur le port 8000)
npm test           # tests unitaires (Vitest, sans navigateur)
```
