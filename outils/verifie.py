# -*- coding: ascii -*-
"""verifie.py -- preuves de sortie de l'export (BKL-CNF-012, mandat par.3 L1 et V3-V7).

Ne modifie rien. Sort en code 1 si une seule preuve tombe.

Usage : python verifie.py --export <racine export> --outils <dir>
"""

import argparse
import os
import posixpath
import re
import sys
from urllib.parse import unquote

ATTR = re.compile(r'(?:href|src)\s*=\s*"([^"]*)"|(?:href|src)\s*=\s*\'([^\']*)\'', re.I)
CSSURL = re.compile(r'url\(\s*([\'"]?)([^\'")]+)\1\s*\)', re.I)
CHARGE = re.compile(r'<(?:script|img|link|iframe|video|audio|source|embed|object)'
                    r'[^>]+(?:src|href|data)\s*=\s*["\']https?://', re.I)
LOCAL = re.compile(r'[A-Za-z]:\\|\\Users\\|/Users/|file:///')
EXCLUS = ('.pdf', '.mp4', '.m4a', '.pptx', '.docx', '.xlsx', '.srt', '.py', '.md', '.txt')
NOMS_INTERDITS = ('SEP/', 'NotebookLM', 'afrofuturisme', 'sensibilisation',
                  'transcriptions', 'NDBI conf', 'Searle')

IGNORE = {'.git'}


