"""Answer mechanics use selected citations and current source status."""
import json
import copy
import tempfile
import unittest
from pathlib import Path

from trace_gc.demo import build_fixture
from trace_gc.errors import ContractError
from trace_gc.paper_answer import _current, draft_answer, review_answer
from trace_gc.retrieval.scenarios import downstream


class CitedAnswerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = build_fixture(Path(self.temporary.name), candidate_count=1)
        self.fixture.publish()
        self.context = downstream(self.fixture, [self.fixture.claim_id])["answer_context_id"]
        answer = self.fixture.catalog.get(self.context, "graphrag-answer")
        self.citation = answer["citations"][0]["evidence_id"]
        graph_context = self.fixture.catalog.get(answer["graph_context_id"], "graph-context")
        self.access = self.fixture.catalog.get(graph_context["access_id"], "graph-access")
        self.kwargs = dict(context_id=self.context, question="What did the paper state?",
                           model_id="local-model", model_revision="sha256:abc",
                           tokenizer_id="local-tokenizer", current_access=self.access)

    def tearDown(self):
        self.fixture.close()
        self.temporary.cleanup()

    def test_cited_draft_requires_attributed_support_review(self):
        def generate(_prompt):
            return json.dumps({"abstain": False, "claims": [{"text": "Aster joined Meridian in 2024.",
                   "evidence_ids": [self.citation]}]}).encode()
        draft = draft_answer(self.fixture.catalog, self.fixture.backend, generate=generate, **self.kwargs)
        self.assertEqual(draft["status"], "REVIEW_REQUIRED")
        review = review_answer(self.fixture.catalog, self.fixture.backend, draft=draft,
                               expected_draft_sha256=draft["sha256"], current_access=self.access,
                               reviewer="assistant-1", reviewer_kind="assistant",
                               reviewed_at="2026-09-28T16:00:00Z", claim_support=[True])
        self.assertEqual(review["status"], "SUPPORTED")
        self.assertFalse(review["independent_review"])

    def test_unsupported_or_withdrawn_citations_fail_closed(self):
        fake = lambda _: json.dumps({"abstain": False, "claims": [{"text": "Unsupported",
            "evidence_ids": ["missing-evidence"]}]}).encode()
        with self.assertRaises(ContractError):
            draft_answer(self.fixture.catalog, self.fixture.backend, generate=fake, **self.kwargs)
        valid = lambda _: json.dumps({"abstain": False, "claims": [{"text": "Possibly supported",
            "evidence_ids": [self.citation]}]}).encode()
        draft = draft_answer(self.fixture.catalog, self.fixture.backend, generate=valid, **self.kwargs)
        rejected = review_answer(self.fixture.catalog, self.fixture.backend, draft=draft,
                                 expected_draft_sha256=draft["sha256"], current_access=self.access,
                                 reviewer="assistant-1", reviewer_kind="assistant",
                                 reviewed_at="2026-09-28T16:00:00Z", claim_support=[False])
        self.assertEqual(rejected["status"], "REJECTED_UNSUPPORTED_CLAIM")
        self.fixture.status_change(self.fixture.source_ids[0], active=False)
        with self.assertRaises(ContractError):
            review_answer(self.fixture.catalog, self.fixture.backend, draft=draft,
                          expected_draft_sha256=draft["sha256"], current_access=self.access,
                          reviewer="assistant-1", reviewer_kind="assistant",
                          reviewed_at="2026-09-28T16:00:00Z", claim_support=[True])

    def test_model_abstention_has_no_support_claim(self):
        response = lambda _: b'{"abstain":true,"claims":[]}'
        draft = draft_answer(self.fixture.catalog, self.fixture.backend, generate=response, **self.kwargs)
        self.assertEqual(draft["status"], "ABSTAIN_MODEL")
        self.assertFalse(draft["review_required"])

    def test_forged_quote_and_rehashed_claims_are_rejected(self):
        answer = copy.deepcopy(self.fixture.catalog.get(self.context, "graphrag-answer"))
        answer["citations"][0]["quote"] = "A fabricated quote absent from the paper."
        forged_id = self.fixture.catalog.put("graphrag-answer", answer)
        with self.assertRaises(ContractError):
            draft_answer(self.fixture.catalog, self.fixture.backend, generate=lambda _: b'{}',
                         **{**self.kwargs, "context_id": forged_id})
        response = lambda _: json.dumps({"abstain": False, "claims": [{"text": "Aster joined Meridian in 2024.",
            "evidence_ids": [self.citation]}]}).encode()
        draft = draft_answer(self.fixture.catalog, self.fixture.backend, generate=response, **self.kwargs)
        tampered = copy.deepcopy(draft)
        tampered["claims"] = [{"text": "Uncited new claim", "evidence_ids": []}]
        from trace_gc.canonical import digest
        tampered["sha256"] = digest({k: v for k, v in tampered.items() if k != "sha256"})
        with self.assertRaises(ContractError):
            review_answer(self.fixture.catalog, self.fixture.backend, draft=tampered,
                          expected_draft_sha256=draft["sha256"], current_access=self.access,
                          reviewer="assistant-1", reviewer_kind="assistant",
                          reviewed_at="2026-09-28T16:00:00Z", claim_support=[True])

    def test_revocation_during_generation_and_duplicate_keys_fail(self):
        with self.assertRaises(ContractError):
            draft_answer(self.fixture.catalog, self.fixture.backend,
                         generate=lambda _: b'{"abstain":false,"abstain":true,"claims":[]}', **self.kwargs)
        def withdraw(_prompt):
            self.fixture.status_change(self.fixture.source_ids[0], active=False)
            return b'{"abstain":true,"claims":[]}'
        with self.assertRaises(ContractError):
            draft_answer(self.fixture.catalog, self.fixture.backend, generate=withdraw, **self.kwargs)

    def test_current_policy_is_required_and_revocation_during_validation_fails(self):
        for invalid_access in (None, {}):
            with self.assertRaises(ContractError):
                draft_answer(self.fixture.catalog, self.fixture.backend,
                             generate=lambda _: b'{"abstain":true,"claims":[]}',
                             **{**self.kwargs, "current_access": invalid_access})
        original = self.fixture.catalog.verify_evidence
        triggered = False
        def revoking_verify(evidence_id):
            nonlocal triggered
            result = original(evidence_id)
            if not triggered:
                triggered = True
                self.fixture.status_change(self.fixture.source_ids[0], active=False)
            return result
        self.fixture.catalog.verify_evidence = revoking_verify
        with self.assertRaises(ContractError):
            _current(self.fixture.catalog, self.fixture.backend, self.context, self.access)
        self.assertTrue(triggered)


if __name__ == "__main__":
    unittest.main()
