"""Model-free tests for the LLM linker producer and its recorded artifact.

These tests never make a network call. They exercise the pure producer helpers
(candidate lookup, prompt building, response parsing, grounding, overlap
selection) and, if the recorded run has been generated and committed, validate
and score it through the same leakage-proof recorded-run path used in CI.
"""

import json
from pathlib import Path
import tempfile
import unittest

from eat_baselines import Case, ResolverRegistry
from eat_recorded_runs import RecordedLinkerAdapter, load_recorded_run
from scripts.run_llm_linker import (
    build_candidate_index,
    candidates_in_text,
    ground_items,
    load_inputs,
    parse_llm_json,
)

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "benchmark" / "external" / "wiki-fair-v2"
RUN_PATH = ROOT / "benchmark" / "results" / "wiki-fair-v2-llm-linker-run.json"
DATASET_NAME = "wiki-fair-v2/test-no-coref@c9a3fe9c4933888d756d702fdb9ff607fc36aa26"

REGISTRY = [
    {"canonical_id": "Q1", "type": "project", "key": "Phoenix", "label": "Phoenix"},
    {"canonical_id": "Q2", "type": "organisation", "key": "Phoenix", "label": "Phoenix"},
    {"canonical_id": "Q3", "type": "location", "key": "New_York", "label": "New York"},
    {"canonical_id": "Q4", "type": "location", "key": "York", "label": "York"},
]


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class BoundaryTests(unittest.TestCase):
    def test_load_inputs_rejects_extra_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.jsonl"
            path.write_text(
                json.dumps({"id": "c1", "plain_text": "Phoenix.", "gold_ids": ["Q1"]})
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exactly id and plain_text"):
                load_inputs(path)


class CandidateIndexTests(unittest.TestCase):
    def test_index_and_aliases_from_registry_and_training(self):
        training = [
            {
                "plain_text": "The PHX project shipped.",
                "mentions": [{"canonical_id": "Q1", "start": 4, "end": 7}],
            }
        ]
        by_id, aliases, typed_keys = build_candidate_index(REGISTRY, training)
        self.assertEqual(set(by_id), {"Q1", "Q2", "Q3", "Q4"})
        self.assertIn(("project", "Phoenix"), typed_keys)
        self.assertEqual(aliases["phoenix"], ("Q1", "Q2"))
        self.assertEqual(aliases["phx"], ("Q1",))  # dev-only alias

    def test_candidates_in_text_uses_word_boundaries(self):
        by_id, aliases, _ = build_candidate_index(REGISTRY, [])
        found = candidates_in_text("Phoenix leads Phoenix.", aliases, by_id)
        self.assertEqual(
            found,
            [
                {"type": "organisation", "key": "Phoenix", "label": "Phoenix"},
                {"type": "project", "key": "Phoenix", "label": "Phoenix"},
            ],
        )
        # "York" must not match inside "New York" only; both are separate labels.
        found_ny = candidates_in_text("New York.", aliases, by_id)
        self.assertIn({"type": "location", "key": "New_York", "label": "New York"}, found_ny)


class ParseTests(unittest.TestCase):
    def test_parses_plain_json_array(self):
        content = '[{"surface": "Phoenix", "type": "project", "key": "Phoenix"}]'
        self.assertEqual(
            parse_llm_json(content),
            [{"surface": "Phoenix", "type": "project", "key": "Phoenix"}],
        )

    def test_strips_code_fences_and_prose(self):
        content = (
            "Here you go:\n```json\n"
            '[{"surface": "York", "type": "location", "key": "York"}]\n```'
        )
        self.assertEqual(
            parse_llm_json(content),
            [{"surface": "York", "type": "location", "key": "York"}],
        )

    def test_drops_incomplete_entries_and_garbage(self):
        self.assertEqual(parse_llm_json("not json at all"), [])
        self.assertEqual(
            parse_llm_json('[{"surface": "X", "type": "t"}, {"key": "k"}]'), []
        )


class GroundTests(unittest.TestCase):
    def setUp(self):
        _, _, self.typed_keys = build_candidate_index(REGISTRY, [])

    def test_grounds_valid_item_to_exact_span(self):
        text = "The Phoenix project shipped."
        detections = ground_items(
            text,
            [{"surface": "Phoenix", "type": "project", "key": "Phoenix"}],
            self.typed_keys,
        )
        self.assertEqual(len(detections), 1)
        self.assertEqual(text[detections[0].start : detections[0].end], "Phoenix")
        self.assertEqual((detections[0].type, detections[0].key), ("project", "Phoenix"))

    def test_skips_unknown_typed_key(self):
        detections = ground_items(
            "Phoenix.",
            [{"surface": "Phoenix", "type": "person", "key": "Phoenix"}],
            self.typed_keys,
        )
        self.assertEqual(detections, [])

    def test_skips_surface_absent_from_text(self):
        detections = ground_items(
            "Nothing here.",
            [{"surface": "Phoenix", "type": "project", "key": "Phoenix"}],
            self.typed_keys,
        )
        self.assertEqual(detections, [])

    def test_longest_span_wins_on_overlap(self):
        detections = ground_items(
            "New York.",
            [
                {"surface": "New York", "type": "location", "key": "New_York"},
                {"surface": "York", "type": "location", "key": "York"},
            ],
            self.typed_keys,
        )
        self.assertEqual(
            [(d.start, d.end, d.key) for d in detections],
            [(0, 8, "New_York")],
        )


@unittest.skipUnless(
    RUN_PATH.is_file(),
    "LLM recorded run not generated yet (run scripts/run_llm_linker.py with an "
    "API key on a machine with network access)",
)
class CommittedRunTests(unittest.TestCase):
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
        predicted_any = any(
            adapter.predict(case, self.registry).predicted_ids for case in self.cases
        )
        self.assertTrue(predicted_any, "expected at least one linked prediction")

    def test_recorded_run_hashes_match_manifest(self):
        manifest = json.loads((EXTERNAL / "manifest.json").read_text(encoding="utf-8"))
        run = json.loads(RUN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            run["dataset"]["registry_sha256"],
            manifest["derived_files"]["registry"]["sha256"],
        )
        self.assertEqual(
            run["dataset"]["sha256"], manifest["derived_files"]["test"]["sha256"]
        )


if __name__ == "__main__":
    unittest.main()
