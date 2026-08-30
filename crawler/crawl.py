#!/usr/bin/env python3
"""Build the public-web Leatherback licensing universe database.

The crawler indexes licensing agencies, licensors, conference exhibitors and
machine-extracted agency/client relationships. It deliberately separates raw
extraction from verification and records provenance for every relationship.
"""
from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import html as html_lib
import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from rapidfuzz.fuzz import ratio

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SEEDS_PATH = Path(__file__).with_name("seeds.json")
DB_PATH = DATA_DIR / "licensing_universe.sqlite"
JSON_PATH = DATA_DIR / "licensing_universe.json"
AGENCIES_CSV = DATA_DIR / "agencies.csv"
RELATIONSHIPS_CSV = DATA_DIR / "agency_client_relationships.csv"
SOURCES_CSV = DATA_DIR / "crawl_sources.csv"
STATS_PATH = DATA_DIR / "stats.json"
ERRORS_PATH = DATA_DIR / "crawl_errors.json"

RUN_STARTED = datetime.now(timezone.utc)
RUN_ID = RUN_STARTED.strftime("%Y%m%dT%H%M%SZ")
USER_AGENT = "Leatherback-Licensing-Atlas/1.1 (+public licensing market research; respectful crawler)"
MAX_SITES = int(os.environ.get("MAX_SITES", "650"))
MAX_PAGES_PER_SITE = int(os.environ.get("MAX_PAGES_PER_SITE", "8"))
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "18"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "14"))
MAX_RESPONSE_BYTES = int(os.environ.get("MAX_RESPONSE_BYTES", str(4 * 1024 * 1024)))
SEARCH_RESULTS_PER_QUERY = int(os.environ.get("SEARCH_RESULTS_PER_QUERY", "12"))

PORTFOLIO_TERMS = re.compile(
    r"brand|brands|portfolio|client|clients|propert|licen[cs]|representation|rights|"
    r"our-work|partners|artists|talent|franchises|catalog|roster|consumer-products",
    re.I,
)
AGENCY_TERMS = {
    "licensing agency": 6,
    "licensing agent": 6,
    "brand licensing": 4,
    "brand extension": 3,
    "represented brands": 4,
    "our brands": 3,
    "our clients": 3,
    "portfolio": 1,
    "consumer products": 2,
    "rights representation": 4,
    "licensing programme": 2,
    "licensing program": 2,
    "licensing partnerships": 2,
    "licensees": 1,
    "licensors": 2,
}
LICENSOR_TERMS = {
    "global consumer products": 5,
    "consumer products and experiences": 5,
    "brand owner": 3,
    "licensing division": 4,
    "licensing programme": 3,
    "licensing program": 3,
    "franchise management": 3,
    "official licensing": 3,
}
NEGATIVE_TERMS = {
    "software license": 5,
    "open source license": 5,
    "driver license": 5,
    "professional licensing": 4,
    "licensing attorney": 2,
    "liquor licensing": 4,
    "music sync licensing platform": 3,
    "license compliance": 4,
    "license management software": 5,
}
GENERIC_NAMES = {
    "home", "about", "about us", "contact", "contact us", "news", "blog", "services",
    "service", "portfolio", "brands", "our brands", "clients", "our clients", "partners",
    "our partners", "licensing", "consumer products", "experiences", "retail", "learn more",
    "read more", "view more", "see more", "discover", "discover more", "work", "our work",
    "team", "our team", "careers", "privacy", "terms", "cookies", "menu", "search", "login",
    "sign in", "sign up", "follow us", "facebook", "instagram", "linkedin", "youtube", "x",
    "twitter", "all rights reserved", "copyright", "events", "event", "shop", "store",
    "press", "media", "resources", "categories", "category", "case studies", "case study",
    "fashion", "entertainment", "lifestyle", "corporate", "sports", "art", "food and beverage",
    "heritage", "publishing", "digital", "gaming", "hospitality", "location based entertainment",
    "north america", "latin america", "europe", "asia", "global", "united kingdom", "united states",
}
EXCLUDED_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com", "x.com", "twitter.com",
    "pinterest.com", "tiktok.com", "wikipedia.org", "amazon.com", "ebay.com", "glassdoor.com",
    "indeed.com", "crunchbase.com", "bloomberg.com", "reuters.com", "prnewswire.com",
    "businesswire.com", "licenseglobal.com", "licensinginternational.org", "licensingexpo.com",
    "brandlicensing.eu", "content-tokyo.jp", "chinalicensingexpo.com", "mapyourshow.com",
    "google.com", "bing.com", "duckduckgo.com", "yahoo.com", "medium.com", "substack.com",
}
DIRECTORY_DOMAIN_MARKERS = {
    "licenseglobal.com", "licensinginternational.org", "licensingexpo.com", "brandlicensing.eu",
    "mapyourshow.com", "content-tokyo.jp", "chinalicensingexpo.com", "licensinghorizons.com",
}
COUNTRY_HINTS = {
    "australia": "Australia and New Zealand", "new zealand": "Australia and New Zealand",
    "united kingdom": "United Kingdom and Ireland", "uk": "United Kingdom and Ireland",
    "ireland": "United Kingdom and Ireland", "united states": "North America", "usa": "North America",
    "canada": "North America", "mexico": "Latin America", "brazil": "Latin America",
    "argentina": "Latin America", "chile": "Latin America", "colombia": "Latin America",
    "india": "India and South Asia", "pakistan": "India and South Asia", "china": "China and Asia-Pacific",
    "hong kong": "Asia-Pacific", "japan": "Asia-Pacific", "korea": "Asia-Pacific",
    "singapore": "Asia-Pacific", "malaysia": "Asia-Pacific", "indonesia": "Asia-Pacific",
    "thailand": "Asia-Pacific", "philippines": "Asia-Pacific", "south africa": "Africa",
    "uae": "Middle East and North Africa", "dubai": "Middle East and North Africa",
    "saudi": "Middle East and North Africa", "turkey": "Turkey and Middle East",
    "france": "France and Europe", "germany": "Germany and Europe", "italy": "Italy and Europe",
    "spain": "Iberia and Europe", "portugal": "Iberia and Europe", "netherlands": "Benelux and Europe",
    "belgium": "Benelux and Europe", "sweden": "Nordics and Europe", "denmark": "Nordics and Europe",
    "finland": "Nordics and Europe", "norway": "Nordics and Europe", "poland": "Central and Eastern Europe",
    "czech": "Central and Eastern Europe",
}

