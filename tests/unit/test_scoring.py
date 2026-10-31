import unittest
from datetime import datetime, timedelta, timezone

from workers.intelligence.classify import validate_category
from workers.intelligence.scoring import credibility_score, importance_score


class ScoringTests(unittest.TestCase):
    def test_primary_source_and_corroboration_raise_credibility(self):
        primary = credibility_score([1], 1, True, True)
        corroborated = credibility_score([1, 2], 2, True, True)
        self.assertGreater(corroborated, primary)

    def test_credibility_rejects_invalid_tier(self):
        with self.assertRaises(ValueError):
            credibility_score([4], 1, True, True)

    def test_importance_decays_with_age(self):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        recent = importance_score(now, 0.5, 0.8, "AI models", now)
        older = importance_score(now - timedelta(hours=24), 0.5, 0.8, "AI models", now)
        self.assertGreater(recent, older)

    def test_importance_rejects_unknown_category(self):
        with self.assertRaises(ValueError):
            importance_score(datetime.now(timezone.utc), 0.5, 0.8, "Other")

    def test_category_hint_is_allow_listed(self):
        self.assertEqual(validate_category("Robotics"), "Robotics")
        self.assertIsNone(validate_category("Unapproved"))


if __name__ == "__main__":
    unittest.main()
