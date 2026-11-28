"""Development-only CLIENT HTTP/Gateway plus private TLS, one owned app process."""

import os, ssl, threading
from wsgiref.simple_server import make_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iam_consumer.settings")
from django.core.wsgi import get_wsgi_application
from internal_api.serve import ThreadedServer, TLSHandler


def main():
    app = get_wsgi_application()
    workers = []
    if os.environ.get('AICED_SYNTHETIC_WORKER') == '1':
        from clients.synthetic_worker import start
        workers.append(start())
    if os.environ.get('AICED_OPERATIONAL_WORKER') == '1':
        from clients.operational_worker import start
        workers.append(start())
    private = make_server(
        "0.0.0.0", 8446, app, server_class=ThreadedServer, handler_class=TLSHandler
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(os.environ["CLIENT_TLS_CERT"], os.environ["CLIENT_TLS_KEY"])
    private.socket = context.wrap_socket(private.socket, server_side=True)
    threading.Thread(target=private.serve_forever, daemon=True).start()
    public = make_server("0.0.0.0", 8000, app, server_class=ThreadedServer)
    try:
        public.serve_forever()
    finally:
        for stop, thread in workers:
            stop.set()
            thread.join(timeout=10)
        private.shutdown()
        private.server_close()
        public.server_close()


if __name__ == "__main__":
    main()
