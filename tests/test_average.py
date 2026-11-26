from __future__ import annotations

import unittest

from bot.commands.average import format_average_embed
from bot.fwastats import ClanSummary, MemberWeight, parse_clan_summaries


class AverageCommandTests(unittest.TestCase):
    def test_parse_clan_summaries(self) -> None:
        payload = [
            {
                "tag": "#CLAN1",
                "name": "Clan One",
                "estimatedWeight": 8000,
                "weightSubmitDate": "2026-10-29T15:00:44Z",
                "th19Count": 10,
                "th18Count": 15,
            },
            {
                "tag": "#CLAN2",
                "name": "No Weight",
                "estimatedWeight": 0,
            },
        ]
        clans = parse_clan_summaries(payload)
        self.assertEqual(len(clans), 2)
        self.assertEqual(clans[0].estimated_weight, 8000)
        self.assertEqual(clans[0].th_counts["TH19"], 10)
        self.assertIsNone(clans[1].estimated_weight)

    def test_format_average_embed(self) -> None:
        clans = [
            ClanSummary("#A", "A", 7000, None, {"TH19": 10, "TH18": 10}),
            ClanSummary("#B", "B", 8000, None, {"TH19": 12, "TH18": 14}),
            ClanSummary("#2LCUU9YYU", "The Originals", 8400, None, {"TH19": 16, "TH18": 18}),
        ]
        members = [
            MemberWeight("#1", "P1", 19, 179000, True, 1, "Co-leader"),
            MemberWeight("#2", "P2", 19, 185000, True, 2, "Member"),
        ]
        embed = format_average_embed(clans, members)
        self.assertIn("FWA Clan Median vs The Originals", embed.title or "")
        self.assertIn("TH19  |    12.0 |         1", embed.description or "")
        self.assertIn("TH18  |    14.0 |         1", embed.description or "")

        fields = {f.name: f.value for f in embed.fields}
        self.assertIn("Median: **8,000,000**", fields["FWA Weight (3/3 clans)"])
        self.assertNotIn("Mean:", fields["FWA Weight (3/3 clans)"])
        self.assertIn("In-War Weight: **364,000** (2 members)", fields["The Originals"])
        self.assertIn("vs Median: **+400,000**", fields["The Originals"])


if __name__ == "__main__":
    unittest.main()
