"""Container outages/restarts and backup/restore; targets only project aiced-s7."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
from compose_context import PRIVATE, COMPOSE, URL
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
report={'status':'running','checks':[]}
compose=COMPOSE
def command(*args):
    return subprocess.run([*compose,*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout
def sql(query,db='aiced_s7_disposable'):
    assert db in ['aiced_s7_disposable','aiced_s7_restore']
    return command('exec','-T','db','psql','-U','s7_admin','-d',db,'-v','ON_ERROR_STOP=1','-Atc',query).strip()
def passed(name):
    report['checks'].append(name)
    (PRIVATE/'recovery-report.json').write_text(json.dumps(report,indent=2))
    print(name,flush=True)
def ready(service):
    until=time.monotonic()+90
    while time.monotonic()<until:
        rows=[json.loads(line) for line in command('ps','--format','json',service).splitlines() if line]
        if rows and rows[0].get('Health')=='healthy': return
        time.sleep(1)
    raise AssertionError(service+' did not recover')
def total():
    return sql('SELECT count(*) FROM aiced_commercial.clients_opportunity')
def backup():
    # Quiesce writers so complete digest comparison uses one stable state.
    command('stop','gateway','commercial','client','integration','iam')
    # Fresh custom-format backup and a different database on this disposable cluster.
    command('exec','-T','db','pg_dump','-U','s7_admin','-d','aiced_s7_disposable','-Fc','-f','/tmp/aiced-s7.dump')
    exists=sql("SELECT 1 FROM pg_database WHERE datname='aiced_s7_restore'")
    if exists: raise AssertionError('Restore target already exists; refusing overwrite')
    command('exec','-T','db','createdb','-U','s7_admin','aiced_s7_restore')
    command('exec','-T','db','pg_restore','-U','s7_admin','-d','aiced_s7_restore','--exit-on-error','/tmp/aiced-s7.dump')
    # pg_dump without --create leaves target-database ACLs to the operator.
    grants=sql("""SELECT format('GRANT %s ON DATABASE aiced_s7_restore TO %s%s',a.privilege_type,CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(a.grantee)) END,CASE WHEN a.is_grantable THEN ' WITH GRANT OPTION' ELSE '' END) FROM pg_database d CROSS JOIN LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a WHERE d.datname=current_database()""").splitlines()
    sql('REVOKE ALL ON DATABASE aiced_s7_restore FROM PUBLIC')
    for grant in grants: sql(grant)
    db_acl="SELECT a.grantee,a.grantor,a.privilege_type,a.is_grantable FROM pg_database d CROSS JOIN LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a WHERE d.datname=current_database() ORDER BY 1,2,3,4"
    assert sql(db_acl)==sql(db_acl,'aiced_s7_restore')
    comparison="""SELECT format('SELECT %L AS table_name,count(*) AS rows,md5(coalesce(string_agg(to_jsonb(t)::text,chr(10) ORDER BY to_jsonb(t)::text),%L)) AS digest FROM %I.%I t',schemaname||'.'||tablename,'',schemaname,tablename) FROM pg_tables WHERE schemaname IN ('public','aiced_iam','aiced_commercial','aiced_integration') ORDER BY schemaname,tablename"""
    queries=sql(comparison).splitlines()
    for query in queries: assert sql(query)==sql(query,'aiced_s7_restore'),query
    # pg_restore may encode an explicit owner-only ACL as NULL (default ACL).
    # Compare effective grants, including grantor/options, rather than storage text.
    acl="""SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner),a.grantee,a.grantor,a.privilege_type,a.is_grantable FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault((CASE WHEN c.relkind='S' THEN 's' ELSE 'r' END)::"char",c.relowner))) a WHERE n.nspname IN ('public','aiced_iam','aiced_commercial','aiced_integration') AND c.relkind IN ('r','S') ORDER BY 1,2,4,5,6,7"""
    assert sql(acl)==sql(acl,'aiced_s7_restore')
    for acl_query in [
        "SELECT nspname,pg_get_userbyid(nspowner),a.grantee,a.grantor,a.privilege_type,a.is_grantable FROM pg_namespace CROSS JOIN LATERAL aclexplode(coalesce(nspacl,acldefault('n',nspowner))) a WHERE nspname IN ('public','aiced_iam','aiced_commercial','aiced_integration') ORDER BY 1,3,4,5,6",
        "SELECT n.nspname,c.relname,t.attname,t.attacl::text FROM pg_attribute t JOIN pg_class c ON c.oid=t.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE t.attacl IS NOT NULL AND n.nspname IN ('public','aiced_iam','aiced_commercial','aiced_integration') ORDER BY 1,2,3",
    ]:
        assert sql(acl_query)==sql(acl_query,'aiced_s7_restore')
    command('start','iam','integration','client','commercial','gateway')
    for service in ['iam','integration','client','commercial','gateway']: ready(service)
    passed('Fresh pg_dump restored to separate disposable database; all '+str(len(queries))+' table counts and complete row digests match')

b=Browser(URL)
def login(): b.login('synthetic.operator.a',cfg['admin']['AICED_SEED_PASSWORD'])
if __name__ == '__main__':
    try:
        login()
        parties=b.request('/api/clients/')[1]['results']
        party=parties[0]['id']
        base=f'/api/clients/{party}/opportunities/'
        code,item,_=b.request(base,{'title':'S7 persistence after restart'})
        assert code==201,(code,item)
        detail=base+item['id']+'/'
        for service,path in [('iam','/api/session/'),('client','/api/clients/'),
                             ('commercial',base),('integration','/api/imports/context/')]:
            before=total()
            command('stop',service)
            try:
                status,_,_=b.request(path)
                assert status in [502,503,504],(service,status)
                denied=b.request(base,{'title':'S7 denied during '+service})[0]
                # Integration is not a dependency of Commercial business operations.
                if service!='integration': assert denied in [502,503,504],(service,denied)
                if service!='integration': assert total()==before
                audit=Browser(b.base)
                if service!='iam':
                    audit.login('synthetic.manager.a',cfg['admin']['AICED_SEED_PASSWORD'])
                    if service in ['commercial','integration']:
                        assert audit.request('/api/audit/')[0] in [502,503,504]
            finally:
                command('start',service)
                ready(service)
            assert b.request('/api/session/')[0]==200
            assert b.request(detail)[0]==200
            passed(service+' outage fails safely; own container restart retains session and opportunity')
        command('stop','db')
        try:
            assert b.request('/api/session/')[0] in [500,502,503,504]
            assert b.request(base,{'title':'S7 DB unavailable'})[0] in [500,502,503,504]
        finally:
            command('start','db')
            ready('db')
        assert b.request(detail)[0]==200
        passed('PostgreSQL interruption rejects operations and recovers without restarting Django services')
        session=next(c.value for c in b.jar if c.name=='sessionid')
        assert session.isalnum()
        sql("UPDATE aiced_iam.django_session SET expire_date=now()-interval '1 second' WHERE session_key='"+session+"'")
        assert b.request('/api/session/')[0]==403
        assert b.request(base,{'title':'S7 expired session denied'})[0]==403
        login()
        session=next(c.value for c in b.jar if c.name=='sessionid')
        assert session.isalnum()
        sql("DELETE FROM aiced_iam.django_session WHERE session_key='"+session+"'")
        assert b.request(base)[0]==403
        login()
        assert b.request('/api/auth/logout/',{},'POST')[0]==204
        assert b.request('/api/session/')[0]==403
        passed('Server-side session expiry, deletion revocation and logout deny subsequent gateway access')
        backup()
        report['status']='passed'
    except Exception as exc:
        report.update(status='failed',error=str(exc))
        raise
    finally:
        command('start','db','iam','integration','client','commercial','gateway')
        (PRIVATE/'recovery-report.json').write_text(json.dumps(report,indent=2))
