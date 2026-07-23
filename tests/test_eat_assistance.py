from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eat_baselines import Case, ResolverRegistry
from eat_recorded_runs import load_recorded_run
from scripts.run_eat_assistance_benchmark import (
    DATASET_NAME,
    evaluate,
    load_jsonl,
    load_oracle_cases,
    write_outputs,
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
                "unannotated_mentions": 669,
                "assisted_documents": 0,
                "assisted_document_entity_pairs": 0,
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
        self.assertEqual(full["unannotated_mentions"], 0)
        self.assertEqual(full["assisted_documents"], 40)
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

    def test_scope_and_coverage_counts_are_explicit(self):
        result, _ = evaluate(
            self.recorded_run, self.oracle_cases, self.registry
        )

        self.assertEqual(
            result["test_scope"],
            {
                "documents": 40,
                "mention_annotations": 669,
                "document_entity_pairs": 444,
                "unique_entities": 434,
            },
        )
        conditions = result["model_with_oracle_eat"]
        self.assertEqual(
            {
                coverage: (
                    condition["annotated_mentions"],
                    condition["unannotated_mentions"],
                    condition["assisted_documents"],
                )
                for coverage, condition in conditions.items()
            },
            {
                "0%": (0, 669, 0),
                "25%": (167, 502, 36),
                "50%": (335, 334, 37),
                "75%": (502, 167, 39),
                "100%": (669, 0, 40),
            },
        )

    def test_generated_summary_and_charts_explain_the_scale(self):
        result, rows = evaluate(
            self.recorded_run, self.oracle_cases, self.registry
        )
        model_dataset = CORPUS / "test.comparison.jsonl"
        oracle_dataset = CORPUS / "test.oracle-eat.jsonl"
        registry_path = CORPUS / "entity-registry.jsonl"

        with TemporaryDirectory() as directory:
            output = Path(directory)
            write_outputs(
                output,
                run=self.recorded_run,
                model_dataset=model_dataset,
                oracle_dataset=oracle_dataset,
                registry_path=registry_path,
                evaluation=result,
                cases=rows,
            )
            summary = (output / "eat-assistance-summary.md").read_text()
            coverage_chart = (output / "coverage-by-level.svg").read_text()
            performance_chart = (
                output / "performance-by-level.svg"
            ).read_text()

        self.assertIn("40 Wikipedia articles", summary)
        self.assertIn("669 entity mentions", summary)
        self.assertIn("It is not the share of files", summary)
        self.assertIn(
            "| Model + EAT (50%) | `335` | `334` | `37 of 40` |",
            summary,
        )
        self.assertIn("335 EAT + 334 plain · 37/40 articles", coverage_chart)
        self.assertIn("F1 rises from 0.7089 to 0.9043", performance_chart)


if __name__ == "__main__":
    unittest.main()
