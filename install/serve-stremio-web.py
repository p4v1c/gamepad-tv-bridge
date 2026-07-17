#!/usr/bin/env python3
"""Serveur statique pour le build du fork stremio-web (kiosk Stremio TV).

Comme `python -m http.server`, mais avec des en-têtes de cache corrects :
- `no-cache` pour index.html et service-worker.js → le kiosk revalide à chaque
  lancement et voit immédiatement un nouveau build (webpack a `output.clean`,
  un index.html périmé pointerait vers des assets supprimés) ;
- cache long + `immutable` pour les assets sous les dossiers hashés par commit.

Usage : serve-stremio-web.py <build-dir> [port]   (bind 127.0.0.1 uniquement)
"""

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class CacheAwareHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        path = self.path.split('?', 1)[0]
        if path.endswith(('.html', '/service-worker.js')) or path == '/':
            self.send_header('Cache-Control', 'no-cache')
        else:
            # Assets sous <hash-de-commit>/… : immuables par construction.
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
        super().end_headers()

    def log_message(self, *args):
        pass  # pas de log par requête dans le journal systemd


def main():
    if len(sys.argv) < 2:
        sys.exit(f'usage: {sys.argv[0]} <build-dir> [port]')
    directory = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8096
    handler = partial(CacheAwareHandler, directory=directory)
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    print(f'Serving {directory} on http://127.0.0.1:{port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
