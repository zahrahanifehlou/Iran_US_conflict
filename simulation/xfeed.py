"""X/Twitter & public social feed — the posts agents see and must reference
when they speak.

Providers (all implement the XFeed interface):

    XFeed
    ├── SyntheticXFeed     hand-written ROUND_POSTS — deterministic, for
    │                      tests and offline/reproducible runs
    ├── RealPublicXFeed    real X posts via *free public* endpoints — no API
    │                      key, no auth, no scraping behind a login: the
    │                      official embed timeline (syndication.twitter.com)
    │                      plus optional Nitter RSS mirrors. Raises
    │                      RealFeedUnavailable when nothing is retrievable —
    │                      it NEVER substitutes fabricated posts.
    └── BlueskyPublicFeed  real posts from Bluesky's public unauthenticated
                           AppView search — the honest free alternative when
                           X is unreachable. Clearly labelled source="bluesky";
                           never represented to agents or logs as X content.

Every post is normalised to (see XPost.to_dict()):

    post_id, author, text, created_at, url, retrieved_at, source

`source` is the provenance: "synthetic", "x:syndication", "x:nitter@<host>"
or "bluesky". It is carried through into the dump, so anything shown to an
agent can be traced back to where it was actually collected from — the hard
rule here is that nothing is ever *claimed* to be an X post unless it was
actually retrieved from a public X endpoint.
"""

from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


# ------------------------------------------------------------------ posts

@dataclass
class XPost:
    handle: str
    text: str
    tags: frozenset[str] = frozenset()   # agent ids this is most relevant to
    post_id: str = ""
    created_at: str = ""
    url: str = ""
    retrieved_at: str = ""
    source: str = "synthetic"

    def fmt(self, source_tag: bool = False) -> str:
        date = f" · {self.created_at[:10]}" if self.created_at else ""
        tag = f"  [{self.source}]" if source_tag else ""
        return f"@{self.handle}{date}: {self.text}{tag}"

    def to_dict(self) -> dict:
        """Normalised record — the shape every provider produces."""
        return {
            "post_id": self.post_id,
            "author": self.handle,
            "text": self.text,
            "created_at": self.created_at,
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "source": self.source,
        }

    @staticmethod
    def from_dict(d: dict) -> "XPost":
        return XPost(
            handle=d.get("author") or d.get("handle", "unknown"),
            text=d.get("text", ""),
            tags=frozenset(d.get("tags") or ()),
            post_id=str(d.get("post_id", "")),
            created_at=d.get("created_at", ""),
            url=d.get("url", ""),
            retrieved_at=d.get("retrieved_at", ""),
            source=d.get("source", "unknown"),
        )


class RealFeedUnavailable(Exception):
    """Raised when a real provider collected zero posts. Never caught-and-
    replaced by synthetic data — caller decides explicitly."""


X_UNAVAILABLE_MSG = (
    "Real X feed unavailable.\n"
    "No real posts were supplied to the simulation.\n"
    "Use SyntheticXFeed explicitly for testing."
)


# ------------------------------------------------------------ HTTP + cache

def _get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (conflict-sim research)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _cache_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "cache", "xfeed")


def _cache_path(provider: str, cfg: dict) -> str:
    raw = json.dumps({"q": cfg.get("query", ""),
                      "accounts": cfg.get("accounts") or []},
                     sort_keys=True)
    h = hashlib.sha1(raw.encode()).hexdigest()[:10]
    return os.path.join(_cache_dir(), f"{provider}_{h}.json")


