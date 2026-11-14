import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Deliberately omit request bodies, arbitrary message text and exception details.
        return json.dumps({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'event': getattr(record, 'event', 'application_log'),
        })
