"""Risk accounting, signed qualification applicability, and frozen-observation replay.

No shipped artifact qualifies a production threshold. Human/external labels and
an authorized qualification issuer are mandatory. The statistical unit is one
independent action group. Unique groups and disjoint source IDs are checked;
actual statistical independence and representative sampling need external review.
"""
from __future__ import annotations
import math
import random
from copy import deepcopy
from typing import Any
from .canonical import digest
from .catalog import Catalog
from .compiler import now,timestamp
from .errors import boundary,require
from .resolver import accepted_probability,primary_observation,acceptance_label,effective_risk
from .trust import TrustStore

SCOPE_FIELDS={"task","predicate","population","candidate_generator","model_version","question_program", "materializer_version",
              "packing_policy","tokenizer_version","resolver_version","policy_version","risk_class","security_scope","execution_mode"}

def pipeline_fingerprint(scope: dict[str,Any]) -> str:
    return digest({"contract":"qualified-fixed-pipeline-v1","scope":scope,"scoring":"single-primary-accepted-label-probability",
                   "resolution":"exact-subset-v1","abstention":"unqualified-or-mismatch","canonicalization":"TRACE-C14N-1"})

def _binomial_cdf(k: int, n: int, p: float) -> float:
    if p<=0:return 1.0
    if p>=1:return 1.0 if k==n else 0.0
    logs=[math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)+i*math.log(p)+(n-i)*math.log1p(-p) for i in range(k+1)]
    largest=max(logs)
    return math.exp(largest)*sum(math.exp(x-largest) for x in logs)

def upper_error_bound(errors: int, accepted: int, confidence: float) -> float:
    """One-sided exact binomial (Clopper-Pearson) upper bound, by inversion."""
    require(type(errors) is int and type(accepted) is int and 0<=errors<=accepted and accepted>0,"RISK_DENOMINATOR","positive accepted-action count required")
    require(type(confidence) in (float,int) and 0<confidence<1,"RISK_CONFIDENCE","confidence must be inside (0,1)")
    if errors==accepted:return 1.0
    if errors==0:return -math.expm1(math.log1p(-confidence)/accepted)
    low,high=errors/accepted,1.0
    for _ in range(72):
        mid=(low+high)/2
        if _binomial_cdf(errors,accepted,mid)>1-confidence:low=mid
        else:high=mid
    return high

@boundary
def evaluate_labels(rows: list[dict[str,Any]], *, scope: dict[str,Any], protocol: dict[str,Any],
                    threshold: float, risk_limit: float, minimum_coverage: float, confidence: float,
                    expires_at: str, created_at: str | None = None) -> dict[str,Any]:
    require(set(scope)==SCOPE_FIELDS,"QUALIFICATION_SCOPE","all applicability fields required")
    require(scope["execution_mode"]!="SYNTHETIC","SYNTHETIC_QUALIFICATION","synthetic labels cannot qualify production")
    for x in (threshold,risk_limit,minimum_coverage):require(type(x) in (int,float) and 0<=x<=1,"RISK_CONFIG","probability range required")
    require(protocol.get("locked") is True and protocol.get("split")=="LOCKED_HOLDOUT" and protocol.get("threshold")==threshold and
            protocol.get("pipeline_hash")==pipeline_fingerprint(scope),"EVALUATION_PROTOCOL","threshold and pipeline must be locked before holdout")
    require(protocol.get("calibration_group_ids") is not None and protocol.get("development_group_ids") is not None,"EVALUATION_SPLITS","prior split groups required")
    groups=set();sources=set();actions=set();accepted=errors=0
    for row in rows:
        required={"action_id","group_id","source_ids","label_correct","labeler","label_origin","score","resolver_selected","constraints_passed","decision","split"}
        require(set(row)==required,"LABEL_FIELDS","independent action label contract")
        require(all(isinstance(row[k],str) and bool(row[k]) for k in ("action_id","group_id","labeler")),"LABEL_FIELDS","nonempty identities required")
        require(row["action_id"] not in actions,"EVALUATION_LEAKAGE","duplicate action identity")
        actions.add(row["action_id"])
        require(type(row["label_correct"]) is bool and row["label_origin"] in {"HUMAN","INDEPENDENT_EXTERNAL"} and bool(row["labeler"]),"INDEPENDENT_LABELS","independent labels required")
        require(row["group_id"] not in groups and row["split"]=="LOCKED_HOLDOUT","EVALUATION_LEAKAGE","one unit per independent group")
        require(row["group_id"] not in set(protocol["calibration_group_ids"])|set(protocol["development_group_ids"]),"EVALUATION_LEAKAGE","holdout overlaps training/calibration")
        require(isinstance(row["source_ids"],list) and bool(row["source_ids"]) and not sources.intersection(row["source_ids"]),"EVALUATION_DEPENDENCE","source-correlated actions must form one evaluation unit")
        groups.add(row["group_id"]);sources.update(row["source_ids"])
        require(type(row["score"]) in (int,float) and 0<=row["score"]<=1 and type(row["resolver_selected"]) is bool and type(row["constraints_passed"]) is bool,
                "LABEL_FIELDS","invalid final-pipeline fields")
        take=row["resolver_selected"] and row["constraints_passed"] and row["score"]>=threshold
        require((row["decision"]=="ACCEPT")==take and row["decision"] in {"ACCEPT","REJECT","ABSTAIN","HUMAN_REVIEW"},"EVALUATION_PIPELINE","label table must describe the final locked pipeline")
        if take:accepted+=1;errors+=int(not row["label_correct"])
    require(accepted>0,"NO_ACCEPTED_ACTIONS","zero acceptance does not demonstrate zero risk")
    upper=upper_error_bound(errors,accepted,confidence);coverage=accepted/len(rows)
    require(upper<=risk_limit and coverage>=minimum_coverage,"QUALIFICATION_FAILED","risk or coverage objective not met")
    when=created_at or now()
    require(timestamp(expires_at)>timestamp(when),"QUALIFICATION_EXPIRED","expiry must follow creation")
    return {"scope":deepcopy(scope),"metric":"ERRORS_PER_ACCEPTED_ACTION","threshold":threshold,"risk_limit":risk_limit,
            "upper_risk_bound":upper,"confidence":confidence,"minimum_coverage":minimum_coverage,"measured_coverage":coverage,
            "n_eligible":len(rows),"n_accepted":accepted,"n_errors":errors,"dataset_hash":digest(rows),"protocol_hash":digest(protocol),
            "pipeline_hash":pipeline_fingerprint(scope),"evaluation_unit":"INDEPENDENT_ACTION_GROUP","split":"LOCKED_HOLDOUT",
            "independent_labels":True,"created_at":when,"expires_at":expires_at,"drift_status":"CLEAR"}

