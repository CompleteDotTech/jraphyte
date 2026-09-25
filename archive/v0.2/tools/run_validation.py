#!/usr/bin/env python3
"""Run and record local, offline package validation; no model/backend calls."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.metadata
import io
import json
import platform
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_package import load_json, validate_bundle

class RecordedResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.records=[]
    def addSuccess(self,test):
        super().addSuccess(test); self.records.append({'test':test.id(),'status':'PASS'})
    def addFailure(self,test,err):
        super().addFailure(test,err); self.records.append({'test':test.id(),'status':'FAIL'})
    def addError(self,test,err):
        super().addError(test,err); self.records.append({'test':test.id(),'status':'ERROR'})

def main():
    bundle_result=validate_bundle(load_json(ROOT/'examples/bundle.json'))
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=RecordedResult).run(suite)
    report={'created_at':datetime.now(timezone.utc).isoformat(),
            'status':'PASS' if result.wasSuccessful() else 'FAIL',
            'python_version':platform.python_version(),'jsonschema_version':importlib.metadata.version('jsonschema'),
            'bundle_validation':bundle_result,'tests_run':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'tests':result.records,
            'claims_not_established':['Jev semantic accuracy','empirical calibration','production authorization',
                                     'existing GraphStore regression compatibility','backend transaction safety',
                                     'Mermaid render correctness','end-to-end graph synthesis performance'],
            'model_calls':0,'database_commits':0}
    (ROOT/'VALIDATION_REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'VALIDATION_LOG.txt').write_text(stream.getvalue())
    print(json.dumps({k:report[k] for k in ['status','tests_run','failures','errors','model_calls','database_commits']},indent=2))
    if not result.wasSuccessful(): raise SystemExit(1)

if __name__=='__main__':main()
