"""Repeat only the backup gate after completed S7 outage/session probes."""
import json
import compose_recovery as recovery

path=recovery.PRIVATE/'recovery-report.json'
prior=json.loads(path.read_text())
assert len(prior['checks'])==6, 'Run the full recovery suite first'
recovery.report=prior
recovery.report['status']='running'
recovery.report.pop('error',None)
try:
    recovery.backup()
    recovery.report['status']='passed'
except Exception as exc:
    recovery.report.update(status='failed',error=str(exc))
    raise
finally:
    recovery.command('start','db','iam','integration','client','commercial','gateway')
    path.write_text(json.dumps(recovery.report,indent=2))