class QualificationRegistry:
    """Service-owned approvals/revocations; never populated from a bundle's claims alone."""
    def __init__(self, trust: TrustStore):
        self.trust=trust
        self._approvals: dict[str,dict[str,Any]]={}
        self._revoked:set[str]=set()
    def register(self, catalog: Catalog, qualification_id: str, receipt: dict[str,Any], *, at: str | None = None) -> None:
        q=catalog.get(qualification_id,"qualification")
        policy=self.trust.verify(receipt,"QUALIFICATION",at=at)
        require(policy.can_review,"QUALIFICATION_AUTHORITY","qualification requires a trusted reviewer")
        expected={"qualification_hash":catalog.hash(qualification_id),"pipeline_hash":q["pipeline_hash"],
                  "security_scope":q["scope"]["security_scope"],"execution_mode":q["scope"]["execution_mode"]}
        require(receipt["payload"]==expected,"QUALIFICATION_BINDING","approval does not bind artifact/scope")
        self._approvals[qualification_id]=deepcopy(receipt)
    def revoke(self, qualification_id: str) -> None:self._revoked.add(qualification_id)
    def applicable(self, catalog: Catalog, qualification_id: str, context: dict[str,Any], *, at: str | None = None) -> dict[str,Any]:
        require(qualification_id in self._approvals and qualification_id not in self._revoked,"UNQUALIFIED_POLICY","no active trusted qualification")
        q=catalog.get(qualification_id,"qualification")
        self.trust.verify(self._approvals[qualification_id],"QUALIFICATION",at=at)
        require(self._approvals[qualification_id]["payload"]["qualification_hash"]==catalog.hash(qualification_id),
                "QUALIFICATION_BINDING","approved artifact bytes changed")
        instant=timestamp(at or now())
        require(q["scope"]==context and set(context)==SCOPE_FIELDS,"QUALIFICATION_SCOPE","task/population/version/risk/scope mismatch")
        require(context["execution_mode"]!="SYNTHETIC" and context["tokenizer_version"]!="utf8-byte-estimate-v1","SYNTHETIC_QUALIFICATION","unqualified observation population")
        require(timestamp(q["created_at"])<=instant<timestamp(q["expires_at"]) and q["drift_status"]=="CLEAR","QUALIFICATION_EXPIRED","expired/drifted/unknown qualification")
        require(q["pipeline_hash"]==pipeline_fingerprint(context),"QUALIFICATION_PIPELINE","pipeline differs")
        upper=upper_error_bound(q["n_errors"],q["n_accepted"],q["confidence"])
        require(q["n_accepted"]<=q["n_eligible"] and q["n_eligible"]>0 and
                math.isclose(q["upper_risk_bound"],upper,abs_tol=1e-12,rel_tol=0) and upper<=q["risk_limit"] and
                math.isclose(q["measured_coverage"],q["n_accepted"]/q["n_eligible"],abs_tol=1e-12,rel_tol=0) and
                q["measured_coverage"]>=q["minimum_coverage"],"QUALIFICATION_METRIC","denominator/bound/coverage inconsistent")
        return q

