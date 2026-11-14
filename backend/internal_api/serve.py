"""Small private TLS WSGI listener for container development/rehearsal.

Production deployments should use an approved hardened WSGI/TLS supervisor.
This listener never adds private routes to the public Django URLConf.
"""

import os
import ssl
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "internal_api.settings")
from django.core.wsgi import get_wsgi_application


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

    def close_request(self, request):
        from django.db import connections
        connections.close_all()
        super().close_request(request)



class TLSHandler(WSGIRequestHandler):
    def get_environ(self):
        env = super().get_environ()
        if isinstance(self.connection, ssl.SSLSocket):
            env["HTTPS"] = "on"
            env["wsgi.url_scheme"] = "https"
        return env


def main():
    server = make_server(
        "0.0.0.0",
        8443,
        get_wsgi_application(),
        server_class=ThreadedServer,
        handler_class=TLSHandler,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(os.environ["IAM_TLS_CERT"], os.environ["IAM_TLS_KEY"])
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
