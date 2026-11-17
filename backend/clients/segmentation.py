"""Descriptive CRM filters. Raw values are not an approved taxonomy."""
from django.db.models import Q, Count, F, Case, When, Value, CharField
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from .policies import client_queryset


def missing(field):
    return Q(**{field+'__isnull':True}) | Q(**{field+'__regex':r'^\s*$'})


class SegmentationFilters(serializers.Serializer):
    profession=serializers.CharField(max_length=120,required=False,trim_whitespace=False)
    sector=serializers.CharField(max_length=120,required=False,trim_whitespace=False)
    profession_missing=serializers.BooleanField(required=False)
    sector_missing=serializers.BooleanField(required=False)
    completeness_min=serializers.IntegerField(min_value=0,max_value=100,required=False)
    completeness_max=serializers.IntegerField(min_value=0,max_value=100,required=False)
    missing_field=serializers.ChoiceField(choices=['email','phone','profession','sector'],required=False)
    ordering=serializers.ChoiceField(choices=['id','display_name','-display_name','profession','-profession','sector','-sector'],required=False)

    def validate(self,data):
        if data.get('completeness_min',0)>data.get('completeness_max',100):
            raise serializers.ValidationError('Intervalle de complétude invalide.')
        from .quality import fields
        if not fields() and any(key in data for key in ['completeness_min','completeness_max']):
            raise serializers.ValidationError('Définition technique indisponible.')
        for field in ['profession','sector']:
            if field in data and field+'_missing' in data:
                raise serializers.ValidationError('Choisissez une valeur ou un filtre de présence, pas les deux.')
        return data


def filter_clients(items,params):
    # QueryDict is treated as an HTML checkbox form by DRF BooleanField;
    # absent presence filters must stay absent rather than becoming False.
    filters=SegmentationFilters(data=params.dict())
    filters.is_valid(raise_exception=True)
    data=filters.validated_data
    if any(key in data for key in ['completeness_min','completeness_max']):
        from .quality import annotate_quality
        items=annotate_quality(items)
        if 'completeness_min' in data: items=items.filter(technical_completeness__gte=data['completeness_min'])
        if 'completeness_max' in data: items=items.filter(technical_completeness__lte=data['completeness_max'])
    if 'missing_field' in data: items=items.filter(missing('crm_profile__'+data['missing_field']))
    for field in ['profession','sector']:
        column='crm_profile__'+field
        if field in data: items=items.filter(**{column:data[field]})
        if field+'_missing' in data:
            condition=missing(column)
            items=items.filter(condition if data[field+'_missing'] else ~condition)
    ordering=data.get('ordering','id')
    name=ordering.lstrip('-')
    if name in ['profession','sector']:
        column='crm_profile__'+name
        items=items.annotate(segment_order=Case(When(missing(column),then=Value(None)),default=F(column),output_field=CharField()))
        expression=F('segment_order')
        return items.order_by(expression.desc(nulls_last=True) if ordering.startswith('-') else expression.asc(nulls_last=True),'id')
    return items.order_by(ordering,'id') if name!='id' else items.order_by('id')


class SegmentValue(serializers.Serializer):
    value=serializers.CharField(trim_whitespace=False)
    count=serializers.IntegerField()


class SegmentOptions(serializers.Serializer):
    values=SegmentValue(many=True)
    missing_count=serializers.IntegerField()


class ClientFilterOptions(serializers.Serializer):
    profession=SegmentOptions()
    sector=SegmentOptions()
    quality=serializers.DictField()
    kind=serializers.ListField(child=serializers.DictField())
    truncated=serializers.DictField(child=serializers.BooleanField())


class ClientFilterOptionsView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','options']

    @extend_schema(responses={200:ClientFilterOptions})
    def get(self,request):
        from .views import require_client_permission
        require_client_permission(request.user,'clients.view')
        items=client_queryset(request.user,'clients.view').filter(prospect__isnull=True)
        data={}
        truncated={}
        for field in ['profession','sector']:
            column='crm_profile__'+field
            condition=missing(column)
            groups=items.exclude(condition).order_by(column).values(column).annotate(count=Count('pk'))
            rows=list(groups[:501])
            truncated[field]=len(rows)>500
            data[field]={'values':[{'value':row[column],'count':row['count']} for row in rows[:500]],
                         'missing_count':items.filter(condition).count()}
        from .quality import summary
        data['quality']=summary(items)
        data['kind']=list(items.order_by('kind').values('kind').annotate(count=Count('pk')))
        data['truncated']=truncated
        return Response(data)
