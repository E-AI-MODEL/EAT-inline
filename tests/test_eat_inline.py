import unittest

from eat_inline import parse, parse_references, validate_reference


class EatInlineTests(unittest.TestCase):
    def test_reference_parsing(self):
        text = "Het rapport is van @@EAT person:Hans_Visser@@ voor @@EAT organisation:EAI_Analyse_Advies@@."
        refs = parse_references(text)
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].type, "person")
        self.assertEqual(refs[0].key, "Hans_Visser")
        self.assertEqual(refs[1].type, "organisation")

    def test_unknown_type_is_still_syntactically_valid(self):
        refs = parse_references("@@EAT research_method:Controlled_Experiment@@")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].type, "research_method")

    def test_invalid_identifier(self):
        valid, code = validate_reference("@@EAT person:Hans Visser@@")
        self.assertFalse(valid)
        self.assertEqual(code, "invalid_identifier")

    def test_missing_closing_marker(self):
        valid, code = validate_reference("@@EAT person:Hans_Visser")
        self.assertFalse(valid)
        self.assertEqual(code, "missing_closing_marker")

    def test_parse_shape(self):
        result = parse("@@EAT person:Hans_Visser@@")
        self.assertEqual(result["version"], "0.3.2")
        self.assertEqual(len(result["references"]), 1)
        self.assertNotIn("tldr", result)


if __name__ == "__main__":
    unittest.main()
