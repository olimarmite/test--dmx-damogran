# Damogran

Petite console web pour piloter des spots RGB en Art-Net (dimmer + couleur), à la place de MagicQ.
Un seul fichier Python, sans dépendance.

## Démarrage (Windows)

1. Installer Python 3 si besoin : https://www.python.org/downloads/ (cocher **Add python.exe to PATH**).
2. **Couper la sortie Art-Net de MagicQ** (ou fermer MagicQ) — sinon les deux logiciels envoient en même temps et ça clignote.
   Dans MagicQ : `Setup > View DMX I/O`, mettre la sortie des univers sur *None*/désactivée.
3. Double-cliquer sur `Lancer.bat` → le navigateur s'ouvre sur http://localhost:8080.
   `Lancer (telephone).bat` rend l'interface accessible depuis un téléphone sur le même réseau (accepter le pare-feu Windows).

## Avant de couper MagicQ, relever dans MagicQ

- **Patch** : pour chaque spot, univers, adresse DMX et mode/ordre des canaux.
- **Setup > View DMX I/O** : quel univers Art-Net correspond à chaque univers MagicQ, et l'IP/broadcast de sortie.
- La carte réseau du PC (`ipconfig`) : souvent 2.x.x.x ou 10.x.x.x en Art-Net.

Puis dans Damogran → **Réglages** : IP de destination, carte réseau, et la liste des projecteurs.
Le bouton **Identifier** fait clignoter un spot ; le **testeur de canal** permet de chercher un spot à l'aveugle.

## Utilisation

- Cliquer sur le nom d'un spot pour le sélectionner ; avec une sélection, tout réglage s'applique à tous les sélectionnés.
- Sans sélection, les pastilles de couleur et les boutons Dim agissent sur tous les spots.
- **Master**, **Blackout** (touche `B`). L'état est mémorisé et restauré au redémarrage.
