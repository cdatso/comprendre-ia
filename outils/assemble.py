# -*- coding: ascii -*-
"""assemble.py -- assemblage de l'export public du portail "Comprendre et discuter l'IA".

BKL-CNF-012. Lit outils/admission.txt (la LISTE D'ADMISSION : ce qui n'y est pas nomme
n'entre pas), copie les fichiers admis vers l'export, reecrit les liens internes, retire les
href vers une cible non admise (texte conserve), pose le noindex, la mention de provenance,
le chapeau date et le bandeau Jansma, convertit la lecture critique par pandoc, ecrit les
pages de service, puis l'inventaire.

IDEMPOTENT : l'export est reconstruit a chaque passe ; deux passes donnent les memes octets.
Le script n'ecrit JAMAIS sous la source. Il est en ASCII pur : tous les textes francais
vivent dans outils/textes.json (UTF-8).

Usage :
  python assemble.py --source <racine CNF> --export <racine export> [--outils <dir>]
"""

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, quote

ATTR = re.compile(r'(\s)(href|src)(\s*=\s*)(["\'])(.*?)\4', re.S | re.I)
HEAD = re.compile(r'<head(?:\s[^>]*)?>', re.I)   # jamais <header>
CSSURL = re.compile(r'url\(\s*([\'"]?)([^\'")]+)\1\s*\)', re.I)
STYLE = re.compile(r'<style>.*?</style>', re.S | re.I)
SEPROW = re.compile(
    r'<tr>.*?<td class="n">(\d+)</td>.*?'
    r'<td class="t"><a href="[^"]*">(.*?)</a><span class="sl">([a-z0-9-]+)</span></td>'
    r'<td class="a">(.*?)</td><td class="d">(.*?)</td>', re.S)

PROTEGES = {'.git', '.gitattributes', '.gitignore', '.nojekyll', 'outils', 'README.md'}


def lire_admission(chemin):
    paires = []
    with open(chemin, 'r', encoding='utf-8') as fh:
        for n, ligne in enumerate(fh, 1):
            ligne = ligne.strip()
            if not ligne or ligne.startswith('#'):
                continue
            if '  ->  ' not in ligne:
                raise SystemExit('admission.txt ligne %d : separateur absent' % n)
            src, dst = ligne.split('  ->  ', 1)
            paires.append((src.strip(), dst.strip()))
    return paires


def vider_export(export):
    """Repart d'un export propre : garantit 0 fichier hors liste ET l'idempotence."""
    if not os.path.isdir(export):
        os.makedirs(export)
        return
    for nom in os.listdir(export):
        if nom in PROTEGES:
            continue
        p = os.path.join(export, nom)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)


def resoudre(src_rel, cible):
    """Cible d'un lien, exprimee en chemin source relatif a la racine CNF."""
    brut = cible.split('#')[0].split('?')[0]
    frag = cible[len(brut):]
    t = unquote(brut).replace('\\', '/')
    if not t:
        return None, frag
    base = posixpath.dirname(src_rel)
    return posixpath.normpath(posixpath.join(base, t)), frag


def vers_export(dst_rel, cible_export, frag):
    rel = posixpath.relpath(cible_export, posixpath.dirname(dst_rel) or '.')
    return quote(rel, safe='/-_.~()') + frag


def reecrire(txt, src_rel, dst_rel, table, redir, journal):
    """Reecrit href/src. Cible admise -> chemin d'export ; cible non admise -> href retire."""
    sortie = []
    fin = 0
    for m in ATTR.finditer(txt):
        espace, attr, eq, q, val = m.groups()
        sortie.append(txt[fin:m.start()])
        fin = m.end()
        brut = val.strip()
        bas = brut.lower()
        if not brut or bas.startswith('#') or bas.startswith(
                ('http://', 'https://', 'mailto:', 'data:', 'javascript:', 'tel:')):
            sortie.append(m.group(0))
            continue
        cible, frag = resoudre(src_rel, brut)
        if cible is None:
            sortie.append(m.group(0))
            continue
        if cible in table:
            neuf = vers_export(dst_rel, table[cible], frag)
            sortie.append('%s%s%s%s%s%s' % (espace, attr, eq, q, neuf, q))
            journal['reecrits'].append((dst_rel, brut, neuf))
        elif cible in redir:
            neuf = vers_export(dst_rel, redir[cible], frag)
            sortie.append('%s%s%s%s%s%s' % (espace, attr, eq, q, neuf, q))
            journal['rediriges'].append((dst_rel, brut, neuf))
        elif attr.lower() == 'href':
            sortie.append('')                      # l'attribut href disparait, le texte reste
            journal['retires'].append((dst_rel, brut, cible))
        else:
            journal['src_orphelins'].append((dst_rel, brut, cible))
            sortie.append(m.group(0))
    sortie.append(txt[fin:])
    return ''.join(sortie)


