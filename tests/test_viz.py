"""Tests for the interaction-network renderer."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from simulation import viz

LOG = {
    "date_range": "28-29 September 2026",
    "actions": [
        {"agent": "trump", "xref": "@khamenei_ir_fa — their card",
         "statement": "s", "reasoning": "squeeze the vault",
         "action": "framework", "escalation": False},
        {"agent": "iran_hardliners", "xref": "@markets — liquidity",
         "statement": "s", "reasoning": "thin markets",
         "action": "UNGA offer", "escalation": True},
        {"agent": "eu", "xref": "@vonderleyen",
         "statement": "s", "reasoning": "",
         "action": "ceasefire track", "escalation": False},
    ],
}


class TestInteractionViz(unittest.TestCase):

    def test_handle_resolution(self):
        self.assertEqual(viz._resolve_target("@khamenei_ir_fa — x"),
                         ("iran_hardliners", "@khamenei_ir_fa"))
        self.assertEqual(viz._resolve_target("@vonderleyen"),
                         ("eu", "@vonderleyen"))
        self.assertEqual(viz._resolve_target("@random_stranger"),
                         ("FEED", "@random_stranger"))
        self.assertEqual(viz._resolve_target(""), ("FEED", ""))

    def test_render_produces_gif_and_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(viz, "OUT_DIR", tmp):
                gif, png = viz.render_interactions(LOG, 99)
        # files existed at render time; paths returned correctly
        self.assertTrue(gif.endswith("round99_interactions.gif"))
        self.assertTrue(png.endswith("round99_network.png"))

    def test_render_files_nonempty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(viz, "OUT_DIR", tmp):
                gif, png = viz.render_interactions(LOG, 99)
                self.assertGreater(os.path.getsize(gif), 1000)
                self.assertGreater(os.path.getsize(png), 1000)

    def test_empty_actions_returns_paths_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(viz, "OUT_DIR", tmp):
                gif, png = viz.render_interactions({"actions": []}, 1)
        self.assertTrue(gif and png)


if __name__ == "__main__":
    unittest.main()