def fichiers(export):
    out = []
    for dp, dn, fn in os.walk(export):
        dn[:] = [d for d in dn if d not in IGNORE]
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), export).replace('\\', '/')
            out.append(rel)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--export', required=True)
    ap.add_argument('--outils', default=None)
    # Depuis le 23/09/2026 (lot << mise en visibilite >>, gate AH) : le noindex est ATTENDU
    # (defaut, etat de la v1 a l'ouverture) ou ABSENT (etat apres la levee). L'un ou l'autre
    # se prouve ; un melange est un echec.
    ap.add_argument('--noindex', choices=('attendu', 'absent'), default='attendu')
    a = ap.parse_args()
    export = os.path.abspath(a.export)
    outils = a.outils or os.path.join(export, 'outils')

    attendus = set()
    for ligne in open(os.path.join(outils, 'admission.txt'), encoding='utf-8'):
        if '  ->  ' in ligne and not ligne.startswith('#'):
            attendus.add(ligne.split('  ->  ')[1].strip())
    neuves = {'fonds-sep.html', '404.html',
              'concepts/cafephilo-lecture-jansma/lecture-critique-jansma.html'}
    service = {'.nojekyll', '.gitattributes', 'README.md',
               'outils/admission.txt', 'outils/assemble.py', 'outils/verifie.py',
               'outils/textes.json', 'outils/INVENTAIRE-EXPORT.md'}

    presents = set(fichiers(export))
    pages = sorted(p for p in presents if p.endswith('.html'))
    echecs = []

    # --- V3 : l'export est exactement la liste d'admission + les pages nommees -------
    hors = presents - attendus - neuves - service
    manque = (attendus | neuves) - presents
    if hors:
        echecs.append('fichiers HORS liste : %s' % sorted(hors))
    if manque:
        echecs.append('fichiers ATTENDUS absents : %s' % sorted(manque))

    # --- V7 : aucun exclu par extension ni par nom ----------------------------------
    par_ext = [p for p in presents if p.lower().endswith(EXCLUS)
               and not p.startswith('outils/') and p != 'README.md']
    if par_ext:
        echecs.append('fichiers a extension exclue : %s' % par_ext)
    par_nom = [p for p in presents for n in NOMS_INTERDITS if n.lower() in p.lower()]
    if par_nom:
        echecs.append('fichiers a nom exclu : %s' % par_nom)

    # --- V4/V5 : liens, chemins, ressources, noindex ---------------------------------
    morts, sortants, locaux, sans_noindex, externes_chargees = [], [], [], [], []
    n_ext = n_ancre = n_interne = 0
    for p in pages:
        txt = open(os.path.join(export, p.replace('/', os.sep)),
                   encoding='utf-8', errors='replace').read()
        i_rob = txt.find('name="robots"')
        if a.noindex == 'absent':
            # apres la levee : aucune page ne doit plus porter le meta
            if i_rob >= 0 and 'noindex' in txt:
                sans_noindex.append((p, 'ENCORE PRESENT'))
        elif i_rob < 0 or 'noindex' not in txt:
            sans_noindex.append((p, 'absent'))
        else:
            # le meta doit etre dans la TETE : avant tout contenu de corps.
            corps = [txt.lower().find(b) for b in ('<body', '<header', '<div class="wrap"',
                                                   '<h1')]
            corps = [c for c in corps if c >= 0]
            if corps and i_rob > min(corps):
                sans_noindex.append((p, 'hors tete'))
        if LOCAL.search(txt):
            locaux.append((p, LOCAL.search(txt).group(0)))
        if CHARGE.search(txt):
            externes_chargees.append((p, CHARGE.search(txt).group(0)[:60]))
        cibles = [m.group(1) if m.group(1) is not None else m.group(2)
                  for m in ATTR.finditer(txt)]
        cibles += [m.group(2) for m in CSSURL.finditer(txt)]
        for c in cibles:
            if not c:
                continue
            b = c.strip().lower()
            if b.startswith('#'):
                n_ancre += 1
                continue
            if b.startswith(('http://', 'https://', 'mailto:', 'data:', 'javascript:',
                             'tel:')):
                n_ext += 1
                continue
            if b.startswith('/'):
                continue                    # /comprendre-ia/ : chemin servi, hors disque
            t = unquote(c.split('#')[0].split('?')[0]).replace('\\', '/')
            if not t:
                continue
            r = posixpath.normpath(posixpath.join(posixpath.dirname(p), t))
            if r.startswith('..'):
                sortants.append((p, c))
            elif r not in presents:
                morts.append((p, c, r))
            else:
                n_interne += 1

    for nom, lst in (('liens internes MORTS', morts),
                     ('liens SORTANTS (..)', sortants),
                     ('chemins LOCAUX', locaux),
                     ('ressources EXTERNES chargees', externes_chargees),
                     ('pages SANS noindex', sans_noindex)):
        if lst:
            echecs.append('%s : %d -> %s' % (nom, len(lst), lst[:6]))

    # --- V5 : mention de provenance aux deux emplacements ----------------------------
    import json
    textes = json.load(open(os.path.join(outils, 'textes.json'), encoding='utf-8'))
    mention = textes['provenance']['texte']
    chapeau = textes['chapeau']['texte']
    for p in ('index.html', 'provenance-licences.html'):
        if mention not in open(os.path.join(export, p), encoding='utf-8').read():
            echecs.append('mention de provenance absente de %s' % p)
    if chapeau not in open(os.path.join(export, 'index.html'), encoding='utf-8').read():
        echecs.append('chapeau date absent de index.html')

    poids = sum(os.path.getsize(os.path.join(export, p.replace('/', os.sep)))
                for p in presents if not p.startswith('outils/'))

    print('pages HTML                    : %d' % len(pages))
    print('fichiers (hors .git)          : %d' % len(presents))
    print('poids (hors outils/)          : %d octets (%.2f Mo)' % (poids, poids / 1048576.0))
    print('liens internes vivants        : %d' % n_interne)
    print('liens externes (non charges)  : %d' % n_ext)
    print('ancres                        : %d' % n_ancre)
    print('---')
    print('0 fichier hors liste          : %s' % ('OUI' if not hors else 'NON'))
    print('0 fichier attendu manquant    : %s' % ('OUI' if not manque else 'NON'))
    print('0 extension/nom exclu         : %s' % ('OUI' if not par_ext and not par_nom else 'NON'))
    print('0 lien interne mort           : %s' % ('OUI' if not morts else 'NON'))
    print('0 lien sortant ..             : %s' % ('OUI' if not sortants else 'NON'))
    print('0 chemin local                : %s' % ('OUI' if not locaux else 'NON'))
    print('0 ressource externe chargee   : %s' % ('OUI' if not externes_chargees else 'NON'))
    print('noindex sur 100%% des pages    : %s' % ('OUI' if not sans_noindex else 'NON'))
    if echecs:
        print('\n=== ECHECS ===')
        for e in echecs:
            print(' - %s' % e)
        sys.exit(1)
    print('\nTOUTES LES PREUVES DE SORTIE PASSENT.')


if __name__ == '__main__':
    main()
