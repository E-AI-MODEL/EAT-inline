import unittest

from eat_baselines import (
    AdapterResult,
    BaselineAdapter,
    Case,
    Cost,
    EatResolverAdapter,
    PlainLabelMatchAdapter,
    ResolverRegistry,
    default_adapters,
    get_adapter,
    register_adapter,
    registered_conditions,
)


REGISTRY_ENTRIES = [
    {"type": "person", "key": "Hans_Visser", "label": "Hans Visser", "canonical_id": "person-0001"},
    {"type": "organisation", "key": "EAI_Analyse_Advies", "label": "EAI Analyse & Advies", "canonical_id": "organisation-0001"},
    # Deliberately ambiguous label shared by two entities.
    {"type": "project", "key": "Phoenix", "label": "Phoenix", "canonical_id": "project-0017"},
    {"type": "system", "key": "Phoenix", "label": "Phoenix", "canonical_id": "system-0099"},
]


class ResolverRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ResolverRegistry(REGISTRY_ENTRIES)

    def test_typed_lookup(self):
        self.assertEqual(
            self.registry.resolve_typed("person", "Hans_Visser"), "person-0001"
        )
        self.assertIsNone(self.registry.resolve_typed("person", "Unknown"))

    def test_ambiguous_label_has_multiple_candidates(self):
        self.assertEqual(len(self.registry.by_label["phoenix"]), 2)


class PlainLabelMatchAdapterTests(unittest.TestCase):
    def setUp(self):
        self.registry = ResolverRegistry(REGISTRY_ENTRIES)
        self.adapter = PlainLabelMatchAdapter()

    def test_resolves_unambiguous_label(self):
        case = Case(
            id="c1",
            plain_text="Hans Visser wrote it.",
            eat_text="@@EAT person:Hans_Visser@@ wrote it.",
            gold_ids=frozenset({"person-0001"}),
        )
        result = self.adapter.predict(case, self.registry)
        self.assertEqual(result.predicted_ids, {"person-0001"})
        self.assertEqual(result.diagnostics["ambiguous_mentions"], 0)

    def test_ambiguous_label_is_reported_not_guessed(self):
        case = Case(
            id="c2",
            plain_text="The Phoenix launch.",
            eat_text="The @@EAT project:Phoenix@@ launch.",
            gold_ids=frozenset({"project-0017"}),
        )
        result = self.adapter.predict(case, self.registry)
        self.assertEqual(result.predicted_ids, set())
        self.assertEqual(result.diagnostics["ambiguous_mentions"], 1)
        self.assertEqual(result.diagnostics["ambiguous_labels"], ["phoenix"])


class EatResolverAdapterTests(unittest.TestCase):
    def setUp(self):
        self.registry = ResolverRegistry(REGISTRY_ENTRIES)
        self.adapter = EatResolverAdapter()

    def test_typed_reference_resolves_ambiguous_label(self):
        case = Case(
            id="c3",
            plain_text="The Phoenix launch.",
            eat_text="The @@EAT project:Phoenix@@ launch.",
            gold_ids=frozenset({"project-0017"}),
        )
        result = self.adapter.predict(case, self.registry)
        self.assertEqual(result.predicted_ids, {"project-0017"})
        self.assertEqual(result.diagnostics["unresolved"], 0)
        self.assertEqual(result.cost.references_read, 1)

    def test_unknown_reference_is_unresolved_not_guessed(self):
        case = Case(
            id="c4",
            plain_text="Unknown.",
            eat_text="@@EAT person:Nobody@@",
            gold_ids=frozenset(),
        )
        result = self.adapter.predict(case, self.registry)
        self.assertEqual(result.predicted_ids, set())
        self.assertEqual(result.diagnostics["unresolved"], 1)
        self.assertEqual(result.diagnostics["unresolved_references"], ["@@EAT person:Nobody@@"])


class FrameworkTests(unittest.TestCase):
    def test_default_adapters_are_ordered_and_model_free(self):
        adapters = default_adapters()
        self.assertEqual([a.condition for a in adapters], ["plain", "eat_inline"])
        self.assertTrue(all(not a.requires_model for a in adapters))

    def test_builtin_conditions_registered(self):
        self.assertIn("plain", registered_conditions())
        self.assertIn("eat_inline", registered_conditions())
        self.assertIs(type(get_adapter("plain")), PlainLabelMatchAdapter)

    def test_duplicate_condition_rejected(self):
        with self.assertRaises(ValueError):
            register_adapter(PlainLabelMatchAdapter())

    def test_cost_accumulates(self):
        total = Cost()
        total.add(Cost(registry_lookups=2, estimated_tokens=5))
        total.add(Cost(registry_lookups=3, model_calls=1))
        self.assertEqual(total.registry_lookups, 5)
        self.assertEqual(total.model_calls, 1)
        self.assertEqual(total.estimated_tokens, 5)

    def test_model_adapter_plugs_into_interface(self):
        class FakeModelAdapter(BaselineAdapter):
            name = "example model adapter"
            condition = "example_model"
            requires_model = True

            def predict(self, case, registry):
                return AdapterResult(
                    predicted_ids=set(),
                    diagnostics={},
                    cost=Cost(model_calls=1, estimated_tokens=10),
                )

        adapter = FakeModelAdapter()
        self.assertTrue(adapter.requires_model)
        result = adapter.predict(
            Case(id="c5", plain_text="", eat_text="", gold_ids=frozenset()),
            ResolverRegistry(REGISTRY_ENTRIES),
        )
        self.assertEqual(result.cost.model_calls, 1)


if __name__ == "__main__":
    unittest.main()
