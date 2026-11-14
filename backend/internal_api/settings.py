from config.settings import *

# Run only on a separate private listener. Never publish this URLConf in Nginx.
ROOT_URLCONF = "internal_api.urls"
MIDDLEWARE = ["core.middleware.RequestContextMiddleware"]
SECURE_SSL_REDIRECT = False  # Local listener; inter-host client enforces HTTPS.
