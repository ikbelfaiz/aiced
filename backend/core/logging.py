import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Deliberately omit request bodies, arbitrary message text and exception details.
        data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'event': getattr(record, 'event', 'application_log'),
        }
        if record.name == 'aiced.metrics':
            allowed = {'request_id', 'peer_request_id', 'peer', 'path', 'status',
                       'seconds', 'sql_count', 'sql_seconds', 'timeout_seconds',
                       'expired', 'phase', 'batches', 'remaining_seconds'}
            data.update({key: value for key, value in getattr(record, 'metrics', {}).items()
                         if key in allowed})
        return json.dumps(data)
