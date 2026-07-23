import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_one_tag_rag_benchmark import (
    BENCHMARK_NAME,
    build_prototypes,
    load_jsonl,
    run_benchmark,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmark" / "external" / "wiki-fair-v2"
RECORDED_RESULT = (
    ROOT
    / "benchmark"
    / "results"
    / "wiki-fair-v2-one-tag-rag"
    / "one-tag-rag-results.json"
)


class OneTagRagBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle_path = CORPUS / "test.oracle-eat.jsonl"
        cls.registry_path = CORPUS / "entity-registry.jsonl"
        cls.source_records = load_jsonl(cls.oracle_path)
        cls.registry_records = load_jsonl(cls.registry_path)

    def test_prototypes_contain_exactly_one_reference(self):
        prototypes = build_prototypes(
            self.source_records,
            self.registry_records,
        )

        self.assertEqual(len(prototypes), 669)
        self.assertEqual(
            len({item.source_id for item in prototypes}),
            40,
        )
        self.assertEqual(
            len({item.entity_id for item in prototypes}),
            434,
        )
        self.assertTrue(
            all(item.eat_text.count("@@EAT ") == 1 for item in prototypes)
        )
        self.assertTrue(
            all(item.entity_id in item.context_entity_ids for item in prototypes)
        )

    def test_small_workload_runs_all_four_retrieval_routes(self):
        result = run_benchmark(
            source_records=self.source_records,
            registry_records=self.registry_records,
            document_count=1_338,
            top_k=10,
            query_rounds=1,
            hybrid_candidates=100,
        )

        workload = result["workload"]
        quality = result["retrieval"]["quality"]
        self.assertEqual(workload["generated_documents"], 1_338)
        self.assertEqual(workload["eat_references"], 1_338)
        self.assertEqual(
            workload["documents_with_exactly_one_eat_reference"],
            1_338,
        )
        self.assertEqual(workload["eat_references_per_document"], 1.0)
        self.assertEqual(result["questions"]["count"], 434)
        self.assertEqual(
            set(quality),
            {
                "ordinary_lexical",
                "inferred_eat",
                "eat_filtered",
                "hybrid",
            },
        )
        self.assertLess(
            quality["ordinary_lexical"]["hit_at_1"],
            quality["inferred_eat"]["hit_at_1"],
        )
        self.assertLessEqual(
            quality["inferred_eat"]["hit_at_1"],
            quality["eat_filtered"]["hit_at_1"],
        )
        self.assertEqual(quality["eat_filtered"]["hit_at_1"], 1.0)
        self.assertEqual(quality["hybrid"]["hit_at_1"], 1.0)
        self.assertEqual(
            quality["eat_filtered"]["source_answer_exact_match"],
            1.0,
        )
        self.assertEqual(
            quality["hybrid"]["source_answer_exact_match"],
            1.0,
        )
        resolution = result["questions"]["query_identity_resolution"]
        self.assertEqual(resolution["unique"], 427)
        self.assertEqual(resolution["ambiguous"], 7)
        self.assertEqual(resolution["unresolved"], 0)
        self.assertEqual(resolution["correct"], 427)
        self.assertEqual(resolution["incorrect"], 0)
        self.assertEqual(resolution["lexical_fallbacks"], 7)
        self.assertEqual(resolution["coverage"], 0.9839)
        self.assertEqual(resolution["accuracy_when_resolved"], 1.0)

    def test_all_ambiguous_labels_report_zero_coverage(self):
        source_records = [
            {
                "id": "all-ambiguous",
                "plain_text": "Alpha page\nAlpha appears here.",
                "annotations": [
                    {
                        "start": 11,
                        "end": 16,
                        "type": "entity",
                        "key": "Q900001",
                    }
                ],
            }
        ]
        registry_records = [
            {
                "canonical_id": "Q900001",
                "key": "Q900001",
                "label": "Alpha",
                "same_as": [],
                "type": "entity",
            },
            {
                "canonical_id": "Q900002",
                "key": "Q900002",
                "label": "Alpha",
                "same_as": [],
                "type": "entity",
            },
        ]

        result = run_benchmark(
            source_records=source_records,
            registry_records=registry_records,
            document_count=1,
            top_k=1,
            query_rounds=1,
            hybrid_candidates=1,
        )

        resolution = result["questions"]["query_identity_resolution"]
        self.assertEqual(resolution["unique"], 0)
        self.assertEqual(resolution["ambiguous"], 1)
        self.assertEqual(resolution["coverage"], 0.0)
        self.assertIsNone(resolution["accuracy_when_resolved"])
        self.assertEqual(resolution["lexical_fallbacks"], 1)

    def test_invalid_workload_and_search_sizes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "document_count"):
            run_benchmark(
                source_records=self.source_records,
                registry_records=self.registry_records,
                document_count=668,
                top_k=10,
                query_rounds=1,
                hybrid_candidates=100,
            )
        with self.assertRaisesRegex(ValueError, "hybrid_candidates"):
            run_benchmark(
                source_records=self.source_records,
                registry_records=self.registry_records,
                document_count=669,
                top_k=10,
                query_rounds=1,
                hybrid_candidates=9,
            )

    def test_outputs_state_the_oracle_and_llm_boundaries(self):
        result = run_benchmark(
            source_records=self.source_records,
            registry_records=self.registry_records,
            document_count=1_338,
            top_k=10,
            query_rounds=1,
            hybrid_candidates=100,
        )
        with TemporaryDirectory() as directory:
            output = Path(directory)
            write_outputs(
                output,
                oracle_path=self.oracle_path,
                registry_path=self.registry_path,
                result=result,
                command="test command",
            )
            artifact = json.loads(
                (output / "one-tag-rag-results.json").read_text(
                    encoding="utf-8"
                )
            )
            summary = (output / "one-tag-rag-summary.md").read_text(
                encoding="utf-8"
            )
            quality_chart = (output / "retrieval-quality.svg").read_text(
                encoding="utf-8"
            )
            latency_chart = (output / "retrieval-latency.svg").read_text(
                encoding="utf-8"
            )

        self.assertEqual(artifact["benchmark"], BENCHMARK_NAME)
        self.assertIn("Matching a name without the answer ID", summary)
        self.assertIn("427 of 434 labels resolved uniquely", summary)
        self.assertIn("does not run embeddings", summary)
        self.assertIn("one EAT tag each", quality_chart)
        self.assertIn("Name match includes the registry lookup", latency_chart)

    def test_committed_result_records_the_full_workload(self):
        artifact = json.loads(RECORDED_RESULT.read_text(encoding="utf-8"))
        result = artifact["result"]
        workload = result["workload"]
        quality = result["retrieval"]["quality"]

        self.assertEqual(artifact["benchmark"], BENCHMARK_NAME)
        self.assertEqual(workload["generated_documents"], 100_000)
        self.assertEqual(workload["eat_references"], 100_000)
        self.assertEqual(
            workload["documents_with_exactly_one_eat_reference"],
            100_000,
        )
        self.assertEqual(workload["eat_references_per_document"], 1.0)
        self.assertEqual(workload["different_passage_prototypes"], 669)
        self.assertEqual(workload["different_source_documents"], 40)
        self.assertEqual(workload["different_entities"], 434)
        self.assertEqual(
            result["questions"]["query_identity_resolution"]["unique"],
            427,
        )
        self.assertEqual(
            result["questions"]["query_identity_resolution"]["ambiguous"],
            7,
        )
        self.assertEqual(
            result["questions"]["query_identity_resolution"]["incorrect"],
            0,
        )
        self.assertGreater(
            quality["inferred_eat"]["hit_at_1"],
            quality["ordinary_lexical"]["hit_at_1"],
        )
        self.assertEqual(quality["eat_filtered"]["hit_at_1"], 1.0)
        self.assertEqual(quality["hybrid"]["hit_at_1"], 1.0)
        self.assertLess(quality["ordinary_lexical"]["hit_at_1"], 1.0)


if __name__ == "__main__":
    unittest.main()
