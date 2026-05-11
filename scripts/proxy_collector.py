#!/usr/bin/env python3
"""Collect, test, and rank free proxy servers for GitHub Actions.

The script is intentionally dependency-light and writes three files:
- proxy-list.md   : human-readable Markdown table
- proxy-list.json : machine-readable list used by 04-browser.yml
- proxy-list.env  : first/fastest proxy in dotenv format

Latency is measured as an HTTP(S) request round-trip through the proxy, not ICMP ping.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import html
import ipaddress
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse, unquote

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Sources are deliberately plain-text/raw endpoints when possible because they are
# more stable for automation than browser-rendered HTML tables.
DEFAULT_SOURCES: List[Tuple[str, str]] = [
    ("http", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"),
    ("socks4", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt"),
    ("socks5", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"),
    ("http", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"),
    ("socks4", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt"),
    ("socks5", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt"),
    ("http", "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt"),
    ("socks4", "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt"),
    ("socks5", "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt"),
    # HTML fallback. The generic regex parser can still extract IP:PORT pairs.
    ("http", "https://free-proxy-list.net/"),
    ("http", "https://www.sslproxies.org/"),
]

PROXY_PATTERN = re.compile(
    r"(?:(?P<scheme>https?|socks4|socks5)://)?"
    r"(?:(?P<user>[^:@\s/]+)(?::(?P<password>[^@\s/]+))?@)?"
    r"(?P<host>(?:\d{1,3}\.){3}\d{1,3}|\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+)"
    r":(?P<port>\d{2,5})"
)


@dataclass(frozen=True)
class ProxyCandidate:
    scheme: str
    host: str
    port: int
    username: str = ""
    password: str = ""
    source: str = ""

    @property
    def server(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def proxy_url(self) -> str:
        if self.username:
            auth = self.username
            if self.password:
                auth += f":{self.password}"
            auth += "@"
        else:
            auth = ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def key(self) -> str:
        return f"{self.scheme}://{self.username}:{self.password}@{self.host}:{self.port}"


@dataclass
class ProxyResult:
    PROXY_SERVER: str
    PROXY_USERNAME: str
    PROXY_PASSWORD: str
    ping_ms: int
    protocol: str
    status_code: int
    final_url: str
    observed_ip: str
    source: str
    tested_at_utc: str


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_sources_from_file(path: Path) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    if not path.exists():
        raise FileNotFoundError(f"sources file not found: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Supported formats:
        #   http https://example.com/list.txt
        #   socks5,https://example.com/socks.txt
        #   https://example.com/list.txt     -> auto/http fallback
        if "," in line:
            first, second = [part.strip() for part in line.split(",", 1)]
            if first.lower() in {"http", "https", "socks4", "socks5", "auto"}:
                rows.append((first.lower(), second))
            else:
                rows.append(("auto", line))
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() in {"http", "https", "socks4", "socks5", "auto"}:
            rows.append((parts[0].lower(), parts[1]))
        else:
            rows.append(("auto", line))
    return rows


def normalize_scheme(value: str, fallback: str) -> str:
    value = (value or "").lower().strip()
    fallback = (fallback or "http").lower().strip()
    if value in {"http", "https", "socks4", "socks5"}:
        return value
    if fallback in {"http", "https", "socks4", "socks5"}:
        return fallback
    return "http"


def valid_host(host: str) -> bool:
    clean = host.strip("[]")
    try:
        ip = ipaddress.ip_address(clean)
        if ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_reserved or ip.is_link_local or ip.is_unspecified:
            return False
        return True
    except ValueError:
        # Allow public-looking hostnames, reject localhost-ish names.
        lowered = clean.lower()
        return lowered not in {"localhost", "local"} and "." in lowered


def parse_candidates(text: str, fallback_scheme: str, source: str, protocol_filter: str) -> List[ProxyCandidate]:
    candidates: List[ProxyCandidate] = []
    decoded = html.unescape(text)
    for match in PROXY_PATTERN.finditer(decoded):
        host = (match.group("host") or "").strip("[]")
        port_raw = match.group("port") or ""
        try:
            port = int(port_raw)
        except ValueError:
            continue
        if port < 1 or port > 65535 or not valid_host(host):
            continue
        scheme = normalize_scheme(match.group("scheme") or "", fallback_scheme)
        if protocol_filter != "all" and scheme != protocol_filter:
            continue
        username = unquote(match.group("user") or "")
        password = unquote(match.group("password") or "")
        candidates.append(ProxyCandidate(scheme, host, port, username, password, source))
    return candidates


def fetch_source(session: requests.Session, source: Tuple[str, str], protocol_filter: str, timeout: float) -> List[ProxyCandidate]:
    fallback_scheme, url = source
    try:
        response = session.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except Exception as exc:
        print(f"WARN: failed to fetch source {url}: {exc}", file=sys.stderr)
        return []
    return parse_candidates(response.text, fallback_scheme, url, protocol_filter)


def dedupe(candidates: Iterable[ProxyCandidate]) -> List[ProxyCandidate]:
    seen: Dict[str, ProxyCandidate] = {}
    for candidate in candidates:
        seen.setdefault(candidate.key, candidate)
    return list(seen.values())


def test_proxy(candidate: ProxyCandidate, test_url: str, timeout: float) -> Optional[ProxyResult]:
    proxies = {
        "http": candidate.proxy_url,
        "https": candidate.proxy_url,
    }
    started = time.perf_counter()
    try:
        response = requests.get(
            test_url,
            proxies=proxies,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"},
            allow_redirects=True,
        )
        elapsed_ms = int(round((time.perf_counter() - started) * 1000))
        if response.status_code >= 400:
            return None
        observed_ip = ""
        ctype = response.headers.get("content-type", "")
        if "json" in ctype.lower():
            try:
                data = response.json()
                observed_ip = str(data.get("ip") or data.get("origin") or data.get("query") or "")
            except Exception:
                observed_ip = ""
        if not observed_ip:
            text = response.text.strip()
            if len(text) <= 120:
                observed_ip = text
        return ProxyResult(
            PROXY_SERVER=candidate.server,
            PROXY_USERNAME=candidate.username,
            PROXY_PASSWORD=candidate.password,
            ping_ms=elapsed_ms,
            protocol=candidate.scheme,
            status_code=response.status_code,
            final_url=response.url,
            observed_ip=observed_ip,
            source=candidate.source,
            tested_at_utc=utc_now(),
        )
    except Exception:
        return None


def markdown_escape(value: object) -> str:
    text = str(value if value is not None else "")
    text = text.replace("|", "\\|").replace("\n", " ").strip()
    return text


def write_outputs(results: List[ProxyResult], output_md: Path, output_json: Path, output_env: Path, metadata: Dict[str, object]) -> None:
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_env.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "metadata": metadata,
        "proxies": [asdict(result) for result in results],
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Proxy List",
        "",
        "این فایل توسط workflow شماره ۵ ساخته شده است.",
        "",
        "> مقدار `ping_ms` زمان رفت‌وبرگشت یک درخواست HTTP/HTTPS از داخل GitHub Actions از مسیر همان proxy است؛ ICMP ping نیست.",
        "",
        "## Fastest proxies",
        "",
        "| Rank | PROXY_SERVER | PROXY_USERNAME | PROXY_PASSWORD | ping_ms | protocol | status | observed_ip | source |",
        "|---:|---|---|---|---:|---|---:|---|---|",
    ]
    for index, result in enumerate(results, start=1):
        source = result.source
        if len(source) > 80:
            source = source[:77] + "..."
        lines.append(
            "| {rank} | `{server}` | `{username}` | `{password}` | {ping} | `{protocol}` | {status} | `{ip}` | `{source}` |".format(
                rank=index,
                server=markdown_escape(result.PROXY_SERVER),
                username=markdown_escape(result.PROXY_USERNAME),
                password=markdown_escape(result.PROXY_PASSWORD),
                ping=result.ping_ms,
                protocol=markdown_escape(result.protocol),
                status=result.status_code,
                ip=markdown_escape(result.observed_ip),
                source=markdown_escape(source),
            )
        )
    if not results:
        lines.append("| - | - | - | - | - | - | - | - | - |")
    lines += [
        "",
        "## استفاده در workflow شماره ۴",
        "",
        "در workflow `🌐 4-Browse the Web` مقدار `proxy_mode` را روی `fastest-from-file` بگذارید تا ردیف اول همین فایل استفاده شود. برای انتخاب ردیف دیگر، `proxy_mode=rank-from-file` و `proxy_list_rank` را برابر شماره ردیف جدول بگذارید.",
        "",
        "فایل ماشینی متناظر: `proxy-list.json`",
        "",
    ]
    output_md.write_text("\n".join(lines), encoding="utf-8")

    if results:
        first = results[0]
        env_lines = [
            f"PROXY_SERVER={first.PROXY_SERVER}",
            f"PROXY_USERNAME={first.PROXY_USERNAME}",
            f"PROXY_PASSWORD={first.PROXY_PASSWORD}",
            f"PROXY_PING_MS={first.ping_ms}",
            f"PROXY_PROTOCOL={first.protocol}",
        ]
    else:
        env_lines = ["PROXY_SERVER=", "PROXY_USERNAME=", "PROXY_PASSWORD=", "PROXY_PING_MS=", "PROXY_PROTOCOL="]
    output_env.write_text("\n".join(env_lines) + "\n", encoding="utf-8")


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect and rank free proxies by real request latency.")
    parser.add_argument("--count", type=positive_int, default=int(os.getenv("PROXY_COUNT", "10")))
    parser.add_argument("--protocol", choices=["http", "https", "socks4", "socks5", "all"], default=os.getenv("PROXY_PROTOCOL", "http"))
    parser.add_argument("--test-url", default=os.getenv("PROXY_TEST_URL", "https://api.ipify.org?format=json"))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("PROXY_TEST_TIMEOUT", "8")))
    parser.add_argument("--fetch-timeout", type=float, default=float(os.getenv("PROXY_FETCH_TIMEOUT", "20")))
    parser.add_argument("--concurrency", type=positive_int, default=int(os.getenv("PROXY_CONCURRENCY", "80")))
    parser.add_argument("--max-candidates", type=positive_int, default=int(os.getenv("PROXY_MAX_CANDIDATES", "1200")))
    parser.add_argument("--sources-file", default=os.getenv("PROXY_SOURCES_FILE", ""))
    parser.add_argument("--output-md", default=os.getenv("PROXY_OUTPUT_MD", "proxy-list.md"))
    parser.add_argument("--output-json", default=os.getenv("PROXY_OUTPUT_JSON", "proxy-list.json"))
    parser.add_argument("--output-env", default=os.getenv("PROXY_OUTPUT_ENV", "proxy-list.env"))
    parser.add_argument("--shuffle", action="store_true", default=os.getenv("PROXY_SHUFFLE", "true").lower() in {"1", "true", "yes", "on"})
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = utc_now()

    sources = read_sources_from_file(Path(args.sources_file)) if args.sources_file else DEFAULT_SOURCES
    if args.protocol != "all":
        # Keep sources that are explicitly compatible or auto-detected.
        sources = [(scheme, url) for scheme, url in sources if scheme in {args.protocol, "auto"}]

    session = requests.Session()
    all_candidates: List[ProxyCandidate] = []
    with futures.ThreadPoolExecutor(max_workers=min(12, max(1, len(sources)))) as pool:
        fetch_jobs = [pool.submit(fetch_source, session, source, args.protocol, args.fetch_timeout) for source in sources]
        for job in futures.as_completed(fetch_jobs):
            all_candidates.extend(job.result())

    candidates = dedupe(all_candidates)
    if args.shuffle:
        random.shuffle(candidates)
    candidates = candidates[: args.max_candidates]

    print(f"Collected {len(candidates)} unique proxy candidates. Testing up to {args.max_candidates} candidates...")

    results: List[ProxyResult] = []
    with futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        test_jobs = [pool.submit(test_proxy, candidate, args.test_url, args.timeout) for candidate in candidates]
        for job in futures.as_completed(test_jobs):
            result = job.result()
            if result:
                results.append(result)
                print(f"OK {result.PROXY_SERVER} ping_ms={result.ping_ms}")

    results.sort(key=lambda item: item.ping_ms)
    selected = results[: args.count]
    metadata: Dict[str, object] = {
        "generated_at_utc": utc_now(),
        "started_at_utc": started_at,
        "requested_count": args.count,
        "protocol": args.protocol,
        "test_url": args.test_url,
        "timeout_seconds": args.timeout,
        "concurrency": args.concurrency,
        "source_count": len(sources),
        "candidate_count": len(candidates),
        "working_count": len(results),
        "selected_count": len(selected),
        "note": "ping_ms is HTTP request latency through the proxy, not ICMP ping.",
    }
    write_outputs(selected, Path(args.output_md), Path(args.output_json), Path(args.output_env), metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if not selected:
        print("ERROR: no working proxies found. Try a larger timeout, a smaller protocol filter, or a custom sources file.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
