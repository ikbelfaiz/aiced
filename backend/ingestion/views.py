import csv
from datetime import date
from io import StringIO
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers
from rest_framework.parsers import BaseParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError
from core.serializers import StrictSerializer
from core.parsers import PayloadTooLarge
from .runtime import adapter, model, record

ImportBatch, ImportPolicy = model("ImportBatch"), model("ImportPolicy")
DATE_FORMAT_CHOICES = ImportBatch._meta.get_field("date_format").choices
from .services import authorize, stage, publish_fixed
from .templates import TEMPLATES, FIXED_CONFIGURATIONS
from .parser import MAX_BYTES


class XLSXParser(BaseParser):
    media_type = "application/octet-stream"

    def parse(self, stream, media_type=None, parser_context=None):
        content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise PayloadTooLarge("Fichier supérieur à 10 Mio.")
        return content


class BatchOutput(serializers.ModelSerializer):
    total = serializers.SerializerMethodField()
    rejected = serializers.SerializerMethodField()
    published_rows = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "template",
            "template_version",
            "digest",
            "source_as_of",
            "snapshot_kind",
            "date_format",
            "data_scope",
            "status",
            "created_at",
            "uploaded_by_id",
            "published_by_id",
            "published_at",
            "policy_id",
            "fixed_configuration_version",
            "total",
            "rejected",
            "published_rows",
        ]

    def get_total(self, obj) -> int:
        return obj.rows.count()

    def get_rejected(self, obj) -> int:
        return obj.rows.exclude(errors=[]).count()

    def get_published_rows(self, obj) -> int:
        return obj.rows.filter(sourcesnapshot__isnull=False).count()


class PolicyOutput(serializers.ModelSerializer):
    class Meta:
        model = ImportPolicy
        fields = [
            "id",
            "template",
            "key_column",
            "template_version",
            "data_scope",
            "date_format",
            "rationale",
            "created_by_id",
            "approved_by_id",
            "approved_at",
            "revoked_at",
            "created_at",
        ]


class PolicyInput(StrictSerializer):
    data_scope = serializers.ChoiceField(choices=["legacy", "synthetic", "operational"], default="legacy")
    template_version = serializers.IntegerField(min_value=1, required=False)
    template = serializers.ChoiceField(choices=list(TEMPLATES))
    key_column = serializers.IntegerField(min_value=1, max_value=41)
    rationale = serializers.CharField(min_length=20, max_length=1000)
    date_format = serializers.ChoiceField(choices=DATE_FORMAT_CHOICES, default="ISO")


class PublishInput(StrictSerializer):
    skip_rejected = serializers.BooleanField(default=False)


class ImportContextView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                "templates": TEMPLATES,
                "mode": "immutable_snapshots_only",
                "organizations": adapter().context(request.user),
            }
        )


class BatchListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: BatchOutput(many=True)})
    def get(self, request, organization_id):
        authorize(request.user, organization_id)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(
            ImportBatch.objects.filter(organization_id=organization_id), request
        )
        return paginator.get_paginated_response(BatchOutput(page, many=True).data)


class UploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [XLSXParser]

    @extend_schema(
        request={"application/octet-stream": {"type": "string", "format": "binary"}},
        responses={201: BatchOutput, 200: BatchOutput},
    )
    def post(self, request, organization_id):
        authorize(request.user, organization_id, "imports.upload")
        if set(request.query_params) - {
            "template",
            "source_as_of",
            "snapshot_kind",
            "date_format",
            "data_scope",
        }:
            raise ValidationError("Paramètre inconnu.")
        try:
            as_of = date.fromisoformat(request.query_params.get("source_as_of", ""))
        except ValueError:
            raise ValidationError("Date source ISO requise.")
        batch, created = stage(
            request.user,
            organization_id,
            request.query_params.get("template"),
            as_of,
            request.query_params.get("snapshot_kind", "partial"),
            request.data,
            request,
            date_format=request.query_params.get("date_format", "ISO"),
            data_scope=request.query_params.get("data_scope", "legacy"),
        )
        return Response(BatchOutput(batch).data, status=201 if created else 200)


