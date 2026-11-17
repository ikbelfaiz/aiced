"""Reviewed additive contracts. The original frozen baseline remains immutable."""
ADDITIONAL_ROUTES = [{'path':'/api/interactions/', 'methods':['GET']}, {'path':'/api/prospects/follow-ups/', 'methods':['GET']}, {'path':'/api/clients/filter-options/', 'methods':['GET']}, {'path':'/api/opportunities/', 'methods':['GET']}, {'path':'/api/agenda/', 'methods':['GET','POST']}, {'path':'/api/agenda/context/', 'methods':['GET']}, {'path':'/api/agenda/<uuid:appointment_id>/', 'methods':['GET','PATCH']}]
ADDITIONAL_ROUTES += [{'path':'/api/campaigns/','methods':['GET','POST']},{'path':'/api/campaigns/context/','methods':['GET']},{'path':'/api/campaigns/<uuid:campaign_id>/','methods':['GET','PATCH']}]
ADDITIONAL_ROUTES += [{'path':'/api/clients/<uuid:party_id>/quality/','methods':['GET']}]
ADDITIONAL_ROUTES += [{'path':'/api/clients/activity-report/','methods':['GET']}]
ADDITIONAL_ROUTES += [{'path':'/api/clients/managerial-report/','methods':['GET']}]
ADDITIONAL_ROUTES += [{'path':'/api/clients/<uuid:party_id>/source-mapping-preview/','methods':['GET']}]


def assert_openapi_compatible(actual, baseline):
    """All pre-existing schema fields must be unchanged; only named additions allowed."""
    import copy
    candidate=copy.deepcopy(actual)
    def schema_path(path):
        import re
        return re.sub(r'<uuid:([^>]+)>',r'{\1}',path)
    assert set(candidate['paths'])-set(baseline['paths']) == {schema_path(route['path']) for route in ADDITIONAL_ROUTES}
    for route in ADDITIONAL_ROUTES: candidate['paths'].pop(schema_path(route['path']))
    # S10 allows only these optional query parameters on the frozen list operation.
    operation=candidate['paths']['/api/clients/']['get']
    additions={'profession','sector','profession_missing','sector_missing','ordering','completeness_min','completeness_max','missing_field'}
    parameters=operation.get('parameters',[])
    added=[p for p in parameters if p['name'] in additions]
    assert {p['name'] for p in added}==additions
    assert all(p['in']=='query' and not p.get('required',False) for p in added)
    operation['parameters']=[p for p in parameters if p['name'] not in additions]
    schemas=candidate.get('components',{}).get('schemas',{})
    original=baseline.get('components',{}).get('schemas',{})
    # Reusable publication rules: additive outputs and optional creation fields.
    scope_enums = set()
    for name, fields in {'BatchOutput': {'data_scope'}, 'PolicyOutput': {'data_scope','template_version'}, 'PolicyInput': {'data_scope','template_version'}}.items():
        for field in fields:
            assert field in schemas[name]['properties']
            if field == 'data_scope':
                definition = schemas[name]['properties'][field]
                references = [definition] if '$ref' in definition else definition.get('allOf', [])
                assert len(references) == 1
                reference = references[0]['$ref']
                assert reference.startswith('#/components/schemas/')
                scope_enums.add(reference.rsplit('/', 1)[1])
            if name == 'PolicyInput':
                assert field not in schemas[name].get('required', [])
            schemas[name]['properties'].pop(field)
        if 'required' in schemas[name]:
            schemas[name]['required'] = [f for f in schemas[name]['required'] if f not in fields]
    # Federation may suffix enum names with a hash. Follow only references from
    # the three explicitly reviewed new properties and verify their exact values.
    for name in scope_enums:
        if name not in original and name in schemas:
            assert schemas[name]['type'] == 'string'
            assert set(schemas[name]['enum']) == {'legacy', 'synthetic', 'operational'}
            schemas.pop(name)
    for name in ['ProfileQuality','QualityField','ActivityReport','ManagerialReport']:
        if name in schemas and name not in original: schemas.pop(name)
    for name in set(schemas)-set(original):
        assert name in {'HistoryItem','HistoryPage','FollowupPage','SegmentValue','SegmentOptions','ClientFilterOptions','PipelineItem','PipelinePage','AppointmentOutput','AgendaInput','PatchedAgendaInput','AgendaPage','AgendaContext','CampaignInput','PatchedCampaignInput','CampaignOutput','CampaignPage','CampaignContext','CampaignOrganization'}, 'Unreviewed schema addition: '+name
        schemas.pop(name)
    assert candidate==baseline, 'Existing OpenAPI contract changed'