_thread_local = threading.local()
_robot_cache: dict[str, bool] = {}
_robot_lock = threading.Lock()
_errors: list[dict[str, Any]] = []
_error_lock = threading.Lock()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(value or "")).strip()


def norm_name(value: str) -> str:
    value = norm_space(value).lower()
    value = re.sub(r"[®™©]", "", value)
    value = re.sub(r"\b(the|incorporated|inc|limited|ltd|llc|plc|gmbh|srl|pty|pvt|co|company|group)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return norm_space(value)


def domain_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return ""
    host = host.lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def root_domain(host: str) -> str:
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if parts[-2] in {"co", "com", "org", "net", "gov", "ac"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_excluded_domain(host: str) -> bool:
    root = root_domain(host)
    return any(root == x or root.endswith("." + x) for x in EXCLUDED_DOMAINS)


def clean_url(url: str, base: str | None = None) -> str | None:
    try:
        out = urllib.parse.urljoin(base or "", url)
        parsed = urllib.parse.urlparse(out)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query = [(k, v) for k, v in query if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
        parsed = parsed._replace(fragment="", query=urllib.parse.urlencode(query))
        return urllib.parse.urlunparse(parsed)
    except Exception:
        return None


def session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-GB,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/pdf,application/xml;q=0.8,*/*;q=0.5",
        })
        adapter = requests.adapters.HTTPAdapter(pool_connections=30, pool_maxsize=30, max_retries=1)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        _thread_local.session = s
    return _thread_local.session


def record_error(stage: str, target: str, error: Exception | str) -> None:
    row = {"stage": stage, "target": target, "error": str(error)[:1000], "at": utcnow()}
    with _error_lock:
        _errors.append(row)


def robots_allowed(url: str) -> bool:
    host = domain_of(url)
    if not host:
        return False
    with _robot_lock:
        if host in _robot_cache:
            return _robot_cache[host]
    robots_url = f"{urllib.parse.urlparse(url).scheme}://{host}/robots.txt"
    allowed = True
    try:
        response = session().get(robots_url, timeout=6)
        if response.ok and len(response.text) < 500_000:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            allowed = parser.can_fetch(USER_AGENT, url)
    except Exception:
        allowed = True
    with _robot_lock:
        _robot_cache[host] = allowed
    return allowed


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: str
    elapsed_ms: int
    robots_allowed: bool


def fetch(url: str, *, timeout: int = REQUEST_TIMEOUT, obey_robots: bool = True) -> FetchResult | None:
    url = clean_url(url) or ""
    if not url:
        return None
    allowed = robots_allowed(url) if obey_robots else True
    if not allowed:
        record_error("robots", url, "Disallowed by robots.txt")
        return FetchResult(url, url, 0, "", b"", utcnow(), 0, False)
    started = time.monotonic()
    try:
        response = session().get(url, timeout=timeout, allow_redirects=True, stream=True)
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(65_536):
            if not chunk:
                continue
            chunks.append(chunk)
            size += len(chunk)
            if size >= MAX_RESPONSE_BYTES:
                break
        return FetchResult(
            requested_url=url,
            final_url=response.url,
            status=response.status_code,
            content_type=(response.headers.get("content-type") or "").lower(),
            body=b"".join(chunks),
            fetched_at=utcnow(),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            robots_allowed=True,
        )
    except Exception as exc:
        record_error("fetch", url, exc)
        return None


def decode_body(result: FetchResult) -> str:
    if not result.body:
        return ""
    for encoding in ("utf-8", "windows-1252", "latin-1"):
        try:
            return result.body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return result.body.decode("utf-8", errors="replace")


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    return norm_space(soup.get_text(" "))


def page_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    if soup.title:
        return norm_space(soup.title.get_text(" "))[:300]
    h1 = soup.find("h1")
    return norm_space(h1.get_text(" "))[:300] if h1 else ""


def score_text(text: str, terms: dict[str, int]) -> int:
    lowered = text.lower()
    return sum(weight for term, weight in terms.items() if term in lowered)


def infer_region(text: str, fallback: str = "Unknown") -> str:
    lowered = text.lower()
    for hint, region in COUNTRY_HINTS.items():
        if hint in lowered:
            return region
    return fallback or "Unknown"


def bing_search(query: str) -> list[dict[str, str]]:
    url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote_plus(query)
    result = fetch(url, timeout=12, obey_robots=False)
    if not result or result.status >= 400:
        return []
    try:
        root = ET.fromstring(result.body)
    except Exception as exc:
        record_error("bing_parse", query, exc)
        return []
    rows = []
    for item in root.findall(".//item")[:SEARCH_RESULTS_PER_QUERY]:
        title = norm_space(item.findtext("title"))
        link = clean_url(item.findtext("link") or "")
        description = norm_space(item.findtext("description"))
        if link:
            rows.append({"title": title, "url": link, "description": description, "engine": "bing_rss"})
    return rows


def ddg_search(query: str) -> list[dict[str, str]]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    result = fetch(url, timeout=12, obey_robots=False)
    if not result or result.status >= 400:
        return []
    soup = BeautifulSoup(decode_body(result), "lxml")
    rows = []
    for anchor in soup.select("a.result__a")[:SEARCH_RESULTS_PER_QUERY]:
        href = clean_url(anchor.get("href") or "")
        if not href:
            continue
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in (parsed.hostname or ""):
            params = urllib.parse.parse_qs(parsed.query)
            href = clean_url((params.get("uddg") or [href])[0])
        if href:
            result_node = anchor.find_parent(class_=re.compile("result"))
            desc_node = result_node.select_one(".result__snippet") if result_node else None
            rows.append({
                "title": norm_space(anchor.get_text(" ")),
                "url": href,
                "description": norm_space(desc_node.get_text(" ")) if desc_node else "",
                "engine": "duckduckgo_html",
            })
    return rows


def web_search(query: str) -> list[dict[str, str]]:
    rows = bing_search(query)
    if len(rows) < 4:
        extra = ddg_search(query)
        seen = {r["url"] for r in rows}
        rows.extend(r for r in extra if r["url"] not in seen)
    return rows[:SEARCH_RESULTS_PER_QUERY]


def choose_official_result(name: str, rows: list[dict[str, str]]) -> str | None:
    best: tuple[float, str] | None = None
    target = norm_name(name)
    for row in rows:
        url = row.get("url") or ""
        host = domain_of(url)
        if not host or is_excluded_domain(host):
            continue
        haystack = norm_name((row.get("title") or "") + " " + host.replace(".", " "))
        similarity = ratio(target, haystack)
        signal = score_text((row.get("title") or "") + " " + (row.get("description") or ""), AGENCY_TERMS)
        value = similarity + min(signal * 3, 25)
        if best is None or value > best[0]:
            best = (value, url)
    return best[1] if best and best[0] >= 45 else None


class Database:
    def __init__(self, path: Path):
        if path.exists():
            path.unlink()
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._create_schema()
        self.org_cache: dict[str, int] = {}
        self.source_cache: dict[str, int] = {}

    def _create_schema(self) -> None:
        self.conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE crawl_runs (
          id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
          status TEXT NOT NULL, configuration_json TEXT, counts_json TEXT, limitations_json TEXT
        );
        CREATE TABLE sources (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, source_type TEXT NOT NULL,
          url TEXT NOT NULL UNIQUE, domain TEXT, discovered_from TEXT, region TEXT,
          status TEXT, http_status INTEGER, content_type TEXT, last_crawled_at TEXT,
          robots_allowed INTEGER, error TEXT
        );
        CREATE TABLE pages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER,
          requested_url TEXT NOT NULL, final_url TEXT, title TEXT, fetched_at TEXT,
          http_status INTEGER, content_type TEXT, elapsed_ms INTEGER,
          byte_length INTEGER, text_length INTEGER, sha256 TEXT, text_excerpt TEXT,
          page_role TEXT, FOREIGN KEY(source_id) REFERENCES sources(id)
        );
        CREATE TABLE organisations (
          id INTEGER PRIMARY KEY AUTOINCREMENT, canonical_name TEXT NOT NULL,
          normalized_name TEXT NOT NULL, organisation_type TEXT NOT NULL,
          website TEXT, domain TEXT, region TEXT, country TEXT, description TEXT,
          discovery_method TEXT, confidence REAL NOT NULL DEFAULT 0.5,
          verification_status TEXT NOT NULL DEFAULT 'machine_discovered',
          first_seen_at TEXT, last_seen_at TEXT, UNIQUE(normalized_name, domain, organisation_type)
        );
        CREATE TABLE aliases (
          id INTEGER PRIMARY KEY AUTOINCREMENT, organisation_id INTEGER NOT NULL,
          alias TEXT NOT NULL, normalized_alias TEXT NOT NULL,
          UNIQUE(organisation_id, normalized_alias),
          FOREIGN KEY(organisation_id) REFERENCES organisations(id)
        );
        CREATE TABLE representations (
          id INTEGER PRIMARY KEY AUTOINCREMENT, agency_id INTEGER NOT NULL,
          client_id INTEGER NOT NULL, relationship_type TEXT NOT NULL DEFAULT 'represents',
          territory TEXT, evidence_url TEXT NOT NULL, evidence_page_id INTEGER,
          evidence_text TEXT, extraction_method TEXT, confidence REAL NOT NULL,
          verification_status TEXT NOT NULL DEFAULT 'machine_extracted_unverified',
          first_seen_at TEXT, last_seen_at TEXT,
          UNIQUE(agency_id, client_id, evidence_url),
          FOREIGN KEY(agency_id) REFERENCES organisations(id),
          FOREIGN KEY(client_id) REFERENCES organisations(id),
          FOREIGN KEY(evidence_page_id) REFERENCES pages(id)
        );
        CREATE TABLE conference_appearances (
          id INTEGER PRIMARY KEY AUTOINCREMENT, organisation_id INTEGER NOT NULL,
          conference_name TEXT NOT NULL, conference_year INTEGER,
          exhibitor_url TEXT, source_id INTEGER, booth TEXT, confidence REAL,
          UNIQUE(organisation_id, conference_name, conference_year),
          FOREIGN KEY(organisation_id) REFERENCES organisations(id),
          FOREIGN KEY(source_id) REFERENCES sources(id)
        );
        CREATE TABLE evidence (
          id INTEGER PRIMARY KEY AUTOINCREMENT, organisation_id INTEGER,
          representation_id INTEGER, evidence_type TEXT NOT NULL, source_url TEXT NOT NULL,
          source_page_id INTEGER, excerpt TEXT, confidence REAL, review_status TEXT,
          captured_at TEXT, FOREIGN KEY(organisation_id) REFERENCES organisations(id),
          FOREIGN KEY(representation_id) REFERENCES representations(id),
          FOREIGN KEY(source_page_id) REFERENCES pages(id)
        );
        CREATE INDEX idx_org_type ON organisations(organisation_type);
        CREATE INDEX idx_org_name ON organisations(normalized_name);
        CREATE INDEX idx_rep_agency ON representations(agency_id);
        CREATE INDEX idx_rep_client ON representations(client_id);
        CREATE INDEX idx_pages_source ON pages(source_id);
        """)
        self.conn.execute(
            "INSERT INTO crawl_runs(id, started_at, status, configuration_json) VALUES(?,?,?,?)",
            (RUN_ID, RUN_STARTED.isoformat(timespec="seconds"), "running", json.dumps({
                "max_sites": MAX_SITES, "max_pages_per_site": MAX_PAGES_PER_SITE,
                "max_workers": MAX_WORKERS, "request_timeout": REQUEST_TIMEOUT,
            })),
        )
        self.conn.commit()

    def add_source(self, *, name: str, source_type: str, url: str, discovered_from: str = "", region: str = "") -> int:
        url = clean_url(url) or url
        with self.lock:
            if url in self.source_cache:
                return self.source_cache[url]
            self.conn.execute(
                "INSERT OR IGNORE INTO sources(name, source_type, url, domain, discovered_from, region, status) VALUES(?,?,?,?,?,?,?)",
                (name, source_type, url, domain_of(url), discovered_from, region, "queued"),
            )
            row = self.conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()
            source_id = int(row[0])
            self.source_cache[url] = source_id
            self.conn.commit()
            return source_id

    def update_source(self, source_id: int, result: FetchResult | None, error: str = "") -> None:
        with self.lock:
            if result is None:
                self.conn.execute(
                    "UPDATE sources SET status='failed', last_crawled_at=?, error=? WHERE id=?",
                    (utcnow(), error[:1000], source_id),
                )
            else:
                status = "blocked_by_robots" if not result.robots_allowed else ("fetched" if 200 <= result.status < 400 else "http_error")
                self.conn.execute(
                    "UPDATE sources SET status=?, http_status=?, content_type=?, last_crawled_at=?, robots_allowed=?, error=? WHERE id=?",
                    (status, result.status, result.content_type, result.fetched_at, int(result.robots_allowed), error[:1000], source_id),
                )
            self.conn.commit()

    def add_page(self, source_id: int, result: FetchResult, *, html: str = "", role: str = "page") -> int:
        text = visible_text(html) if html and "html" in result.content_type else ""
        title = page_title(html) if html and "html" in result.content_type else ""
        digest = hashlib.sha256(result.body).hexdigest() if result.body else ""
        with self.lock:
            cur = self.conn.execute(
                """INSERT INTO pages(source_id, requested_url, final_url, title, fetched_at,
                http_status, content_type, elapsed_ms, byte_length, text_length, sha256, text_excerpt, page_role)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id, result.requested_url, result.final_url, title, result.fetched_at,
                 result.status, result.content_type, result.elapsed_ms, len(result.body), len(text), digest, text[:12000], role),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def upsert_org(self, name: str, org_type: str, *, website: str = "", region: str = "Unknown",
                   description: str = "", discovery_method: str = "", confidence: float = 0.5,
                   verification_status: str = "machine_discovered") -> int | None:
        name = clean_entity_name(name)
        if not name:
            return None
        website = clean_url(website) or ""
        host = domain_of(website)
        normalized = norm_name(name)
        if not normalized:
            return None
        key = f"{normalized}|{host}|{org_type}"
        with self.lock:
            if key in self.org_cache:
                org_id = self.org_cache[key]
                self.conn.execute(
                    """UPDATE organisations SET last_seen_at=?, website=CASE WHEN website='' THEN ? ELSE website END,
                    domain=CASE WHEN domain='' THEN ? ELSE domain END, region=CASE WHEN region IN ('','Unknown') THEN ? ELSE region END,
                    confidence=MAX(confidence, ?) WHERE id=?""",
                    (utcnow(), website, host, region, confidence, org_id),
                )
                self.conn.commit()
                return org_id
            self.conn.execute(
                """INSERT OR IGNORE INTO organisations(canonical_name, normalized_name, organisation_type,
                website, domain, region, description, discovery_method, confidence, verification_status,
                first_seen_at, last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, normalized, org_type, website, host, region or "Unknown", description[:2000],
                 discovery_method, confidence, verification_status, utcnow(), utcnow()),
            )
            row = self.conn.execute(
                "SELECT id FROM organisations WHERE normalized_name=? AND domain=? AND organisation_type=?",
                (normalized, host, org_type),
            ).fetchone()
            if not row and not host:
                row = self.conn.execute(
                    "SELECT id FROM organisations WHERE normalized_name=? AND organisation_type=? ORDER BY confidence DESC LIMIT 1",
                    (normalized, org_type),
                ).fetchone()
            if not row:
                return None
            org_id = int(row[0])
            self.org_cache[key] = org_id
            self.conn.execute(
                "INSERT OR IGNORE INTO aliases(organisation_id, alias, normalized_alias) VALUES(?,?,?)",
                (org_id, name, normalized),
            )
            self.conn.commit()
            return org_id

    def add_representation(self, agency_id: int, client_id: int, evidence_url: str, page_id: int | None,
                           evidence_text: str, method: str, confidence: float) -> int:
        with self.lock:
            self.conn.execute(
                """INSERT OR IGNORE INTO representations(agency_id, client_id, evidence_url,
                evidence_page_id, evidence_text, extraction_method, confidence, first_seen_at, last_seen_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (agency_id, client_id, evidence_url, page_id, evidence_text[:1500], method,
                 confidence, utcnow(), utcnow()),
            )
            row = self.conn.execute(
                "SELECT id FROM representations WHERE agency_id=? AND client_id=? AND evidence_url=?",
                (agency_id, client_id, evidence_url),
            ).fetchone()
            rep_id = int(row[0])
            self.conn.execute(
                """INSERT INTO evidence(organisation_id, representation_id, evidence_type, source_url,
                source_page_id, excerpt, confidence, review_status, captured_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (client_id, rep_id, "agency_portfolio_listing", evidence_url, page_id,
                 evidence_text[:1500], confidence, "unreviewed", utcnow()),
            )
            self.conn.commit()
            return rep_id

    def add_conference(self, org_id: int, name: str, year: int | None, url: str, source_id: int, confidence: float) -> None:
        with self.lock:
            self.conn.execute(
                """INSERT OR IGNORE INTO conference_appearances(organisation_id, conference_name,
                conference_year, exhibitor_url, source_id, confidence) VALUES(?,?,?,?,?,?)""",
                (org_id, name, year, url, source_id, confidence),
            )
            self.conn.commit()

    def finish(self, counts: dict[str, int], limitations: list[str], status: str = "completed") -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE crawl_runs SET completed_at=?, status=?, counts_json=?, limitations_json=? WHERE id=?",
                (utcnow(), status, json.dumps(counts), json.dumps(limitations), RUN_ID),
            )
            self.conn.commit()
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.conn.commit()
            self.conn.close()


def clean_entity_name(value: str) -> str:
    value = norm_space(value)
    value = re.sub(r"^(view|meet|discover|explore|visit|about)\s+", "", value, flags=re.I)
    value = re.sub(r"\s+(homepage|official site|website)$", "", value, flags=re.I)
    value = value.strip(" |•·–—:-_\t\n\r")
    if not value or len(value) < 2 or len(value) > 120:
        return ""
    if len(value.split()) > 12:
        return ""
    if value.lower() in GENERIC_NAMES:
        return ""
    if re.fullmatch(r"[\d\W_]+", value):
        return ""
    if re.search(r"\b(click|read|learn|view|privacy|cookie|terms|subscribe|newsletter|copyright)\b", value, re.I):
        return ""
    if value.count("/") > 1 or value.count("|") > 1:
        return ""
    return value


def extract_same_domain_links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    host = root_domain(domain_of(base_url))
    scored: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = clean_url(anchor.get("href") or "", base_url)
        if not url or url in seen or root_domain(domain_of(url)) != host:
            continue
        seen.add(url)
        label = norm_space(anchor.get_text(" "))
        haystack = f"{label} {urllib.parse.urlparse(url).path}"
        score = 0
        if PORTFOLIO_TERMS.search(haystack):
            score += 8
        if re.search(r"about|who-we-are|company", haystack, re.I):
            score += 3
        if re.search(r"contact", haystack, re.I):
            score += 1
        depth = urllib.parse.urlparse(url).path.count("/")
        score -= max(depth - 3, 0)
        if score > 0:
            scored.append((score, url, label))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    return [(url, label) for _, url, label in scored[: max(MAX_PAGES_PER_SITE * 2, 12)]]


def element_context(tag: Any) -> str:
    parts = []
    node = tag
    for _ in range(3):
        if node is None:
            break
        if getattr(node, "attrs", None):
            parts.extend([
                " ".join(node.get("class") or []), str(node.get("id") or ""),
                str(node.get("data-testid") or ""), str(node.get("aria-label") or ""),
            ])
        node = getattr(node, "parent", None)
    return " ".join(parts)


def client_name_ok(name: str, agency_name: str) -> bool:
    if not name or name.lower() in GENERIC_NAMES:
        return False
    if norm_name(name) == norm_name(agency_name):
        return False
    if len(name.split()) > 9 or len(name) > 90:
        return False
    if re.search(r"\b(licensing|portfolio|client services|brand management|contact|case study|latest news|"
                 r"consumer products|retail solutions|strategic consulting|brand extension|what we do|"
                 r"our capabilities|our services|terms of use|privacy policy)\b", name, re.I):
        return False
    if name.lower().startswith(("our ", "more ", "all ", "the latest", "find out")):
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]", name):
        return False
    return True


def extract_clients(html: str, page_url: str, agency_name: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    path = urllib.parse.urlparse(page_url).path
    page_text = visible_text(html)[:4000]
    portfolio_page = bool(PORTFOLIO_TERMS.search(path) or re.search(
        r"our brands|our clients|our portfolio|properties we represent|represented brands|client portfolio|brand portfolio",
        page_text, re.I,
    ))
    candidates: dict[str, dict[str, Any]] = {}

    def add(raw: str, confidence: float, method: str, context: str = "", link: str = "") -> None:
        name = clean_entity_name(raw)
        if not client_name_ok(name, agency_name):
            return
        key = norm_name(name)
        if len(key) < 2:
            return
        current = candidates.get(key)
        item = {
            "name": name, "confidence": round(min(confidence, 0.94), 2), "method": method,
            "context": norm_space(context)[:500], "link": clean_url(link, page_url) or "",
        }
        if current is None or item["confidence"] > current["confidence"]:
            candidates[key] = item

    for tag in soup.find_all(["h2", "h3", "h4", "h5", "a", "li", "img"]):
        context = element_context(tag)
        relevant_container = bool(PORTFOLIO_TERMS.search(context))
        if tag.name == "img":
            raw = tag.get("alt") or tag.get("title") or ""
            base_conf = 0.70
            method = "portfolio_image_alt"
            link = ""
        else:
            raw = tag.get_text(" ", strip=True)
            base_conf = 0.72 if tag.name in {"h2", "h3", "h4", "h5"} else 0.64
            method = f"portfolio_{tag.name}_text"
            link = tag.get("href") or "" if tag.name == "a" else ""
        if not (portfolio_page or relevant_container):
            continue
        if relevant_container:
            base_conf += 0.08
        if tag.name == "a" and link and PORTFOLIO_TERMS.search(link):
            base_conf += 0.06
        add(raw, base_conf, method, context, link)

    # Frequently used data attributes in JavaScript portfolio grids.
    for tag in soup.find_all(True):
        context = element_context(tag)
        if not (portfolio_page or PORTFOLIO_TERMS.search(context)):
            continue
        for attr in ("data-title", "data-name", "data-brand", "data-client", "aria-label", "title"):
            if tag.get(attr):
                add(str(tag.get(attr)), 0.72, f"portfolio_{attr}", context)

    # JSON-LD item names can expose card content omitted from visible text.
    for script in soup.find_all("script", type=re.compile("ld\+json", re.I)):
        try:
            payload = json.loads(script.string or "null")
        except Exception:
            continue
        stack = [payload]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if isinstance(value.get("name"), str):
                    add(value["name"], 0.58 if portfolio_page else 0.45, "json_ld_name")
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)

    rows = sorted(candidates.values(), key=lambda x: (-x["confidence"], x["name"].lower()))
    return rows[:350]


def directory_names_from_html(html: str, url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    rows: dict[str, dict[str, str]] = {}
    selector_terms = re.compile(r"exhibitor|company|member|agent|vendor|brand|profile|listing", re.I)
    for tag in soup.find_all(["a", "h2", "h3", "h4", "li"]):
        context = element_context(tag)
        href = clean_url(tag.get("href") or "", url) if tag.name == "a" else ""
        raw = norm_space(tag.get_text(" "))
        if not (selector_terms.search(context) or (href and selector_terms.search(href))):
            continue
        name = clean_entity_name(raw)
        if not name or name.lower() in GENERIC_NAMES or len(name.split()) > 12:
            continue
        key = norm_name(name)
        if len(key) < 3:
            continue
        rows.setdefault(key, {"name": name, "profile_url": href or url})
    return list(rows.values())[:5000]


def directory_names_from_pdf(body: bytes) -> list[dict[str, str]]:
    try:
        reader = PdfReader(io.BytesIO(body))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        record_error("pdf_parse", "directory PDF", exc)
        return []
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        line = clean_entity_name(line)
        if not line or line.lower() in GENERIC_NAMES:
            continue
        if re.search(r"\b(booth|stand|page|exhibitor list|floor plan|conference|licensing expo|brand licensing europe)\b", line, re.I):
            continue
        if re.fullmatch(r"[A-Z]?\d{1,5}[A-Z]?", line):
            continue
        if len(line.split()) > 12:
            continue
        rows.setdefault(norm_name(line), {"name": line, "profile_url": ""})
    return list(rows.values())[:8000]


def render_directory(url: str) -> str:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1600,1200")
        options.add_argument(f"--user-agent={USER_AGENT}")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(45)
        driver.get(url)
        previous = 0
        stable = 0
        for _ in range(28):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.75)
            height = driver.execute_script("return document.body.scrollHeight")
            if height == previous:
                stable += 1
            else:
                stable = 0
            previous = height
            # Click common load-more controls without submitting forms.
            for node in driver.find_elements(By.XPATH, "//*[self::button or self::a][contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more') or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]")[:2]:
                try:
                    driver.execute_script("arguments[0].click()", node)
                    time.sleep(0.5)
                except Exception:
                    pass
            if stable >= 3:
                break
        html = driver.page_source
        driver.quit()
        return html
    except Exception as exc:
        record_error("render_directory", url, exc)
        try:
            driver.quit()  # type: ignore[name-defined]
        except Exception:
            pass
        return ""


def process_directory(db: Database, entry: dict[str, str]) -> list[dict[str, Any]]:
    name = entry["name"]
    url = entry["url"]
    source_id = db.add_source(name=name, source_type=entry.get("kind", "directory"), url=url, discovered_from="seed_registry")
    result = fetch(url, timeout=25)
    if result is None:
        db.update_source(source_id, None, "Fetch failed")
        return []
    db.update_source(source_id, result)
    html = ""
    rows: list[dict[str, str]] = []
    if "pdf" in result.content_type or result.body.startswith(b"%PDF"):
        page_id = db.add_page(source_id, result, role="directory_pdf")
        rows = directory_names_from_pdf(result.body)
    else:
        html = decode_body(result)
        page_id = db.add_page(source_id, result, html=html, role="directory")
        rows = directory_names_from_html(html, result.final_url)
        if len(rows) < 10 and entry.get("kind") in {"conference", "member_directory", "industry_directory"}:
            rendered = render_directory(url)
            if rendered:
                rendered_rows = directory_names_from_html(rendered, result.final_url)
                if len(rendered_rows) > len(rows):
                    rows = rendered_rows
    conference_year_match = re.search(r"(20\d{2})", name)
    conference_year = int(conference_year_match.group(1)) if conference_year_match else None
    discovered: list[dict[str, Any]] = []
    for row in rows:
        org_id = db.upsert_org(
            row["name"], "conference_exhibitor" if entry.get("kind", "").startswith("conference") else "directory_member",
            website=row.get("profile_url", ""), region="Unknown", discovery_method=f"directory:{name}",
            confidence=0.62, verification_status="directory_listed_unclassified",
        )
        if org_id and entry.get("kind", "").startswith("conference"):
            db.add_conference(org_id, name, conference_year, row.get("profile_url") or url, source_id, 0.75)
        discovered.append({"name": row["name"], "url": row.get("profile_url", ""), "source": name, "page_id": page_id})
    return discovered


@dataclass
class SiteCandidate:
    name: str
    url: str
    region: str = "Unknown"
    seed_type: str = "agency_candidate"
    discovery: set[str] = field(default_factory=set)
    confidence: float = 0.5


def merge_candidate(store: dict[str, SiteCandidate], candidate: SiteCandidate) -> None:
    url = clean_url(candidate.url) or ""
    host = root_domain(domain_of(url))
    if not host or is_excluded_domain(host):
        return
    key = host
    if key in store:
        old = store[key]
        old.discovery.update(candidate.discovery)
        if len(candidate.name) > len(old.name) and ratio(norm_name(candidate.name), norm_name(old.name)) > 55:
            old.name = candidate.name
        if old.region == "Unknown" and candidate.region != "Unknown":
            old.region = candidate.region
        if old.seed_type == "agency_candidate" and candidate.seed_type != "agency_candidate":
            old.seed_type = candidate.seed_type
        old.confidence = max(old.confidence, candidate.confidence)
    else:
        candidate.url = url
        store[key] = candidate


def resolve_known_sites(seeds: dict[str, Any]) -> dict[str, SiteCandidate]:
    store: dict[str, SiteCandidate] = {}
    missing: list[dict[str, str]] = []
    for org in seeds["known_organisations"]:
        if org.get("url"):
            merge_candidate(store, SiteCandidate(
                name=org["name"], url=org["url"], region=org.get("region", "Unknown"),
                seed_type=org.get("seed_type", "agency"), discovery={"manual_seed"}, confidence=0.82,
            ))
        else:
            missing.append(org)
    for index, org in enumerate(missing):
        rows = web_search(f'"{org["name"]}" licensing')
        url = choose_official_result(org["name"], rows)
        if url:
            merge_candidate(store, SiteCandidate(
                name=org["name"], url=url, region=org.get("region", "Unknown"),
                seed_type=org.get("seed_type", "agency"), discovery={"seed_name_search"}, confidence=0.68,
            ))
        if index and index % 10 == 0:
            time.sleep(0.4)
    return store


def discover_sites_by_search(seeds: dict[str, Any], store: dict[str, SiteCandidate]) -> None:
    for index, query in enumerate(seeds["discovery_queries"]):
        for row in web_search(query):
            url = row.get("url") or ""
            host = domain_of(url)
            if not host or is_excluded_domain(host):
                continue
            snippet = f"{row.get('title','')} {row.get('description','')}"
            signal = score_text(snippet, AGENCY_TERMS) + score_text(snippet, LICENSOR_TERMS) - score_text(snippet, NEGATIVE_TERMS)
            if signal < 2 and not re.search(r"licen[cs]", snippet, re.I):
                continue
            name = clean_entity_name(re.split(r"[|–—:]", row.get("title") or "")[0]) or host
            merge_candidate(store, SiteCandidate(
                name=name, url=url, region=infer_region(query), seed_type="agency_candidate",
                discovery={f"web_search:{query}"}, confidence=min(0.52 + signal * 0.025, 0.76),
            ))
        if index and index % 12 == 0:
            time.sleep(0.5)
        if len(store) >= MAX_SITES * 2:
            break


def classify_site(candidate: SiteCandidate, html: str, final_url: str) -> tuple[str, float, str, str]:
    text = visible_text(html)[:50000]
    title = page_title(html)
    combined = f"{title} {text}"
    agency_score = score_text(combined, AGENCY_TERMS)
    licensor_score = score_text(combined, LICENSOR_TERMS)
    negative = score_text(combined, NEGATIVE_TERMS)
    agency_score -= negative
    licensor_score -= negative
    seeded = candidate.seed_type
    if seeded in {"agency", "art_agency", "cultural_agency", "rights_agency", "music_agency", "experiential_agency"}:
        org_type = "licensing_agency"
        confidence = max(candidate.confidence, 0.70 + min(max(agency_score, 0), 12) * 0.015)
    elif seeded in {"licensor", "brand_owner"}:
        org_type = "licensor_brand_owner"
        confidence = max(candidate.confidence, 0.70 + min(max(licensor_score, 0), 12) * 0.015)
    elif agency_score >= 6 and agency_score >= licensor_score:
        org_type = "licensing_agency"
        confidence = min(0.55 + agency_score * 0.025, 0.90)
    elif licensor_score >= 5:
        org_type = "licensor_brand_owner"
        confidence = min(0.55 + licensor_score * 0.025, 0.88)
    elif re.search(r"licen[cs]", combined, re.I) and agency_score >= 2:
        org_type = "licensing_business_unclassified"
        confidence = 0.52
    else:
        org_type = "not_confirmed_relevant"
        confidence = max(0.20, candidate.confidence - 0.25)
    description = ""
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", attrs={"name": re.compile("description", re.I)}) or soup.find("meta", property="og:description")
    if meta:
        description = norm_space(meta.get("content"))
    if not description:
        description = text[:500]
    region = infer_region(combined, candidate.region)
    return org_type, round(min(confidence, 0.96), 2), description, region


def crawl_site(db: Database, candidate: SiteCandidate) -> dict[str, Any]:
    source_id = db.add_source(
        name=candidate.name, source_type="organisation_website", url=candidate.url,
        discovered_from="; ".join(sorted(candidate.discovery)), region=candidate.region,
    )
    homepage = fetch(candidate.url)
    if homepage is None:
        db.update_source(source_id, None, "Homepage fetch failed")
        return {"status": "failed", "candidate": candidate.name}
    db.update_source(source_id, homepage)
    if homepage.status >= 400 or not homepage.body:
        db.add_page(source_id, homepage, role="homepage_error")
        return {"status": "http_error", "candidate": candidate.name, "http": homepage.status}
    html = decode_body(homepage)
    page_id = db.add_page(source_id, homepage, html=html, role="homepage")
    org_type, confidence, description, region = classify_site(candidate, html, homepage.final_url)
    if org_type == "not_confirmed_relevant" and "manual_seed" not in candidate.discovery:
        return {"status": "not_relevant", "candidate": candidate.name}
    agency_id = db.upsert_org(
        candidate.name, org_type, website=homepage.final_url, region=region, description=description,
        discovery_method="; ".join(sorted(candidate.discovery)), confidence=confidence,
        verification_status="website_fetched_machine_classified",
    )
    if not agency_id:
        return {"status": "invalid_name", "candidate": candidate.name}
    db.conn.execute(
        "INSERT INTO evidence(organisation_id, evidence_type, source_url, source_page_id, excerpt, confidence, review_status, captured_at) VALUES(?,?,?,?,?,?,?,?)",
        (agency_id, "organisation_website", homepage.final_url, page_id, description[:1000], confidence, "unreviewed", utcnow()),
    )
    db.conn.commit()

    pages = [(homepage.final_url, html, page_id)]
    visited = {clean_url(homepage.final_url)}
    links = extract_same_domain_links(html, homepage.final_url)
    for url, label in links:
        if len(pages) >= MAX_PAGES_PER_SITE:
            break
        url = clean_url(url)
        if not url or url in visited:
            continue
        visited.add(url)
        result = fetch(url)
        if not result or result.status >= 400 or not result.body:
            continue
        child_html = decode_body(result)
        role = "portfolio" if PORTFOLIO_TERMS.search(f"{url} {label}") else "site_page"
        child_page_id = db.add_page(source_id, result, html=child_html, role=role)
        pages.append((result.final_url, child_html, child_page_id))

    relationships = 0
    if org_type == "licensing_agency":
        combined_clients: dict[str, dict[str, Any]] = {}
        for url, child_html, child_page_id in pages:
            for item in extract_clients(child_html, url, candidate.name):
                key = norm_name(item["name"])
                existing = combined_clients.get(key)
                item["url"] = url
                item["page_id"] = child_page_id
                if existing is None or item["confidence"] > existing["confidence"]:
                    combined_clients[key] = item
        for item in sorted(combined_clients.values(), key=lambda x: (-x["confidence"], x["name"].lower()))[:500]:
            client_id = db.upsert_org(
                item["name"], "brand_or_property", website=item.get("link", ""), region="Unknown",
                discovery_method=f"agency_portfolio:{candidate.name}", confidence=item["confidence"],
                verification_status="machine_extracted_from_agency_portfolio",
            )
            if not client_id or client_id == agency_id:
                continue
            excerpt = item.get("context") or f"Listed on {candidate.name} portfolio page"
            db.add_representation(
                agency_id, client_id, item["url"], item["page_id"], excerpt,
                item["method"], item["confidence"],
            )
            relationships += 1
    return {
        "status": "indexed", "candidate": candidate.name, "organisation_type": org_type,
        "pages": len(pages), "relationships": relationships, "confidence": confidence,
    }


def export_database(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    agencies = [dict(r) for r in conn.execute(
        """SELECT o.*, COUNT(DISTINCT r.client_id) AS client_count,
        COUNT(DISTINCT p.id) AS captured_page_count
        FROM organisations o
        LEFT JOIN representations r ON r.agency_id=o.id
        LEFT JOIN sources s ON s.domain=o.domain
        LEFT JOIN pages p ON p.source_id=s.id
        WHERE o.organisation_type='licensing_agency'
        GROUP BY o.id ORDER BY client_count DESC, o.canonical_name COLLATE NOCASE"""
    )]
    licensors = [dict(r) for r in conn.execute(
        "SELECT * FROM organisations WHERE organisation_type='licensor_brand_owner' ORDER BY canonical_name COLLATE NOCASE"
    )]
    properties = [dict(r) for r in conn.execute(
        """SELECT o.*, COUNT(DISTINCT r.agency_id) AS agency_count
        FROM organisations o LEFT JOIN representations r ON r.client_id=o.id
        WHERE o.organisation_type='brand_or_property'
        GROUP BY o.id ORDER BY agency_count DESC, canonical_name COLLATE NOCASE"""
    )]
    relationships = [dict(r) for r in conn.execute(
        """SELECT r.id, a.canonical_name AS agency_name, a.website AS agency_website,
        c.canonical_name AS client_name, c.website AS client_website,
        r.evidence_url, r.evidence_text, r.extraction_method, r.confidence,
        r.verification_status, r.territory
        FROM representations r
        JOIN organisations a ON a.id=r.agency_id
        JOIN organisations c ON c.id=r.client_id
        ORDER BY a.canonical_name COLLATE NOCASE, c.canonical_name COLLATE NOCASE"""
    )]
    sources = [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY name COLLATE NOCASE")]
    conferences = [dict(r) for r in conn.execute(
        """SELECT ca.*, o.canonical_name AS organisation_name
        FROM conference_appearances ca JOIN organisations o ON o.id=ca.organisation_id
        ORDER BY conference_name, organisation_name COLLATE NOCASE"""
    )]
    type_counts = {r["organisation_type"]: r["n"] for r in conn.execute(
        "SELECT organisation_type, COUNT(*) n FROM organisations GROUP BY organisation_type"
    )}
    counts = {
        "licensing_agencies": type_counts.get("licensing_agency", 0),
        "licensor_brand_owners": type_counts.get("licensor_brand_owner", 0),
        "brands_and_properties": type_counts.get("brand_or_property", 0),
        "conference_exhibitors_and_directory_members": type_counts.get("conference_exhibitor", 0) + type_counts.get("directory_member", 0),
        "all_organisations": sum(type_counts.values()),
        "agency_client_relationships": len(relationships),
        "sources_registered": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "sources_fetched": conn.execute("SELECT COUNT(*) FROM sources WHERE status='fetched'").fetchone()[0],
        "pages_captured": conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
        "conference_appearances": len(conferences),
        "errors": len(_errors),
    }
    payload = {
        "metadata": {
            "run_id": RUN_ID,
            "started_at": RUN_STARTED.isoformat(timespec="seconds"),
            "completed_at": utcnow(),
            "methodology": "Public-web directory discovery plus respectful crawl of organisation websites and machine extraction of portfolio relationships.",
            "verification_note": "Rows marked machine_extracted_unverified require human confirmation before outreach.",
            "scope_note": "This is a broad public-web index, not a mathematical guarantee of every licensing business worldwide. Login-only, paywalled, blocked and non-indexed organisations may be absent.",
        },
        "counts": counts,
        "agencies": agencies,
        "licensors": licensors,
        "properties": properties,
        "relationships": relationships,
        "sources": sources,
        "conference_appearances": conferences,
        "organisation_type_counts": type_counts,
        "limitations": [
            "Only publicly accessible pages were fetched; no login, paywall, CAPTCHA or access control was bypassed.",
            "robots.txt exclusions were respected.",
            "Portfolio names are machine-extracted and can contain false positives until reviewed.",
            "Representation territories and exclusivity are often not stated publicly and remain blank unless found.",
            "Conference directories change over time and may expose incomplete or JavaScript-only records.",
        ],
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    STATS_PATH.write_text(json.dumps(payload["metadata"] | {"counts": counts, "organisation_type_counts": type_counts}, indent=2), encoding="utf-8")
    ERRORS_PATH.write_text(json.dumps(_errors, ensure_ascii=False, indent=2), encoding="utf-8")

    with AGENCIES_CSV.open("w", newline="", encoding="utf-8") as handle:
        fields = ["id", "canonical_name", "website", "domain", "region", "description", "confidence", "verification_status", "client_count", "captured_page_count"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(agencies)
    with RELATIONSHIPS_CSV.open("w", newline="", encoding="utf-8") as handle:
        fields = ["id", "agency_name", "agency_website", "client_name", "client_website", "evidence_url", "evidence_text", "extraction_method", "confidence", "verification_status", "territory"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(relationships)
    with SOURCES_CSV.open("w", newline="", encoding="utf-8") as handle:
        fields = ["id", "name", "source_type", "url", "domain", "discovered_from", "region", "status", "http_status", "content_type", "last_crawled_at", "robots_allowed", "error"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(sources)
    conn.close()
    return payload


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seeds = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
    db = Database(DB_PATH)
    print(f"[{RUN_ID}] Starting licensing universe crawl", flush=True)

    directory_discoveries: list[dict[str, Any]] = []
    for entry in seeds["directories"]:
        try:
            rows = process_directory(db, entry)
            directory_discoveries.extend(rows)
            print(f"Directory {entry['name']}: {len(rows)} names", flush=True)
        except Exception as exc:
            record_error("directory", entry.get("url", entry.get("name", "")), exc)

    candidates = resolve_known_sites(seeds)
    print(f"Resolved known website seeds: {len(candidates)}", flush=True)
    discover_sites_by_search(seeds, candidates)
    print(f"Website candidates after search discovery: {len(candidates)}", flush=True)

    # Directory records that link directly to an external official domain join the crawl queue.
    for row in directory_discoveries:
        url = row.get("url") or ""
        host = domain_of(url)
        if host and not any(marker in root_domain(host) for marker in DIRECTORY_DOMAIN_MARKERS) and not is_excluded_domain(host):
            merge_candidate(candidates, SiteCandidate(
                name=row["name"], url=url, region="Unknown", seed_type="agency_candidate",
                discovery={f"directory_link:{row.get('source','directory')}"}, confidence=0.58,
            ))

    candidate_list = sorted(candidates.values(), key=lambda c: (-c.confidence, c.name.lower()))[:MAX_SITES]
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(crawl_site, db, candidate): candidate for candidate in candidate_list}
        for index, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            candidate = future_map[future]
            try:
                outcome = future.result()
            except Exception as exc:
                record_error("crawl_site", candidate.url, exc)
                outcome = {"status": "exception", "candidate": candidate.name, "error": str(exc)}
            results.append(outcome)
            if index % 25 == 0 or index == len(candidate_list):
                indexed = sum(1 for row in results if row.get("status") == "indexed")
                relationships = sum(int(row.get("relationships", 0)) for row in results)
                print(f"Sites {index}/{len(candidate_list)}; indexed={indexed}; relationships={relationships}", flush=True)

    # Export while connection remains available; then write final run metadata.
    db.conn.commit()
    preliminary = export_database(DB_PATH)
    counts = preliminary["counts"]
    limitations = preliminary["limitations"]
    db.finish(counts, limitations)
    # Re-export so crawl_runs contains completed status in the binary database.
    payload = export_database(DB_PATH)

    result_summary = Counter(row.get("status", "unknown") for row in results)
    print(json.dumps({
        "run_id": RUN_ID,
        "counts": payload["counts"],
        "site_outcomes": result_summary,
        "database": str(DB_PATH),
        "json": str(JSON_PATH),
    }, indent=2, default=dict), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        record_error("fatal", "crawler", exc)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ERRORS_PATH.write_text(json.dumps(_errors, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FATAL: {exc}", file=sys.stderr, flush=True)
        raise