def context_for(catalog: Catalog, candidate_id: str, observation_ids: list[str], batch_id: str, *, population: str,
                policy_version: str) -> dict[str,Any]:
    c=catalog.get(candidate_id,"candidate");batch=catalog.get(batch_id,"resolution-batch")
    o=primary_observation(catalog,candidate_id,observation_ids)
    if o is None:
        matches=[catalog.get(x,"observation") for x in observation_ids if catalog.get(x,"observation")["candidate_id"]==candidate_id]
        require(bool(matches),"MISSING_OBSERVATION",candidate_id);o=matches[0]
    p=catalog.get(o["pack_id"],"pack")
    operation="ADD_IDENTITY_ASSERTION" if c["candidate_kind"]=="IDENTITY" else "ADD_ASSERTION"
    from .programs import PROGRAM_HASH
    return {"task":"IDENTITY" if c["candidate_kind"]=="IDENTITY" else "SUPPORT","predicate":c["assertion"]["predicate"],
            "population":population,"candidate_generator":c["generator_version"],"model_version":p["model_version"],
            "question_program":p["program_version"]+":"+PROGRAM_HASH,"materializer_version":p["materializer_version"],"packing_policy":p["packing_version"],
            "tokenizer_version":p["tokenizer_version"],"resolver_version":batch["solver_version"],"policy_version":policy_version,
            "risk_class":effective_risk(operation,batch),"security_scope":p["security_scope"],"execution_mode":p["execution_mode"]}

def evaluate_policy(catalog: Catalog, *, candidate_id: str, batch_id: str, policy_version: str, population: str,
                    registry: QualificationRegistry | None = None, qualification_id: str | None = None,
                    at: str | None = None) -> str:
    batch=catalog.get(batch_id,"resolution-batch")
    ids=[x for x in batch["observation_ids"] if catalog.get(x,"observation")["candidate_id"]==candidate_id]
    context=context_for(catalog,candidate_id,ids,batch_id,population=population,policy_version=policy_version)
    score=accepted_probability(catalog,candidate_id,ids)
    outcome,reason="ABSTAIN","No applicable trusted qualification."
    if batch["status"]!="OPTIMAL":reason="Global resolution did not complete."
    elif candidate_id not in batch["selected_ids"]:outcome,reason="REJECT","Not selected by the global constraint resolver."
    elif registry is not None and qualification_id is not None and score is not None:
        try:
            qualified=registry.applicable(catalog,qualification_id,context,at=at)
            primary=primary_observation(catalog,candidate_id,ids)
            label=acceptance_label(catalog.get(candidate_id,"candidate"))
            if score>=qualified["threshold"] and primary["semantic_outcome"]==label:
                outcome,reason="ACCEPT","Qualified final-pipeline policy; authorization is a separate requirement."
            else:outcome,reason="ABSTAIN","Qualified threshold/polarity not satisfied."
        except Exception as exc:
            from .errors import ContractError
            if not isinstance(exc,ContractError):raise
            reason=str(exc)
    from .policy import find_policy
    policy_id=find_policy(catalog,policy_version)
    if catalog.get(policy_id,"policy")["mode"]=="ANALYSIS_ONLY" and outcome=="ACCEPT":
        outcome,reason="ABSTAIN","Analysis-only policy cannot accept."
    return catalog.put("evaluation",{"policy_id":policy_id,"candidate_id":candidate_id,"observation_ids":ids,"resolution_batch_id":batch_id,
                    "policy_version":policy_version,"qualification_id":qualification_id,"context":context,"outcome":outcome,
                    "score":score,"reason":reason,"created_at":at or now()})

def audit_sample(action_ids: list[str], sample_size: int, *, seed: int) -> list[str]:
    require(len(action_ids)==len(set(action_ids)) and type(sample_size) is int and 0<=sample_size<=len(action_ids),"AUDIT_SAMPLE","invalid sample")
    return sorted(random.Random(seed).sample(sorted(action_ids),sample_size))
