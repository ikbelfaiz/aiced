"""Summarize sanitized S16.1 request spans; raw evidence stays excluded."""
import json
from pathlib import Path
import statistics
import re
import sys

dest=Path(sys.argv[1])
events={}
for service in ['commercial','client','iam']:
    rows=[]
    for line in (dest/(service+'.log')).read_text(encoding='utf-8',errors='replace').splitlines():
        offset=line.find('{')
        if offset<0:continue
        try:data=json.loads(line[offset:])
        except ValueError:continue
        if data.get('logger')=='aiced.metrics':rows.append(data)
    events[service]=rows
requests=[]
for row in events['commercial']:
    if row.get('event')!='request' or row.get('path')!='/api/opportunities/':continue
    ident=row['request_id']
    hops=[r for r in events['commercial'] if r.get('event')=='internal_http' and r['request_id']==ident]
    children={r.get('peer_request_id') for r in hops if r.get('peer')=='client'}
    nested=[r for r in events['client'] if r.get('event')=='internal_http' and r['request_id'] in children]
    client_requests=[r for r in events['client'] if r.get('event')=='request' and r['request_id'] in children]
    iam_ids={r.get('peer_request_id') for r in [*hops,*nested] if r.get('peer')=='iam'}
    iam_requests=[r for r in events['iam'] if r.get('event')=='request' and r['request_id'] in iam_ids]
    requests.append(dict(row, commercial_http=len(hops),client_iam_http=len(nested),
        outbound_seconds=round(sum(r['seconds'] for r in hops),6),
        max_hop_seconds=max([r['seconds'] for r in hops],default=0),
        client_sql_count=sum(r['sql_count'] for r in client_requests),
        client_sql_seconds=round(sum(r['sql_seconds'] for r in client_requests),6),
        iam_sql_count=sum(r['sql_count'] for r in iam_requests),
        iam_sql_seconds=round(sum(r['sql_seconds'] for r in iam_requests),6),
        scans=[r for r in events['commercial'] if r.get('event')=='pipeline_scan' and r['request_id']==ident]))
summary={'requests':requests,'statuses':{str(s):sum(r['status']==s for r in requests) for s in {r['status'] for r in requests}}}
resources={}
for line in (dest/'stats.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
    line=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',line).strip()
    try:row=json.loads(line)
    except ValueError:continue
    resource=resources.setdefault(row['Name'],{'cpu_percent_max':0,'memory_mib_max':0,'pids_max':0})
    resource['cpu_percent_max']=max(resource['cpu_percent_max'],float(row['CPUPerc'].rstrip('%')))
    value=re.match(r'([0-9.]+)([A-Za-z]+)',row['MemUsage'])
    if value:
        mib=float(value[1])*{'KiB':1/1024,'MiB':1,'GiB':1024,'B':1/1048576}.get(value[2],0)
        resource['memory_mib_max']=max(resource['memory_mib_max'],round(mib,3))
    resource['pids_max']=max(resource['pids_max'],int(row['PIDs']))
summary['resources']=resources
ok=[r['seconds'] for r in requests if r['status']==200]
if ok:summary.update(success_seconds_min=min(ok),success_seconds_median=statistics.median(ok),success_seconds_max=max(ok))
(dest/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='requests'},indent=2))
