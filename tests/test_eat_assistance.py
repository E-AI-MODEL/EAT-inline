from pathlib import Path
import unittest

from eat_baselines import Case, ResolverRegistry
from eat_recorded_runs import load_recorded_run
from scripts.run_eat_assistance_benchmark import (
    DATASET_NAME,
    evaluate,
    load_jsonl,
    load_oracle_cases,
)


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmark" / "external" / "wiki-fair-v2"
RUN = ROOT / "benchmark" / "results" / "wiki-fair-v2-tfidf-linker-run.json"


class EatAssistanceBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_dataset = CORPUS / "test.comparison.jsonl"
        registry_path = CORPUS / "entity-registry.jsonl"
        cls.model_cases = [
            Case.from_record(item) for item in load_jsonl(model_dataset)
        ]
        cls.registry = ResolverRegistry(load_jsonl(registry_path))
        cls.recorded_run = load_recorded_run(
            RUN,
            cls.model_cases,
            cls.registry,
            dataset_name=DATASET_NAME,
            dataset_path=model_dataset,
            registry_path=registry_path,
        )
        cls.oracle_cases = load_oracle_cases(
            CORPUS / "test.oracle-eat.jsonl",
            cls.model_cases,
            cls.registry,
        )

    def test_zero_coverage_equals_frozen_model_run(self):
        result, _ = evaluate(
            self.recorded_run, self.oracle_cases, self.registry
        )

        self.assertEqual(
            result["model_with_oracle_eat"]["0%"],
            {
                **result["model_baseline"],
                "annotated_mentions": 0,
                "assisted_entity_cases": 0,
                "f1_delta_vs_model": 0.0,
                "false_positives_removed_vs_model": 0,
                "false_negatives_removed_vs_model": 0,
            },
        )

    def test_full_assistance_has_complete_recall_and_eat_only_is_exact(self):
        result, _ = evaluate(
            self.recorded_run, self.oracle_cases, self.registry
        )

        full = result["model_with_oracle_eat"]["100%"]
        self.assertEqual(full["recall"], 1.0)
        self.assertEqual(full["false_negatives"], 0)
        self.assertEqual(full["annotated_mentions"], 669)
        self.assertEqual(
            result["eat_only_oracle"],
            {
                "precision": 1.0,
                "recall": 1.0,
                "f1": 1.0,
                "exact_match_rate": 1.0,
                "true_positives": 444,
                "false_positives": 0,
                "false_negatives": 0,
            },
        )

    def test_assistance_curve_is_monotonic_for_this_frozen_run(self):
        result, _ = evaluate(
            self.recorded_run, self.oracle_cases, self.registry
        )
        conditions = result["model_with_oracle_eat"]
        f1_values = [
            conditions[coverage]["f1"]
            for coverage in ("0%", "25%", "50%", "75%", "100%")
        ]

        self.assertEqual(f1_values, sorted(f1_values))


if __name__ == "__main__":
    unittest.main()
