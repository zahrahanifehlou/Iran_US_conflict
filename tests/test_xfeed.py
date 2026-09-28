"""Tests for the social feed layer — all network access is mocked.

Run:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

from simulation import xfeed
from simulation.xfeed import (
    BlueskyPublicFeed, RealFeedUnavailable, RealPublicXFeed,
    SyntheticXFeed, XPost,
)

CFG = {
    "provider": "real",
    "query": "Iran OR Israel",
    "max_posts": 50,
    "cache": True,
    "cache_ttl_hours": 12,
    "accounts": ["realDonaldTrump"],
    "nitter_instances": ["nitter.test"],
    "timeout": 5,
}

# ------------------------------------------------------------ fixtures

SYNDICATION_HTML = """
<html><body><script id="__NEXT_DATA__" type="application/json">
{"props": {"pageProps": {"timeline": {"entries": [
  {"entryId": "tweet-1901", "content": {"tweet": {
      "id_str": "1901", "full_text": "Iran must come to the table or face consequences, believe me!",
      "created_at": "Sun Sep 28 10:00:00 +0000 2026",
      "user": {"screen_name": "realDonaldTrump"}}}},
  {"entryId": "tweet-1902", "content": {"tweet": {
      "id_str": "1902", "full_text": "Iran deal talks continue at the UN.",
      "created_at": "Sun Sep 28 11:00:00 +0000 2026",
      "user": {"screen_name": "realDonaldTrump"}}}},
  {"entryId": "tweet-1903", "content": {"tweet": {
      "id_str": "1901", "full_text": "Iran must come to the table or face consequences, believe me!",
      "created_at": "Sun Sep 28 10:00:00 +0000 2026",
      "user": {"screen_name": "realDonaldTrump"}}}},
  {"entryId": "ad-1", "content": {"tweet": {
      "id_str": "9999", "full_text": "ad",
      "created_at": "", "user": {"screen_name": "promoted"}}}}
]}}}}
</script></body></html>
"""

NITTER_RSS = """<?xml version="1.0"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
<channel><title>Search</title>
<item><title>Israel strikes reported overnight</title>
<link>https://nitter.test/osintguy/status/3001</link>
<dc:creator>@osintguy</dc:creator>
<pubDate>Sun, 28 Sep 2026 12:00:00 GMT</pubDate>
<description>Israel strikes reported near Natanz overnight, multiple sources.</description></item>
<item><title>unrelated food post</title>
<link>https://nitter.test/foodie/status/3002</link>
<dc:creator>@foodie</dc:creator>
<pubDate>Sun, 28 Sep 2026 12:30:00 GMT</pubDate>
<description>Best pizza recipe ever, pineapple belongs everywhere.</description></item>
</channel></rss>
"""

BSKY_JSON = {
    "posts": [
        {"uri": "at://did:plc:x/app.bsky.feed.post/abc",
         "cid": "cid-aaa",
         "author": {"handle": "watcher.bsky.social"},
         "record": {"text": "Iran diplomatic track moving at UNGA.",
                    "createdAt": "2026-09-28T09:00:00Z"}},
        {"uri": "at://did:plc:y/app.bsky.feed.post/def",
         "cid": "cid-bbb",
         "author": {"handle": "foodie.bsky.social"},
         "record": {"text": "Lunch was nice today.",
                    "createdAt": "2026-09-28T09:05:00Z"}},
        {"uri": "at://did:plc:x/app.bsky.feed.post/abc",
         "cid": "cid-aaa",
         "author": {"handle": "watcher.bsky.social"},
         "record": {"text": "Iran diplomatic track moving at UNGA.",
                    "createdAt": "2026-09-28T09:00:00Z"}},
    ]
}


class FeedTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._dir_patch = mock.patch.object(
            xfeed, "_cache_dir", return_value=self._tmp)
        self._dir_patch.start()

    def tearDown(self):
        self._dir_patch.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestParsing(FeedTestBase):

    def test_syndication_html_parses_embedded_json(self):
        posts = xfeed._parse_syndication_html(SYNDICATION_HTML)
        self.assertEqual(len(posts), 4)          # incl. duplicate + ad
        p = posts[0]
        self.assertEqual(p.post_id, "1901")
        self.assertEqual(p.handle, "realDonaldTrump")
        self.assertEqual(p.source, "x:syndication")
        self.assertIn("Iran", p.text)
        self.assertTrue(p.url.endswith("/status/1901"))

    def test_syndication_html_without_json_returns_empty(self):
        self.assertEqual(xfeed._parse_syndication_html("<html></html>"), [])
        self.assertEqual(xfeed._parse_syndication_html("not json at all"), [])

    def test_nitter_rss_parses_items(self):
        posts = xfeed._parse_nitter_rss(NITTER_RSS, "nitter.test")
        self.assertEqual(len(posts), 2)
        p = posts[0]
        self.assertEqual(p.post_id, "3001")
        self.assertEqual(p.handle, "osintguy")
        self.assertEqual(p.source, "x:nitter@nitter.test")
        self.assertIn("Israel", p.text)
        self.assertEqual(p.url, "https://nitter.test/osintguy/status/3001")

    def test_bluesky_json_parses_posts(self):
        posts = xfeed._parse_bluesky(BSKY_JSON)
        self.assertEqual(len(posts), 3)
        p = posts[0]
        self.assertEqual(p.post_id, "cid-aaa")
        self.assertEqual(p.handle, "watcher.bsky.social")
        self.assertEqual(p.source, "bluesky")
        self.assertEqual(
            p.url, "https://bsky.app/profile/watcher.bsky.social/post/abc")


class TestNormalization(FeedTestBase):

    def test_normalized_dict_has_required_keys(self):
        p = xfeed._parse_bluesky(BSKY_JSON)[0]
        d = p.to_dict()
        for key in ("post_id", "author", "text", "created_at", "url",
                    "retrieved_at"):
            self.assertIn(key, d)
        self.assertTrue(d["retrieved_at"])      # populated at collection
        self.assertEqual(d["author"], "watcher.bsky.social")

    def test_roundtrip_from_dict(self):
        d = xfeed._parse_bluesky(BSKY_JSON)[0].to_dict()
        p2 = XPost.from_dict(d)
        self.assertEqual(p2.to_dict(), d)


class TestDedupeAndFilter(FeedTestBase):

    def test_dedup_by_post_id(self):
        posts = xfeed._parse_bluesky(BSKY_JSON)
        self.assertEqual(len(posts), 3)
        self.assertEqual(len(xfeed._dedupe(posts)), 2)

    def test_dedup_text_fallback_when_no_id(self):
        a = XPost("x", "same text here that is long enough to matter")
        b = XPost("x", "same text here that is long enough to matter")
        self.assertEqual(len(xfeed._dedupe([a, b])), 1)

    def test_filter_drops_irrelevant_and_short(self):
        posts = xfeed._parse_nitter_rss(NITTER_RSS, "nitter.test")
        kept = xfeed._filter_posts(
            posts, xfeed._query_terms("Iran OR Israel"), set())
        self.assertEqual([p.post_id for p in kept], ["3001"])
        kept = xfeed._filter_posts(
            posts, xfeed._query_terms("Iran OR Israel"), {"foodie"})
        self.assertEqual(len(kept), 2)          # watched account always kept

    def test_query_terms_or_semantics(self):
        self.assertEqual(xfeed._query_terms("Iran OR Israel OR Trump"),
                         ["iran", "israel", "trump"])


class TestRealFeed(FeedTestBase):

    def _http(self, url, timeout=0):
        if "syndication" in url:
            return SYNDICATION_HTML
        if "nitter.test" in url:
            return NITTER_RSS
        raise OSError("unexpected url " + url)

    def test_collect_filters_dedupes_and_labels(self):
        feed = RealPublicXFeed()
        with mock.patch.object(xfeed, "_get", side_effect=self._http):
            posts, status = feed.collect(CFG)
        ids = [p.post_id for p in posts]
        self.assertEqual(ids, ["1901", "1902", "3001"])  # dup + ad + junk gone
        self.assertEqual(status["state"], "live")
        self.assertTrue(all(p.source.startswith("x:") for p in posts))
        self.assertTrue(all(p.retrieved_at for p in posts))
        # watched-account tweets are kept even when the query misses
        self.assertIn("Iran", posts[0].text)

    def test_all_backends_down_raises_exact_error(self):
        feed = RealPublicXFeed()

        def boom(url, timeout=0):
            raise urllib.error.HTTPError(url, 503, "down", None, None)

        with mock.patch.object(xfeed, "_get", side_effect=boom):
            with self.assertRaises(RealFeedUnavailable) as cm:
                feed.collect(CFG)
        self.assertIn("Real X feed unavailable", str(cm.exception))
        self.assertIn("No real posts were supplied", str(cm.exception))
        self.assertIn("SyntheticXFeed", str(cm.exception))

    def test_collect_feed_real_propagates_error(self):
        cfg = dict(CFG, cache=False)
        with mock.patch.object(xfeed, "_get",
                               side_effect=OSError("no route")):
            with self.assertRaises(RealFeedUnavailable):
                xfeed.collect_feed(cfg)


class TestCaching(FeedTestBase):

    def _posts(self, url, timeout=0):
        if "syndication" in url:
            return SYNDICATION_HTML
        raise OSError("nope")

    def test_second_collect_reads_cache_no_network(self):
        feed = RealPublicXFeed()
        calls = []

        def counted(url, timeout=0):
            calls.append(url)
            return self._posts(url)

        with mock.patch.object(xfeed, "_get", side_effect=counted):
            posts1, st1 = feed.collect(CFG)
        self.assertEqual(st1["state"], "live")
        self.assertTrue(calls)

        # second run: fresh cache -> zero HTTP calls
        with mock.patch.object(xfeed, "_get",
                               side_effect=AssertionError("must not call")):
            posts2, st2 = feed.collect(CFG)
        self.assertEqual(st2["state"], "cache")
        self.assertEqual([p.post_id for p in posts2],
                         [p.post_id for p in posts1])
        # provenance survives the cache round-trip
        self.assertTrue(all(p.source.startswith("x:") for p in posts2))
        self.assertTrue(all(p.retrieved_at for p in posts2))

    def test_stale_cache_served_when_live_fetch_fails(self):
        feed = RealPublicXFeed()
        with mock.patch.object(xfeed, "_get", side_effect=self._posts):
            feed.collect(CFG)
        cfg = dict(CFG, cache_ttl_hours=0)      # force expiry
        with mock.patch.object(xfeed, "_get", side_effect=OSError("down")):
            posts, st = feed.collect(cfg)
        self.assertEqual(st["state"], "stale-cache")
        self.assertTrue(posts)
        self.assertTrue(st["error"])

    def test_cache_disabled_always_fetches(self):
        feed = RealPublicXFeed()
        cfg = dict(CFG, cache=False)
        calls = []

        def counted(url, timeout=0):
            calls.append(url)
            return self._posts(url)

        with mock.patch.object(xfeed, "_get", side_effect=counted):
            feed.collect(cfg)
            feed.collect(cfg)
        self.assertGreaterEqual(len(calls), 2)


class TestBlueskyFeed(FeedTestBase):

    def test_collect_normalizes_and_labels_not_x(self):
        feed = BlueskyPublicFeed()
        with mock.patch.object(xfeed, "_get",
                               return_value=json.dumps(BSKY_JSON)):
            posts, st = feed.collect(dict(CFG))
        self.assertEqual(st["provider"], "bluesky")
        self.assertEqual(len(posts), 1)          # dup removed, lunch filtered
        self.assertTrue(all(p.source == "bluesky" for p in posts))
        # and the honesty check: nothing is labelled as an x source
        self.assertFalse(any(p.source.startswith("x:") for p in posts))

    def test_bluesky_down_raises(self):
        feed = BlueskyPublicFeed()
        with mock.patch.object(xfeed, "_get", side_effect=OSError("down")):
            with self.assertRaises(RealFeedUnavailable):
                feed.collect(dict(CFG))


class TestProviderResolution(FeedTestBase):

    def test_synthetic_deterministic(self):
        posts, st = SyntheticXFeed().collect(round_no=1)
        posts2, _ = SyntheticXFeed().collect(round_no=1)
        self.assertEqual(st["provider"], "synthetic")
        self.assertEqual([p.handle for p in posts],
                         [p.handle for p in posts2])
        self.assertTrue(all(p.source == "synthetic" for p in posts))

    def test_offline_forces_synthetic(self):
        posts, st = xfeed.collect_feed(dict(CFG), offline=True)
        self.assertEqual(st["provider"], "synthetic")
        self.assertTrue(posts)

    def test_auto_falls_back_to_bluesky_with_provenance(self):
        cfg = dict(CFG, provider="auto", cache=False)

        def fake_get(url, timeout=0):
            if "bsky" in url:
                return json.dumps(BSKY_JSON)
            raise urllib.error.HTTPError(url, 429, "rate limited", None, None)

        with mock.patch.object(xfeed, "_get", side_effect=fake_get):
            posts, st = xfeed.collect_feed(cfg)
        self.assertEqual(st["provider"], "bluesky")
        self.assertEqual(st["fallback_from"], "real-x")
        self.assertIn("fallback_reason", st)     # the failure is recorded
        self.assertTrue(all(p.source == "bluesky" for p in posts))

    def test_feed_header_honesty(self):
        self.assertIn("unavailable", xfeed.feed_header([]))
        syn, _ = SyntheticXFeed().collect(round_no=1)
        self.assertIn("fictional", xfeed.feed_header(syn))
        real = [XPost("a", "text", source="x:syndication")]
        self.assertIn("X/TWITTER POSTS", xfeed.feed_header(real))
        bsky = [XPost("a", "text", source="bluesky")]
        self.assertIn("NOT X/Twitter", xfeed.feed_header(bsky))
        mixed = real + bsky
        self.assertIn("MIXED PROVENANCE", xfeed.feed_header(mixed))

    def test_posts_for_routes_tagged_first(self):
        posts = [XPost("a", "x", frozenset({"oil_market"})),
                 XPost("b", "y"), XPost("c", "z")]
        routed = xfeed.posts_for(posts, "oil_market")
        self.assertEqual(routed[0].handle, "a")


if __name__ == "__main__":
    unittest.main()
