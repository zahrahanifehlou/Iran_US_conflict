"""Tests for the swarm consensus layer. Run: python3 -m unittest discover -s tests -v"""

from __future__ import annotations

import unittest

from simulation import swarm


def _vote(aid, pw=None, pd=None, bd=None, hits=0, n=0):
    return {"agent_id": aid, "p_war": pw, "p_deal": pd, "brent_dir": bd,
            "skill": (hits / n) if n >= 3 else 0.5, "n_graded": n}


class TestVoteCollection(unittest.TestCase):

    def test_collect_votes_normalizes_and_uses_track_record(self):
        class A:  # minimal agent stub
            def __init__(self, stats): self.pred_stats = stats
        learning = {
            "trump": {"p_war": 8, "p_deal": 2, "brent_dir": "UP"},
            "eu": {"p_war": 3, "p_deal": 7, "brent_dir": "down"},
            "ghost": {},                                   # no call -> skipped
        }
        agents = {"trump": A({"n": 10, "hits": 8}),        # proven forecaster
                  "eu": A({"n": 0, "hits": 0}),            # unproven
                  "ghost": A({})}
        votes = swarm.collect_votes(learning, agents)
        self.assertEqual(len(votes), 2)
        tv = next(v for v in votes if v["agent_id"] == "trump")
        ev = next(v for v in votes if v["agent_id"] == "eu")
        self.assertEqual(tv["p_war"], 0.8)                 # /10 normalized
        self.assertEqual(tv["brent_dir"], "up")            # lowercased
        self.assertAlmostEqual(tv["skill"], 0.8)           # 8/10 track record
        self.assertEqual(ev["skill"], 0.5)                 # neutral weight

    def test_empty_learning_gives_no_votes(self):
        out = swarm.swarm_consensus(swarm.collect_votes({}, {}))
        self.assertEqual(out["state"], "no votes")


class TestConvergence(unittest.TestCase):

    def test_unanimous_converges_with_zero_dispersion(self):
        votes = [_vote("a", 0.4, 0.6, "up", 9, 10),
                 _vote("b", 0.4, 0.6, "up", 9, 10),
                 _vote("c", 0.4, 0.6, "up", 1, 10)]
        out = swarm.swarm_consensus(votes)
        self.assertAlmostEqual(out["p_war_72h"]["value"], 0.4, places=3)
        self.assertAlmostEqual(out["p_war_72h"]["dispersion"], 0.0, places=3)
        self.assertAlmostEqual(out["conviction"], 1.0)
        self.assertEqual(out["brent_dir"]["direction"], "up")

    def test_low_skill_voter_is_pulled_toward_skilled_consensus(self):
        # two proven forecasters agree at 0.8; one rookie says 0.1
        votes = [_vote("vet1", 0.8, None, None, 9, 10),
                 _vote("vet2", 0.8, None, None, 8, 10),
                 _vote("rookie", 0.1, None, None, 0, 0)]
        out = swarm.swarm_consensus(votes)
        val = out["p_war_72h"]["value"]
        # consensus must be much closer to 0.8 than the naive mean (0.567)
        self.assertGreater(val, 0.65)
        # and the rookie's final position moved substantially
        self.assertGreater(out["p_war_72h"]["final_positions"][-1], 0.3)

    def test_brent_plurality_skill_weighted(self):
        votes = [_vote("a", None, None, "up", 9, 10),       # expert: up
                 _vote("d", None, None, "up", 9, 10),       # expert: up
                 _vote("b", None, None, "down", 0, 0),      # rookie: down
                 _vote("c", None, None, "down", 0, 0)]      # rookie: down
        out = swarm.swarm_consensus(votes)
        # experts 2x1.4 vs rookies 2x1.0 -> up wins on skill
        self.assertEqual(out["brent_dir"]["direction"], "up")
        self.assertGreater(out["brent_dir"]["share"], 0.5)

    def test_single_voter_passes_through(self):
        out = swarm.swarm_consensus([_vote("a", 0.7, 0.3, "flat")])
        self.assertEqual(out["p_war_72h"]["value"], 0.7)
        self.assertEqual(out["p_war_72h"]["n"], 1)

    def test_deterministic(self):
        votes = [_vote("a", 0.2, 0.9, "up", 5, 10),
                 _vote("b", 0.8, 0.1, "down", 5, 10)]
        self.assertEqual(swarm.swarm_consensus(votes),
                         swarm.swarm_consensus(votes))


class TestJevComparison(unittest.TestCase):

    def test_gap_computed_when_both_present(self):
        sw = {"p_war_72h": {"value": 0.6}, "p_deal_7d": {"value": 0.4}}
        verdict = {"p_war_72h": {"value": 0.2},
                   "p_deal_7d": {"value": 0.9}}
        gaps = swarm.compare_with_jev(sw, verdict)
        self.assertAlmostEqual(gaps["p_war_72h"], 0.4)
        self.assertAlmostEqual(gaps["p_deal_7d"], 0.5)

    def test_gap_absent_when_values_missing(self):
        self.assertEqual(swarm.compare_with_jev({}, {}), {})


if __name__ == "__main__":
    unittest.main()


class TestDaemonSchedule(unittest.TestCase):
    """The scheduler must fire when a 12h mark is crossed, not only when
    a check lands inside a 1-second window before it."""

    def test_mark_due_on_approach(self):
        from simulation import daemon
        self.assertTrue(daemon._mark_due(prev=25.0, remaining=0.8))

    def test_mark_due_on_overshoot(self):
        from simulation import daemon
        # slept 30s from 00:00-05s -> woke at 00:00+25s; remaining jumped
        # to ~12h because the mark is now in the past
        self.assertTrue(daemon._mark_due(prev=5.0, remaining=43175.0))

    def test_not_due_mid_wait(self):
        from simulation import daemon
        self.assertFalse(daemon._mark_due(prev=43100.0, remaining=43070.0))
        self.assertFalse(daemon._mark_due(prev=None, remaining=50000.0))
