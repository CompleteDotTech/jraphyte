"""Controller freeze and recovery checks over the authored pilot fixture."""
import copy
import unittest

from trace_gc.errors import ContractError
from trace_gc.paper_pilot_controller import PaperPilotController
from trace_gc.paper_ingestion import CHECKS
from tests.test_paper_pilot import PaperPilotTests


class ControllerTests(PaperPilotTests):
    def setUp(self):
        super().setUp()
        self.manifest = {"version": "real-paper-pilot-controller-v1", "pilot_config": self.config,
            "questions": self.config["questions"], "acceptance": {
                "phase": "source_preparation_only", "source_review_checks": sorted(CHECKS)},
            "pages": [{"id": "paper-page-2", "source_id": "authored-paper", "version": "v1",
                       "pdf_sha256": self.config["documents"][0]["document_sha256"],
                       "physical_page": 2, "start": 0, "end": len(self.native.strip())}]}
        self.controller = PaperPilotController(self.pilot, manifest=self.manifest, private_dir=self.root)

    def tearDown(self):
        self.controller.close()
        super().tearDown()

    def test_frozen_pdf_prepare_and_fresh_process_reopen(self):
        self.assertEqual(self.controller.preflight({"paper-page-2": self.pdf})["status"], "PREFLIGHT_PASS")
        first = self.controller.prepare("paper-page-2", self.pdf)
        self.assertEqual(first["state"], "WAIT_SOURCE_REVIEW")
        self.assertEqual(self.controller.prepare("paper-page-2", self.pdf), first)
        self.controller.close()
        self.reopen()
        self.controller = PaperPilotController(self.pilot, manifest=self.manifest, private_dir=self.root)
        self.assertEqual(self.controller.prepare("paper-page-2", self.pdf), first)
        self.assertEqual(self.backend.state()["graph_version"], 0)
        self.assertEqual(self.budget.snapshot()["used"]["model_calls"], 0)

    def test_rejects_changed_pdf_and_frozen_frame(self):
        with self.assertRaises(ContractError):
            self.controller.preflight({"paper-page-2": self.pdf + b"x"})
        with self.assertRaises(ContractError):
            self.controller.prepare("paper-page-2", self.pdf + b"x")
        altered = copy.deepcopy(self.manifest)
        altered["questions"] = ["changed question"]
        with self.assertRaises(ContractError):
            PaperPilotController(self.pilot, manifest=altered, private_dir=self.root)

    def test_preflight_is_required_and_covers_second_page(self):
        second = copy.deepcopy(self.manifest["pages"][0])
        second["id"] = "paper-page-2-second-span"
        second["start"] = 1
        manifest = copy.deepcopy(self.manifest)
        manifest["pages"].append(second)
        self.controller.close()
        # A distinct run is needed because the journal froze the original frame.
        (self.root / "application-journal.sqlite3").unlink()
        self.controller = PaperPilotController(self.pilot, manifest=manifest, private_dir=self.root)
        with self.assertRaises(ContractError):
            self.controller.prepare("paper-page-2", self.pdf)
        with self.assertRaises(ContractError):
            self.controller.preflight({"paper-page-2": self.pdf})
        with self.assertRaises(ContractError):
            self.controller.preflight({"paper-page-2": self.pdf,
                                       "paper-page-2-second-span": self.pdf + b"tampered"})
        self.assertEqual(self.controller.status()["pilot"]["requests"], [])
        self.controller.preflight({"paper-page-2": self.pdf, "paper-page-2-second-span": self.pdf})
        self.assertEqual(self.controller.prepare("paper-page-2", self.pdf)["state"], "WAIT_SOURCE_REVIEW")

    def test_detects_missing_pilot_result(self):
        self.controller.preflight({"paper-page-2": self.pdf})
        self.controller.prepare("paper-page-2", self.pdf)
        self.pilot.requests.pop("source-prepare:paper-page-2")
        with self.assertRaises(ContractError):
            self.controller.status()


if __name__ == "__main__":
    unittest.main()
