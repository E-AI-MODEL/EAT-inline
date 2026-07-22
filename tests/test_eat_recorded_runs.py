import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from eat_baselines import Case, ResolverRegistry, metrics, score
from eat_recorded_runs import (
    RecordedLinkerAdapter,
    RecordedRunValidationError,
    load_recorded_run,
    sha256_file,
    validate_recorded_run,
)


DATASET_NAME = "test/comparison"
DATASET_HASH = "a" * 64
REGISTRY_HASH = "b" * 64
CASES = [
    Case(
        id="case-1",
        plain_text="Hans Visser spoke.",
        eat_text="@@EAT person:Hans_Visser@@ spoke.",
        gold_ids=frozenset({"person-0001"}),
    ),
    Case(
        id="case-2",
        plain_text="Phoenix launched.",
        eat_text="@@EAT project:Phoenix@@ launched.",
        gold_ids=frozenset({"project-0017"}),
    ),
]
REGISTRY = ResolverRegistry(
    [
        {
            "type": "person",
            "key": "Hans_Visser",
            "label": "Hans Visser",
            "canonical_id": "person-0001",
        },
        {
            "type": "project",
            "key": "Phoenix",
            "label": "Phoenix",
            "canonical_id": "project-0017",
        },
    ]
)


def artifact(dataset_hash=DATASET_HASH):
    return {
        "schema_version": "1.0",
        "dataset": {
            "name": DATASET_NAME,
            "sha256": dataset_hash,
            "registry_sha256": REGISTRY_HASH,
        },
        "input": "plain_text",
        "model": {
            "name": "test-model",
            "version": "revision-1",
            "source": "https://example.test/model",
        },
        "runner": {
            "source": "https://example.test/runner",
            "commit": "abcdef1",
            "command": "python run_model.py",
            "parameters": {"temperature": 0},
        },
        "cases": [
            {
                "id": "case-1",
                "mentions": [
                    {
                        "label": "Hans Visser",
                        "start": 0,
                        "end": 11,
                        "type": "person",
                        "key": "Hans_Visser",
                    }
                ],
                "cost": {"model_calls": 1, "estimated_tokens": 8},
            },
            {
                "id": "case-2",
                "mentions": [
                    {
                        "label": "Phoenix",
                        "start": 0,
                        "end": 7,
                        "type": "project",
                        "key": "Phoenix",
                    }
                ],
                "cost": {"model_calls": 1, "estimated_tokens": 6},
            },
        ],
    }


def validate(raw):
    return validate_recorded_run(
        raw,
        CASES,
        REGISTRY,
        dataset_name=DATASET_NAME,
        dataset_sha256=DATASET_HASH,
        registry_sha256=REGISTRY_HASH,
    )


class RecordedRunValidationTests(unittest.TestCase):
    def test_valid_run_replays_as_model_adapter(self):
        run = validate(artifact())
        adapter = RecordedLinkerAdapter(run)

        result = adapter.predict(CASES[0], REGISTRY)

        self.assertTrue(adapter.requires_model)
        self.assertEqual(result.predicted_ids, {"person-0001"})
        self.assertEqual(result.cost.model_calls, 1)
        self.assertEqual(result.cost.estimated_tokens, 8)
        self.assertEqual(result.cost.registry_lookups, 1)

    def test_rejects_dataset_hash_mismatch(self):
        raw = artifact("b" * 64)
        with self.assertRaises(RecordedRunValidationError) as caught:
            validate(raw)
        self.assertIn("dataset hash does not match", str(caught.exception))

    def test_rejects_registry_hash_mismatch(self):
        raw = artifact()
        raw["dataset"]["registry_sha256"] = "c" * 64
        with self.assertRaises(RecordedRunValidationError) as caught:
            validate(raw)
        self.assertIn("registry hash does not match", str(caught.exception))

    def test_rejects_missing_unknown_and_duplicate_cases(self):
        mutations = []

        missing = artifact()
        missing["cases"].pop()
        mutations.append((missing, "missing cases"))

        unknown = artifact()
        unknown["cases"][1]["id"] = "unknown"
        mutations.append((unknown, "unknown case"))

        duplicate = artifact()
        duplicate["cases"].append(copy.deepcopy(duplicate["cases"][0]))
        mutations.append((duplicate, "duplicate case"))

        for raw, message in mutations:
            with self.subTest(message=message):
                with self.assertRaises(RecordedRunValidationError) as caught:
                    validate(raw)
                self.assertIn(message, str(caught.exception))

    def test_rejects_span_that_does_not_match_plain_text(self):
        raw = artifact()
        raw["cases"][0]["mentions"][0]["start"] = 1
        with self.assertRaises(RecordedRunValidationError) as caught:
            validate(raw)
        self.assertIn("label does not match the plain_text span", str(caught.exception))

    def test_rejects_unknown_typed_key(self):
        raw = artifact()
        raw["cases"][0]["mentions"][0]["key"] = "Unknown"
        with self.assertRaises(RecordedRunValidationError) as caught:
            validate(raw)
        self.assertIn("unknown typed key person:Unknown", str(caught.exception))

    def test_rejects_gold_or_eat_fields(self):
        raw = artifact()
        raw["cases"][0]["gold_ids"] = ["person-0001"]
        raw["cases"][1]["eat_text"] = "@@EAT project:Phoenix@@"
        raw["runner"]["parameters"]["gold_ids"] = ["person-0001"]
        with self.assertRaises(RecordedRunValidationError) as caught:
            validate(raw)
        self.assertIn("unknown field 'gold_ids'", str(caught.exception))
        self.assertIn("unknown field 'eat_text'", str(caught.exception))
        self.assertIn("forbidden benchmark input field", str(caught.exception))

    def test_rejects_wrong_input_boundary_and_runner_commit(self):
        raw = artifact()
        raw["input"] = "eat_text"
        raw["model"]["source"] = "model"
        raw["runner"]["source"] = "https://"
        raw["runner"]["commit"] = "main"
        with self.assertRaises(RecordedRunValidationError) as caught:
            validate(raw)
        self.assertIn("expected 'plain_text'", str(caught.exception))
        self.assertIn("expected an absolute URI", str(caught.exception))
        self.assertIn("expected a 7 to 40 character commit SHA", str(caught.exception))

    def test_rejects_duplicate_mention_prediction(self):
        raw = artifact()
        mention = copy.deepcopy(raw["cases"][0]["mentions"][0])
        raw["cases"][0]["mentions"].append(mention)
        with self.assertRaises(RecordedRunValidationError) as caught:
            validate(raw)
        self.assertIn("duplicate mention prediction", str(caught.exception))