def poser_css(txt, css):
    """La regle des liens retires doit passer APRES le style de la page : a meme
    specificite que `.fiches a`, c'est la derniere declaree qui l'emporte.
    Une page sans </head> (ESPACE-LATENT-INTERACTIF) a une tete IMPLICITE : le style y
    entre quand meme, pourvu qu'il suive le <style> de la page."""
    i = txt.lower().rfind('</head>')
    if i >= 0:
        return txt[:i] + css + txt[i:]
    j = txt.lower().find('</style>')
    if j < 0:
        raise SystemExit('ni </head> ni </style> : impossible de poser le style')
    j += len('</style>')
    return txt[:j] + css + txt[j:]


def poser_noindex(txt, noindex):
    if 'name="robots"' in txt:
        return txt
    m = HEAD.search(txt)
    if not m:
        # Tete IMPLICITE : un <meta> place en tete de document est absorbe par le <head>
        # que le parseur cree. Aucune balise n'est ajoutee a la page.
        return noindex + txt
    return txt[:m.end()] + noindex + txt[m.end():]


def inserer_avant(txt, ancre, bloc, quoi):
    i = txt.find(ancre)
    if i < 0:
        raise SystemExit('ancre introuvable pour %s : %s' % (quoi, ancre))
    return txt[:i] + bloc + txt[i:]


def inserer_pied(txt, phrase, quoi):
    i = txt.rfind('</footer>')
    if i < 0:
        raise SystemExit('pas de </footer> pour ' + quoi)
    return txt[:i] + '<br>' + phrase + txt[i:]


def gabarit(style, titre, noindex, corps, css=''):
    return ('<!DOCTYPE html>\n<html lang="fr">\n<head>' + noindex
            + '<meta charset="utf-8"><meta name="viewport" '
              'content="width=device-width, initial-scale=1">\n<title>'
            + titre + '</title>\n' + style + css + '</head>\n<body><div class="wrap">\n'
            + corps + '\n</div></body></html>\n')


def barre_nav(textes):
    n = textes['nav']
    return ('<div class="nav"><a href="index.html">%s</a>'
            '<a href="pieces-recurrentes.html">%s</a>'
            '<a href="provenance-licences.html">%s</a></div>\n'
            % (n['accueil'], n['pieces'], n['provenance']))


def page_fonds_sep(style, textes, sep_index, css):
    t = textes['fonds_sep']
    lignes = []
    for num, titre, slug, auteur, date in SEPROW.findall(sep_index):
        lignes.append(
            '<tr><td class="an">%s</td><td>%s</td><td>%s</td><td class="an">%s</td>'
            '<td><a class="lien-ext" href="https://plato.stanford.edu/entries/%s/" '
            'rel="noopener">plato.stanford.edu</a></td></tr>'
            % (num, titre, auteur, date, slug))
    col = t['colonnes']
    corps = (
        barre_nav(textes)
        + '<h1>' + t['titre'] + '</h1>\n'
        '<div class="avert"><b>' + t['bandeau'] + '</b></div>\n'
        '<p class="chapeau">' + t['chapeau'] + '</p>\n'
        + '\n'.join(t['corps']) + '\n'
        '<h2>' + t['titre_liste'] + '</h2>\n'
        '<p class="chapeau">' + t['chapeau_liste'] + '</p>\n'
        '<div class="tbl"><table>\n'
        '<tr><th style="width:1%">' + col[0] + '</th><th>' + col[1] + '</th><th>' + col[2]
        + '</th><th style="width:1%">' + col[3] + '</th><th style="width:1%">' + col[4]
        + '</th></tr>\n'
        + '\n'.join(lignes) + '\n</table></div>\n'
        '<footer>' + t['pied'] + '</footer>')
    return gabarit(style, t['titre'], textes['noindex'], corps, css), len(lignes)


def page_404(style, textes, css):
    t = textes['p404']
    corps = ('<h1>' + t['titre'] + '</h1>\n<p class="chapeau">' + t['chapeau'] + '</p>\n'
             + t['corps'] + '\n<p><a href="/comprendre-ia/">' + t['lien'] + '</a></p>')
    return gabarit(style, t['titre'], textes['noindex'], corps, css)


