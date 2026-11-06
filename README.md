# Damogran

Petite console web pour piloter des spots RGB en Art-Net (dimmer + couleur), à la place de MagicQ.
Python standard, sans dépendance.

## Démarrage (Windows, sans droits admin)

Rien à installer.

1. Récupérer le dossier sur le PC et l'extraire (clic droit > *Extraire tout* : ne pas lancer depuis l'intérieur du ZIP).
2. **Couper la sortie Art-Net de MagicQ** vers les projecteurs (ou fermer MagicQ), sinon les deux logiciels se battent.
3. Double-cliquer sur `Lancer.bat` : une fenêtre noire s'ouvre (la laisser ouverte) et le navigateur s'ouvre sur http://localhost:8080.
   Le lanceur utilise [uv](https://docs.astral.sh/uv/) : au premier lancement (avec Internet), il installe uv et
   un Python dans un dossier `uv\` à côté, sans installation système ni droits admin. Ensuite ça démarre directement.
   Pour un PC sans Internet : prendre un ZIP qui contient déjà un dossier `python\` (Python portable), le lanceur s'en sert.
   Pour piloter depuis un téléphone, voir « Télécommande téléphone » plus bas.

Sur un autre système (macOS, Linux) : `uv run damogran.py` (ou `python3 damogran.py`).

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

Pensé pour quelqu'un qui n'y connaît rien en lumière : on coche des spots, puis on choisit ce qu'ils font.

- **Spots** : une carte par spot, avec sa vraie couleur en grand, son état en mots (« blanc chaud, 80 % ») et ses petits
  faders (luminosité, rouge, vert, bleu, lime). Les faders d'une carte ne règlent que ce spot.
  Toucher le haut de la carte le **coche** (bandeau ambre et coche) ; la barre « N spots cochés » dit toujours qui est coché.
- **Pour les spots cochés** (panneau à droite, ou bouton « Régler ↓ » sur téléphone) : 8 couleurs, 3 blancs
  (**chaud / neutre / froid**), la luminosité. Repliés en dessous : « Affiner le blanc » (de 2700 à 6500 K, et la
  correction si la peau paraît trop verte ou trop rose) et les canaux un par un pour les experts.
  « Faire clignoter » repère les spots dans la salle. Un seul bouton « Tout cocher / Tout décocher ».
  Sans spot coché, le panneau est grisé et explique quoi faire.
- **Plan de scène** : les mêmes spots, placés comme dans la salle (lointain en haut, public en bas, jardin à gauche,
  cour à droite). « Disposer les spots » : touche un spot puis sa case (ou flèches) ; la grille se règle en colonnes et rangs.
- **Bande régie** (en haut, toujours visible sur ordinateur) : tout ce qui sert pendant le spectacle. « En scène » dit ce
  qui est allumé ; **GO** lance l'ambiance suivante (barre d'espace) ; « + Enregistrer l'ambiance » garde la lumière telle
  quelle ; **Lumière générale**, **Blackout**, la durée de transition et les effets sont juste à côté.
  Sur téléphone, cette régie a sa propre page **Ambiances** (celle qui s'ouvre en premier) : GO en grand, la liste
  des ambiances, lumière générale et blackout ; l'onglet **Spots** ne montre que les spots.
  Transition et effet sont deux menus déroulants. Sur téléphone, les cartes n'ont que le fader de luminosité (les canaux un par un restent dans le panneau des spots cochés).
- Raccourcis : Espace = GO, 1 à 9 = ambiance, B = blackout, Échap = tout décocher (désactivables dans Réglages > Clavier).

### Les blancs et le lime

Les blancs sont calculés à partir de la couleur de chaque LED (rouge, vert, bleu, lime) dans l'espace colorimétrique
CIE : pour une température donnée, Damogran cherche le mélange qui tombe sur ce blanc avec le plus de lumière possible,
en utilisant le lime. Les caractéristiques des LED sont des valeurs typiques, pas des mesures des ColorSource :
si un blanc tire vers le rose ou le vert, la correction « plus vert / plus rose » sert à l'ajuster à l'œil.
Les aperçus à l'écran utilisent le même modèle, à partir des valeurs réellement envoyées aux LED.

## Ambiances (mémoires)

- Régler les spots, puis **+ Enregistrer l'ambiance actuelle** et donner un nom.
- Toucher une ambiance (ou touches **1** à **9**) pour la rappeler, avec la **transition** choisie (aucune, 2, 5 ou 10 s).
  **GO** enchaîne sur la suivante.
- **⋯** sur une ambiance : renommer, remplacer par la lumière actuelle, supprimer.
- Toucher un réglage après un rappel marque l'ambiance « modifiée à la main » (et interrompt une transition en cours).
- Lumière générale et Blackout restent indépendants des ambiances. Les ambiances sont gardées dans `state.json`.

## Effets

Trois effets, un à la fois, avec un réglage de vitesse : **Chase** (un spot après l'autre, avec sa couleur),
**C'est la fête** (arc-en-ciel qui tourne) et **Applaudissements** (blanc chaud qui scintille, pour les saluts).
Un effet remplace le plateau tant qu'il tourne ; **Stop** ou le rappel d'une mémoire y met fin.
Master et Blackout restent actifs. Sur la console, un fader peut lancer un effet (au-delà de la moitié) ou régler la vitesse.

## Télécommande téléphone (même en 4G/5G)

Le téléphone pilote Damogran en direct (pair à pair, WebRTC), sans être sur le réseau de la salle.

**Une seule fois : mettre en ligne la page télécommande.** C'est le petit fichier `remote/index.html`, une page statique
(elle ne contient pas l'interface : le téléphone la reçoit du PC, toujours à jour).
- Cloudflare (gratuit) : tableau de bord > *Workers & Pages* > *Create* > *Pages* > *Upload assets*, un nom de projet
  (par ex. `damogran-salle`), glisser le dossier `remote`, *Deploy*. L'adresse est du type `https://damogran-salle.pages.dev/`.
- Ou n'importe quel hébergement statique (Netlify Drop : glisser le dossier `remote` sur https://app.netlify.com/drop).

**Au spectacle :** dans Damogran sur le PC, *Réglages > Téléphone* : coller l'adresse de la page, *Activer*, scanner le
QR code. Le téléphone ouvre directement la page **Ambiances**. Le code reste le même d'une fois sur l'autre
(le téléphone le garde : pas besoin de rescanner) ; *Nouveau code* déconnecte les téléphones et invalide l'ancien.

À savoir :
- le PC doit avoir Internet (en plus du réseau des projecteurs), et l'onglet Damogran doit rester ouvert dessus
  (en arrière-plan, ça va) : c'est lui qui relaie les commandes au programme ;
- la mise en relation passe par le relais public gratuit de PeerJS ; ensuite les commandes vont directement du
  téléphone au PC, chiffrées. Si un réseau bloque le direct, elles passent par un relais TURN de PeerJS (toujours chiffrées) ;
- le QR code donne la main sur la lumière : ne le montrer qu'aux gens de confiance.

## Console MagicQ / Mini Connect

Les faders de la Mini Connect ne sont lisibles que par MagicQ. MagicQ sert donc de pont : il envoie la position
des faders en Art-Net sur un univers libre, et Damogran l'écoute (**Réglages > Console**).

1. MagicQ, `Setup > DMX I/O` : univers 1 (les projecteurs) sur *None* ; univers 2 en Art-Net, univers Art-Net 1, broadcast.
2. `Patch` : 10 *Generic Dimmer* sur l'univers 2, adresses 1 à 10.
3. Pour chaque fader *n* : sélectionner le dimmer *n*, 100 %, `Record`, bouton **S** du fader *n*. `Clear`.
4. Dans Damogran, Réglages > Console & MIDI : bouger un fader l'allume sur le dessin (ou « Apprendre un fader »), puis choisir ce qu'il commande
   (intensité d'un spot ou de tous, blanc chaud/froid, teinte, master, blackout, GO d'une mémoire,
   ou **transition vers une mémoire** : le fader passe à la main de l'état actuel, en bas, à la mémoire, en haut).

**Contrôleur MIDI USB** : branché sur le PC, il est lu directement par le navigateur (Chrome ou Edge, page ouverte),
et ses faders et boutons s'affectent de la même façon dans Réglages > Console & MIDI.

Un fader n'agit que quand on le bouge : à la connexion, Damogran prend la position des faders sans rien changer.
MagicQ et Damogran tournent alors sur le même PC : c'est à tester avant un spectacle.

## Structure du code

```
damogran.py          point d'entrée (lance le serveur)
app/config.py        config.json / state.json, valeurs par défaut
app/colors.py        couleurs des LED, blancs calculés avec le lime
app/effects.py       Chase, C'est la fête, Applaudissements
app/artnet.py        paquets Art-Net et RDM
app/discovery.py     découverte des nodes (ArtPoll) et des projecteurs (RDM)
app/engine.py        état du plateau, sortie Art-Net, console / MIDI, ambiances et fondus
app/web.py           serveur web et API JSON
web/index.html       la page (le serveur y recopie style.css et js/*.js : une seule page servie)
web/js/              un fichier par partie de l'écran (régie, spots, plan, réglages, console, télécommande…)
remote/index.html    page télécommande à héberger (Cloudflare Pages ou équivalent)
```
