"""Authored synthetic gate tests; no real corpus, queries, PDFs or rankings."""
import copy
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import paper_relevance_packets as co


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(co.canonical(obj) + b"\n")
    return co.file_sha(path)


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="paper-packet-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.prereg_sha = "a"*64
        self.code_head = "b"*40
        self.rubric = self.base / "rubric.json"
        self.rubric_sha = write(self.rubric,{"prereg_sha256":self.prereg_sha,
            "status":"APPROVED_PRE_RESULT_RUBRIC_ONLY","relevance_review_performed":False})
        self.data = self.base / "data"
        self.source = self.base / "originals"
        self.trial = self.data / "trial"
        self.data.mkdir(); self.source.mkdir(); self.trial.mkdir()
        self.ids = ["focus-a", "focus-b"] + [f"x{i:04d}" for i in range(9998)]
        self.queries = [{"id": f"q{i:02d}", "query": f"authored synthetic topic {i}",
                         "target_id": "focus-a" if i == 0 else "focus-b" if i == 1 else self.ids[i]}
                        for i in range(60)]
        selected = set(self.ids[:13])
        self.rows = []
        self.fields = []
        for index, sid in enumerate(self.ids):
            raw = f"%PDF-1.4\nauthored source {sid}\n".encode()
            if sid in ("x0000", "x0001"):
                raw = b"%PDF-1.4\nshared authored source\n"
            sha = hashlib.sha256(raw).hexdigest()
            page = b"%PDF-1.4\nauthored page " + (b"shared" if sid in ("x0000", "x0001") else sid.encode())
            image = b"PNG authored " + (b"shared" if sid in ("x0000", "x0001") else sid.encode())
            row = {"sample_id":sid,"source_root_id":"external","source_relative":sid+".pdf",
                   "physical_page":1,
                   "source_sha256":sha,"page_relative":"assets/"+sid+"-page.pdf",
                   "page_sha256":hashlib.sha256(page).hexdigest(),
                   "image_relative":"assets/"+sid+"-render.png",
                   "image_sha256":hashlib.sha256(image).hexdigest()}
            self.rows.append(row)
            self.fields.append({"id":sid,"source_sha256":sha})
            if sid in selected:
                (self.source / row["source_relative"]).write_bytes(raw)
                (self.data / "assets").mkdir(exist_ok=True)
                (self.data / row["page_relative"]).write_bytes(page)
                (self.data / row["image_relative"]).write_bytes(image)
        query_sha = write(self.data / "queries.json", {"queries":self.queries})
        self.query_sha = query_sha
        fields_sha = write(self.data / "fields.json", {"fields":self.fields})
        manifest_sha = write(self.data / "manifest.json", {"pdfs":self.rows})
        rank_id = co.value_sha([{"id":q["id"],"query":q["query"]} for q in self.queries])
        label_id = co.value_sha([{"id":q["id"],"target_id":q["target_id"]} for q in self.queries])
        primary = {q["id"]: ([f"x{i:04d}" for i in range(10)] if q["id"] == "q00"
                              else [q["target_id"]]) for q in self.queries}
        other = copy.deepcopy(primary)
        other["q00"] = ["x0010"] + primary["q00"][:9]
        def result(rankings):
            return {"status":"MEASURED_PENDING_FINAL_INTEGRITY","result":{
                "rankings":rankings,"ranking_inputs_sha256":rank_id,
                "evaluation_labels_sha256":label_id,"ranking_outputs_sha256":co.value_sha(rankings),
                "candidates":{qid:{"pool":rank,"pool_sha256":co.value_sha(rank)}
                              for qid,rank in rankings.items()}}}
        psha = write(self.trial / "primary.json", result(primary))
        dsha = write(self.trial / "without_dense.json", result(other))
        self.protocol = self.data / "protocol.json"
        self.protocol_sha = write(self.protocol,{"configuration":{"queries":"queries.json",
            "fields":"fields.json","preparation_manifest":"manifest.json",
            "document_count":10000,"query_count":60},
            "snapshot":{"code":{"git_head":self.code_head},
                        "file_sha256":{"queries":query_sha,"fields":fields_sha,
                                          "preparation_manifest":manifest_sha}}})
        self.receipt_sha = write(self.trial / "receipt.json",{
            "status":"COMPLETE","protocol_sha256":self.protocol_sha,
            "frozen_input_code_runtime_readback":"MATCH","full_10000_by_60":True,
            "document_count":10000,"query_count":60,"relevance_judgments":"NOT_PERFORMED",
            "result_file_sha256":{"primary.json":psha,"without_dense.json":dsha}})
        self.authorization = {"schema_version":co.VERSION,"data_root":str(self.data),
            "source_root":str(self.source),"trial_relative":"trial",
            "protocol_relative":"protocol.json","protocol_sha256":self.protocol_sha,
            "receipt_sha256":self.receipt_sha,"rubric_path":str(self.rubric),
            "rubric_sha256":self.rubric_sha,"expected_prereg_sha256":self.prereg_sha,
            "expected_queries_sha256":self.query_sha,"expected_code_head":self.code_head,
            "coordinator_code_sha256":co.file_sha(Path(co.__file__)),
            "focus_target_ids":["focus-a","focus-b"],
            "authorized_output_root":str(self.base),"output_name":"unused"}

    def build(self, name):
        self.authorization["output_name"] = name
        auth = self.base / (name + "-authorization.json")
        return co.run_authorized(auth,write(auth,self.authorization))

    def test_complete_blinded_and_deterministic_order(self):
        first = self.build("out1")
        second = self.build("out2")
        self.assertEqual(first["selected_queries"], 2)
        private1 = json.loads((self.base / "out1/coordinator_private/selection-map.json").read_bytes())
        private2 = json.loads((self.base / "out2/coordinator_private/selection-map.json").read_bytes())
        preflight = json.loads((self.base / "out1/coordinator_private/selection-preflight.json").read_bytes())
        self.assertEqual(len(preflight["all_60_target_ranks_and_union"]),60)
        self.assertIsNone(preflight["all_60_target_ranks_and_union"][0]["primary_target_rank"])
        self.assertEqual([[t["source_sha256"] for t in row["tasks"]] for row in private1["selection"]],
                         [[t["source_sha256"] for t in row["tasks"]] for row in private2["selection"]])
        q0 = private1["selection"][0]
        self.assertEqual(q0["pairs"]["without_dense"]["status"],"PAIRED")
        self.assertEqual(q0["pairs"]["without_page"]["status"],"NOT_RUN")
        self.assertEqual(private1["selection"][1]["pairs"]["without_dense"]["status"],"IDENTICAL_TOP10")
        self.assertTrue(any(set(t["document_ids"]) == {"x0000","x0001"} for t in q0["tasks"]))
        self.assertTrue(all(t["physical_page"] == 1 and len(t["page_sha256"]) == 64 and
                            len(t["image_sha256"]) == 64 for row in private1["selection"]
                            for t in row["tasks"]))
        packet = json.loads((self.base / "out1/reviewer/packets.json").read_bytes())
        self.assertTrue(all(p["query_id"].startswith("qry-") for p in packet["packets"]))
        self.assertNotIn("q00",str(packet))
        self.assertEqual(private1["reviewer_packet_sha256"],
                         co.file_sha(self.base / "out1/reviewer/packets.json"))
        self.assertNotIn("target_id", str(packet))
        self.assertNotIn("target_rank", str(packet))
        self.assertNotIn("arm", str(packet))
        self.assertNotIn("focus-a", str(packet))
        self.assertNotIn("focus-b", str(packet))
        self.assertTrue(all(co.file_sha(self.base / "out1/reviewer" / t["assets"]["pdf"]) ==
                            t["source_sha256"] for row in private1["selection"] for t in row["tasks"]))

    def test_no_source_access_before_complete_and_tampered_result(self):
        receipt = json.loads((self.trial / "receipt.json").read_bytes())
        receipt["status"] = "BLOCKED"
        bad_sha = write(self.trial / "receipt.json", receipt)
        self.authorization["receipt_sha256"] = bad_sha
        with self.assertRaisesRegex(ValueError,"complete_bound_trial_required"):
            self.build("blocked")
        self.assertFalse((self.base / "blocked").exists())
        receipt["status"] = "COMPLETE"
        self.receipt_sha = write(self.trial / "receipt.json", receipt)
        self.authorization["receipt_sha256"] = self.receipt_sha
        (self.trial / "primary.json").write_bytes(b"{}\n")
        with self.assertRaisesRegex(ValueError,"listed_trial_result_artifact_changed"):
            self.build("tampered")
        self.assertFalse((self.base / "tampered").exists())

    def test_source_mismatch_holds(self):
        row = self.rows[2]
        (self.source / row["source_relative"]).write_bytes(b"%PDF changed")
        with self.assertRaisesRegex(ValueError,"duplicate_source_asset_bytes_changed"):
            self.build("mismatch")

    def test_second_duplicate_pdf_page_and_render_mismatch_hold(self):
        row = next(r for r in self.rows if r["sample_id"] == "x0001")
        for kind, path in (("pdf",self.source / row["source_relative"]),
                           ("page",self.data / row["page_relative"]),
                           ("render",self.data / row["image_relative"])):
            original = path.read_bytes()
            path.write_bytes(original + b" altered")
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError,"duplicate_source_asset_bytes_changed"):
                    self.build("duplicate-" + kind)
            path.write_bytes(original)

    def test_wrong_rubric_and_code_head_stop_before_output(self):
        self.authorization["rubric_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError,"pinned_input_changed"):
            self.build("wrong-rubric")
        self.assertFalse((self.base / "wrong-rubric").exists())
        self.authorization["rubric_sha256"] = self.rubric_sha
        protocol = json.loads(self.protocol.read_bytes())
        protocol["snapshot"]["code"]["git_head"] = "0"*40
        changed_sha = write(self.protocol,protocol)
        receipt = json.loads((self.trial / "receipt.json").read_bytes())
        receipt["protocol_sha256"] = changed_sha
        changed_receipt = write(self.trial / "receipt.json",receipt)
        self.authorization["protocol_sha256"] = changed_sha
        self.authorization["receipt_sha256"] = changed_receipt
        with self.assertRaisesRegex(ValueError,"expected_code_and_queries_required"):
            self.build("wrong-code")
        self.assertFalse((self.base / "wrong-code").exists())

    def test_order_collision_and_physical_page_duplicate_hold(self):
        q = self.queries[:1]
        sources = {row["sample_id"]:row for row in self.rows}
        ranks = [f"x{i:04d}" for i in range(10)]
        arms = {"primary":{"rankings":{"q00":ranks},
                           "candidates":{"q00":{"pool":ranks}}}}
        with patch.object(co,"order_key",return_value="0"*64):
            with self.assertRaisesRegex(ValueError,"ordering_key_collision"):
                co.select(q,sources,arms,{"focus-a","focus-b"})
        sources["x0001"] = {**sources["x0001"],"physical_page":2}
        with self.assertRaisesRegex(ValueError,"same_pdf_different_page_evidence"):
            co.select(q,sources,arms,{"focus-a","focus-b"})

    def test_output_outside_authorized_private_root_rejected(self):
        self.authorization["output_name"] = "outside-packets"
        self.authorization["authorized_output_root"] = str(self.base / "authorized")
        (self.base / "authorized").mkdir()
        auth = self.base / "outside-auth.json"
        with self.assertRaisesRegex(ValueError,"packet_output_must_be_new_child"):
            co.produce(self.data,self.source,self.trial,self.protocol,self.protocol_sha,
                       self.receipt_sha,self.rubric,self.rubric_sha,self.prereg_sha,
                       self.query_sha,self.code_head,["focus-a","focus-b"],self.base / "authorized",
                       self.base / "outside-packets")
        self.assertFalse((self.base.parent / "outside-packets").exists())

    def test_authorization_bytes_must_match_external_hash(self):
        auth = self.base / "approved-authorization.json"
        approved_sha = write(auth,self.authorization)
        changed = dict(self.authorization)
        changed["output_name"] = "changed-after-approval"
        write(auth,changed)
        with self.assertRaisesRegex(ValueError,"pinned_input_changed"):
            co.run_authorized(auth,approved_sha)
        self.assertFalse((self.base / "changed-after-approval").exists())

    def test_changed_coordinator_code_pin_rejected_before_source_access(self):
        self.authorization["coordinator_code_sha256"] = "0"*64
        with patch.object(co, "produce", side_effect=AssertionError("source access")):
            with self.assertRaisesRegex(ValueError,"approved_coordinator_code_changed"):
                self.build("bad-code")
        self.assertFalse((self.base / "bad-code").exists())

    def test_coordinator_code_changed_during_production_rejected(self):
        original = co.file_sha
        module_file = Path(co.__file__).resolve()
        reads = 0
        def changed_after(path):
            nonlocal reads
            if Path(path).resolve() == module_file:
                reads += 1
                if reads == 2:
                    return "0"*64
            return original(path)
        with patch.object(co,"file_sha",side_effect=changed_after):
            with self.assertRaisesRegex(ValueError,"approved_coordinator_code_changed_after_production"):
                self.build("changed-code-after")
        self.assertTrue((self.base / "changed-code-after/reviewer/packets.json").exists())

    def test_redirected_authorized_output_root_rejected(self):
        private = self.base / "private"
        private.mkdir()
        redirected = self.base / "redirected"
        try:
            redirected.symlink_to(private, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            if os.name != "nt":
                self.skipTest(f"symlink unavailable: {error}")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(redirected), str(private)],
                                    capture_output=True, text=True, check=False)
            if result.returncode:
                self.skipTest(f"junction unavailable: {result.stderr}")
        self.authorization["authorized_output_root"] = str(redirected)
        with self.assertRaisesRegex(ValueError,"authorized_output_path_redirected"):
            self.build("redirected-packets")
        self.assertFalse((private / "redirected-packets").exists())

    def test_listed_result_changed_during_copy_holds_before_success(self):
        original_copy = co.copy_checked
        changed = False
        def change_after_first_copy(*args):
            nonlocal changed
            original_copy(*args)
            if not changed:
                changed = True
                with (self.trial / "primary.json").open("ab") as handle:
                    handle.write(b"\nchanged after initial COMPLETE check")
        with patch.object(co,"copy_checked",side_effect=change_after_first_copy):
            with self.assertRaisesRegex(ValueError,
                                        "frozen_trial_result_changed_during_packet_construction"):
                self.build("changed-listed-result")
        self.assertTrue((self.base / "changed-listed-result/coordinator_private/selection-preflight.json").exists())
        self.assertTrue((self.base / "changed-listed-result/reviewer/packets.json").exists())

    def test_focus_ids_require_exact_corpus_membership(self):
        self.authorization["focus_target_ids"] = ["not-in-synthetic-corpus"]
        with self.assertRaisesRegex(ValueError,"focus_targets_must_be_unique_corpus_ids"):
            self.build("bad-focus")
        self.assertFalse((self.base / "bad-focus").exists())


if __name__ == "__main__":
    unittest.main()
