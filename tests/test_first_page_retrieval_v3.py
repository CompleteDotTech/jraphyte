import copy
import tempfile
import unittest
from pathlib import Path

from trace_gc.pdf_source_v3 import digest
from src.abstract_validation_v3.retrieval import title_fields, candidate_pool, ranking_metrics, rerank, bm25
from src.abstract_validation_v3.retrieval_experiment import evaluate


def native(i, text, y, size, *, block=None):
    return {"id":i,"page_no":1,"text":text,"bbox":[40,y,560,y+size],"font":"Fixture-Regular",
            "size":size,"flags":0,"color":0,"block_id":i if block is None else block}


class RetrievalFieldTests(unittest.TestCase):
    def test_graphical_abstract_label_does_not_replace_article_title(self):
        lines=[native(0,"Graphical Abstract",30,28),
               native(1,"Controlled transport through layered materials",420,18),
               native(2,"A graphical sketch describes the experimental setup.",500,11)]
        fields=title_fields(lines,(600,800),source_sha256="a"*64,page_sha256="b"*64)
        self.assertEqual(fields["title"],lines[1]["text"])
        self.assertEqual(fields["title_spans"][0]["line_id"],1)
        self.assertEqual(fields["abstract"],"")
        self.assertFalse(fields["graph_evidence"])

    def test_multi_line_title_stays_in_one_native_block(self):
        lines=[native(0,"Transport through",30,18,block=1),native(1,"layered materials",51,18,block=1),
               native(2,"Other large text far away",400,18,block=2)]
        f=title_fields(lines,(600,800),source_sha256="a"*64,page_sha256="b"*64)
        self.assertEqual(f["title"],"Transport through layered materials")

    def test_image_only_cover_has_explicit_review_queue_not_fake_fields(self):
        fields=title_fields([],(600,800),source_sha256="a"*64,page_sha256="b"*64)
        self.assertFalse(fields["indexable"])
        self.assertEqual(fields["candidate_path"],"image_transcription_review_queue")
        self.assertEqual(fields["title"],"")
        self.assertEqual(fields["abstract"],"")

    def test_reviewed_cover_title_creates_lexical_path_not_abstract(self):
        review={"source_sha256":"a"*64,"page_sha256":"b"*64,"image_sha256":"c"*64,"physical_page":1,
                "reviewer":"fixture reviewer","reviewer_kind":"assistant","reviewed_at":"2026-01-01T00:00:00+00:00",
                "source_image_reviewed":True,"title":"Transport Phenomena in Layered Solids","text":"Transport Phenomena in Layered Solids"}
        review["review_sha256"]=digest(review)
        f=title_fields([],(600,800),source_sha256="a"*64,page_sha256="b"*64,image_review=review,image_sha256="c"*64)
        self.assertTrue(f["indexable"])
        self.assertEqual(f["abstract"],"")
        self.assertEqual(f["field_source"],"reviewed_first_page_image_transcription")
        scores=bm25("layered solids",{"cover":f["body"],"other":"unrelated botanical observations"})
        self.assertGreater(scores["cover"],scores["other"])
        with self.assertRaises(ValueError):
            title_fields([],(600,800),source_sha256="a"*64,page_sha256="b"*64,image_review=review,image_sha256="d"*64)

    def test_page_two_fields_are_rejected(self):
        line=native(0,"A title from the second page",20,20);line["page_no"]=2
        with self.assertRaises(ValueError):
            title_fields([line],(600,800),source_sha256="a"*64,page_sha256="b"*64)