def page_jansma(style, textes, md, pandoc, tmp, css):
    # Les retraits du Markdown passent AVANT pandoc : ce sont des textes d'auteur, chaque
    # retrait est prononce par AH en elicitation et consigne dans textes.json.
    with open(md, 'r', encoding='utf-8') as fh:
        src = fh.read()
    for r in textes['retraits_jansma']:
        src, n = re.subn(r['motif'], r['remplacement'], src)
        if n != r['attendu']:
            raise SystemExit('ARRET : retrait Jansma applique %d fois, %d attendu'
                             % (n, r['attendu']))
    ecrire(tmp, src)
    res = subprocess.run([pandoc, '-f', 'markdown', '-t', 'html', '--no-highlight', tmp],
                         capture_output=True)
    os.remove(tmp)
    if res.returncode != 0:
        raise SystemExit('pandoc : ' + res.stderr.decode('utf-8', 'replace'))
    b = textes['bandeau_jansma']
    n = textes['nav']
    corps = ('<div class="nav"><a href="../index.html">' + n['jansma_dossier'] + '</a>'
             '<a href="../concept-07-verite-direction.html">' + n['jansma_concept7']
             + '</a></div>\n'
             '<div class="avert"><b>' + b['titre'] + '.</b> ' + b['texte'] + '</div>\n'
             + res.stdout.decode('utf-8'))
    return gabarit(style, textes['titre_jansma'], textes['noindex'], corps, css)


def sha(chemin):
    h = hashlib.sha256()
    with open(chemin, 'rb') as fh:
        for bloc in iter(lambda: fh.read(1 << 20), b''):
            h.update(bloc)
    return h.hexdigest()