def _read_cache(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(path: str, provider: str, query: str,
                 posts: list[XPost]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "provider": provider, "query": query,
        "retrieved_at": _now_iso(),
        "posts": [p.to_dict() for p in posts],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cache_age_seconds(blob: dict) -> float | None:
    try:
        ts = datetime.strptime(blob["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ")
        return (datetime.now(timezone.utc)
                - ts.replace(tzinfo=timezone.utc)).total_seconds()
    except (KeyError, ValueError):
        return None


# ------------------------------------------------------ filter / dedupe

def _query_terms(query: str) -> list[str]:
    """'Iran OR Israel OR Trump' -> ['iran','israel','trump'] (OR semantics)."""
    terms = re.split(r"(?i)\s+or\s+|[,;|]", query)
    return [t.strip().strip('"').lower() for t in terms if t.strip().strip('"')]


def _matches_query(post: XPost, terms: list[str]) -> bool:
    if not terms:
        return True
    hay = f"{post.handle} {post.text}".lower()
    return any(re.search(rf"\b{re.escape(t)}\b", hay) for t in terms)


def _dedupe(posts: list[XPost]) -> list[XPost]:
    """By post_id (per source); falls back to author+normalised text hash."""
    seen = set()
    out = []
    for p in posts:
        norm_text = re.sub(r"\s+", " ", p.text.lower())[:120]
        key = ((p.source, p.post_id) if p.post_id
               else (p.source, hashlib.sha1(
                   f"{p.handle}:{norm_text}".encode()).hexdigest()))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _filter_posts(posts: list[XPost], terms: list[str],
                  watched: set[str]) -> list[XPost]:
    """Keep posts that either match the query or come from a watched account;
    drop empty/link-only content and obvious embed boilerplate."""
    out = []
    for p in posts:
        text = re.sub(r"\s+", " ", (p.text or "")).strip()
        p.text = text
        if len(text) < 25 or re.fullmatch(r"(https?://\S+\s*)+", text):
            continue
        if not _matches_query(p, terms) and p.handle.lower() not in watched:
            continue
        out.append(p)
    return out


# coarse relevance routing so each agent sees what touches its interests
_TAG_KEYWORDS = {
    "trump": {"trump", "us_public"}, "iran": {"iran_public", "iran_hardliners",
                                             "oil_market"},
    "israel": {"netanyahu", "israeli_public"}, "netanyahu": {"netanyahu"},
    "hormuz": {"oil_market", "iran_hardliners", "gulf", "shipping"},
    "brent": {"oil_market", "central_banks"}, "oil": {"oil_market", "gas_market"},
    "crude": {"oil_market"}, "ceasefire": {"eu", "trump"},
    "protest": {"iran_public", "humanitarian"}, "gas": {"gas_market", "us_public"},
    "russia": {"russia"}, "china": {"china"}, "europe": {"eu"},
}


def _infer_tags(post: XPost) -> None:
    if post.tags:
        return
    hay = f"{post.handle} {post.text}".lower()
    tags = set()
    for word, agents in _TAG_KEYWORDS.items():
        if word in hay:
            tags |= agents
    post.tags = frozenset(tags)


# ------------------------------------------------------------ feed classes

class XFeed:
    """Feed interface. collect() -> (posts, status_dict)."""
    name = "xfeed"
    source = "base"

    def fetch(self, query: str, max_posts: int,
              accounts: list[str], timeout: int) -> list[XPost]:
        raise NotImplementedError

    def collect(self, cfg: dict, round_no: int) -> tuple[list[XPost], dict]:
        posts = self.fetch(cfg.get("query", ""), cfg.get("max_posts", 50),
                           cfg.get("accounts") or [],
                           cfg.get("timeout", 10))
        return posts, self._status("live", posts)

    def _status(self, state: str, posts: list[XPost],
                error: str | None = None) -> dict:
        return {"provider": self.name, "state": state,
                "n_posts": len(posts),
                "sources": sorted({p.source for p in posts}),
                "collected_at": _now_iso(), "error": error}


class SyntheticXFeed(XFeed):
    """Hand-written posts — deterministic, so tests and offline runs are
    reproducible. Every post carries source='synthetic'."""
    name = "synthetic"
    source = "synthetic"

    def collect(self, cfg: dict | None = None,
                round_no: int = 1) -> tuple[list[XPost], dict]:
        posts = ROUND_POSTS.get(round_no, DEFAULT_POSTS)
        for i, p in enumerate(posts):
            if not p.post_id:           # stable synthetic ids for the ledger
                p.post_id = f"syn-r{round_no}-{i:02d}"
        return posts, self._status("synthetic", posts)


class RealPublicXFeed(XFeed):
    """Real X posts from free public endpoints — the official unauthenticated
    embed timeline (syndication.twitter.com, the same backend Twitter's own
    embed.js widgets use) and optional Nitter RSS mirrors. One request per
    account; a 429 is respected, not retried. Nothing fabricated: if every
    backend yields zero posts, raises RealFeedUnavailable."""
    name = "real-x"
    source = "x"

    def _fetch_accounts(self, accounts: list[str], timeout: int,
                        errors: list[str]) -> list[XPost]:
        posts = []
        for handle in accounts:
            url = ("https://syndication.twitter.com/srv/timeline-profile/"
                   f"screen-name/{urllib.parse.quote(handle)}"
                   "?dnt=true&embedId=twitter-widget-0&lang=en")
            try:
                posts += _parse_syndication_html(_get(url, timeout))
            except urllib.error.HTTPError as exc:
                errors.append(f"syndication/@{handle}: HTTP {exc.code}")
                if exc.code == 429:            # rate limited — stop asking
                    break
            except Exception as exc:
                errors.append(
                    f"syndication/@{handle}: {type(exc).__name__}")
        return posts

    def _fetch_nitter(self, query: str, timeout: int,
                      errors: list[str], instances: list[str]) -> list[XPost]:
        posts = []
        for host in instances:
            url = (f"https://{host}/search/rss"
                   f"?f=tweets&q={urllib.parse.quote(query)}")
            try:
                posts += _parse_nitter_rss(_get(url, timeout), host)
            except Exception as exc:
                errors.append(f"nitter/{host}: {type(exc).__name__}")
        return posts

    def collect(self, cfg: dict, round_no: int = 1) -> tuple[list[XPost], dict]:
        query = cfg.get("query", "")
        ttl = float(cfg.get("cache_ttl_hours", 12)) * 3600
        cpath = _cache_path(self.name, cfg)
        cached = _read_cache(cpath) if cfg.get("cache") else None
        age = _cache_age_seconds(cached) if cached else None

        if cached and age is not None and age < ttl:
            posts = [XPost.from_dict(d) for d in cached["posts"]]
            st = self._status("cache", posts)
            st["cache_path"], st["cache_age_s"] = cpath, round(age)
            return posts, st

        errors: list[str] = []
        posts = self._fetch_accounts(cfg.get("accounts") or [],
                                     cfg.get("timeout", 10), errors)
        posts += self._fetch_nitter(query, cfg.get("timeout", 10),
                                    errors, cfg.get("nitter_instances") or [])
        posts = _dedupe(_filter_posts(posts, _query_terms(query),
                                      {a.lower() for a in cfg.get("accounts") or []}))
        for p in posts:
            _infer_tags(p)
        posts = posts[:cfg.get("max_posts", 50)]

        if posts:
            if cfg.get("cache"):
                _write_cache(cpath, self.name, query, posts)
            st = self._status("live", posts)
            if errors:
                st["warnings"] = errors
            return posts, st

        # real endpoints failed — stale cache is still honestly real data
        if cached and cached.get("posts"):
            posts = [XPost.from_dict(d) for d in cached["posts"]]
            st = self._status("stale-cache", posts, error="; ".join(errors))
            st["cache_path"] = cpath
            return posts, st
        raise RealFeedUnavailable(
            X_UNAVAILABLE_MSG + ("\nBackend errors: " + "; ".join(errors)
                                 if errors else ""))


class BlueskyPublicFeed(XFeed):
    """Real public posts from Bluesky's unauthenticated AppView search —
    clearly labelled source='bluesky', never presented as X content. The
    honest free alternative when no public X path works."""
    name = "bluesky"
    source = "bluesky"
    SEARCH = ("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
              "?sort=latest&limit={limit}&q={q}")

    def collect(self, cfg: dict, round_no: int = 1) -> tuple[list[XPost], dict]:
        query = cfg.get("query", "")
        ttl = float(cfg.get("cache_ttl_hours", 12)) * 3600
        cpath = _cache_path(self.name, cfg)
        cached = _read_cache(cpath) if cfg.get("cache") else None
        age = _cache_age_seconds(cached) if cached else None
        if cached and age is not None and age < ttl:
            posts = [XPost.from_dict(d) for d in cached["posts"]]
            st = self._status("cache", posts)
            st["cache_path"], st["cache_age_s"] = cpath, round(age)
            return posts, st

        url = self.SEARCH.format(limit=cfg.get("max_posts", 50),
                                 q=urllib.parse.quote(query))
        try:
            data = json.loads(_get(url, cfg.get("timeout", 10)))
            posts = _dedupe(_filter_posts(
                _parse_bluesky(data), _query_terms(query), set()))
        except Exception as exc:
            posts, err = [], f"{type(exc).__name__}: {exc}"
        else:
            err = None
        for p in posts:
            _infer_tags(p)

        if posts:
            if cfg.get("cache"):
                _write_cache(cpath, self.name, query, posts)
            return posts, self._status("live", posts)
        if cached and cached.get("posts"):
            posts = [XPost.from_dict(d) for d in cached["posts"]]
            st = self._status("stale-cache", posts, error=err)
            st["cache_path"] = cpath
            return posts, st
        raise RealFeedUnavailable(
            "Public social feed (Bluesky) unavailable.\n"
            "No real posts were supplied to the simulation.\n"
            f"{err or '0 posts returned'}")


# ------------------------------------------------------------- parsers

def _walk(obj):
    """Yield every nested dict inside a JSON blob."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _parse_syndication_html(html_text: str) -> list[XPost]:
    """Official embed timeline pages embed a __NEXT_DATA__ JSON blob; tweet
    objects are found defensively by schema (full_text + id_str/id) so the
    parser survives layout changes."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                  html_text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []
    posts = []
    for o in _walk(data):
        if not (isinstance(o, dict) and o.get("full_text")
                and (o.get("id_str") or o.get("id"))):
            continue
        pid = str(o.get("id_str") or o["id"])
        screen = ((o.get("user") or {}).get("screen_name")
                  or o.get("screen_name") or "x_user")
        posts.append(XPost(
            handle=screen, text=o["full_text"],
            post_id=pid,
            created_at=o.get("created_at", ""),
            url=(o.get("permalink")
                 or f"https://x.com/{screen}/status/{pid}"),
            retrieved_at=_now_iso(),
            source="x:syndication"))
    return posts


def _parse_nitter_rss(xml_text: str, host: str) -> list[XPost]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    posts = []
    for item in root.iter("item"):
        link = item.findtext("link") or ""
        m = re.search(r"/status(?:es)?/(\d+)", link)
        creator = item.findtext("{http://purl.org/dc/elements/1.1/}creator")
        author = creator or next(
            (seg for seg in link.split("/") if seg and "." not in seg),
            "x_user")
        desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "")
        posts.append(XPost(
            handle=author.lstrip("@"), text=_html.unescape(desc).strip()
            or (item.findtext("title") or "").strip(),
            post_id=m.group(1) if m else "",
            created_at=item.findtext("pubDate") or "",
            url=link, retrieved_at=_now_iso(),
            source=f"x:nitter@{host}"))
    return posts


def _parse_bluesky(data: dict) -> list[XPost]:
    posts = []
    for rec in data.get("posts") or []:
        author = (rec.get("author") or {}).get("handle", "bsky_user")
        rkey = (rec.get("uri") or "").rsplit("/", 1)[-1]
        posts.append(XPost(
            handle=author,
            text=((rec.get("record") or {}).get("text") or ""),
            post_id=rec.get("cid") or "",
            created_at=(rec.get("record") or {}).get("createdAt", ""),
            url=f"https://bsky.app/profile/{author}/post/{rkey}",
            retrieved_at=_now_iso(),
            source="bluesky"))
    return posts


# ------------------------------------------------------------ entry points

def collect_feed(cfg: dict | None = None, round_no: int = 1,
                 offline: bool = False) -> tuple[list[XPost], dict]:
    """Resolve the configured provider and collect one day's posts.

    provider: synthetic | real | bluesky | auto
      synthetic  hand-written posts (also forced when offline)
      real       public X endpoints only — RealFeedUnavailable on failure
      bluesky    Bluesky public search — real posts, labelled not-X
      auto       real X first, then Bluesky (both real; the fallback is
                 recorded in status['fallback'], never hidden)
    """
    if cfg is None:
        import config
        cfg = dict(config.X_FEED)
    if offline:
        posts = SyntheticXFeed().collect(cfg, round_no)[0]
        return posts, SyntheticXFeed()._status("offline-synthetic", posts)

    provider = cfg.get("provider", "synthetic")
    candidates = {
        "synthetic": [SyntheticXFeed],
        "real": [RealPublicXFeed],
        "bluesky": [BlueskyPublicFeed],
        "auto": [RealPublicXFeed, BlueskyPublicFeed],
    }.get(provider, [SyntheticXFeed])

    errors = []
    for i, cls in enumerate(candidates):
        feed = cls()
        try:
            posts, status = feed.collect(cfg, round_no)
        except Exception as exc:
            errors.append(f"{feed.name}: {exc}")
            continue
        if posts:
            if i > 0:                       # an earlier provider failed
                status["fallback_from"] = candidates[0].name
                status["fallback_reason"] = "; ".join(errors)
            return posts, status
        errors.append(f"{feed.name}: 0 posts")

    msg = (X_UNAVAILABLE_MSG if provider == "real" else
           "No real public feed could be reached.\n"
           "No real posts were supplied to the simulation.\n"
           "Use SyntheticXFeed explicitly for testing.")
    raise RealFeedUnavailable(
        msg + ("\nAttempts: " + "; ".join(errors) if errors else ""))


def posts_for(posts: list[XPost], agent_id: str, limit: int = 6) -> list[XPost]:
    """Relevance routing: posts tagged for this agent first, then the rest."""
    tagged = [p for p in posts if agent_id in p.tags]
    rest = [p for p in posts if agent_id not in p.tags]
    return (tagged + rest)[:limit]


def feed_header(posts: list[XPost]) -> str:
    """Honest provenance header for the agent prompt — never calls
    synthetic content real, never calls Bluesky posts 'X'."""
    if not posts:
        return ("X/TWITTER FEED: unavailable — no real posts were supplied "
                "today. Do not cite any post.")
    sources = {p.source for p in posts}
    if sources == {"synthetic"}:
        return ("SIMULATED X-STYLE POSTS (written by the scenario author — "
                "fictional, not real):")
    if all(s.startswith("x:") for s in sources):
        return ("RECENT PUBLIC X/TWITTER POSTS (real posts collected from "
                "public web endpoints — provenance recorded):")
    if sources == {"bluesky"}:
        return ("RECENT PUBLIC POSTS — source: Bluesky public feed (real "
                "posts, NOT X/Twitter):")
    return ("RECENT POSTS, MIXED PROVENANCE (each post tagged [source]):")


ROUND_POSTS: dict[int, list[XPost]] = {
    1: [
        XPost("realDonaldTrump",
              "Iran can make a DEAL and rebuild, or they can be ANNIHILATED. "
              "Their choice. Witkoff and Jared are doing a GREAT job at the UN. "
              "Gas prices coming down soon, mark my words!",
              frozenset({"trump", "us_public", "eu", "oil_market"})),
        XPost("netanyahu",
              "There will be no agreement that leaves a single centrifuge "
              "spinning in Iran. Israel will finish the job — alone if needed.",
              frozenset({"netanyahu", "iran_hardliners", "eu"})),
        XPost("khamenei_ir_fa",
              "The martyred Leader's path continues. The enemy demands our "
              "surrender dressed as negotiation. Iran does not surrender. "
              "— Office of the Supreme Leader",
              frozenset({"iran_hardliners", "iran_public"})),
        XPost("MEKhbar",
              "Tehran bazaar shut again today. Rial at 1.65M/dollar on the "
              "open market. People are selling gold teeth for bread. #Iran",
              frozenset({"iran_public", "iran_hardliners", "humanitarian"})),
        XPost("IranIntl_En",
              "Sources: IRGC-Quds pushing Mojtaba for a 'decisive' Hormuz move "
              "before US midterms; civilian cabinet resisting. #Iran",
              frozenset({"iran_hardliners", "iran_public", "oil_market"})),
        XPost("markets",
              "Brent $100.2 (+1.4%). War-risk premium now ~$18/bbl, Hormuz "
              "insurance rates at 6-month highs. Tanker traffic -22% WoW.",
              frozenset({"oil_market", "trump", "eu", "us_public",
                         "markets", "shipping", "gas_market"})),
        XPost("JavierBlas",
              "If Hormuz closes even partially for a week, $130 Brent is "
              "the floor, not the ceiling. SPR is already 40% drawn down.",
              frozenset({"oil_market", "trump", "eu"})),
        XPost("vonderleyen",
              "Europe cannot absorb another energy shock. We urge all parties "
              "to convert the UNGA contacts into a structured ceasefire track.",
              frozenset({"eu", "oil_market"})),
        XPost("amanpour",
              "UNGA hallways: both delegations deny 'negotiations', both "
              "confirm 'contact'. Diplomatic jargon doing heavy lifting.",
              frozenset({"eu", "us_public", "media"})),
        XPost("GStephanopoulos",
              "NEW POLL: 58% of voters say gas prices are their top issue; "
              "only 34% back continued strikes on Iran. GOP internal numbers "
              "worse. #Midterms",
              frozenset({"us_public", "trump"})),
        XPost("charliekirk11",
              "We didn't vote for 'manageable war'. Finish the job, Mr. "
              "President — or bring them home. This half-war is the worst "
              "option.",
              frozenset({"us_public", "trump"})),
        XPost("afshin_tehran",
              "7 months of war. My cousin's pharmacy has no insulin. The "
              "regime blames America, America bombs, we starve. Who exactly "
              "is winning? [fa]",
              frozenset({"iran_public", "israeli_public"})),
        XPost("bariweiss",
              "The 'annihilate or deal' framing leaves no room for what Iran "
              "will actually accept. Watch the Hormuz insurance market, not "
              "the speeches.",
              frozenset({"us_public", "eu", "oil_market"})),
        XPost("SecRubio",
              "Maximum pressure continues until Iran chooses to be a normal "
              "nation. All options remain on the table.",
              frozenset({"trump", "iran_hardliners", "eu"})),
        XPost("Radio_Farda",
              "Bread queues in Shiraz and Mashhad reported; Basij deploying "
              "around university campuses ahead of Friday prayers. [fa]",
              frozenset({"iran_public", "humanitarian"})),
        XPost("SpokespersonCHN",
              "China calls for maximum restraint and opposes unilateral "
              "measures that escalate tensions. Beijing stands ready to "
              "host contacts between the parties at any time. #Hormuz",
              frozenset({"china", "eu", "iran_hardliners", "oil_market"})),
        XPost("ReutersEnergy",
              "China's teapot refiners are buying discounted Iranian crude "
              "via yuan-settled channels again — volumes up 30% since the "
              "blockade tightened, per tanker trackers.",
              frozenset({"china", "oil_market", "iran_hardliners"})),
        XPost("mfa_russia",
              "Washington's 'binary choice' is gangster diplomacy. Russia "
              "will veto any UNSC cover for further aggression and is "
              "ready to discuss air-defence cooperation with Tehran.",
              frozenset({"russia", "iran_hardliners", "trump", "eu"})),
        XPost("TASS_agency",
              "Lavrov: every US carrier day in the Gulf is a day not spent "
              "elsewhere. Moscow 'wishes our American colleagues stamina'.",
              frozenset({"russia", "us_public", "trump"})),
        XPost("KSAMOFA",
              "The Kingdom urges de-escalation. Saudi Arabia is raising "
              "East-West pipeline throughput to keep crude flowing to "
              "markets regardless of Hormuz.",
              frozenset({"gulf", "oil_market", "eu", "trump"})),
        XPost("JavierBlas",
              "OPEC watch: Riyadh holds ~3mb/d spare. The price for opening "
              "the taps won't be money — it will be a US security "
              "guarantee with teeth.",
              frozenset({"gulf", "oil_market", "trump"})),
        XPost("MOFA_Taiwan",
              "Taiwan supports the international coalition's efforts to "
              "restore stability. We note reports of munitions stockpiles "
              "being drawn down for Gulf operations.",
              frozenset({"taiwan", "trump", "china"})),
        XPost("RTErdogan",
              "Turkey is ready to host the parties in Istanbul. We warned "
              "for months this escalation would price everyone out of "
              "peace. Ankara's door is open to all sides.",
              frozenset({"turkey", "eu", "iran_hardliners", "trump"})),
        XPost("haaretzcom",
              "Reservist call-up fatigue deepens: 40% of tech firms report "
              "staff shortages; northern residents still displaced after "
              "7 months. Poll: majority want 'victory or an end'.",
              frozenset({"israeli_public", "netanyahu"})),
        XPost("UNOCHA",
              "Access update: fuel deliveries to southern Iran hospitals "
              "remain blocked; estimated 310,000 internally displaced; "
              "medicine stockouts reported in 12 provinces.",
              frozenset({"humanitarian", "iran_public", "eu"})),
        XPost("business",
              "Fed watch: energy shock meets slowing payrolls — traders "
              "price a knife-edge hold; 'supply shocks can't be fixed "
              "with rate cuts' says one governor.",
              frozenset({"central_banks", "markets", "us_public"})),
        XPost("Osinttechnical",
              "Viral tonight: IRGCN small-boat swarm footage vs CENTCOM "
              "denial of a boarding attempt. Both narratives are "
              "circulating; the truth is doing push-ups.",
              frozenset({"media", "us_public", "iran_public"})),
    ],
}

DEFAULT_POSTS: list[XPost] = [
    XPost("markets",
          "Brent drifting on thin liquidity; war premium intact pending "
          "Hormuz clarity.", frozenset({"oil_market"})),
]


def feed_for(round_no: int, agent_id: str, limit: int = 6) -> list[XPost]:
    """Back-compat shim: the synthetic feed exactly as before."""
    posts = ROUND_POSTS.get(round_no, DEFAULT_POSTS)
    return posts_for(posts, agent_id, limit)
