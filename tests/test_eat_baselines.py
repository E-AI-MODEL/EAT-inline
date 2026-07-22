import unittest

from eat_baselines import (
    AdapterResult,
    BaselineAdapter,
    Case,
    Cost,
    EatResolverAdapter,
    EntityLinker,
    GazetteerLinker,
    LinkedMention,
    LinkerAdapter,
    LinkOutput,
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
        self.assertEqual(
            [a.condition for a in adapters], ["plain", "linker", "eat_inline"]
        )
        self.assertTrue(all(not a.requires_model for a in adapters))

    def test_builtin_conditions_registered(self):
        self.assertIn("plain", registered_conditions())
        self.assertIn("linker", registered_conditions())
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


class GazetteerLinkerTests(unittest.TestCase):
    def setUp(self):
        self.registry = ResolverRegistry(REGISTRY_ENTRIES)
        self.linker = GazetteerLinker()

    def test_links_unambiguous_mention(self):
        output = self.linker.link("Hans Visser spoke.", self.registry)
        linked = [m for m in output.mentions if m.type is not None]
        self.assertEqual(len(linked), 1)
        self.assertEqual((linked[0].type, linked[0].key), ("person", "Hans_Visser"))

    def test_abstains_on_ambiguous_mention_without_cue(self):
        output = self.linker.link("They mentioned Phoenix today.", self.registry)
        phoenix = [m for m in output.mentions if m.label == "phoenix"]
        self.assertEqual(len(phoenix), 1)
        self.assertIsNone(phoenix[0].type)
        self.assertEqual(phoenix[0].candidate_count, 2)

    def test_disambiguates_with_context_type_cue(self):
        # A nearby type word ("project") resolves the ambiguity.
        output = self.linker.link("The Phoenix project shipped.", self.registry)
        phoenix = [m for m in output.mentions if m.label == "phoenix"]
        self.assertEqual(phoenix[0].type, "project")
        self.assertEqual(phoenix[0].key, "Phoenix")

    def test_uses_nearest_type_cue_for_each_mention(self):
        output = self.linker.link(
            "project Phoenix versus system Phoenix", self.registry
        )
        phoenix = [mention for mention in output.mentions if mention.label == "phoenix"]
        self.assertEqual(
            [(mention.type, mention.key) for mention in phoenix],
            [("project", "Phoenix"), ("system", "Phoenix")],
        )

    def test_does_not_match_label_inside_longer_word(self):
        registry = ResolverRegistry(
            [
                {
                    "type": "concept",
                    "key": "Art",
                    "label": "art",
                    "canonical_id": "concept-0001",
                }
            ]
        )
        output = self.linker.link("This article is about art.", registry)
        self.assertEqual(len(output.mentions), 1)
        self.assertEqual(output.mentions[0].start, 22)

    def test_prefers_longest_overlapping_label(self):
        registry = ResolverRegistry(
            [
                {
                    "type": "location",
                    "key": "York",
                    "label": "York",
                    "canonical_id": "location-0001",
                },
                {
                    "type": "location",
                    "key": "New_York",
                    "label": "New York",
                    "canonical_id": "location-0002",
                },
            ]
        )
        output = self.linker.link("New York", registry)
        self.assertEqual(len(output.mentions), 1)
        self.assertEqual(output.mentions[0].key, "New_York")

    def test_abstains_with_three_candidates_and_no_cue(self):
        registry = ResolverRegistry(
            REGISTRY_ENTRIES
            + [{"type": "system", "key": "Phoenix", "label": "Phoenix", "canonical_id": "system-0500"}]
        )
        output = GazetteerLinker().link("Phoenix appeared.", registry)
        phoenix = [m for m in output.mentions if m.label == "phoenix"]
        self.assertIsNone(phoenix[0].type)
        self.assertEqual(phoenix[0].candidate_count, 3)


class LinkerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.registry = ResolverRegistry(REGISTRY_ENTRIES)
        self.adapter = LinkerAdapter(GazetteerLinker())

    def test_condition_and_model_flag_from_linker(self):
        self.assertEqual(self.adapter.condition, "linker")
        self.assertFalse(self.adapter.requires_model)

    def test_predicts_unambiguous_and_abstains_on_ambiguous(self):
        case = Case(
            id="c1",
            plain_text="Hans Visser works on Phoenix.",
            eat_text="@@EAT person:Hans_Visser@@ works on @@EAT project:Phoenix@@.",
            gold_ids=frozenset({"person-0001", "project-0017"}),
        )
        result = self.adapter.predict(case, self.registry)
        self.assertEqual(result.predicted_ids, {"person-0001"})
        self.assertIn("phoenix", result.diagnostics["abstained_ambiguous"])
        self.assertEqual(result.diagnostics["linked"], 1)
        self.assertEqual(result.cost.registry_lookups, 3)

    def test_never_receives_author_tags(self):
        # The adapter reads plain_text only; eat_text tags must not leak in.
        case = Case(
            id="c2",
            plain_text="Nothing resolvable here.",
            eat_text="@@EAT person:Hans_Visser@@",
            gold_ids=frozenset(),
        )
        result = self.adapter.predict(case, self.registry)
        self.assertEqual(result.predicted_ids, set())


class ModelLinkerTests(unittest.TestCase):
    """A model-backed linker plugs into the same interface as the offline one."""

    def test_model_linker_requires_model_and_scores(self):
        class FakeModelLinker(EntityLinker):
            name = "fake model linker"
            requires_model = True

            def link(self, text, registry):
                # Pretend a model committed to a typed mention.
                return LinkOutput(
                    mentions=[LinkedMention("hans visser", 0, 11, "person", "Hans_Visser", 1)],
                    cost=Cost(model_calls=1, estimated_tokens=12),
                )

        adapter = LinkerAdapter(FakeModelLinker(), condition="model_linker")
        self.assertTrue(adapter.requires_model)
        result = adapter.predict(
            Case(id="c3", plain_text="Hans Visser.", eat_text="", gold_ids=frozenset({"person-0001"})),
            ResolverRegistry(REGISTRY_ENTRIES),
        )
        self.assertEqual(result.predicted_ids, {"person-0001"})
        self.assertEqual(result.cost.model_calls, 1)


if __name__ == "__main__":
    unittest.main()
