import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_tfidf_linker import (
    build_model_data,
    detect_mentions,
    load_inputs,
)


class TfidfLinkerBoundaryTests(unittest.TestCase):
    def test_load_inputs_accepts_only_id_and_plain_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "id": "case-1",
                        "plain_text": "Atlas launched.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(
                load_inputs(path),
                [{"id": "case-1", "plain_text": "Atlas launched."}],
            )

    def test_load_inputs_rejects_gold_and_eat_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "id": "case-1",
                        "plain_text": "Atlas launched.",
                        "gold_ids": ["Q1"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "exactly id and plain_text"):
                load_inputs(path)

    def test_detection_uses_longest_non_overlapping_alias(self):
        detections = detect_mentions(
            "New York borders York.",
            {"new york": ("Q60",), "york": ("Q61",)},
        )

        self.assertEqual(
            [(item.start, item.end, item.candidates) for item in detections],
            [(0, 8, ("Q60",)), (17, 21, ("Q61",))],
        )

    def test_aliases_come_from_registry_and_training_only(self):
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

        candidates, aliases, profiles = build_model_data(registry, training)

        self.assertEqual(len(candidates), 2)
        self.assertEqual(aliases["atlas"], ("Q1", "Q2"))
        self.assertIn("Project Atlas launched.", profiles[0])
        self.assertNotIn("Project Atlas launched.", profiles[1])


if __name__ == "__main__":
    unittest.main()
