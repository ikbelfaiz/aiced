"""Bounded request diagnostics: identifiers and timings, never credentials or SQL."""
from contextvars import ContextVar
import logging

request_id = ContextVar('aiced_request_id', default=None)


def record(event, **fields):
    logging.getLogger('aiced.metrics').info('', extra={
        'event': event, 'metrics': dict(request_id=request_id.get(), **fields)})