class RecordedRunIoTests(unittest.TestCase):
    def test_sha256_file_hashes_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            path.write_bytes(b"one\ntwo\n")
            self.assertEqual(sha256_file(path), hashlib.sha256(b"one\ntwo\n").hexdigest())

    def test_load_recorded_run_uses_dataset_file_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "comparison.jsonl"
            dataset_path.write_text("frozen dataset\n", encoding="utf-8")
            digest = sha256_file(dataset_path)
            registry_path = root / "entity-registry.jsonl"
            registry_path.write_text("frozen registry\n", encoding="utf-8")
            run_path = root / "run.json"
            raw = artifact(digest)
            raw["dataset"]["registry_sha256"] = sha256_file(registry_path)
            run_path.write_text(json.dumps(raw), encoding="utf-8")

            run = load_recorded_run(
                run_path,
                CASES,
                REGISTRY,
                dataset_name=DATASET_NAME,
                dataset_path=dataset_path,
                registry_path=registry_path,
            )

            self.assertEqual(run.dataset_sha256, digest)

    def test_cli_validates_and_scores_complete_run(self):
        root = Path(__file__).resolve().parents[1]
        dataset_path = root / "benchmark" / "corpora" / "comparison.jsonl"
        registry_path = root / "benchmark" / "corpora" / "entity-registry.jsonl"
        case_ids = [
            json.loads(line)["id"]
            for line in dataset_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        raw = {
            "schema_version": "1.0",
            "dataset": {
                "name": "eat-inline-gold/comparison",
                "sha256": sha256_file(dataset_path),
                "registry_sha256": sha256_file(registry_path),
            },
            "input": "plain_text",
            "model": {
                "name": "empty-test-model",
                "version": "test-only",
                "source": "https://example.test/model",
            },
            "runner": {
                "source": "https://example.test/runner",
                "commit": "abcdef1",
                "command": "test-only",
                "parameters": {},
            },
            "cases": [
                {
                    "id": case_id,
                    "mentions": [],
                    "cost": {"model_calls": 0, "estimated_tokens": 0},
                }
                for case_id in case_ids
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            run_path = temporary / "run.json"
            run_path.write_text(json.dumps(raw), encoding="utf-8")
            output_path = temporary / "results"
            environment = {**os.environ, "PYTHONPATH": str(root / "src")}
            completed = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts" / "run_recorded_linker_benchmark.py"),
                    str(run_path),
                    "--output-dir",
                    str(output_path),
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(
                (output_path / "recorded-linker-results.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(result["summary"]["cases"], len(case_ids))
            self.assertEqual(result["summary"]["condition"]["f1"], 0.0)


class SharedScoringTests(unittest.TestCase):
    def test_score_and_metrics_are_shared_by_benchmark_runners(self):
        tp, fp, fn = score({"a", "b"}, {"b", "c"})
        self.assertEqual((tp, fp, fn), (1, 1, 1))
        self.assertEqual(metrics(tp, fp, fn), {"precision": 0.5, "recall": 0.5, "f1": 0.5})


if __name__ == "__main__":
    unittest.main()
