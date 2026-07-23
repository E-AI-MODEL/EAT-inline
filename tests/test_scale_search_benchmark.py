import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eat_baselines import ResolverRegistry
from scripts.run_scale_search_benchmark import (
    BENCHMARK_NAME,
    load_jsonl,
    resolve_source_documents,
    run_benchmark,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmark" / "external" / "wiki-fair-v2"
RECORDED_RESULT = (
    ROOT
    / "benchmark"
    / "results"
    / "wiki-fair-v2-scale-search"
    / "scale-search-results.json"
)


class ScaleSearchBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle_path = CORPUS / "test.oracle-eat.jsonl"
        cls.registry_path = CORPUS / "entity-registry.jsonl"
        cls.registry = ResolverRegistry(load_jsonl(cls.registry_path))
        cls.sources = resolve_source_documents(
            load_jsonl(cls.oracle_path),
            cls.registry,
        )

    def test_small_workload_preserves_all_counts_and_index_contents(self):
        result = run_benchmark(
            sources=self.sources,
            registry=self.registry,
            document_count=400,
            query_repetitions=3,
            query_rounds=2,
        )

        self.assertEqual(
            result["workload"],
            {
                "generated_documents": 400,
                "different_source_documents": 40,
                "generation_method": (
                    "repeat the 40 source documents in deterministic order "
                    "and assign each workload copy a distinct integer document ID"
                ),
                "different_entities": 434,
                "plain_text_bytes": 1_039_640,
                "eat_text_bytes": 1_107_010,
                "eat_references": 6_690,
                "document_entity_pairs": 4_440,
                "eat_markup_extra_bytes": 67_370,
            },
        )
        self.assertTrue(result["index"]["indexes_identical"])
        self.assertEqual(result["index"]["postings"], 4_440)
        self.assertEqual(result["index"]["postings_payload_bytes"], 17_760)
        self.assertEqual(
            result["entity_lookup"]["index_lookup_only"]["metadata_control"][
                "checksum"
            ],
            result["entity_lookup"]["index_lookup_only"]["eat_inline"][
                "checksum"
            ],
        )
        self.assertEqual(
            result["entity_lookup"]["lookup_and_read_all_results"][
                "metadata_control"
            ]["checksum"],
            result["entity_lookup"]["lookup_and_read_all_results"][
                "eat_inline"
            ]["checksum"],
        )

    def test_invalid_workload_size_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "document_count"):
            run_benchmark(
                sources=self.sources,
                registry=self.registry,
                document_count=0,
                query_repetitions=1,
                query_rounds=1,
            )

    def test_outputs_state_the_scale_and_limits(self):
        result = run_benchmark(
            sources=self.sources,
            registry=self.registry,
            document_count=400,
            query_repetitions=2,
            query_rounds=1,
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
            artifact = (output / "scale-search-results.json").read_text()
            summary = (output / "scale-search-summary.md").read_text()
            overview = (output / "scale-overview.svg").read_text()
            latency = (output / "search-latency.svg").read_text()

        self.assertIn(BENCHMARK_NAME, artifact)
        self.assertIn("400 generated workload documents", summary)
        self.assertIn("40 different Wikipedia source pages", summary)
        self.assertIn(
            "not a 400-different-source-document test",
            summary,
        )
        self.assertIn("Generated documents", overview)
        self.assertIn("canonical-entity lookup", latency)

    def test_committed_result_records_the_full_workload(self):
        artifact = json.loads(RECORDED_RESULT.read_text(encoding="utf-8"))
        result = artifact["result"]
        workload = result["workload"]
        scan = result["entity_lookup"]["lookup_and_read_all_results"]

        self.assertEqual(artifact["benchmark"], BENCHMARK_NAME)
        self.assertEqual(workload["generated_documents"], 100_000)
        self.assertEqual(workload["different_source_documents"], 40)
        self.assertEqual(workload["eat_references"], 1_672_500)
        self.assertEqual(workload["document_entity_pairs"], 1_110_000)
        self.assertTrue(result["index"]["indexes_identical"])
        self.assertEqual(
            scan["metadata_control"]["document_ids_read"],
            22_200_000,
        )
        self.assertEqual(
            scan["metadata_control"]["checksum"],
            scan["eat_inline"]["checksum"],
        )
        self.assertEqual(scan["metadata_control"]["rounds"], 20)
        self.assertGreater(result["index_build"]["eat_inline_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
