from __future__ import annotations

from datetime import datetime, timezone
import unittest

from bot.commands.average import (
    adjust_medians_to_total,
    filter_recent_weighed_clans,
    format_average_embed,
)
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

    def test_filter_recent_weighed_clans(self) -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
        clans = [
            ClanSummary("#RECENT1", "R1", 8000, "2026-11-25T10:00:00Z", {"TH19": 12}),
            ClanSummary("#RECENT2", "R2", 8200, "2026-11-19T12:00:00Z", {"TH19": 14}),
            ClanSummary("#STALE", "Stale", 7000, "2026-11-10T10:00:00Z", {"TH19": 5}),
            ClanSummary("#NODATE", "NoDate", 7500, None, {"TH19": 8}),
        ]
        recent = filter_recent_weighed_clans(clans, days=7, now=now)
        self.assertEqual([c.tag for c in recent], ["#RECENT1", "#RECENT2"])

    def test_adjust_medians_to_total_scales_up_and_down_to_50(self) -> None:
        # Raw medians: 20 + 15 + 12 = 47 (< 50), TH19 mean is 23 (> 20)
        under = adjust_medians_to_total(
            {
                "TH19": [20, 20, 29],
                "TH18": [15, 15, 16],
                "TH17": [12, 12, 12],
            },
            target_total=50,
        )
        self.assertEqual(sum(under.values()), 50)
        self.assertGreater(under["TH19"], 20)

        # Raw medians: 20 + 20 + 13 = 53 (> 50), TH17 mean is 9 (< 13)
        over = adjust_medians_to_total(
            {
                "TH19": [20, 20, 20],
                "TH18": [20, 20, 20],
                "TH17": [1, 13, 13],
            },
            target_total=50,
        )
        self.assertEqual(sum(over.values()), 50)
        self.assertEqual(over["TH17"], 10)

    def test_format_average_embed_uses_last_7_days_and_50_total(self) -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
        clans = [
            ClanSummary("#A", "A", 7800, "2026-11-24T10:00:00Z", {"TH19": 20, "TH18": 30}),
            ClanSummary("#B", "B", 8000, "2026-11-25T10:00:00Z", {"TH19": 20, "TH18": 30}),
            ClanSummary("#STALE", "Stale", 6000, "2026-10-01T10:00:00Z", {"TH19": 2, "TH18": 4}),
            ClanSummary("#2LCUU9YYU", "The Originals", 8400, "2026-10-25T10:00:00Z", {"TH19": 16, "TH18": 18}),
        ]
        members = [
            MemberWeight("#1", "P1", 19, 179000, True, 1, "Co-leader"),
            MemberWeight("#2", "P2", 19, 185000, True, 2, "Member"),
        ]
        embed = format_average_embed(clans, members, now=now)
        self.assertIn("FWA Clan Median (Last 7d) vs The Originals", embed.title or "")
        self.assertIn("TH19  |      20 |         1", embed.description or "")
        self.assertIn("TH18  |      30 |         1", embed.description or "")
        self.assertIn("Total |      50 |         2", embed.description or "")

        fields = {f.name: f.value for f in embed.fields}
        self.assertIn("Median: **7,900,000**", fields["FWA Weight (2/4 clans, 7d)"])
        self.assertIn("Projected (2/50): **364,000** (2 current)", fields["The Originals"])
        self.assertIn("vs Median: **+500,000**", fields["The Originals"])


if __name__ == "__main__":
    unittest.main()
