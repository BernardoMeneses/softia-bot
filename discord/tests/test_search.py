import unittest

from bot.search import _result_from_ddgs_item


class SearchTest(unittest.TestCase):
    def test_result_from_ddgs_item(self):
        result = _result_from_ddgs_item(
            {"title": "Example", "href": "https://example.com", "body": "Snippet"}
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "Example")
        self.assertEqual(result.url, "https://example.com")
        self.assertEqual(result.snippet, "Snippet")

    def test_result_from_ddgs_item_rejects_invalid_url(self):
        self.assertIsNone(_result_from_ddgs_item({"title": "Example", "href": "javascript:void(0)"}))


if __name__ == "__main__":
    unittest.main()
