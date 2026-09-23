# Comprendre et discuter l'IA

Conférences, dossiers et documentation sur l'intelligence artificielle, 2025-2026.
Production de **Christo Datso** et de sa squad de travail, servie sous
<https://www.cdatso.be/comprendre-ia/>.

Le fonds rassemble quatre conférences données ou en préparation, leurs restitutions fiche par
fiche, sept fiches de concepts adossées à des démonstrations exécutables, trois dossiers de fond
et quelques notes de lecture. **92 pages.**

> **Ce dépôt est une COPIE ASSEMBLÉE, pas un atelier.** Les pages sont écrites ailleurs, dans un
> dossier de travail local qui n'est pas versionné. Ce dépôt en reçoit une copie publiable,
> produite par un script, à partir d'une **liste d'admission** : `outils/admission.txt` nomme un
> par un les 140 fichiers qui entrent. Ce qui n'y est pas nommé n'entre pas.

## Pourquoi une liste d'admission, et pas une liste d'exclusion

Un dépôt public n'oublie rien : l'historique git ne s'efface pas. Une pièce non redistribuable
oubliée dans une liste d'exclusion serait publiée pour de bon. Oubliée dans une liste
d'admission, elle reste simplement locale. C'est toute la différence, et c'est la raison de la
forme de ce dépôt.

## Ce qui n'entre pas, et pourquoi

| Ce qui reste hors ligne | Motif |
|---|---|
| Le fonds SEP — 41 pages de la *Stanford Encyclopedia of Philosophy* | La licence autorise la copie locale pour l'étude et **interdit la redistribution**. Voir [`fonds-sep.html`](fonds-sep.html), qui renvoie aux entrées en ligne. |
| Tout document de tiers : thèses, articles, rapports, figures, vidéo, audio | Œuvres d'autrui ; aucune n'est redistribuée. |
| Les transcriptions de conférences (`.srt`) | Des personnes physiques y parlent. |
| Le mini-site « Cinéma, IA et conscience » | Publication différée après la conférence du 1er décembre 2026, et sans ses données tierces. |
| La conférence de sensibilisation « IA et emploi » et son quiz | Conférence non confirmée ; dossier dormant. |
| Le carnet NotebookLM, le site frère Afrofuturisme, le dossier Searle | Hors périmètre de cette première version. |
| Les scripts de démonstration (`.py`), les sources de diaporama (`.pptx`) | Version 1 : pages HTML seules. |

**Les références à ces pièces n'ont pas été effacées du texte.** Quand une page citait un
document qui n'entre pas, la référence reste lisible — titre, auteur, date — et seul le lien
disparaît. `outils/INVENTAIRE-EXPORT.md` en donne la liste complète : 39 liens retirés, avec leur
page et leur cible.

## Ce que le lecteur doit savoir

- Les pages ont été **écrites pour un usage local** entre janvier 2025 et septembre 2026, et sont
  publiées **telles quelles**, sans réécriture. Certaines citent les dossiers où elles ont été
  produites. L'accueil le dit en chapeau daté.
- Le fonds est **daté** : chaque restitution de conférence porte l'état des choses au jour où
  elle a été donnée, et n'est pas actualisée.
- Les pages ont été produites avec des agents IA (Claude d'Anthropic), révisées et validées par
  Christo Datso. La mention figure au pied de l'accueil et sur
  [`provenance-licences.html`](provenance-licences.html), qui détaille les régimes de licence
  site par site.
- Toutes les pages portent `<meta name="robots" content="noindex, nofollow">` : le fonds n'est
  pas indexé par les moteurs pour l'instant.
- Les restitutions de conférences sont sous licence **CC BY-NC-SA** de Christo Datso.

## Régénérer le dépôt

```
python outils/assemble.py --source <dossier de travail> --export <racine de ce depot>
python outils/verifie.py  --export <racine de ce depot>
```

`assemble.py` (Python 3, bibliothèque standard seule, ASCII pur) reconstruit **tout** l'export à
chaque passe : il copie les fichiers admis, réécrit les liens internes vers les chemins publiés,
retire les `href` vers une cible non admise en conservant le texte, pose le `noindex`, le chapeau
daté, la mention de provenance et le bandeau de la lecture critique, convertit cette dernière du
Markdown vers HTML par **pandoc**, écrit les trois pages de service et l'inventaire.

Le script est **idempotent** : deux passes produisent les mêmes octets. Il n'écrit jamais dans le
dossier source.

`verifie.py` rejoue les contrôles et sort en erreur si l'un tombe : aucun fichier hors liste,
aucun fichier attendu manquant, aucune extension ni aucun nom exclu, aucun lien interne mort,
aucun lien sortant, aucun chemin local, aucune ressource externe chargée, `noindex` présent **et
placé dans la tête** de chacune des 92 pages.

## Les fichiers de l'outillage

| Fichier | Rôle |
|---|---|
| `outils/admission.txt` | La liste d'admission : 140 fichiers, source → chemin publié. La borne. |
| `outils/assemble.py` | L'assemblage. ASCII pur, chemins en paramètre. |
| `outils/textes.json` | Tous les textes français injectés, les motifs de retrait, les renvois. Un mot à corriger se corrige **ici**, puis on rejoue — jamais à la main dans les pages. |
| `outils/verifie.py` | Les preuves de sortie. |
| `outils/INVENTAIRE-EXPORT.md` | Fichiers copiés avec leur SHA-256, liens retirés, pages neuves. |