def ecrire(chemin, texte):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(texte)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--export', required=True)
    ap.add_argument('--outils', default=None)
    ap.add_argument('--pandoc', default='pandoc')
    a = ap.parse_args()
    source = os.path.abspath(a.source)
    export = os.path.abspath(a.export)
    outils = os.path.abspath(a.outils) if a.outils else os.path.join(export, 'outils')
    if os.path.commonpath([source, export]) == source:
        raise SystemExit('ARRET : l\'export serait sous la source.')

    paires = lire_admission(os.path.join(outils, 'admission.txt'))
    with open(os.path.join(outils, 'textes.json'), 'r', encoding='utf-8') as fh:
        textes = json.load(fh)
    table = dict(paires)
    redir = {k: v for k, v in textes['redirections'].items() if not k.startswith('_')}
    noindex = textes['noindex']
    css = textes['style_liens_retires']['css']

    manquants = [s for s, _ in paires
                 if not os.path.isfile(os.path.join(source, s.replace('/', os.sep)))]
    if manquants:
        raise SystemExit('ARRET : source absente : ' + '; '.join(manquants[:5]))

    vider_export(export)
    journal = {'reecrits': [], 'retires': [], 'rediriges': [], 'src_orphelins': [],
               'copies': [], 'neuves': []}

    canon = os.path.join(source, 'CAFE-PHILO-I', 'index.html')
    with open(canon, 'r', encoding='utf-8') as fh:
        m = STYLE.search(fh.read())
    if not m:
        raise SystemExit('style du canon CAFE-PHILO-I/index.html introuvable')
    style = m.group(0)

    for src_rel, dst_rel in paires:
        src = os.path.join(source, src_rel.replace('/', os.sep))
        dst = os.path.join(export, dst_rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if dst_rel.lower().endswith('.html'):
            with open(src, 'r', encoding='utf-8') as fh:
                txt = fh.read()
            # Les retraits passent AVANT la reecriture : ils visent le balisage d'origine,
            # dont l'attribut href que la reecriture ferait disparaitre.
            for r in textes['retraits']:
                if r['cible'] == dst_rel:
                    txt, n = re.subn(r['motif'], r['remplacement'], txt)
                    if n != r['attendu']:
                        raise SystemExit('ARRET : retrait "%s" applique %d fois, %d attendu'
                                         % (r['cible'], n, r['attendu']))
            txt = reecrire(txt, src_rel, dst_rel, table, redir, journal)
            txt = poser_noindex(txt, noindex)
            txt = poser_css(txt, css)
            if dst_rel == 'index.html':
                txt = inserer_avant(txt, '<div class="note">',
                                    '<div class="note"><p>' + textes['chapeau']['texte']
                                    + '</p></div>\n', 'chapeau')
                txt = inserer_pied(txt, textes['provenance']['texte'], 'index.html')
            if dst_rel == 'provenance-licences.html':
                txt = inserer_avant(txt, '<h2>',
                                    '<div class="note"><p><b>Provenance de ces pages.</b> '
                                    + textes['provenance']['texte'] + '</p></div>\n',
                                    'provenance')
                txt = inserer_pied(txt, textes['provenance']['texte'],
                                   'provenance-licences.html')
            ecrire(dst, txt)
        else:
            shutil.copyfile(src, dst)
            if dst_rel.lower().endswith('.css'):
                with open(dst, 'r', encoding='utf-8') as fh:
                    for u in CSSURL.findall(fh.read()):
                        if not u[1].lower().startswith(('http', 'data:')):
                            journal['src_orphelins'].append((dst_rel, u[1], 'url() css'))
        journal['copies'].append((src_rel, dst_rel, os.path.getsize(dst), sha(dst)))

    # --- pages de service, ecrites par la session -------------------------------------
    with open(os.path.join(source, 'CAFE-PHILO-II', 'SEP', 'index.html'),
              'r', encoding='utf-8') as fh:
        sep_txt = fh.read()
    html, n_entrees = page_fonds_sep(style, textes, sep_txt, css)
    ecrire(os.path.join(export, 'fonds-sep.html'), html)
    journal['neuves'].append(('fonds-sep.html', n_entrees))

    ecrire(os.path.join(export, '404.html'), page_404(style, textes, css))
    journal['neuves'].append(('404.html', 0))

    md = os.path.join(source, 'CAFE-PHILO-I', 'cafephilo-lecture-jansma',
                      'LECTURE-CRITIQUE-JANSMA-v1.md')
    cible_jansma = 'concepts/cafephilo-lecture-jansma/lecture-critique-jansma.html'
    ecrire(os.path.join(export, cible_jansma.replace('/', os.sep)),
           page_jansma(style, textes, md, a.pandoc,
                       os.path.join(outils, '.jansma-source.tmp.md'), css))
    journal['neuves'].append((cible_jansma, 0))

    for nom in ('.nojekyll',):
        ecrire(os.path.join(export, nom), '')

    inventaire(export, outils, textes, journal)
    print('pages+fichiers copies : %d' % len(journal['copies']))
    print('pages neuves          : %d' % len(journal['neuves']))
    print('liens reecrits        : %d' % len(journal['reecrits']))
    print('liens rediriges (SEP) : %d' % len(journal['rediriges']))
    print('href RETIRES          : %d' % len(journal['retires']))
    print('src orphelins         : %d' % len(journal['src_orphelins']))
    if journal['src_orphelins']:
        for x in journal['src_orphelins']:
            print('  !! %s | %s | %s' % x)
        raise SystemExit('ARRET : une ressource chargee n\'est pas admise.')


def inventaire(export, outils, textes, journal):
    L = []
    L.append("# INVENTAIRE DE L'EXPORT -- portail \"Comprendre et discuter l'IA\"")
    L.append('')
    L.append("*Ecrit par `outils/assemble.py` (BKL-CNF-012). Date d'export : **%s** "
             "(champ `date_export` de `outils/textes.json`). Ce fichier est reproductible "
             "a l'octet : il ne porte aucune heure de passe.*" % textes['date_export'])
    L.append('')
    total = sum(t[2] for t in journal['copies'])
    L.append('## 1. Compte')
    L.append('')
    L.append('| | |')
    L.append('|---|---:|')
    L.append('| Fichiers copies depuis la source | %d |' % len(journal['copies']))
    L.append('| Pages neuves ecrites par la session | %d |' % len(journal['neuves']))
    L.append('| Liens internes reecrits | %d |' % len(journal['reecrits']))
    L.append('| Liens renvoyes vers `fonds-sep.html` | %d |' % len(journal['rediriges']))
    L.append('| Attributs `href` RETIRES (texte conserve) | %d |' % len(journal['retires']))
    L.append('| Poids des fichiers copies | %d octets |' % total)
    L.append('')
    L.append('## 2. Liens retires -- page, texte du lien, cible exclue')
    L.append('')
    L.append('*Decision 3 d\'AH : la reference reste en TEXTE, l\'attribut `href` disparait, '
             'aucun remplacement par un lien en ligne.*')
    L.append('')
    L.append('| Page de l\'export | Lien d\'origine | Cible exclue |')
    L.append('|---|---|---|')
    for page, brut, cible in journal['retires']:
        L.append('| `%s` | `%s` | `%s` |' % (page, brut, cible))
    L.append('')
    L.append('## 3. Pages neuves')
    L.append('')
    for nom, n in journal['neuves']:
        L.append('- `%s`%s' % (nom, (' -- %d entrees SEP listees' % n) if n else ''))
    L.append('')
    L.append('## 4. Fichiers copies -- source, export, octets, SHA-256')
    L.append('')
    L.append('| Source (sous `CNF\\`) | Export | Octets | SHA-256 |')
    L.append('|---|---|---:|---|')
    for src, dst, taille, h in journal['copies']:
        L.append('| `%s` | `%s` | %d | `%s` |' % (src, dst, taille, h))
    L.append('')
    ecrire(os.path.join(outils, 'INVENTAIRE-EXPORT.md'), '\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