class BatchView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, organization_id, batch_id):
        authorize(request.user, organization_id)
        batch = get_object_or_404(
            ImportBatch, pk=batch_id, organization_id=organization_id
        )
        rows = batch.rows.all()
        if request.query_params.get("rejected") == "1":
            rows = rows.exclude(errors=[])
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rows, request)
        response = paginator.get_paginated_response(
            [
                {
                    "id": row.pk,
                    "number": row.number,
                    "cells": row.cells,
                    "errors": row.errors,
                    "warnings": row.warnings,
                    "normalized_dates": row.normalized_dates,
                }
                for row in page
            ]
        )
        response.data["batch"] = BatchOutput(batch).data
        response.data["headers"] = TEMPLATES[batch.template]["headers"]
        configuration = FIXED_CONFIGURATIONS.get(batch.template)
        response.data["fixed_configuration"] = configuration
        from .matching import policy_match
        response.data["policy_match"] = policy_match(batch, PolicyOutput)
        if batch.data_scope == "legacy":
            compatible = ImportPolicy.objects.filter(
                organization_id=organization_id, template=batch.template,
                template_version=batch.template_version, date_format=batch.date_format,
                data_scope="legacy", approved_at__isnull=False, revoked_at__isnull=True,
            ).order_by("id")[:2]
            response.data["legacy_rule_unique"] = len(list(compatible)) == 1

        response.data["history"] = [
            {
                "action": event.action,
                "timestamp": event.occurred_at,
                "actor_id": event.actor_id,
                "context": event.context,
            }
            for event in adapter().history(organization_id, batch.pk)
        ]
        return response


def safe_csv(value):
    text = "" if value is None else str(value)
    return (
        "'" + text
        if text.startswith(("\t", "\r", "\n"))
        or text.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@"))
        else text
    )


class RejectionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: bytes})
    def get(self, request, organization_id, batch_id):
        authorize(request.user, organization_id)
        batch = get_object_or_404(
            ImportBatch, pk=batch_id, organization_id=organization_id
        )
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["Ligne", "Erreurs"]
            + [
                f'{i}: {label or "Sans libellé"}'
                for i, label in enumerate(TEMPLATES[batch.template]["headers"], 1)
            ]
        )
        for row in batch.rows.exclude(errors=[]).iterator():
            writer.writerow(
                [row.number, "; ".join(row.errors)]
                + [
                    safe_csv(row.cells.get(str(i)))
                    for i in range(1, len(TEMPLATES[batch.template]["headers"]) + 1)
                ]
            )

        record(
            "imports.rejections_downloaded",
            actor=request.user,
            organization_id=organization_id,
            target_id=batch.pk,
            request=request,
        )
        response = HttpResponse(
            "\ufeff" + out.getvalue(), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = 'attachment; filename="rejets.csv"'
        return response


class PoliciesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: PolicyOutput(many=True)})
    def get(self, request, organization_id):
        authorize(request.user, organization_id)
        rules = ImportPolicy.objects.filter(organization_id=organization_id)
        view = request.query_params.get("view", "all")
        if view not in ["all", "available", "approved", "pending", "history", "operational", "synthetic"]:
            raise ValidationError("Vue de règles inconnue.")
        if view in ["available", "approved", "pending"]:
            rules = rules.filter(revoked_at__isnull=True).exclude(data_scope="legacy")
            if view != "available":
                rules = rules.filter(approved_at__isnull=view == "pending")
        elif view == "history":
            from django.db.models import Q
            rules = rules.filter(Q(revoked_at__isnull=False) | Q(data_scope="legacy"))
        elif view in ["operational", "synthetic"]:
            rules = rules.filter(data_scope=view, approved_at__isnull=False, revoked_at__isnull=True)
        try:
            page = int(request.query_params.get("page", "1"))
            if not 1 <= page <= 10000:
                raise ValueError()
        except ValueError:
            raise ValidationError("Page invalide.")
        return Response(
            PolicyOutput(
                rules.order_by("-created_at", "id")[(page-1)*100:page*100],
                many=True,
            ).data
        )

class PolicyApproveView(APIView):
    permission_classes = [IsAuthenticated]
    revoke = False

    @extend_schema(exclude=True)
    def post(self, request, organization_id, policy_id):
        from rest_framework.exceptions import MethodNotAllowed
        raise MethodNotAllowed("POST")


class PolicyRevokeView(PolicyApproveView):
    revoke = True


class PublishView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PublishInput, responses={200: BatchOutput})
    def post(self, request, organization_id, batch_id):
        authorize(request.user, organization_id, "imports.approve")
        serializer = PublishInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            batch = publish_fixed(
                request.user,
                organization_id,
                batch_id,
                **serializer.validated_data,
                request=request,
            )
        except ValidationError:

            record(
                "imports.publication_rejected",
                actor=request.user,
                organization_id=organization_id,
                target_id=batch_id,
                result="denied",
                request=request,
            )
            raise
        return Response(BatchOutput(batch).data)
