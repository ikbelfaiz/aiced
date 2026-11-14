"""One development service process: Gateway HTTP plus private verified TLS.

No host ports are published by Compose. Hardened production WSGI supervision
remains a deployment prerequisite; this preserves the project's dev-server scope.
"""

import os
import ssl
import threading
from wsgiref.simple_server import make_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "integration_service.settings")
from django.core.wsgi import get_wsgi_application
from internal_api.serve import ThreadedServer, TLSHandler


def main():
    app = get_wsgi_application()
    private = make_server(
        "0.0.0.0", 8444, app, server_class=ThreadedServer, handler_class=TLSHandler
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        os.environ["INTEGRATION_TLS_CERT"], os.environ["INTEGRATION_TLS_KEY"]
    )
    private.socket = context.wrap_socket(private.socket, server_side=True)
    worker = threading.Thread(target=private.serve_forever, daemon=True)
    worker.start()
    public = make_server("0.0.0.0", 8002, app, server_class=ThreadedServer)
    try:
        public.serve_forever()
    finally:
        private.shutdown()
        private.server_close()
        public.server_close()


if __name__ == "__main__":
    main()
