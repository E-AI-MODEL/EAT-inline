"""Model-free tests for the spaCy linker producer and its recorded artifact.

These tests never import spaCy. They exercise the pure producer helpers and, if
the recorded run has been generated and committed, validate and score it through
the same leakage-proof recorded-run path used in CI.
"""

import json
from pathlib import Path
import tempfile
import unittest

from eat_baselines import Case, ResolverRegistry
from eat_recorded_runs import RecordedLinkerAdapter, load_recorded_run
from scripts.run_spacy_linker import (
    Detection,
    build_candidate_index,
    candidate_ids,
    load_inputs,
    normalize_surface,
    select_non_overlapping,
)

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "benchmark" / "external" / "wiki-fair-v2"
RUN_PATH = ROOT / "benchmark" / "results" / "wiki-fair-v2-spacy-linker-run.json"
DATASET_NAME = "wiki-fair-v2/test-no-coref@c9a3fe9c4933888d756d702fdb9ff607fc36aa26"


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class BoundaryTests(unittest.TestCase):
    def test_load_inputs_accepts_only_id_and_plain_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.jsonl"
            path.write_text(
                json.dumps({"id": "case-1", "plain_text": "Atlas launched."}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_inputs(path),
                [{"id": "case-1", "plain_text": "Atlas launched."}],
            )

    def test_load_inputs_rejects_gold_and_eat_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.jsonl"
            path.write_text(
                json.dumps(
                    {"id": "case-1", "plain_text": "Atlas.", "gold_ids": ["Q1"]}
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exactly id and plain_text"):
                load_inputs(path)


class NormalizationTests(unittest.TestCase):
    def test_strips_leading_article_and_reports_offset(self):
        body, left = normalize_surface("the University of Southampton")
        self.assertEqual(body, "University of Southampton")
        self.assertEqual(left, len("the "))

    def test_keeps_plain_surface(self):
        self.assertEqual(normalize_surface("Atlas"), ("Atlas", 0))

    def test_strips_surrounding_whitespace(self):
        body, left = normalize_surface("  Atlas ")
        self.assertEqual(body, "Atlas")
        self.assertEqual(left, 2)


class CandidateTests(unittest.TestCase):
    def test_candidate_lookup_is_casefold(self):
        aliases = {"atlas": ("Q1", "Q2")}
        self.assertEqual(candidate_ids("Atlas", aliases), ("Q1", "Q2"))
        self.assertEqual(candidate_ids("missing", aliases), ())

    def test_aliases_and_profiles_come_from_registry_and_training_only(self):
        registry = [
            {"canonical_id": "Q1", "type": "entity", "key": "Q1", "label": "Atlas"},
            {"canonical_id": "Q2", "type": "entity", "key": "Q2", "label": "Atlas"},
        ]
        training = [
            {
                "plain_text": "Project Atlas launched.",
                "mentions": [{"canonical_id": "Q1", "start": 8, "end": 13}],
            }
        ]
        candidates, aliases, profiles = build_candidate_index(registry, training)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(aliases["atlas"], ("Q1", "Q2"))
        self.assertIn("Project Atlas launched.", profiles["Q1"])
        self.assertNotIn("Project Atlas launched.", profiles["Q2"])


class OverlapTests(unittest.TestCase):
    def test_longest_span_wins_and_result_is_ordered(self):
        detections = [
            Detection(start=0, end=8, candidates=("Q60",)),
            Detection(start=4, end=8, candidates=("Q61",)),
            Detection(start=17, end=21, candidates=("Q61",)),
        ]
        selected = select_non_overlapping(detections)
        self.assertEqual(
            [(item.start, item.end) for item in selected],
            [(0, 8), (17, 21)],
        )


@unittest.skipUnless(
    RUN_PATH.is_file(),
    "spaCy recorded run not generated yet (run scripts/run_spacy_linker.py on a "
    "machine with the model available)",
)
class CommittedRunTests(unittest.TestCase):
    """Runs only once the recorded artifact has been produced and committed."""

    def setUp(self):
        self.dataset_path = EXTERNAL / "test.comparison.jsonl"
        self.registry_path = EXTERNAL / "entity-registry.jsonl"
        self.cases = [Case.from_record(item) for item in load_jsonl(self.dataset_path)]
        self.registry = ResolverRegistry(load_jsonl(self.registry_path))

    def test_recorded_run_validates_and_scores(self):
        run = load_recorded_run(
            RUN_PATH,
            self.cases,
            self.registry,
            dataset_name=DATASET_NAME,
            dataset_path=self.dataset_path,
            registry_path=self.registry_path,
        )
        adapter = RecordedLinkerAdapter(run)
        predicted_any = False
        for case in self.cases:
            result = adapter.predict(case, self.registry)
            predicted_any = predicted_any or bool(result.predicted_ids)
        self.assertTrue(predicted_any, "expected at least one linked prediction")

    def test_recorded_run_hashes_match_manifest(self):
        manifest = json.loads((EXTERNAL / "manifest.json").read_text(encoding="utf-8"))
        run = json.loads(RUN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            run["dataset"]["registry_sha256"],
            manifest["derived_files"]["registry"]["sha256"],
        )
        self.assertEqual(
            run["dataset"]["sha256"],
            manifest["derived_files"]["test"]["sha256"],
        )


if __name__ == "__main__":
    unittest.main()
