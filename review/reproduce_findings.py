#!/usr/bin/env python3
"""Compatibility note: v0.3 adds a claims manifest entry; probes are unchanged.

Non-destructive, offline probes for TRACE-GC 0.2-design contracts.

Usage:
  python reproduce_findings.py /path/to/trace_gc_revision --output findings.json

These probes create synthetic fixtures, not real inference receipts. Hashes are
recomputed to distinguish a broken invariant from simple stale-hash detection.
No network, model, database, or accepted-graph writes are performed. An accepted
probe demonstrates a contract-validation gap, NOT a production-write exploit.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Callable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    if not (root / 'tools' / 'validate_package.py').is_file():
        parser.error('package must contain tools/validate_package.py')
    sys.path.insert(0, str(root / 'tools'))
    from validate_package import ContractError, RECORD_TYPES, digest, load_json, validate_bundle
    template = load_json(root / 'examples' / 'bundle.json')

    def refresh(b: dict[str, Any]) -> None:
        cs = {c['candidate_id']: c for c in b['candidates']}
        for p in b['packs']:
            p['state_hash'] = digest(p['state'])
            p['request_hash'] = digest({'model': p['model_version'], 'state': p['state'], 'questions': p['questions']})
            qs = {q['question_id']: q for q in p['questions']}
            for d in b['decisions']:
                if d['pack_id'] == p['pack_id'] and d['question_id'] in qs:
                    d.update(candidate_hash=digest(cs[d['candidate_id']]), question_hash=digest(qs[d['question_id']]),
                             state_hash=p['state_hash'], request_hash=p['request_hash'])
        names = {'claims':'claim_refs', 'evidence':'evidence_refs', 'candidates':'candidate_refs', 'packs':'pack_refs',
                 'decisions':'decision_refs', 'resolutions':'resolution_refs', 'plans':'mutation_plan_refs', 'ledger':'ledger_event_refs'}
        records = {}
        for coll, (_, key) in RECORD_TYPES.items():
            records.update({x[key]: x for x in b[coll]})
            b['graph'][names[coll]] = [x[key] for x in b[coll]]
        previous = None
        for e in b['ledger']:
            e['previous_event_hash'] = previous
            e['payload_hash'] = digest([records[x] for x in e['payload_refs']])
            e['event_hash'] = digest({k:v for k,v in e.items() if k != 'event_hash'})
            previous = e['event_hash']

    probes: list[tuple[str, str, str, Callable[[dict[str, Any]], None]]] = []
    def probe(id_: str, title: str, location: str):
        def register(fn):
            probes.append((id_, title, location, fn))
            return fn
        return register

    @probe('P01', 'Pack state can be completely empty despite complete closure', 'tools/validate_package.py:158-194; schemas/question-pack.schema.json:state')
    def empty_state(b):
        b['packs'][0]['state'] = {}

    @probe('P02', 'Rendered evidence can differ from the verified quoted span', 'tools/validate_package.py:125-133,158-194')
    def forged_state_span(b):
        b['packs'][0]['state']['evidence'][0]['text'] = 'Mira never joined Northwind Labs.'

    @probe('P03', 'Rendered claim can change without changing the candidate assertion', 'tools/validate_package.py:178-194,207-212')
    def unrelated_claim(b):
        b['packs'][0]['state']['claim'] = 'A completely unrelated company acquired a factory in 2030.'

    @probe('P04', 'Declared closure omits a transitive candidate prerequisite', 'tools/validate_package.py:167-171')
    def missing_transitive_dependency(b):
        original = b['candidates'][0]
        middle, last = deepcopy(original), deepcopy(original)
        middle.update(candidate_id='candidate-middle', evidence_refs=[], prerequisite_candidate_refs=['candidate-last'])
        last.update(candidate_id='candidate-last', evidence_refs=[], prerequisite_candidate_refs=[])
        original['prerequisite_candidate_refs'] = ['candidate-middle']
        b['candidates'].extend([middle,last])
        b['packs'][0]['closure_requirement_refs'].append('candidate-middle')
        for e in b['ledger']:
            if original['candidate_id'] in e['payload_refs']:
                e['payload_refs'].extend(['candidate-middle', 'candidate-last'])
                break

    @probe('P05', 'Question names a dependency that does not exist', 'tools/validate_package.py:176-184')
    def dangling_question(b):
        b['packs'][0]['questions'][0]['depends_on_question_ids'] = ['question-does-not-exist']

    @probe('P06', 'A decision can list itself as a parent', 'tools/validate_package.py:214')
    def cyclic_decision_parent(b):
        b['decisions'][0]['parent_decision_refs'] = [b['decisions'][0]['decision_id']]

    @probe('P07', 'Cross-pack prior-decision dependencies can form a cycle', 'tools/validate_package.py:181-184,214')
    def cyclic_packs(b):
        p1=b['packs'][0]; p2=deepcopy(p1)
        p2['pack_id']='pack-second'; p2['closure_id']='closure-second'
        d1=b['decisions'][0]; d2=deepcopy(d1)
        d2['decision_id']='decision-second'; d2['pack_id']='pack-second'
        p1['questions'][0]['prior_decision_refs']=['decision-second']
        p2['questions'][0]['prior_decision_refs']=[d1['decision_id']]
        b['packs'].append(p2); b['decisions'].append(d2)
        for e in b['ledger']:
            if p1['pack_id'] in e['payload_refs']: e['payload_refs'].append('pack-second')
            if d1['decision_id'] in e['payload_refs']: e['payload_refs'].append('decision-second')

    @probe('P08', 'A semantic support decision can omit every evidence reference', 'tools/validate_package.py:214-215')
    def empty_decision_evidence(b):
        b['decisions'][0]['evidence_refs']=[]

    @probe('P09', 'Withdrawn support escapes the active-source check when omitted from pack evidence_refs', 'tools/validate_package.py:167-175,214-215,268-277')
    def withdrawn_support(b):
        b['sources'][0]['active']=False
        b['packs'][0]['evidence_refs']=[]
        for d in b['decisions']: d['evidence_refs']=[]

    @probe('P10', 'Identity operation can target an ordinary document-support candidate', 'tools/validate_package.py:268-274; schemas/mutation-plan.schema.json:operations')
    def wrong_operation_kind(b):
        b['plans'][0]['operations'][0].update(operation='ADD_IDENTITY_ASSERTION', risk_class='R4')

    @probe('P11', 'Two operations can share an operation_id in one plan', 'tools/validate_package.py:268-277')
    def duplicate_operation_id(b):
        b['plans'][0]['operations'].append(deepcopy(b['plans'][0]['operations'][0]))

    @probe('P12', 'Decision supersedes points to a nonexistent decision', 'tools/validate_package.py:202-245; schemas/decision.schema.json:supersedes')
    def dangling_supersession(b):
        b['decisions'][0]['supersedes']='decision-does-not-exist'

    @probe('P13', 'Resolution alternative candidate reference does not exist', 'tools/validate_package.py:247-256')
    def dangling_alternative(b):
        b['resolutions'][0]['alternative_candidate_refs']=['candidate-does-not-exist']

    @probe('P14', 'All ledger events can be removed while retaining every substantive record', 'tools/validate_package.py:279-291')
    def no_ledger(b):
        b['ledger']=[]

    @probe('P15', 'Synthetic ledger event can claim another run and LIVE mode', 'tools/validate_package.py:279-287')
    def ledger_wrong_run_mode(b):
        b['ledger'][0].update(run_id='unrelated-run', execution_mode='LIVE')

    @probe('P16', 'Score response legend descriptions can disagree with the question rubric', 'tools/validate_package.py:241-243')
    def wrong_score_legend(b):
        b['decisions'][2]['raw_answer']['legend']['0']='Directly usable evidence (reversed rubric).'

    @probe('P17', 'Resolution risk can be lower than its planned ordinary assertion operation', 'tools/validate_package.py:247-277')
    def inconsistent_risk(b):
        b['resolutions'][0]['risk_class']='R0'

    @probe('P18', 'A plan can be DRY_RUN_VALIDATED while a required implemented constraint reports FAIL', 'tools/validate_package.py:260-277')
    def failed_but_validated(b):
        b['plans'][0]['status']='DRY_RUN_VALIDATED'
        b['plans'][0]['constraint_checks'][0]['result']='FAIL'

    results=[]
    for id_, title, location, mutate in probes:
        b=deepcopy(template)
        try:
            mutate(b); refresh(b)
            result=validate_bundle(b)
            outcome='ACCEPTED_BY_VALIDATOR'
            detail=result['status']
        except ContractError as e:
            outcome='REJECTED_BY_VALIDATOR'; detail=str(e)
        except Exception as e:
            outcome='HARNESS_OR_UNHANDLED_ERROR'; detail=f'{type(e).__name__}: {e}'
        results.append(dict(id=id_,finding=title,location=location,outcome=outcome,detail=detail))
        print(f'{id_}: {outcome}: {title}')
    report={'scope':'Additional offline synthetic probes; hashes intentionally refreshed; no live inference or graph writes.',
            'package_revision':'0.3.0-hardened-legacy-fixture','baseline':validate_bundle(deepcopy(template)),
            'probe_count':len(results),'accepted_probe_count':sum(x['outcome']=='ACCEPTED_BY_VALIDATOR' for x in results),
            'warning':'An accepted probe is not evidence of a deployed exploit. Some findings are draft/lifecycle or future-integration contract gaps.',
            'results':results}
    if args.output:
        args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    main()
