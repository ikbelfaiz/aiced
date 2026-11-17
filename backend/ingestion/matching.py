"""Suggestions only; publication always revalidates authorization and policy state."""
from .runtime import model
from .templates import TEMPLATES


def policy_match(batch, serializer):
    def blocked(code, reason):
        return {"status": code, "reason": reason, "policy": None}
    if batch.data_scope == "legacy":
        result = blocked("unclassified", "Lot historique non classifié : aucune suggestion automatique. La sélection historique reste manuelle et ne requalifie pas ce lot comme opérationnel.")
        rules = model("ImportPolicy").objects.filter(organization_id=batch.organization_id,
            template=batch.template, template_version=batch.template_version,
            date_format=batch.date_format, data_scope="legacy",
            approved_at__isnull=False, revoked_at__isnull=True).order_by("-created_at", "id")[:100]
        result["legacy_policies"] = serializer(rules, many=True).data
        return result
    if batch.template_version != TEMPLATES.get(batch.template, {}).get("version"):
        return blocked("schema", "Version du schéma non prise en charge.")
    rules = list(model("ImportPolicy").objects.filter(
        organization_id=batch.organization_id, template=batch.template,
        template_version=batch.template_version, date_format=batch.date_format,
        data_scope=batch.data_scope, approved_at__isnull=False, revoked_at__isnull=True,
    ).order_by("created_at", "id")[:2])
    if not rules:
        candidates = model("ImportPolicy").objects.filter(
            organization_id=batch.organization_id, data_scope=batch.data_scope)
        exact = candidates.filter(template=batch.template,
            template_version=batch.template_version, date_format=batch.date_format)
        diagnostics = [
            (exact.filter(approved_at__isnull=True, revoked_at__isnull=True), "pending", "Une règle compatible attend une approbation indépendante."),
            (exact.filter(revoked_at__isnull=False), "revoked", "La configuration compatible a été révoquée : elle ne peut plus publier de nouveaux lots."),
            (candidates.filter(template=batch.template, template_version=batch.template_version, approved_at__isnull=False, revoked_at__isnull=True).exclude(date_format=batch.date_format), "date_format", "Les règles approuvées utilisent un autre format de dates. Ne modifiez pas le format déclaré sans corriger et valider le fichier."),
            (candidates.filter(template=batch.template, approved_at__isnull=False, revoked_at__isnull=True).exclude(template_version=batch.template_version), "schema", "Les règles approuvées concernent une autre version du schéma."),
            (candidates.filter(approved_at__isnull=False, revoked_at__isnull=True).exclude(template=batch.template), "source_type", "Des règles existent pour d'autres types de source, mais aucune configuration compatible n'est approuvée pour ce type."),
        ]
        for query, code, reason in diagnostics:
            if query.exists():
                result = blocked("missing", reason)
                result["detail_code"] = code
                return result
        return blocked("missing", "Aucune règle approuvée active pour ce type de source, schéma, format de dates et usage. Une approbation indépendante est requise ; aucune règle n’est créée automatiquement.")
    if len(rules) != 1:
        return blocked("ambiguous", "Plusieurs règles correspondent : résoudre le conflit explicitement avant publication.")
    rule = rules[0]
    # No source identifiers are inferred. Validate only the explicitly approved column.
    from django.db.models import CharField, Count, F, Func, Value
    rows = batch.rows.filter(errors=[])
    if not rows.exists():
        return blocked("invalid_rows", "Aucune ligne valide pour la publication.")
    # Positional column names are JSON object keys "2", not JSON array offsets.
    keys = rows.annotate(candidate=Func(F("cells"), Value(str(rule.key_column)), function="jsonb_extract_path_text", output_field=CharField()))
    # Parser already rejects numeric/whitespace candidate identifiers. Null keys and
    # duplicate approved keys must still block the suggestion (bounded SQL aggregates).
    if keys.filter(candidate__isnull=True).exists() or keys.filter(candidate="").exists() or keys.values("candidate").annotate(n=Count("id")).filter(n__gt=1).exists():
        result = blocked("invalid_key", "La colonne clé approuvée contient des valeurs manquantes ou dupliquées. Corrigez le fichier ; aucune autre clé n’est choisie automatiquement.")
        result["configuration"] = serializer(rule).data
        return result
    return {"status": "matched", "reason": "Règle approuvée réutilisable suggérée après validation du format. La revue indépendante de chaque lot reste obligatoire.", "policy": serializer(rule).data}
