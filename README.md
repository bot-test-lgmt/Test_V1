# 🏠 Bot logement étudiant (ESILV, La Défense)

Ce bot vérifie **toutes les 5 minutes, 24h/24, même ordi éteint** :

| Site | Ce qui est surveillé |
|---|---|
| **CROUS** (trouverunlogement.lescrous.fr) | tous les logements mis en ligne (phase complémentaire + attribution au fil de l'eau) |
| **Fac-Habitat + Logifac** | le module de réservation de chaque résidence proche (passage de « Complet » à « Disponible » ou « A venir ») |
| **ARPEJ** | le compteur « N logements disponibles » de chaque résidence proche |
| **ALJT** | le site est en maintenance (22/10/2026) : tu es prévenue dès qu'il revient |

Il ne garde que ce qui correspond à **tes critères** (modifiables dans `reglages.py`) :
- trajet estimé **≤ 35 min** jusqu'à l'ESILV **Campus du Parc** (29 allée Le Corbusier, Nanterre), à pied ou en RER A, RER E, métro 1, T2, Transilien L ;
- jusqu'à **45 min** si c'est vraiment bien : **à La Défense** (Courbevoie, Puteaux, quartier d'affaires, 1,5 km autour) ou à **≤ 500 €** ;
- loyer : le but, c'est **le moins cher possible**.
  - **≤ 500 €** : 💰 **l'objectif**, signalé en priorité ;
  - **500 à 700 €** : alerte normale ;
  - **700 à 800 €** : seulement si c'est un ❤️ **coup de cœur** (à ≤ 20 min à pied du campus, ou à La Défense) ;
  - au-delà de 800 € : jamais.

Et il te prévient de **deux façons** : 📱 **Telegram** (notification instantanée avec un bouton « Voir / réserver ») **et** 📧 **email**. En option, une 3e : **ntfy** (application avec sonnerie forte).

> ⚡ Le bot te prévient, mais **c'est toi qui réserves**. Les logements partent en quelques minutes : garde ton dossier prêt (voir la fin du guide).

---

## Installation (environ 30 minutes, une seule fois)

Tu as besoin d'un ordinateur pour l'installation. Ensuite, plus besoin de lui.

### Étape 1 — Créer ton bot Telegram (5 min)

1. Installe **Telegram** sur ton téléphone et crée un compte si ce n'est pas déjà fait.
2. Dans la recherche Telegram, tape **@BotFather** (badge bleu ✔) et ouvre la conversation.
3. Envoie `/newbot`.
4. Il demande un **nom** : écris par exemple `Mon alerte logement`.
5. Il demande un **identifiant** finissant par `bot` : par exemple `alerte_logement_amelia_bot` (il doit être unique, ajoute des chiffres si besoin).
6. BotFather te répond avec un **jeton** qui ressemble à `7412345678:AAH...`. **Copie-le** dans un bloc-notes : c'est ton `TELEGRAM_TOKEN`. Ne le partage avec personne.
7. Clique sur le lien de ton bot (`t.me/alerte_logement_..._bot`) et appuie sur **Démarrer** (ou envoie `/start`). C'est indispensable, sinon le bot n'a pas le droit de t'écrire.

### Étape 2 — Créer un mot de passe d'application Gmail (3 min)

Gmail refuse ton mot de passe habituel pour un programme : il faut un « mot de passe d'application ».

1. Va sur https://myaccount.google.com/security et active la **Validation en deux étapes** si ce n'est pas fait.
2. Va sur https://myaccount.google.com/apppasswords
3. Nom de l'application : `bot logement` → **Créer**.
4. Google affiche un code de **16 lettres**. Copie-le : c'est ton `GMAIL_MOT_DE_PASSE_APP`.

### Étape 3 — Mettre le bot sur GitHub (10 min)

1. Crée un compte gratuit sur https://github.com
2. En haut à droite : **+** → **New repository**.
   - Repository name : `bot-logement`
   - Coche **Public** (important : c'est ce qui rend l'hébergement gratuit et illimité. Aucun mot de passe n'y sera visible, ils seront chiffrés à l'étape 4.)
   - Ne coche rien d'autre → **Create repository**.
3. Sur la page qui s'affiche, clique sur le lien **uploading an existing file**.
4. Décompresse le fichier `bot-logement.zip` sur ton ordinateur, ouvre le dossier, **sélectionne tout son contenu** et glisse-le dans la page GitHub.
   - ⚠️ Le dossier `.github` est souvent **caché**. Sur Mac : dans le Finder, appuie sur `Cmd + Shift + .` pour l'afficher. Sur Windows : Explorateur → Affichage → cocher « Éléments masqués ».
5. En bas : **Commit changes**.
6. Vérifie : en haut de ton dépôt, clique sur l'onglet **Actions**. Tu dois voir **« Veille logement »** à gauche.
   - Si tu ne le vois pas (le dossier `.github` n'a pas été envoyé) : onglet **Code** → **Add file** → **Create new file** → dans le nom du fichier, tape exactement `.github/workflows/veille.yml` → colle tout le contenu du fichier `veille.yml` du zip → **Commit changes**.
   - Si GitHub affiche un bouton vert « I understand my workflows, go ahead and enable them », clique dessus.

### Étape 4 — Donner tes codes au bot, en sécurité (5 min)

Dans ton dépôt : **Settings** (⚙️ en haut) → menu de gauche **Secrets and variables** → **Actions** → bouton vert **New repository secret**.

Crée ces secrets un par un (le **nom** doit être écrit exactement pareil) :

| Name | Secret |
|---|---|
| `TELEGRAM_TOKEN` | le jeton de BotFather (étape 1) |
| `GMAIL_ADRESSE` | ton adresse Gmail |
| `GMAIL_MOT_DE_PASSE_APP` | le code de 16 lettres (étape 2) |

Facultatif :
| Name | Secret |
|---|---|
| `EMAIL_DESTINATAIRE` | une autre adresse qui reçoit les alertes (sinon : ta Gmail). Plusieurs possibles, séparées par des virgules |
| `NTFY_TOPIC` | voir « Option : 3e alerte ntfy » plus bas |

Il manque `TELEGRAM_CHAT_ID` : on va le trouver à l'étape suivante.

### Étape 5 — Premier test et ton TELEGRAM_CHAT_ID (3 min)

1. Onglet **Actions** → **Veille logement** (à gauche) → bouton **Run workflow** (à droite) → coche **Envoyer un message de test** → **Run workflow**.
2. Attends 30 secondes, clique sur la ligne qui apparaît, puis sur **veille** → **Vérifier les logements**.
3. Tu vois une ligne : `👉 TON TELEGRAM_CHAT_ID est : 123456789`. Copie ce nombre.
   - Si à la place tu vois « Aucun message reçu par ton bot » : retourne sur Telegram, envoie `/start` à ton bot, et relance le test.
4. Crée le secret `TELEGRAM_CHAT_ID` avec ce nombre (comme à l'étape 4).
5. Relance le test (même manip qu'au point 1). Tu dois recevoir :
   - un message **🧪 TEST** sur Telegram **et** par email ;
   - un message **✅ Ton bot logement est lancé !** avec ce qui est **déjà disponible** en ce moment dans tes critères.

👉 Le bot tourne déjà (environ toutes les 15 min). L'étape 6 le rend **plus rapide et plus régulier**.

### Étape 6 — Vérifier toutes les 5 minutes, sans faute (8 min)

GitHub retarde parfois ses vérifications automatiques (parfois d'une heure ou plus). Pour une vraie vérification toutes les 5 minutes, un service gratuit, **cron-job.org**, va « réveiller » le bot.

**6a. Créer un jeton GitHub**
1. Sur GitHub : ta photo en haut à droite → **Settings** → tout en bas à gauche **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Token name : `cron logement`. Expiration : choisis la **durée la plus longue** proposée (note la date pour le renouveler).
3. Repository access : **Only select repositories** → choisis `bot-logement`.
4. Permissions → **Repository permissions** → **Actions** : **Read and write**. (Rien d'autre.)
5. **Generate token** → copie le jeton (`github_pat_...`). Il ne s'affiche qu'une fois.

**6b. Programmer cron-job.org**
1. Crée un compte gratuit sur https://cron-job.org (pas de carte bancaire).
2. **Create cronjob** :
   - **Title** : `bot logement`
   - **URL** : `https://api.github.com/repos/TON_PSEUDO_GITHUB/bot-logement/actions/workflows/veille.yml/dispatches` (remplace `TON_PSEUDO_GITHUB`)
   - **Execution schedule** : *Every 5 minutes*
3. Onglet **Advanced** :
   - **Request method** : `POST`
   - **Headers** (ajoute 3 lignes) :
     - `Authorization` → `Bearer github_pat_...` (ton jeton, avec le mot `Bearer` et un espace devant)
     - `Accept` → `application/vnd.github+json`
     - `Content-Type` → `application/json`
   - **Request body** : `{"ref":"main"}`
4. **Create**. Clique ensuite sur **Test run** : le résultat attendu est **204** (= ça marche). Dans l'onglet **Actions** de GitHub, un nouveau passage apparaît.

C'est fini 🎉 Le bot vérifie maintenant toutes les 5 minutes, jour et nuit.

---

## Ce que tu vas recevoir

- **🚨 DISPO MAINTENANT** : un nouveau logement correspond à tes critères. Message avec résidence, type, prix, surface, adresse, trajet estimé et **bouton direct** vers la réservation.
- **⏳ BIENTÔT DISPO** : Fac-Habitat a passé un logement en « A venir ». Dépose ta demande tout de suite.
- **🚶 à pied** / **🏙 La Défense** / **💰 OBJECTIF (< 500 €)** / **❤️ coup de cœur** : les meilleures offres sont marquées (et sonnent plus fort sur ntfy).
- **🔔 Le site ALJT est de retour** : quand ALJT sort de maintenance.
- **⚠️ … ne répond plus** : un site ne répond plus depuis environ 1 h (puis **✅** quand ça repart).
- **📊 Résumé** chaque dimanche soir : la preuve que le bot tourne toujours.

Un logement déjà signalé n'est pas renvoyé. S'il disparaît (réservé par quelqu'un) puis **revient** (réservation annulée), tu es prévenue à nouveau : c'est une nouvelle chance.

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
