import unittest

from eat_inline import parse, parse_references, parse_tldr_blocks, validate_reference


class EatInlineTests(unittest.TestCase):
    def test_reference_parsing(self):
        text = "Het rapport is van @@EAT person:Hans_Visser@@ voor @@EAT organisation:EAI_Analyse_Advies@@."
        refs = parse_references(text)
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].type, "person")
        self.assertEqual(refs[0].key, "Hans_Visser")
        self.assertEqual(refs[0].status, "valid-core")

    def test_unknown_type_is_extension(self):
        refs = parse_references("@@EAT research_method:Controlled_Experiment@@")
        self.assertEqual(refs[0].status, "valid-extension")

    def test_invalid_identifier(self):
        valid, code = validate_reference("@@EAT person:Hans Visser@@")
        self.assertFalse(valid)
        self.assertEqual(code, "E005 invalid_identifier")

    def test_missing_closing_marker(self):
        valid, code = validate_reference("@@EAT person:Hans_Visser")
        self.assertFalse(valid)
        self.assertEqual(code, "E006 missing_closing_marker")

    def test_tldr_block(self):
        text = "@@EAT tldr:\nEAT Inline maakt referenties expliciet.\n@@"
        blocks = parse_tldr_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].content, "EAT Inline maakt referenties expliciet.")

    def test_parse_shape(self):
        result = parse("@@EAT person:Hans_Visser@@")
        self.assertEqual(result["version"], "0.3.1")
        self.assertEqual(len(result["references"]), 1)


if __name__ == "__main__":
    unittest.main()
