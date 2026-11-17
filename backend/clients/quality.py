"""Provisional technical presence checks, never KYC or a business score."""
import os
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Case, When, Value, IntegerField, Count, Q
from django.db.models.functions import Cast, Floor, Lower, Trim
from django.db.models import FloatField
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

LABELS={'email':'Email CRM','phone':'Téléphone CRM','profession':'Profession CRM','sector':'Secteur CRM'}


def fields():
    selected=os.environ.get('AICED_PROFILE_COMPLETENESS_FIELDS','email,phone,profession,sector')
    result=tuple(v.strip() for v in selected.split(',') if v.strip())
    if len(set(result))!=len(result) or set(result)-set(LABELS):
        raise ImproperlyConfigured('AICED_PROFILE_COMPLETENESS_FIELDS: champs CRM autorisés uniquement, sans doublon.')
    return result


def annotate_quality(items):
    from .segmentation import missing
    selected=fields()
    present=Value(0,output_field=IntegerField())
    for field in selected:
        present=present+Case(When(missing('crm_profile__'+field),then=Value(0)),default=Value(1),output_field=IntegerField())
    return items.annotate(technical_completeness=Floor(Cast(present,FloatField())*100/len(selected),output_field=IntegerField()) if selected else Value(None,output_field=IntegerField()))


def definition():
    selected=fields()
    return {'available':bool(selected),'provisional':True,'fields':[{'key':f,'label':LABELS[f]} for f in selected],
            'definition':'Présence technique CRM, poids égaux, pourcentage arrondi vers le bas ; ni KYC ni conformité. Une valeur blanche est absente. La validité métier et la source Carthago ne sont pas évaluées.'}


def summary(items):
    from .segmentation import missing
    selected=fields()
    checks={f:Count('pk',filter=missing('crm_profile__'+f)) for f in selected}
    result=annotate_quality(items).aggregate(total=Count('pk'),complete=Count('pk',filter=Q(technical_completeness=100)),**checks)
    formatting={}
    for f in ['profession','sector']:
        column='crm_profile__'+f
        groups=items.exclude(missing(column)).annotate(label_comparison=Lower(Trim(column))).values('label_comparison').annotate(variants=Count(column,distinct=True)).filter(variants__gt=1)
        formatting[f]={'variant_groups':groups.count(),
                       'edge_whitespace_count':items.exclude(missing(column)).filter(**{column+'__regex':r'^\s|\s$'}).count()}
    return dict(definition(),formatting=formatting,total=result['total'],complete=result['complete'] if selected else None,
                incomplete=result['total']-result['complete'] if selected else None,
                missing_counts={f:result[f] for f in selected})


class QualityField(serializers.Serializer):
    key=serializers.CharField()
    label=serializers.CharField()


class ProfileQuality(serializers.Serializer):
    available=serializers.BooleanField()
    provisional=serializers.BooleanField()
    fields=QualityField(many=True)
    definition=serializers.CharField()
    percentage=serializers.IntegerField(allow_null=True)
    missing_fields=QualityField(many=True)
    ownership=serializers.DictField(child=serializers.CharField())


class ClientQualityView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','options']

    @extend_schema(responses={200:ProfileQuality})
    def get(self,request,party_id):
        from .views import require_client_permission
        from .policies import client_queryset
        from .segmentation import missing
        require_client_permission(request.user,'clients.view')
        flags={f+'_absent':Case(When(missing('crm_profile__'+f),then=Value(1)),default=Value(0),output_field=IntegerField()) for f in fields()}
        item=get_object_or_404(annotate_quality(client_queryset(request.user,'clients.view')).annotate(**flags),pk=party_id)
        absent=[{'key':f,'label':LABELS[f]} for f in fields() if getattr(item,f+'_absent')]
        return Response(dict(definition(),percentage=item.technical_completeness,missing_fields=absent,
            ownership={'crm':'AICED — modifiable seulement avec habilitation CRM',
                       'source':'Carthago — lecture seule ; mapping non validé, qualité source non calculable'}))
