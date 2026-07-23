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

    def test_small_workload_runs_all_three_retrieval_routes(self):
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
        self.assertLess(
            quality["ordinary_lexical"]["hit_at_1"],
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
        self.assertIn("correct canonical entity ID", summary)
        self.assertIn("does not run embeddings", summary)
        self.assertIn("one EAT tag each", quality_chart)
        self.assertIn("Hybrid includes lexical", latency_chart)

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
        self.assertEqual(quality["eat_filtered"]["hit_at_1"], 1.0)
        self.assertEqual(quality["hybrid"]["hit_at_1"], 1.0)
        self.assertLess(quality["ordinary_lexical"]["hit_at_1"], 1.0)


if __name__ == "__main__":
    unittest.main()
