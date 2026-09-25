"""Compatibility fixes for the 0.2 fixture API. No graph-publication authority.

The v0.3 runtime is authoritative for authenticated receipts, multi-version
sources, policy replay and transactional publication. These extra checks keep
the original 42 fixture tests and all 18 design-review regressions useful.
"""
from collections import deque
from datetime import datetime
from trace_gc.references import topological_order

def validate_extended(bundle,indices,all_records,require,digest,text_digest):
    graph=bundle['graph'];sources={s['source_id']:s for s in bundle['sources']}
    for claim in bundle['claims']:
        require(claim['content_hash']==text_digest(claim['text']),'CLAIM_BINDING','claim content hash differs')
    for c in bundle['candidates']:
        require(c['claim_ref'] in indices['claims'],'MISSING_REFERENCE','candidate claim')
        require(c['claim_content_hash']==indices['claims'][c['claim_ref']]['content_hash'],'CLAIM_BINDING','claim bytes changed')
        if c['assertion']['predicate'] in {'supports','refutes'}:
            require(c['assertion']['object']==c['claim_ref'],'CLAIM_BINDING','support object must identify the bound claim')
    packs={p['pack_id']:p for p in bundle['packs']}
    decisions=indices['decisions']
    causal={d['decision_id']:set(d['parent_decision_refs']) for d in bundle['decisions']}
    pack_dependencies={ref:set() for ref in packs}
    all_questions={(p['run_id'],p['pack_id'],q['question_id']):q for p in bundle['packs'] for q in p['questions']}
    for d in bundle['decisions']:
        if d['supersedes'] is not None:
            require(d['supersedes'] in decisions,'MISSING_REFERENCE','superseded decision missing')
            require(d['supersedes']!=d['decision_id'],'DEPENDENCY_CYCLE','self supersession')
            earlier=decisions[d['supersedes']]
            require(earlier['candidate_id']==d['candidate_id'] and earlier['created_at']<=d['created_at'],'SUPERSESSION_ORDER','invalid supersession')
            causal[d['decision_id']].add(d['supersedes'])
        for ref in d['parent_decision_refs']:
            require(decisions[ref]['created_at']<=d['created_at'],'TEMPORAL_ORDER','parent decision is later')
        q=all_questions[(graph['run_id'],d['pack_id'],d['question_id'])]
        causal[d['decision_id']].update(q['prior_decision_refs'])
        for ref in q['prior_decision_refs']:
            pack_dependencies[d['pack_id']].add(decisions[ref]['pack_id'])
        if d['status']=='OK' and d['primitive']=='SCORE':
            expected={option['label']:option['description'] for option in q['criteria']}
            require(d['raw_answer']['legend']==expected,'RUBRIC_MISMATCH','returned Score level meanings changed')
        required=set(indices['candidates'][d['candidate_id']]['evidence_refs'])
        require(set(d['evidence_refs'])==required,'MISSING_EVIDENCE','decision must bind its task-required evidence')
    # Normalize the shared validator's structured exception into the legacy error class.
    try:
        topological_order(causal);topological_order(pack_dependencies)
    except ValueError as exc:require(False,'DEPENDENCY_CYCLE',str(exc))
    for p in bundle['packs']:
        for q in p['questions']:
            for dep in q['depends_on_question_ids']:
                targets=[key for key in all_questions if key[2]==dep or '/'.join(key)==dep]
                require(len(targets)==1,'MISSING_REFERENCE','question dependency missing or ambiguous; use run/pack/question')
                target=targets[0]
                require(target[1]!=p['pack_id'],'PACK_DEPENDENCY_VIOLATION','same-pack dependency')
                upstream=[decisions[ref] for ref in q['prior_decision_refs'] if decisions[ref]['pack_id']==target[1] and decisions[ref]['question_id']==target[2]]
                require(bool(upstream) and all(x['status']=='OK' for x in upstream),'PREREQUISITE_NOT_COMPLETED','required answer not completed')
        needed=set();todo=deque(p['candidate_refs']);candidate_ids=[];ev_ids=set();claim_ids=set()
        while todo:
            ref=todo.popleft()
            if ref in needed:continue
            needed.add(ref);candidate_ids.append(ref);c=indices['candidates'][ref]
            claim_ids.add(c['claim_ref']);needed.add(c['claim_ref'])
            ev_ids.update(c['evidence_refs']);needed.update(c['evidence_refs'])
            todo.extend(c['prerequisite_candidate_refs'])
        require(needed<=set(p['closure_requirement_refs']),'CLOSURE_INCOMPLETE','recursive closure omitted context')
        require(ev_ids==set(p['evidence_refs']),'MISSING_EVIDENCE','pack evidence differs from computed closure')
        for ref in ev_ids:
            e=indices['evidence'][ref]
            require(e['integrity_status']=='VERIFIED' and sources[e['source_id']]['active'],'STALE_EVIDENCE','required support unavailable')
        # Legacy single-root state shape is retained; stronger arbitrary-task state
        # compilation and field traces are implemented by trace_gc.compiler.
        require(len(p['candidate_refs'])==1,'LEGACY_PACK_SCOPE','migrate multi-root packs to runtime v0.3')
        root=indices['candidates'][p['candidate_refs'][0]]
        expected={'candidate_id':root['candidate_id'],'evidence':[{'evidence_id':ref,'text':indices['evidence'][ref]['quoted_span']} for ref in sorted(ev_ids)],
                  'claim':indices['claims'][root['claim_ref']]['text'],'source_notice':'Entire example is synthetic.'}
        # Required transitive candidate content is explicitly materialized.
        if len(candidate_ids)>1:
            expected['prerequisites']=[{'candidate_id':ref,'assertion':indices['candidates'][ref]['assertion'],
                                       'claim':indices['claims'][indices['candidates'][ref]['claim_ref']]['text']}
                                      for ref in sorted(candidate_ids) if ref!=root['candidate_id']]
        prior=sorted({ref for q in p['questions'] for ref in q['prior_decision_refs']})
        if prior:
            expected['prior_decisions']=[{'decision_id':ref,'raw_answer':decisions[ref]['raw_answer']} for ref in prior]
        require(p['state']==expected,'MATERIALIZATION_MISMATCH','model-visible state not derived from immutable records')
    for r in bundle['resolutions']:
        require(set(r['alternative_candidate_refs'])<=set(indices['candidates']),'MISSING_REFERENCE','resolution alternative missing')
        require(set(r['evidence_refs'])==set(indices['candidates'][r['candidate_id']]['evidence_refs']),'MISSING_EVIDENCE','resolution evidence projection')
    for p in bundle['plans']:
        ids=[op['operation_id'] for op in p['operations']]
        require(len(ids)==len(set(ids)),'DUPLICATE_OPERATION_ID','operation identity collision')
        if p['status']=='DRY_RUN_VALIDATED':
            require(bool(p['constraint_checks']) and all(x['capability']=='IMPLEMENTED' and x['result']=='PASS' for x in p['constraint_checks']),
                    'PREFLIGHT_FAILED','validation label contradicts required check results')
        for op in p['operations']:
            c=indices['candidates'][op['candidate_ref']];r=indices['resolutions'][op['resolution_ref']]
            require(op['risk_class']==r['risk_class'],'RISK_UNDERCLASSIFIED','operation and resolution risk differ')
            require(all(decisions[x]['candidate_id']==c['candidate_id'] for x in op['decision_refs']),'CANDIDATE_BINDING','operation decision belongs to another candidate')
            if op['operation']=='ADD_IDENTITY_ASSERTION':
                require(c['kind']=='IDENTITY' and c['assertion']['predicate']=='same_as','OPERATION_CANDIDATE_KIND','identity action requires an identity candidate')
                require(False,'LEGACY_COMPONENT_UNSUPPORTED','use runtime v0.3 component certificates for identity operations')
            elif op['operation']=='ADD_ASSERTION':
                require(c['kind']=='ASSERTION' and c['assertion']['predicate']!='same_as','OPERATION_CANDIDATE_KIND','ordinary assertion operation mismatch')
                require(op['assertion']==c['assertion'],'CANDIDATE_BINDING','operation assertion bytes differ')
    require(bool(bundle['ledger']),'LEDGER_COVERAGE','complete legacy fixture must include provenance events')
    covered=set()
    for event in bundle['ledger']:
        require(event['run_id']==graph['run_id'] and event['execution_mode']==graph['execution_mode'],'MODE_MISMATCH','ledger run/mode differs')
        covered.update(event['payload_refs'])
    require(set(all_records)-set(indices['ledger'])<=covered,'LEDGER_COVERAGE','unlogged substantive records')
