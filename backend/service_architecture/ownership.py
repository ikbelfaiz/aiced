"""Explicit target ownership. Fail closed for new, unclassified tables/routes."""

SCHEMAS = {
    "iam": "aiced_iam",
    "client_crm": "aiced_client_crm",
    "commercial": "aiced_commercial",
    "integration": "aiced_integration",
}


def table_owner(table):
    if table == "django_migrations":
        return "legacy_registry"
    if table.startswith(("identity_", "auth_")) or table in (
        "django_session",
        "django_content_type",
        "audit_auditevent",
        "audit_auditoutbox",
        "audit_auditreceipt",
    ):
        return "iam"
    if table == "clients_opportunity":
        return "commercial"
    if table in (
        "clients_party",
        "clients_physicalperson",
        "clients_legalentity",
        "clients_crmprofile",
        "clients_externalidentity",
        "clients_financialaccount",
        "clients_prospect",
        "clients_interaction",
    ):
        return "client_crm"
    if table in (
        "ingestion_importpolicy",
        "ingestion_importbatch",
        "ingestion_stagingrow",
        "ingestion_sourcesnapshot",
        "ingestion_runtimestate",
    ):
        return "integration"
    raise ValueError(f"Unclassified table: {table}")


def route_owner(path):
    if path in ("/api/health/", "/api/schema/"):
        return "platform_contract"
    if path == "/api/audit/":
        return "iam"  # Audit bounded module, not an independent service yet.
    if path.startswith(("/api/auth/", "/api/session/", "/api/organizations/")):
        return "iam"
    if path.startswith("/api/imports/"):
        return "integration"
    if path.startswith("/api/clients/") and "/opportunities/" in path:
        return "commercial"
    if path.startswith(("/api/clients/", "/api/prospects/")):
        return "client_crm"
    raise ValueError(f"Unclassified public route: {path}")
