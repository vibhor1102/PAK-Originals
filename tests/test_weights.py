from __future__ import annotations

import unittest

from bot.commands.weights import format_weights_embed, sort_members_by_weight
from bot.fwastats import FwaStatsError, MemberWeight, normalize_tag, parse_member_weights, weight_to_th_band


class FwaStatsParsingTests(unittest.TestCase):
    def test_normalize_tag(self) -> None:
        self.assertEqual(normalize_tag("2lcuu9yyu"), "#2LCUU9YYU")
        self.assertEqual(normalize_tag(" #2LCUU9YYU "), "#2LCUU9YYU")
        with self.assertRaises(ValueError):
            normalize_tag("   ")

    def test_weight_to_th_band_boundaries(self) -> None:
        self.assertIsNone(weight_to_th_band(None))
        self.assertIsNone(weight_to_th_band(0))
        self.assertEqual(weight_to_th_band(170_000), 17)
        self.assertEqual(weight_to_th_band(170_001), 18)
        self.assertEqual(weight_to_th_band(180_000), 18)
        self.assertEqual(weight_to_th_band(180_001), 19)
        self.assertEqual(weight_to_th_band(190_000), 19)

    def test_parse_member_weights_valid_payload(self) -> None:
        payload = [
            {
                "tag": "#LPCUP8LL",
                "name": "Tom7363",
                "role": "Co-leader",
                "rank": 1,
                "townHall": 19,
                "weight": 179000,
                "inWar": True,
            },
            {
                "tag": "#ABC",
                "name": "Alt",
                "townHall": 15,
                "weight": None,
                "inWar": False,
            },
        ]
        members = parse_member_weights(payload)
        self.assertEqual(len(members), 2)
        self.assertEqual(members[0].name, "Tom7363")
        self.assertEqual(members[0].weight, 179000)
        self.assertTrue(members[0].in_war)
        self.assertIsNone(members[1].weight)
        self.assertFalse(members[1].in_war)

    def test_parse_member_weights_rejects_non_list(self) -> None:
        with self.assertRaises(FwaStatsError):
            parse_member_weights({"error": "bad"})


class WeightsFormattingTests(unittest.TestCase):
    def test_sort_and_format_embed(self) -> None:
        members = [
            MemberWeight("#2", "Lower", 16, 150000, False, 2, "Member"),
            MemberWeight("#1", "Top", 19, 179000, True, 1, "Co-leader"),
            MemberWeight("#3", "Unweighed", 14, None, False, 3, "Member"),
        ]
        sorted_members = sort_members_by_weight(members)
        self.assertEqual([m.name for m in sorted_members], ["Top", "Lower", "Unweighed"])

        embed = format_weights_embed(members)
        self.assertIn("The Originals (#2LCUU9YYU)", embed.title or "")
        self.assertIn("1.* TH18 | 179,000 | Top (TH19)", embed.description or "")
        self.assertIn("2.  TH15 | 150,000 | Lower (TH16)", embed.description or "")
        self.assertIn("3.  TH?? |     N/A | Unweighed", embed.description or "")

        fields = {f.name: f.value for f in embed.fields}
        self.assertEqual(fields["Members"], "3 (1 in war)")
        self.assertEqual(fields["In-War Weight"], "179,000")
        self.assertEqual(fields["Total Roster Weight"], "329,000")
        self.assertEqual(fields["Weight-Band THs (In War)"], "TH18: 1")


if __name__ == "__main__":
    unittest.main()