class CandidateCoverageTests(unittest.TestCase):
    def test_full_page_channel_restores_candidate_lost_by_title_channels(self):
        dense=[{"id":f"d{i:03}","score":1-i/1000} for i in range(60)]
        field=[{"id":f"e{i:03}","score":1-i/1000} for i in range(60)]
        page=[{"id":f"p{i:03}","score":1-i/1000} for i in range(43)]+[{"id":"target","score":.5}]
        old=candidate_pool({"specter2":dense,"bm25f":field})
        new=candidate_pool({"specter2":dense,"bm25f":field,"bm25_page":page})
        self.assertNotIn("target",old["document_ids"])
        self.assertIn("target",new["document_ids"])
        self.assertEqual(new["channels"]["target"]["bm25_page"],44)
        self.assertFalse(new["target_insertion"])

    def test_target_outside_all_channels_is_not_inserted(self):
        pool=candidate_pool({"bm25_page":[{"id":"other","score":1.0}]})
        result=ranking_metrics([{"candidate_ids":pool["document_ids"],"ranking":pool["document_ids"],"target_id":"missing"}])
        self.assertEqual(result["candidate_coverage"],0)
        self.assertEqual(result["mrr"],0)

    def test_empty_fields_zero_scores_do_not_make_arbitrary_candidates(self):
        pool=candidate_pool({"bm25_page":[{"id":"empty","score":0.0}],"bm25f":[{"id":"empty","score":0.0}]})
        self.assertEqual(pool["document_ids"],[])

    def test_ties_are_id_stable_and_do_not_use_labels(self):
        a=candidate_pool({"bm25_page":[{"id":"b","score":1},{"id":"a","score":1}]})
        b=candidate_pool({"bm25_page":[{"id":"a","score":1},{"id":"b","score":1}]})
        self.assertEqual(a,b)
        self.assertEqual(a["document_ids"],["a","b"])

    def test_duplicate_nonfinite_and_cloud_channels_rejected(self):
        for rankings in ({"gemini":[{"id":"x","score":1}]},
                         {"bm25f":[{"id":"x","score":float("nan")}]},
                         {"bm25f":[{"id":"x","score":1},{"id":"x","score":.5}]}):
            with self.assertRaises(ValueError):candidate_pool(rankings)

    def test_reranker_receives_only_query_and_frozen_candidates(self):
        pool=candidate_pool({"bm25f":[{"id":"a","score":1},{"id":"b","score":.5}]})
        seen=[]
        def scorer(q,docs):
            seen.append((q,docs));return [.1,.9]
        result=rerank(pool,{"a":"doc a","b":"doc b","secret":"not a candidate"},"question",scorer)
        self.assertEqual(seen,[("question",["doc a","doc b"])])
        self.assertEqual(result["ranking"],["b","a"])
        self.assertEqual(ranking_metrics([{"target_id":"a","candidate_ids":["a","b"],"ranking":result["ranking"]}])["mrr"],.5)

    def test_unjudged_top_result_not_marked_irrelevant(self):
        r=ranking_metrics([{"target_id":"target","candidate_ids":["competitor","target"],"ranking":["competitor","target"]}])
        self.assertEqual(r["ranks"],[2])
        self.assertFalse(r["competing_results_judged"])

    def test_metrics_reject_target_inserted_by_reranker(self):
        with self.assertRaises(ValueError):
            ranking_metrics([{"target_id":"t","candidate_ids":["a"],"ranking":["t","a"]}])

    def test_candidate_only_report_does_not_fabricate_rerank_metrics(self):
        fields={"one":{"title":"Layered transport","abstract":"","body":"transport in layered media","indexable":True},
                "two":{"title":"Unrelated plants","abstract":"","body":"botanical observations","indexable":True}}
        receipt={"fields":fields,"fields_sha256":digest(fields)}
        with tempfile.TemporaryDirectory() as tmp:
            r=evaluate(receipt,[{"query_id":"q1","text":"layered transport","target_id":"one"}],Path(tmp))
            self.assertEqual(r["candidate_metrics"]["candidate_coverage"],1.0)
            self.assertIsNone(r["reranker_metrics"])
            self.assertIn("RERANK_GATE_OUTSTANDING",r["status"])

    def test_stale_semantic_receipt_cannot_use_old_title_embeddings(self):
        fields={"one":{"title":"New title","body":"body","abstract":"","indexable":True}}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                evaluate({"fields":fields,"fields_sha256":digest(fields)},
                         [{"query_id":"q1","text":"question","target_id":"one"}],Path(tmp),
                         semantic_receipt={"fields_sha256":"old","queries_sha256":"old","channel":"specter2","model_revision":"pinned"})


if __name__=="__main__":unittest.main()
