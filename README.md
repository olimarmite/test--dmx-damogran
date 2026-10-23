# Damogran

Petite console web pour piloter des spots RGB en Art-Net (dimmer + couleur), à la place de MagicQ.
Un seul fichier Python, sans dépendance.

## Démarrage (Windows, sans droits admin)

Rien à installer : la version par défaut utilise PowerShell, présent sur tous les Windows.

1. Récupérer le dossier sur le PC (sur GitHub : **Code > Download ZIP**, puis clic droit > *Extraire tout*).
   Il faut extraire le ZIP : les fichiers ne marchent pas s'ils sont lancés depuis l'intérieur du ZIP.
2. **Couper la sortie Art-Net de MagicQ** (ou fermer MagicQ) — sinon les deux logiciels envoient en même temps et ça clignote.
   Dans MagicQ : `Setup > View DMX I/O`, mettre la sortie des univers sur *None*/désactivée.
3. Double-cliquer sur `Lancer.bat` → une fenêtre noire s'ouvre (la laisser ouverte) et le navigateur s'ouvre sur http://localhost:8080.
   `Lancer (telephone).bat` rend l'interface accessible depuis un téléphone sur le même réseau (il peut demander une autorisation du pare-feu : si elle est refusée, rester sur le PC).

Si `Lancer.bat` est bloqué : ouvrir PowerShell dans le dossier et taper
`powershell -ExecutionPolicy Bypass -File .\damogran.ps1`.

**Plan B : Python portable.** Si PowerShell est bloqué, utiliser `Lancer (Python).bat` (ou `Lancer telephone (Python).bat`).
Ces lanceurs utilisent le Python portable officiel fourni dans le dossier `python\` (Python 3.12.7 embeddable de python.org, signature vérifiée) : rien à installer.
Même interface, mêmes réglages.

## Découverte automatique

Dans **Réglages > Découverte automatique** (MagicQ fermé) :

- **Nodes Art-Net** (ArtPoll) : IP, nom et univers de sortie de chaque node. Un clic remplit l'IP de destination
  (l'IP du node, ou le broadcast s'il y a plusieurs nodes).
- **Projecteurs** (RDM via Art-Net) : adresse DMX, modèle, mode et ordre des canaux, puis **Ajouter** / **Tout ajouter**.
  Ne marche que si le node *et* les projecteurs gèrent le RDM. Un ordre de canaux marqué « à vérifier » a été deviné
  d'après le nombre de canaux, parce que le projecteur ne le décrit pas lui-même : contrôle-le avec **Identifier**.
- Si rien ne répond en RDM : saisie manuelle à partir du Patch de MagicQ (ci-dessous).

## Avant de couper MagicQ, relever dans MagicQ

- **Patch** : pour chaque spot, univers, adresse DMX et mode/ordre des canaux.
- **Setup > View DMX I/O** : quel univers Art-Net correspond à chaque univers MagicQ, et l'IP/broadcast de sortie.
- La carte réseau du PC (`ipconfig`) : souvent 2.x.x.x ou 10.x.x.x en Art-Net.

Puis dans Damogran → **Réglages** : IP de destination, carte réseau, et la liste des projecteurs.
Le bouton **Identifier** fait clignoter un spot ; le **testeur de canal** permet de chercher un spot à l'aveugle.

## Utilisation

- **Plateau** : chaque spot est dessiné comme une flaque de lumière, à sa couleur et son intensité réelles.
  Clic pour sélectionner (re-clic pour ajouter ou retirer). Rien de sélectionné : le réglage agit sur tous.
- **Réglage** : fader d'intensité, champ de couleur (teinte de gauche à droite, saturation de bas en haut),
  bande de blanc de 2700 K à 6500 K. Sur les projecteurs avec lime (ETC ColorSource), le blanc passe surtout
  par le lime, pour des peaux moins rosées. « Réglage fin des canaux » donne les faders R, G, B, Lime directs.
- **Master**, **Blackout** (touche `B`), **Échap** pour tout désélectionner. L'état est gardé au redémarrage.

## Console MagicQ / Mini Connect

Les faders de la Mini Connect ne sont lisibles que par MagicQ. MagicQ sert donc de pont : il envoie la position
des faders en Art-Net sur un univers libre, et Damogran l'écoute (**Réglages > Console**).

1. MagicQ, `Setup > DMX I/O` : univers 1 (les projecteurs) sur *None* ; univers 2 en Art-Net, univers Art-Net 1, broadcast.
2. `Patch` : 10 *Generic Dimmer* sur l'univers 2, adresses 1 à 10.
3. Pour chaque fader *n* : sélectionner le dimmer *n*, 100 %, `Record`, bouton **S** du fader *n*. `Clear`.
4. Dans Damogran, onglet Console : bouger un fader allume sa colonne, choisir ce qu'il commande
   (intensité d'un spot ou de tous, blanc chaud/froid, teinte, master, blackout, GO d'une mémoire).

Un fader n'agit que quand on le bouge : à la connexion, Damogran prend la position des faders sans rien changer.
MagicQ et Damogran tournent alors sur le même PC : c'est à tester avant un spectacle.

## Mémoires (scènes)

- Régler les projecteurs, puis **+ Mémoriser l'état actuel** et donner un nom.
- Clic sur une mémoire (ou touches **1** à **9**) pour la rappeler, avec le **fondu** choisi (0 s = cut, jusqu'à 10 s).
- **⋯** sur une mémoire : renommer, écraser avec l'état actuel, supprimer.
- La mémoire rappelée est encadrée ; toucher un réglage la désélectionne (et interrompt un fondu en cours).
- Master et Blackout restent indépendants des mémoires. Les mémoires sont gardées dans `state.json`.
