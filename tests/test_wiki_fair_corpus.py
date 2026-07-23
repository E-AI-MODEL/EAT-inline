import hashlib
import json
from pathlib import Path
import unittest

from eat_inline import parse_references


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmark" / "external" / "wiki-fair-v2"


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class WikiFairCorpusTests(unittest.TestCase):
    def test_manifest_hashes_and_counts_match_frozen_files(self):
        manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
        expected_counts = {
            "training": "training_articles",
            "inputs": "test_input_articles",
            "test": "test_articles",
            "oracle": "oracle_test_articles",
            "registry": "registry_entities",
        }
        for name, count_name in expected_counts.items():
            entry = manifest["derived_files"][name]
            path = CORPUS / entry["path"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, entry["sha256"])
            self.assertEqual(len(load_jsonl(path)), manifest["records"][count_name])

    def test_training_and_test_article_ids_are_disjoint(self):
        training_ids = {item["id"] for item in load_jsonl(CORPUS / "dev.training.jsonl")}
        test_ids = {item["id"] for item in load_jsonl(CORPUS / "test.comparison.jsonl")}

        self.assertTrue(training_ids)
        self.assertTrue(test_ids)
        self.assertTrue(training_ids.isdisjoint(test_ids))

    def test_inference_file_contains_no_scoring_fields(self):
        inputs = load_jsonl(CORPUS / "test.inputs.jsonl")
        comparison = load_jsonl(CORPUS / "test.comparison.jsonl")

        self.assertTrue(all(set(item) == {"id", "plain_text"} for item in inputs))
        self.assertEqual(
            [(item["id"], item["plain_text"]) for item in inputs],
            [(item["id"], item["plain_text"]) for item in comparison],
        )

    def test_registry_uses_typed_wikidata_keys(self):
        registry = load_jsonl(CORPUS / "entity-registry.jsonl")
        self.assertEqual(len({item["key"] for item in registry}), len(registry))
        self.assertTrue(all(item["type"] == "entity" for item in registry))
        self.assertTrue(all(item["key"].startswith("Q") for item in registry))

    def test_oracle_eat_references_cover_every_gold_id(self):
        oracle = load_jsonl(CORPUS / "test.oracle-eat.jsonl")
        annotation_count = 0
        for item in oracle:
            annotations = item["annotations"]
            annotation_count += len(annotations)
            self.assertEqual(
                {annotation["key"] for annotation in annotations},
                set(item["gold_ids"]),
            )
            self.assertEqual(
                {reference.key for reference in parse_references(item["eat_text"])},
                set(item["gold_ids"]),
            )
            spans = sorted(
                (annotation["start"], annotation["end"])
                for annotation in annotations
            )
            self.assertTrue(
                all(left[1] <= right[0] for left, right in zip(spans, spans[1:]))
            )
        self.assertEqual(annotation_count, 669)


if __name__ == "__main__":
    unittest.main()
