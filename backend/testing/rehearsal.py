"""Fail-closed identification of newly created, synthetic M1 databases only."""

import re


def validate_environment(env, database=None):
    run = env.get("AICED_REHEARSAL_RUN", "")
    if not re.fullmatch(r"[0-9a-f]{32}", run):
        raise ValueError("A synthetic rehearsal run identifier is required.")
    if env.get("DJANGO_DEBUG") != "1" or env.get("POSTGRES_HOST") not in (
        "127.0.0.1",
        "localhost",
        "::1",
    ):
        raise ValueError("Rehearsal requires DEBUG and loopback PostgreSQL.")
    name = database or env.get("POSTGRES_DB")
    if name not in (f"aiced_m1_{run}_source", f"aiced_m1_{run}_restore"):
        raise ValueError("Only this run's generated scratch databases are permitted.")
    return name
