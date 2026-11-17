"""S17 disposable-only fixtures and real signed gateway reporting checks."""
import json,os,sys,time
from pathlib import Path
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser
cfg=json.loads(Path('/private/config.json').read_text());admin=cfg['admin']
assert admin['POSTGRES_DB']=='aiced_s7_disposable' and admin['POSTGRES_HOST']=='db'
def db():return psycopg.connect(host='db',dbname=admin['POSTGRES_DB'],user=admin['POSTGRES_USER'],password=admin['POSTGRES_PASSWORD'],autocommit=True)
with db() as c:
    assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0]=='aiced-s7-synthetic-only'
os.environ.update(cfg['iam'],DJANGO_SETTINGS_MODULE='iam_service.settings')
import django
django.setup()
from identity.models import User,Membership,Role,RoleAssignment,Capability
from django.db import transaction
with transaction.atomic():
    org=Membership.objects.get(user__username='synthetic.reader.a').organization
    user,created=User.objects.get_or_create(username='synthetic.s17.empty')
    if created:
        user.set_password(admin['AICED_SEED_PASSWORD']);user.save()
    assert user.is_active and not user.is_superuser and not user.is_staff
    member,_=Membership.objects.get_or_create(user=user,organization=org)
    role,_=Role.objects.get_or_create(code='s17-synthetic-empty',defaults={'name':'S17 SYNTHETIC empty scope'})
    role.permissions.set(Capability.objects.filter(code__in=['clients.view','interactions.view','prospects.view','opportunities.view']))
    assignment,_=RoleAssignment.objects.get_or_create(membership=member,role=role,defaults={'scope':'assigned'})
    assert assignment.is_active and assignment.scope=='assigned'
    disjoint,created=User.objects.get_or_create(username='synthetic.s17.disjoint')
    if created:
        disjoint.set_password(admin['AICED_SEED_PASSWORD']);disjoint.save()
    assert disjoint.is_active and not disjoint.is_superuser and not disjoint.is_staff
    other_org=Membership.objects.get(user__username='synthetic.reader.b').organization
    assert org.pk!=other_org.pk
    for scope_org,code,caps,scope in [
        (org,'s17-synthetic-client-only',['clients.view'],'assigned'),
        (other_org,'s17-synthetic-disjoint-activity',['interactions.view','prospects.view'],'organization'),
    ]:
        membership,_=Membership.objects.get_or_create(user=disjoint,organization=scope_org)
        scoped_role,_=Role.objects.get_or_create(code=code,defaults={'name':'S17 SYNTHETIC disjoint scope'})
        scoped_role.permissions.set(Capability.objects.filter(code__in=caps))
        grant,_=RoleAssignment.objects.get_or_create(membership=membership,role=scoped_role,defaults={'scope':scope})
        assert grant.is_active and grant.scope==scope

base='http://gateway:8080';browsers={}
for name in ['reader.a','operator.a','it.a','s17.empty','s17.disjoint']:
    b=Browser(base);b.login('synthetic.'+name,admin['AICED_SEED_PASSWORD']);browsers[name]=b
url='/api/clients/managerial-report/?date_from=2024-06-19&date_to=2024-06-19'
checks=[];measurements=[]
def report(b):
    tick=time.perf_counter();status,data,headers=b.request(url)
    measurements.append({'status':status,'seconds':time.perf_counter()-tick,'request_id':headers.get('X-Request-ID')})
    assert status==200,(status,data)
    return data
for name in ['reader.a','operator.a']:
    b=browsers[name];data=report(b)
    assert data['portfolio']['quality']==b.request('/api/clients/filter-options/')[1]['quality']
    assert data['portfolio']['quality']['total']==b.request('/api/clients/?page_size=1')[1]['count']
    assert sum(data['portfolio']['by_kind'].values())==data['portfolio']['quality']['total']
    if name=='operator.a':
        activity=b.request('/api/clients/activity-report/?date_from=2024-06-19&date_to=2024-06-19')[1]
        assert all(data[k]==activity[k] for k in ['interactions','appointments','followups'])
checks.append('Reader assigned / operator organization scopes equal existing authorized list, quality and activity APIs before aggregation')
empty=browsers['s17.empty'];data=report(empty)
assert data['portfolio']['quality']['total']==0 and data['portfolio']['quality']['complete']==0
assert data['interactions']['total']==data['appointments']['total']==0 and sum(data['followups'].values())==0
assert empty.request('/api/opportunities/?page_size=1')[1]['count']==0
assert empty.request('/api/campaigns/?page_size=1')[1]['count']==0
assert browsers['it.a'].request(url)[0]==403 and Browser(base).request(url)[0]==403
checks.append('Real empty authorized user has zero CRM/activity/opportunity/draft counts; IT/anonymous receive no metrics')
data=report(browsers['s17.disjoint'])
assert data['portfolio']['quality']['total']==0
assert all(data[key] is None for key in ['interactions','appointments','followups'])
checks.append('Disjoint client/activity organization grants preserve authorized portfolio access without enabling unsupported activity metrics')
def invariants():
    with db() as c:return [c.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ['public.clients_externalidentity','public.clients_financialaccount','aiced_integration.ingestion_sourcesnapshot','public.audit_auditevent','public.audit_auditoutbox','aiced_commercial.commercial_store_journal','aiced_commercial.commercial_store_outbox','aiced_integration.integration_store_journal','aiced_integration.integration_store_outbox']]
before=invariants();report(browsers['operator.a']);assert invariants()==before
checks.append('Successful reporting writes no authoritative identities/accounts/snapshots or business audit/outbox records')
for key in [4711239301896721,591445740000006]:
    with db() as c:
        with c.transaction():
            c.execute('SELECT pg_advisory_xact_lock(%s)',[key])
            status,error,_=browsers['operator.a'].request(url)
            assert status==503 and 'portfolio' not in error and 'interactions' not in error
checks.append('Both live exclusive IAM/Client barriers deny metrics without partial response')
try:
    with db() as c:
        with c.transaction():
            c.execute('SELECT pg_advisory_xact_lock(%s)',[4711239301896721])
            c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment.pk])
    for path in [url,'/api/opportunities/?page_size=1','/api/campaigns/?page_size=1']:
        status,error,_=empty.request(path)
        assert status==403 and not any(k in error for k in ['portfolio','count','results','interactions'])
finally:
    with db() as c:
        with c.transaction():
            c.execute('SELECT pg_advisory_xact_lock(%s)',[4711239301896721])
            c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=%s',[assignment.pk])
assert report(empty)['portfolio']['quality']['total']==0
checks.append('Actual IAM grant revocation denies same-session Client/Commercial statistics, then recovers after restoration')
for query in ['date_from=bad','date_from=2024-06-20&date_to=2024-06-19','date_from=2024-01-01&date_to=2024-06-19','kind=invalid']:
    assert browsers['operator.a'].request('/api/clients/managerial-report/?'+query)[0]==400
checks.append('Gateway rejects invalid or oversized periods and unknown activity type')
Path('/private/managerial-report.json').write_text(json.dumps({'status':'passed','checks':checks,'measurements':measurements,'synthetic_empty_user':'synthetic.s17.empty'},indent=2))
print('PASS:',len(checks),'S17 real gateway reporting/security groups; synthetic empty browser fixture prepared')
