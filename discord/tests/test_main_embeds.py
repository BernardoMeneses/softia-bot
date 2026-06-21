import unittest

from bot.main import build_devs_embed, build_info_embed, build_summary_embed


class MainEmbedsTest(unittest.TestCase):
    def test_info_embed_groups_command_sections(self):
        embed = build_info_embed()
        data = embed.to_dict()

        self.assertEqual(data["title"], "Softia Command Center")
        self.assertIn("-musicinfo", data["fields"][1]["value"])
        self.assertIn("-gameinfo", data["fields"][2]["value"])

    def test_devs_embed_mentions_creator(self):
        data = build_devs_embed().to_dict()

        self.assertIn("RaiNz", data["fields"][0]["value"])

    def test_summary_embed_points_to_info(self):
        data = build_summary_embed().to_dict()

        self.assertEqual(data["title"], "Softia")
        self.assertIn("-info", data["fields"][1]["value"])


if __name__ == "__main__":
    unittest.main()
