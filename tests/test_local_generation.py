"""Local model snapshots fail closed before loading optional model libraries."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trace_gc.errors import ContractError
from trace_gc.local_generation import MODEL_URL, verify_model_snapshot


class LocalModelSnapshotTests(unittest.TestCase):
    def test_complete_snapshot_and_changed_weights(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "model"
            root.mkdir()
            files = {"config.json": b"{}", "tokenizer.json": b"{}",
                     "model.safetensors.index.json": b'{"weight_map":{"layer":"model-00001.safetensors"}}',
                     "model-00001.safetensors": b"weights"}
            for name, data in files.items():
                (root / name).write_bytes(data)
            manifest = {"schema_version": "local-generation-model-v1",
                        "revision": "a" * 40, "source": MODEL_URL,
                        "license": "apache-2.0",
                        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
            path = Path(temp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(verify_model_snapshot(root, path)["file_count"], 4)
            (root / "model-00001.safetensors").write_bytes(b"other weights")
            with self.assertRaises(ContractError):
                verify_model_snapshot(root, path)
            (root / "model-00001.safetensors").write_bytes(b"weights")
            (root / "unlisted.txt").write_text("surprise", encoding="utf-8")
            with self.assertRaises(ContractError):
                verify_model_snapshot(root, path)

    def test_index_cannot_reference_unpinned_or_external_shards(self):
        for shard in ("../outside.safetensors", "unlisted.safetensors"):
            with self.subTest(shard=shard), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "model"
                root.mkdir()
                files = {"config.json": b"{}", "tokenizer.json": b"{}",
                         "model.safetensors.index.json": json.dumps({"weight_map": {"x": shard}}).encode(),
                         "model-00001.safetensors": b"weights"}
                for name, data in files.items():
                    (root / name).write_bytes(data)
                manifest = {"schema_version": "local-generation-model-v1", "revision": "a" * 40,
                            "source": MODEL_URL, "license": "apache-2.0",
                            "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
                path = Path(temp) / "manifest.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ContractError):
                    verify_model_snapshot(root, path)


if __name__ == "__main__":
    unittest.main()
