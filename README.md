## Changer tes critères

Dans ton dépôt GitHub, ouvre `reglages.py` → crayon ✏️ → modifie les nombres → **Commit changes**. Les explications sont dans le fichier.

## Option : 3e alerte avec ntfy (sonnerie forte)

1. Installe l'appli **ntfy** (Android / iPhone, gratuite, sans compte).
2. Dans l'appli : **+** → invente un nom de sujet long et secret, par exemple `logement-amelia-x7k29q` → **S'abonner**.
3. Crée le secret GitHub `NTFY_TOPIC` avec ce nom exact.
4. Dans l'appli, tu peux régler la priorité « max » pour qu'elle sonne même en silencieux.

## Dépannage

- **Je ne reçois rien sur Telegram** : as-tu bien envoyé `/start` à ton bot ? Le `TELEGRAM_CHAT_ID` est-il le bon nombre (sans espace) ?
- **Je ne reçois pas l'email** : regarde dans les spams. Vérifie que la validation en deux étapes est active et que le code de 16 lettres est bien copié.
- **Pour voir ce que fait le bot** : onglet **Actions** → clique sur un passage → **Vérifier les logements**. Tu vois combien d'offres chaque site a renvoyées.
- **cron-job.org affiche une erreur (401 ou 403)** : le jeton GitHub a expiré ou n'a pas la permission Actions « Read and write ». Refais l'étape 6a et remplace-le.
- **Arrêter le bot** : désactive le job sur cron-job.org, puis GitHub → Actions → Veille logement → `…` → **Disable workflow**.

## Limites (à savoir)

- Le **trajet est une estimation** (distance + grandes lignes de transport). Vérifie toujours sur Citymapper ou IDF Mobilités avant de réserver.
- **CROUS** : les numéros d'outil changent chaque année (`CROUS_OUTILS` dans `reglages.py`). L'outil 47 correspond à la phase complémentaire 2026 et doit fermer début novembre. L'outil 44 (au fil de l'eau) continue toute l'année.
- **ALJT** : comme le site est en maintenance, je n'ai pas pu voir comment il affiche ses disponibilités. Le bot te prévient quand il revient. À ce moment-là, on pourra ajouter une surveillance précise (ou tu peux ajouter une page dans `PAGES_EN_PLUS`).
- **Lokaviz** (logements chez des particuliers, géré par le CROUS) n'est **pas** surveillé : le site bloque les robots. Crée plutôt une alerte email directement sur lokaviz.fr.
- Les listes de résidences Fac-Habitat et ARPEJ sont figées au 22/10/2026 (`data/`). Une nouvelle résidence ouverte après ne sera pas vue automatiquement.

## Pour réserver vite quand l'alerte arrive

- **CROUS** : compte sur messervices.etudiant.gouv.fr déjà créé, Dossier Social Étudiant (DSE) à jour.
- **Garant** : fais ta demande **Visale** maintenant (gratuit, sur visale.fr). Le visa est accepté par le CROUS, ARPEJ, Fac-Habitat, etc.
- **Justificatifs prêts en PDF sur ton téléphone** : pièce d'identité, certificat de scolarité ESILV, avis d'imposition (le tien ou celui de tes parents), RIB, attestation Visale.
- **Comptes déjà créés** sur ibail.arpej.fr (ARPEJ) et sur le module de réservation Fac-Habitat (bouton « Déposer une demande » d'une résidence), pour ne pas perdre 10 minutes à t'inscrire au moment de l'alerte.
