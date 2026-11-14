"""Stable public opportunity input, independent of Client and IAM models."""

from rest_framework import serializers
from core.serializers import StrictSerializer


class OpportunityInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1, required=False)
    title = serializers.CharField(max_length=160)
    notes = serializers.CharField(max_length=5000, allow_blank=True, default="")
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=3, min_value=0, allow_null=True, default=None
    )
    currency = serializers.ChoiceField(choices=["TND"], default="TND")
    status = serializers.ChoiceField(choices=["open", "won", "lost"], default="open")
    due_date = serializers.DateField(allow_null=True, default=None)
