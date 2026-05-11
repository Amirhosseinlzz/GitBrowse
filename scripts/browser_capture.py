#!/usr/bin/env python3
"""Browser capture runner for GitHub Actions.

Features:
- Opens a page with a real Chromium browser through Playwright.
- Handles cookie / age / confirm popups with default and user-provided rules.
- Runs Selenium-like automation steps from JSON.
- Saves screenshot, final DOM, MHTML, offline HTML with local assets, network logs,
  downloads, cookies/localStorage/sessionStorage state, and Markdown summaries.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import mimetypes
import os
import posixpath
import random
import re
import shutil
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import (  # type: ignore
    APIResponse,
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

VIDEO_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".avi",
    ".mov",
    ".mkv",
    ".m4v",
    ".flv",
    ".wmv",
    ".mpeg",
    ".mpg",
    ".3gp",
    ".ogv",
}

TEXT_BODY_HINTS = (
    "text/",
    "application/json",
    "application/javascript",
    "application/x-javascript",
    "application/xml",
    "application/xhtml+xml",
    "application/rss+xml",
    "application/atom+xml",
    "image/svg+xml",
)

SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
    "x-xsrf-token",
}

DEFAULT_POPUP_RULES: List[Dict[str, Any]] = [
    {
        "name": "Common cookie / age accept button",
        "role": "button",
        "name_regex": r"^(accept|accept all|allow all|agree|i agree|ok|okay|continue|enter|yes|confirm|got it|save and accept|i am 18|i am over 18|over 18|بالای 18|بالای ۱۸|من بالای 18|من بالای ۱۸|تایید|تأیید|قبول|موافقم|ادامه|ورود|بله|متوجه شدم)$",
        "timeout": 900,
    },
    {
        "name": "Cookie banners with data-testid",
        "selector": "[data-testid*='accept' i], [id*='accept' i], [class*='accept' i]",
        "timeout": 700,
    },
    {
        "name": "OneTrust accept button",
        "selector": "#onetrust-accept-btn-handler, .ot-sdk-container #accept-recommended-btn-handler",
        "timeout": 700,
    },
    {
        "name": "Cookiebot accept button",
        "selector": "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, #CybotCookiebotDialogBodyButtonAccept",
        "timeout": 700,
    },
    {
        "name": "Consent manager accept button",
        "selector": "button:has-text('Accept'), button:has-text('Accept all'), button:has-text('I agree'), button:has-text('Allow all'), button:has-text('OK')",
        "timeout": 700,
    },
    {
        "name": "Persian accept button",
        "selector": "button:has-text('قبول'), button:has-text('تایید'), button:has-text('تأیید'), button:has-text('ادامه'), button:has-text('ورود'), button:has-text('بله')",
        "timeout": 700,
    },
    {
        "name": "Close modal button",
        "selector": "button[aria-label='Close'], button[aria-label='close'], .modal button.close, .popup button.close, .modal .close, .popup .close",
        "timeout": 500,
    },
]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def timestamp() -> str:
    return now_utc().strftime("%Y%m%d_%H%M%S")


def safe_slug(value: str, max_len: int = 110) -> str:
    value = value.strip()
    value = re.sub(r"^https?://", "", value, flags=re.I)
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-") or "page"
    return value[:max_len]


def sanitize_session_key(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("._-") or "default"


def normalize_url(raw_url: str) -> str:
    raw_url = raw_url.strip()
    if not raw_url:
        raise ValueError("URL is empty")
    if not re.match(r"^https?://", raw_url, flags=re.I):
        raw_url = "https://" + raw_url
    return raw_url


def domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.split("@").pop().split(":")[0].lower()
    return re.sub(r"^www\.", "", domain) or "unknown-domain"


def bytes_to_human(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def load_json_argument(value: str, file_path: Optional[str], default: Any, label: str) -> Any:
    if file_path:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"{label} file not found: {file_path}")
        value = path.read_text(encoding="utf-8")
    value = (value or "").strip()
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {label} JSON: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip("\n") + "\n")


def write_github_env(values: Dict[str, str]) -> None:
    github_env = os.getenv("GITHUB_ENV")
    if not github_env:
        return
    with open(github_env, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")



def first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def parse_proxy_server(raw_server: str, username: str = "", password: str = "") -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Return a Playwright proxy config and non-sensitive metadata.

    Playwright expects credentials separately from the server URL. This function
    accepts both forms:
    - http://1.2.3.4:8080
    - socks5://user:pass@1.2.3.4:1080
    - 1.2.3.4:8080  -> treated as http://1.2.3.4:8080
    """
    raw_server = (raw_server or "").strip()
    if not raw_server:
        raise ValueError("proxy server is empty")
    if not re.match(r"^(https?|socks4|socks5)://", raw_server, flags=re.I):
        raw_server = "http://" + raw_server
    parsed = urlparse(raw_server)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https", "socks4", "socks5"}:
        raise ValueError(f"unsupported proxy scheme: {scheme}")
    if not parsed.hostname:
        raise ValueError(f"invalid proxy server: {raw_server}")
    host = parsed.hostname
    port = parsed.port
    if not port:
        raise ValueError("proxy server must include a port, for example http://1.2.3.4:8080")
    if ":" in host and not host.startswith("["):
        host_for_url = f"[{host}]"
    else:
        host_for_url = host
    server = f"{scheme}://{host_for_url}:{port}"
    proxy_username = first_non_empty(username, unquote(parsed.username or ""))
    proxy_password = first_non_empty(password, unquote(parsed.password or ""))
    config: Dict[str, str] = {"server": server}
    if proxy_username:
        config["username"] = proxy_username
    if proxy_password:
        config["password"] = proxy_password
    metadata = {
        "enabled": True,
        "server": server,
        "scheme": scheme,
        "host": host,
        "port": port,
        "username_set": bool(proxy_username),
        "password_set": bool(proxy_password),
    }
    return config, metadata


def load_proxy_rows_from_json(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        rows = data.get("proxies", [])
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    if not isinstance(rows, list):
        raise ValueError(f"proxy list JSON must contain a list or a 'proxies' array: {path}")
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        server = first_non_empty(str(row.get("PROXY_SERVER", "")), str(row.get("proxy_server", "")), str(row.get("server", "")))
        if not server:
            continue
        normalized.append(
            {
                "PROXY_SERVER": server,
                "PROXY_USERNAME": first_non_empty(str(row.get("PROXY_USERNAME", "")), str(row.get("proxy_username", "")), str(row.get("username", ""))),
                "PROXY_PASSWORD": first_non_empty(str(row.get("PROXY_PASSWORD", "")), str(row.get("proxy_password", "")), str(row.get("password", ""))),
                "ping_ms": int(float(row.get("ping_ms", row.get("ping", 999999)) or 999999)),
                "source": str(row.get("source", "")),
                "protocol": str(row.get("protocol", "")),
            }
        )
    return normalized


def load_proxy_rows_from_markdown(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    pattern = re.compile(r"^\|\s*(\d+)\s*\|\s*`([^`]*)`\s*\|\s*`([^`]*)`\s*\|\s*`([^`]*)`\s*\|\s*(\d+)", re.I)
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        rows.append(
            {
                "PROXY_SERVER": match.group(2).strip(),
                "PROXY_USERNAME": match.group(3).strip(),
                "PROXY_PASSWORD": match.group(4).strip(),
                "ping_ms": int(match.group(5)),
                "source": "proxy-list.md",
            }
        )
    return rows


def load_proxy_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"proxy list file not found: {path}")
    if path.suffix.lower() == ".md":
        rows = load_proxy_rows_from_markdown(path)
    else:
        rows = load_proxy_rows_from_json(path)
    rows.sort(key=lambda item: int(item.get("ping_ms") or 999999))
    return rows


def resolve_proxy_config(args: argparse.Namespace) -> Tuple[Optional[Dict[str, str]], Dict[str, Any]]:
    mode = (args.proxy_mode or "none").strip().lower().replace("_", "-")
    if mode in {"", "none", "off", "direct", "false", "0"}:
        return None, {"enabled": False, "mode": "none"}

    try:
        if mode == "manual":
            server = first_non_empty(args.proxy_server, args.proxy_server_secret)
            username = first_non_empty(args.proxy_username, args.proxy_username_secret)
            password = first_non_empty(args.proxy_password, args.proxy_password_secret)
            config, metadata = parse_proxy_server(server, username, password)
            metadata["mode"] = mode
            metadata["source"] = "workflow input / GitHub secret"
            return config, metadata

        if mode in {"fastest-from-file", "rank-from-file", "random-from-file", "file", "auto"}:
            rows = load_proxy_rows(Path(args.proxy_list_file))
            if not rows:
                raise ValueError(f"proxy list is empty: {args.proxy_list_file}")
            if mode == "random-from-file":
                selected = random.choice(rows)
                selected_rank = rows.index(selected) + 1
            else:
                rank = max(1, int(args.proxy_list_rank or 1))
                selected_rank = min(rank, len(rows))
                selected = rows[selected_rank - 1]
            config, metadata = parse_proxy_server(
                str(selected.get("PROXY_SERVER", "")),
                str(selected.get("PROXY_USERNAME", "")),
                str(selected.get("PROXY_PASSWORD", "")),
            )
            metadata["mode"] = "fastest-from-file" if mode in {"file", "auto"} else mode
            metadata["source"] = str(args.proxy_list_file)
            metadata["rank"] = selected_rank
            metadata["ping_ms"] = selected.get("ping_ms")
            metadata["list_protocol"] = selected.get("protocol", "")
            return config, metadata

        raise ValueError(f"unsupported proxy_mode: {args.proxy_mode}")
    except Exception:
        if args.proxy_allow_direct_fallback:
            return None, {"enabled": False, "mode": mode, "fallback_to_direct": True, "error": traceback.format_exc()}
        raise

def redact_headers(headers: Dict[str, str], redact: bool) -> Dict[str, str]:
    if not redact:
        return dict(headers or {})
    cleaned: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        if key.lower() in SENSITIVE_HEADERS:
            cleaned[key] = "[REDACTED]"
        else:
            cleaned[key] = value
    return cleaned


def redact_post_data(value: Optional[str], redact: bool) -> Optional[str]:
    if not redact or not value:
        return value
    # Conservative token-style redaction while preserving request shape.
    value = re.sub(r"(?i)(password|passwd|token|secret|authorization|api[_-]?key)=([^&\s]+)", r"\1=[REDACTED]", value)
    value = re.sub(r"(?i)(\"(?:password|passwd|token|secret|authorization|api[_-]?key)\"\s*:\s*)\".*?\"", r"\1\"[REDACTED]\"", value)
    return value


@dataclass
class AssetResult:
    url: str
    rel: str
    name: str
    content_type: str
    size: int
    skipped: bool = False
    reason: str = ""


class NetworkLogger:
    def __init__(
        self,
        network_dir: Path,
        save_response_bodies: bool = True,
        max_response_body_bytes: int = 2 * 1024 * 1024,
        redact_sensitive: bool = False,
    ) -> None:
        self.network_dir = network_dir
        self.bodies_dir = network_dir / "bodies"
        self.save_response_bodies = save_response_bodies
        self.max_response_body_bytes = max_response_body_bytes
        self.redact_sensitive = redact_sensitive
        self.entries: List[Dict[str, Any]] = []
        self._request_to_entry: Dict[int, Dict[str, Any]] = {}
        self._responses: List[Tuple[int, Any]] = []
        self._counter = 0
        self._started_at = time.time()

    def attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)
        page.on("requestfinished", self._on_request_finished)

    def _on_request(self, request: Any) -> None:
        self._counter += 1
        try:
            post_data = request.post_data
        except Exception:
            post_data = None
        entry = {
            "id": self._counter,
            "started_ms": int((time.time() - self._started_at) * 1000),
            "method": request.method,
            "url": request.url,
            "resource_type": request.resource_type,
            "headers": redact_headers(request.headers, self.redact_sensitive),
            "post_data": redact_post_data(post_data, self.redact_sensitive),
            "response": None,
            "failure": None,
            "finished_ms": None,
            "response_body_file": None,
            "response_body_sha256": None,
            "response_body_size": None,
            "response_body_truncated": False,
            "response_body_note": None,
        }
        self.entries.append(entry)
        self._request_to_entry[id(request)] = entry

    def _on_response(self, response: Any) -> None:
        request = response.request
        entry = self._request_to_entry.get(id(request))
        if not entry:
            return
        try:
            status_text = response.status_text
        except Exception:
            status_text = ""
        entry["response"] = {
            "url": response.url,
            "status": response.status,
            "status_text": status_text,
            "headers": redact_headers(response.headers, self.redact_sensitive),
        }
        self._responses.append((id(request), response))

    def _on_request_failed(self, request: Any) -> None:
        entry = self._request_to_entry.get(id(request))
        if not entry:
            return
        failure = None
        try:
            failure = request.failure
        except Exception:
            pass
        entry["failure"] = failure or "requestfailed"
        entry["finished_ms"] = int((time.time() - self._started_at) * 1000)

    def _on_request_finished(self, request: Any) -> None:
        entry = self._request_to_entry.get(id(request))
        if not entry:
            return
        entry["finished_ms"] = int((time.time() - self._started_at) * 1000)
        try:
            entry["sizes"] = request.sizes()
        except Exception:
            pass
        try:
            entry["timing"] = request.timing
        except Exception:
            pass

    def _looks_textual(self, entry: Dict[str, Any]) -> bool:
        response = entry.get("response") or {}
        headers = response.get("headers") or {}
        content_type = headers.get("content-type") or headers.get("Content-Type") or ""
        content_type = content_type.split(";", 1)[0].lower().strip()
        if entry.get("resource_type") in {"xhr", "fetch", "document", "script", "stylesheet"}:
            return True
        return any(content_type.startswith(prefix) for prefix in TEXT_BODY_HINTS)

    def finalize(self) -> None:
        self.network_dir.mkdir(parents=True, exist_ok=True)
        self.bodies_dir.mkdir(parents=True, exist_ok=True)
        if self.save_response_bodies:
            for request_id, response in list(self._responses):
                entry = self._request_to_entry.get(request_id)
                if not entry or not entry.get("response"):
                    continue
                if not self._looks_textual(entry):
                    entry["response_body_note"] = "binary body skipped"
                    continue
                try:
                    body = response.body()
                except Exception as exc:
                    entry["response_body_note"] = f"body unavailable: {exc}"
                    continue
                entry["response_body_size"] = len(body)
                entry["response_body_sha256"] = hashlib.sha256(body).hexdigest()
                if len(body) > self.max_response_body_bytes:
                    body_to_write = body[: self.max_response_body_bytes]
                    entry["response_body_truncated"] = True
                else:
                    body_to_write = body
                suffix = self._suffix_for_body(entry)
                file_name = f"{entry['id']:04d}_{entry.get('resource_type','body')}{suffix}"
                body_path = self.bodies_dir / file_name
                body_path.write_bytes(body_to_write)
                entry["response_body_file"] = str(body_path.relative_to(self.network_dir.parent))

        write_json(self.network_dir / "network.json", self.entries)
        with (self.network_dir / "network.jsonl").open("w", encoding="utf-8") as handle:
            for entry in self.entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._write_markdown()

    def _suffix_for_body(self, entry: Dict[str, Any]) -> str:
        response = entry.get("response") or {}
        headers = response.get("headers") or {}
        content_type = (headers.get("content-type") or headers.get("Content-Type") or "").split(";", 1)[0].lower().strip()
        mapping = {
            "text/html": ".html",
            "text/css": ".css",
            "application/json": ".json",
            "application/javascript": ".js",
            "application/x-javascript": ".js",
            "text/javascript": ".js",
            "application/xml": ".xml",
            "text/xml": ".xml",
            "image/svg+xml": ".svg",
        }
        if content_type in mapping:
            return mapping[content_type]
        guessed = mimetypes.guess_extension(content_type or "")
        return guessed or ".txt"

    def _write_markdown(self) -> None:
        lines = [
            "# Network Log",
            "",
            "این فایل خلاصه‌ی درخواست‌ها و پاسخ‌های ثبت‌شده توسط مرورگر است. جزئیات کامل در `network.json` و `network.jsonl` ذخیره شده است.",
            "",
            "| # | Method | Type | Status | URL | Body |",
            "|---:|---|---|---:|---|---|",
        ]
        for entry in self.entries[:500]:
            response = entry.get("response") or {}
            status = response.get("status", "")
            body = entry.get("response_body_file") or entry.get("response_body_note") or ""
            url = str(entry.get("url", "")).replace("|", "%7C")
            if len(url) > 160:
                url = url[:157] + "..."
            lines.append(
                f"| {entry.get('id')} | `{entry.get('method')}` | `{entry.get('resource_type')}` | {status} | `{url}` | {body} |"
            )
        if len(self.entries) > 500:
            lines.append("")
            lines.append(f"فقط 500 مورد اول نمایش داده شد. تعداد کل: {len(self.entries)}")
        (self.network_dir / "network.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


class OfflineSaver:
    def __init__(
        self,
        context: BrowserContext,
        base_url: str,
        offline_dir: Path,
        include_videos: bool = False,
        max_asset_size_bytes: int = 25 * 1024 * 1024,
        request_timeout_ms: int = 30000,
    ) -> None:
        self.context = context
        self.base_url = base_url
        self.offline_dir = offline_dir
        self.assets_dir = offline_dir / "assets"
        self.include_videos = include_videos
        self.max_asset_size_bytes = max_asset_size_bytes
        self.request_timeout_ms = request_timeout_ms
        self.url_to_asset: Dict[str, AssetResult] = {}
        self.asset_log: List[Dict[str, Any]] = []
        self._fetching: set[str] = set()

    def save(self, page: Page) -> Dict[str, Any]:
        self.offline_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        html = page.content()
        (self.offline_dir / "final_dom_before_rewrite.html").write_text(html, encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        self._rewrite_html(soup)
        html_out = "<!doctype html>\n" + str(soup)
        (self.offline_dir / "index.html").write_text(html_out, encoding="utf-8")
        self._write_assets_markdown()
        write_json(self.offline_dir / "assets.json", self.asset_log)
        return {
            "offline_index": str((self.offline_dir / "index.html")),
            "downloaded_assets": sum(1 for item in self.asset_log if item.get("status") == "saved"),
            "skipped_assets": sum(1 for item in self.asset_log if item.get("status") == "skipped"),
            "failed_assets": sum(1 for item in self.asset_log if item.get("status") == "failed"),
        }

    def _rewrite_html(self, soup: BeautifulSoup) -> None:
        # Remove remote <base> tags. They break relative offline paths.
        for base in soup.find_all("base"):
            base.decompose()

        asset_attrs = {
            "img": ["src", "data-src", "data-lazy-src", "data-original", "data-srcset", "srcset"],
            "script": ["src"],
            "link": ["href"],
            "source": ["src", "srcset"],
            "picture": ["src", "srcset"],
            "iframe": ["src"],
            "embed": ["src"],
            "object": ["data"],
            "input": ["src"],
            "video": ["poster"],
            "audio": ["src"],
            "track": ["src"],
        }
        all_links: List[str] = []

        for tag in soup.find_all(True):
            tag_name = (tag.name or "").lower()
            attrs = asset_attrs.get(tag_name, [])
            if tag_name == "link" and not self._link_is_asset(tag):
                attrs = []
            if tag_name in {"video", "source"} and tag.has_attr("src"):
                src_value = str(tag.get("src") or "")
                absolute = self._absolute_url(src_value, self.base_url)
                if absolute and self._is_video_url(absolute):
                    tag["data-offline-skipped-src"] = src_value
                    if tag_name == "video":
                        tag["controls"] = ""
                    try:
                        del tag["src"]
                    except Exception:
                        pass

            for attr in attrs:
                if not tag.has_attr(attr):
                    continue
                raw_value = str(tag.get(attr) or "")
                if not raw_value.strip():
                    continue
                if attr.endswith("srcset"):
                    tag[attr] = self._rewrite_srcset(raw_value, self.base_url)
                else:
                    all_links.append(raw_value)
                    asset = self.fetch_asset(raw_value, referrer_url=self.base_url)
                    if asset and not asset.skipped:
                        tag[attr] = asset.rel

            if tag.has_attr("style"):
                tag["style"] = self._rewrite_css(str(tag.get("style") or ""), self.base_url, html_context=True)

        for style_tag in soup.find_all("style"):
            style_text = style_tag.string if style_tag.string is not None else style_tag.get_text()
            if style_text:
                style_tag.string = self._rewrite_css(style_text, self.base_url, html_context=True)

        (self.offline_dir / "all_dom_asset_links.txt").write_text(
            "\n".join(sorted(set(all_links))) + "\n", encoding="utf-8"
        )

    def _link_is_asset(self, tag: Any) -> bool:
        rel_raw = tag.get("rel") or []
        if isinstance(rel_raw, str):
            rel = {x.strip().lower() for x in rel_raw.split()}
        else:
            rel = {str(x).strip().lower() for x in rel_raw}
        as_value = str(tag.get("as") or "").lower()
        href = str(tag.get("href") or "")
        if not href:
            return False
        if rel & {"stylesheet", "icon", "shortcut", "apple-touch-icon", "manifest", "preload", "modulepreload", "prefetch"}:
            return True
        if as_value in {"script", "style", "font", "image"}:
            return True
        return self._looks_like_static_asset(href)

    def _rewrite_srcset(self, value: str, referrer_url: str) -> str:
        parts: List[str] = []
        for candidate in value.split(","):
            candidate = candidate.strip()
            if not candidate:
                continue
            bits = candidate.split()
            url_part = bits[0]
            descriptor = " ".join(bits[1:])
            asset = self.fetch_asset(url_part, referrer_url=referrer_url)
            if asset and not asset.skipped:
                new_url = asset.rel
            else:
                new_url = url_part
            parts.append((new_url + (" " + descriptor if descriptor else "")).strip())
        return ", ".join(parts)

    def _rewrite_css(self, css_text: str, referrer_url: str, html_context: bool) -> str:
        def replace_url(match: re.Match[str]) -> str:
            quote = match.group(1) or ""
            raw_url = (match.group(2) or "").strip()
            if not raw_url or self._should_ignore_url(raw_url):
                return match.group(0)
            asset = self.fetch_asset(raw_url, referrer_url=referrer_url)
            if not asset or asset.skipped:
                return match.group(0)
            replacement = asset.rel if html_context else asset.name
            return f"url({quote}{replacement}{quote})"

        css_text = re.sub(r"url\(\s*(['\"]?)(.*?)\1\s*\)", replace_url, css_text, flags=re.I)

        def replace_import(match: re.Match[str]) -> str:
            prefix = match.group(1)
            quote = match.group(2) or "'"
            raw_url = match.group(3).strip()
            suffix = match.group(4) or ";"
            asset = self.fetch_asset(raw_url, referrer_url=referrer_url)
            if not asset or asset.skipped:
                return match.group(0)
            replacement = asset.rel if html_context else asset.name
            return f"{prefix}{quote}{replacement}{quote}{suffix}"

        css_text = re.sub(
            r"(@import\s+)(?:url\(\s*)?(['\"]?)([^'\"\)\s;]+)\2\s*\)?([^;]*;)",
            replace_import,
            css_text,
            flags=re.I,
        )
        return css_text

    def fetch_asset(self, raw_url: str, referrer_url: str) -> Optional[AssetResult]:
        absolute = self._absolute_url(raw_url, referrer_url)
        if not absolute:
            return None
        if absolute in self.url_to_asset:
            return self.url_to_asset[absolute]
        if absolute in self._fetching:
            return None
        if not self.include_videos and self._is_video_url(absolute):
            return self._record_skip(absolute, "video skipped")
        self._fetching.add(absolute)
        try:
            response = self.context.request.get(absolute, timeout=self.request_timeout_ms, max_redirects=5)
            status = response.status
            headers = response.headers
            content_type = (headers.get("content-type") or "").split(";", 1)[0].lower().strip()
            if not self.include_videos and (content_type.startswith("video/") or self._is_video_url(response.url)):
                return self._record_skip(absolute, "video skipped")
            if status >= 400:
                return self._record_failure(absolute, f"HTTP {status}")
            body = response.body()
            if len(body) > self.max_asset_size_bytes:
                return self._record_skip(absolute, f"asset too large: {bytes_to_human(len(body))}")
            final_url = response.url or absolute
            file_name = self._asset_file_name(final_url, content_type, body)
            rel_path = f"assets/{file_name}"
            out_path = self.assets_dir / file_name
            if self._is_css(final_url, content_type):
                try:
                    text = body.decode(self._charset_from_headers(headers), errors="replace")
                    text = self._rewrite_css(text, final_url, html_context=False)
                    body = text.encode("utf-8")
                except Exception as exc:
                    self.asset_log.append({"url": absolute, "status": "failed", "reason": f"CSS rewrite failed: {exc}"})
            out_path.write_bytes(body)
            asset = AssetResult(absolute, rel_path, file_name, content_type, len(body))
            self.url_to_asset[absolute] = asset
            self.asset_log.append(
                {
                    "url": absolute,
                    "final_url": final_url,
                    "status": "saved",
                    "path": rel_path,
                    "content_type": content_type,
                    "size": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
            return asset
        except Exception as exc:
            return self._record_failure(absolute, str(exc))
        finally:
            self._fetching.discard(absolute)

    def _record_skip(self, absolute: str, reason: str) -> AssetResult:
        asset = AssetResult(absolute, "", "", "", 0, skipped=True, reason=reason)
        self.url_to_asset[absolute] = asset
        self.asset_log.append({"url": absolute, "status": "skipped", "reason": reason})
        return asset

    def _record_failure(self, absolute: str, reason: str) -> AssetResult:
        asset = AssetResult(absolute, "", "", "", 0, skipped=True, reason=reason)
        self.url_to_asset[absolute] = asset
        self.asset_log.append({"url": absolute, "status": "failed", "reason": reason})
        return asset

    def _absolute_url(self, raw_url: str, referrer_url: str) -> Optional[str]:
        raw_url = (raw_url or "").strip()
        if not raw_url or self._should_ignore_url(raw_url):
            return None
        absolute = urljoin(referrer_url, raw_url)
        absolute, _fragment = urldefrag(absolute)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            return None
        return absolute

    def _should_ignore_url(self, raw_url: str) -> bool:
        lowered = raw_url.strip().lower()
        return (
            not lowered
            or lowered.startswith("data:")
            or lowered.startswith("blob:")
            or lowered.startswith("javascript:")
            or lowered.startswith("mailto:")
            or lowered.startswith("tel:")
            or lowered.startswith("#")
            or lowered.startswith("about:")
        )

    def _is_video_url(self, url: str) -> bool:
        parsed = urlparse(url)
        ext = posixpath.splitext(parsed.path.lower())[1]
        return ext in VIDEO_EXTENSIONS

    def _looks_like_static_asset(self, raw_url: str) -> bool:
        parsed = urlparse(raw_url)
        ext = posixpath.splitext(parsed.path.lower())[1]
        return ext in {
            ".css",
            ".js",
            ".mjs",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".webp",
            ".bmp",
            ".ico",
            ".avif",
            ".woff",
            ".woff2",
            ".ttf",
            ".otf",
            ".eot",
            ".json",
            ".xml",
        }

    def _is_css(self, url: str, content_type: str) -> bool:
        return content_type == "text/css" or posixpath.splitext(urlparse(url).path.lower())[1] == ".css"

    def _charset_from_headers(self, headers: Dict[str, str]) -> str:
        content_type = headers.get("content-type") or ""
        match = re.search(r"charset=([^;]+)", content_type, flags=re.I)
        return match.group(1).strip() if match else "utf-8"

    def _asset_file_name(self, url: str, content_type: str, body: bytes) -> str:
        parsed = urlparse(url)
        base = posixpath.basename(parsed.path) or "asset"
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:80].strip("._-") or "asset"
        stem, ext = os.path.splitext(base)
        if not ext:
            ext = mimetypes.guess_extension(content_type or "") or self._guess_extension_from_bytes(body) or ""
        digest = hashlib.sha256((url + str(len(body))).encode("utf-8") + body[:2048]).hexdigest()[:16]
        stem = stem[:50] or "asset"
        return f"{digest}_{stem}{ext}"

    def _guess_extension_from_bytes(self, body: bytes) -> str:
        if body.startswith(b"\x89PNG"):
            return ".png"
        if body.startswith(b"\xff\xd8"):
            return ".jpg"
        if body.startswith(b"GIF8"):
            return ".gif"
        if body.startswith(b"RIFF") and b"WEBP" in body[:16]:
            return ".webp"
        if body.strip().startswith(b"<svg"):
            return ".svg"
        return ""

    def _write_assets_markdown(self) -> None:
        lines = [
            "# Offline Assets",
            "",
            "| Status | Size | Type | Local path / reason | URL |",
            "|---|---:|---|---|---|",
        ]
        for item in self.asset_log[:1000]:
            status = item.get("status", "")
            size = bytes_to_human(int(item.get("size") or 0)) if item.get("size") else ""
            ctype = item.get("content_type", "")
            local = item.get("path") or item.get("reason", "")
            url = str(item.get("url", "")).replace("|", "%7C")
            if len(url) > 160:
                url = url[:157] + "..."
            lines.append(f"| {status} | {size} | `{ctype}` | `{local}` | `{url}` |")
        if len(self.asset_log) > 1000:
            lines.append("")
            lines.append(f"فقط 1000 مورد اول نمایش داده شد. تعداد کل: {len(self.asset_log)}")
        (self.offline_dir / "assets.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def click_locator_safely(locator: Any, timeout_ms: int, force: bool = False) -> bool:
    try:
        locator.wait_for(state="visible", timeout=timeout_ms)
        locator.click(timeout=timeout_ms, force=force)
        return True
    except Exception:
        return False


def find_root(page: Page, config: Dict[str, Any]) -> Any:
    frame_url_contains = config.get("frame_url_contains")
    frame_name = config.get("frame_name")
    if frame_url_contains or frame_name:
        for frame in page.frames:
            if frame_url_contains and frame_url_contains in frame.url:
                return frame
            if frame_name and frame.name == frame_name:
                return frame
    return page


def locator_from_config(page: Page, config: Dict[str, Any]) -> Any:
    root = find_root(page, config)
    timeout_ms = int(config.get("timeout", 10000))
    if config.get("selector"):
        return root.locator(config["selector"]).first
    if config.get("text") is not None:
        return root.get_by_text(str(config["text"]), exact=bool(config.get("exact", False))).first
    if config.get("text_regex"):
        return root.get_by_text(re.compile(str(config["text_regex"]), re.I)).first
    if config.get("role"):
        role = str(config["role"])
        if config.get("name_regex"):
            return root.get_by_role(role, name=re.compile(str(config["name_regex"]), re.I)).first
        if config.get("name") is not None:
            return root.get_by_role(role, name=str(config["name"]), exact=bool(config.get("exact", False))).first
        return root.get_by_role(role).first
    raise ValueError(f"Step/rule needs selector, text, text_regex, or role: {config}")


def handle_popups(page: Page, rules: List[Dict[str, Any]], log: List[Dict[str, Any]], rounds: int = 3) -> int:
    clicked = 0
    if not rules:
        return clicked
    for round_index in range(rounds):
        clicked_this_round = 0
        for rule in rules:
            rule_timeout = int(rule.get("timeout", 900))
            try:
                # Try main page and all frames for modal/banner popups.
                roots: List[Any] = [page] + [frame for frame in page.frames if frame != page.main_frame]
                for root in roots:
                    candidate = dict(rule)
                    if root is not page:
                        # locator_from_config can target frames, but here root is already a frame.
                        if candidate.get("selector"):
                            locator = root.locator(candidate["selector"]).first
                        elif candidate.get("text") is not None:
                            locator = root.get_by_text(str(candidate["text"]), exact=bool(candidate.get("exact", False))).first
                        elif candidate.get("text_regex"):
                            locator = root.get_by_text(re.compile(str(candidate["text_regex"]), re.I)).first
                        elif candidate.get("role"):
                            if candidate.get("name_regex"):
                                locator = root.get_by_role(str(candidate["role"]), name=re.compile(str(candidate["name_regex"]), re.I)).first
                            elif candidate.get("name") is not None:
                                locator = root.get_by_role(str(candidate["role"]), name=str(candidate["name"]), exact=bool(candidate.get("exact", False))).first
                            else:
                                locator = root.get_by_role(str(candidate["role"])).first
                        else:
                            continue
                    else:
                        locator = locator_from_config(page, candidate)
                    if click_locator_safely(locator, rule_timeout, force=bool(rule.get("force", False))):
                        clicked += 1
                        clicked_this_round += 1
                        log.append(
                            {
                                "kind": "popup",
                                "round": round_index + 1,
                                "rule": rule.get("name") or rule.get("selector") or rule.get("text") or rule.get("role"),
                                "action": "click",
                                "time": now_utc().isoformat(),
                                "frame_url": getattr(root, "url", ""),
                            }
                        )
                        try:
                            page.wait_for_timeout(350)
                        except Exception:
                            pass
                        break
            except Exception as exc:
                log.append(
                    {
                        "kind": "popup",
                        "rule": rule.get("name") or rule,
                        "action": "error",
                        "error": str(exc),
                        "time": now_utc().isoformat(),
                    }
                )
        if clicked_this_round == 0:
            break
    return clicked


def auto_scroll_page(page: Page, log: List[Dict[str, Any]], max_scrolls: int = 18) -> None:
    script = """
    async ({ maxScrolls }) => {
      await new Promise((resolve) => {
        let lastHeight = 0;
        let sameHeightCount = 0;
        let scrolls = 0;
        const step = Math.max(500, Math.floor(window.innerHeight * 0.85));
        const timer = setInterval(() => {
          const height = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
          window.scrollBy(0, step);
          scrolls += 1;
          if (height === lastHeight) sameHeightCount += 1;
          else sameHeightCount = 0;
          lastHeight = height;
          if (scrolls >= maxScrolls || sameHeightCount >= 3 || (window.innerHeight + window.scrollY) >= height) {
            clearInterval(timer);
            window.scrollTo(0, 0);
            setTimeout(resolve, 400);
          }
        }, 450);
      });
    }
    """
    try:
        page.evaluate(script, {"maxScrolls": max_scrolls})
        log.append({"kind": "automation", "action": "auto_scroll", "max_scrolls": max_scrolls, "time": now_utc().isoformat()})
    except Exception as exc:
        log.append({"kind": "automation", "action": "auto_scroll", "error": str(exc), "time": now_utc().isoformat()})


def run_automation(page: Page, steps: List[Dict[str, Any]], output_dir: Path, popup_rules: List[Dict[str, Any]], log: List[Dict[str, Any]]) -> None:
    for index, step in enumerate(steps, start=1):
        action = str(step.get("action") or "").strip().lower()
        if not action:
            raise ValueError(f"Automation step #{index} is missing action")
        timeout_ms = int(step.get("timeout", 10000))
        started = now_utc().isoformat()
        record: Dict[str, Any] = {"kind": "automation", "step": index, "action": action, "started_at": started, "config": step}
        try:
            if action in {"click", "tap"}:
                locator = locator_from_config(page, step)
                locator.click(timeout=timeout_ms, force=bool(step.get("force", False)))
                if step.get("wait_for_network", True):
                    try:
                        page.wait_for_load_state("networkidle", timeout=int(step.get("network_timeout", 10000)))
                    except Exception:
                        pass
            elif action == "dblclick":
                locator = locator_from_config(page, step)
                locator.dblclick(timeout=timeout_ms, force=bool(step.get("force", False)))
            elif action == "hover":
                locator = locator_from_config(page, step)
                locator.hover(timeout=timeout_ms)
            elif action == "fill":
                locator = locator_from_config(page, step)
                locator.fill(str(step.get("value", "")), timeout=timeout_ms)
            elif action == "type":
                locator = locator_from_config(page, step)
                locator.type(str(step.get("value", "")), delay=int(step.get("delay", 0)), timeout=timeout_ms)
            elif action == "press":
                locator = locator_from_config(page, step)
                locator.press(str(step.get("key", "Enter")), timeout=timeout_ms)
            elif action == "check":
                locator = locator_from_config(page, step)
                locator.check(timeout=timeout_ms, force=bool(step.get("force", False)))
            elif action == "uncheck":
                locator = locator_from_config(page, step)
                locator.uncheck(timeout=timeout_ms, force=bool(step.get("force", False)))
            elif action == "select_option":
                locator = locator_from_config(page, step)
                value = step.get("value")
                locator.select_option(value=value, timeout=timeout_ms)
            elif action == "wait":
                ms = int(step.get("ms", step.get("timeout", 1000)))
                page.wait_for_timeout(ms)
            elif action == "wait_for_selector":
                locator = locator_from_config(page, step)
                locator.wait_for(state=str(step.get("state", "visible")), timeout=timeout_ms)
            elif action == "wait_for_url":
                page.wait_for_url(str(step.get("url") or step.get("pattern") or "**"), timeout=timeout_ms)
            elif action == "wait_for_load_state":
                page.wait_for_load_state(str(step.get("state", "networkidle")), timeout=timeout_ms)
            elif action == "goto":
                url = normalize_url(str(step.get("url") or ""))
                page.goto(url, wait_until=str(step.get("wait_until", "domcontentloaded")), timeout=timeout_ms)
            elif action == "scroll":
                if step.get("selector") or step.get("text") or step.get("role"):
                    locator = locator_from_config(page, step)
                    locator.scroll_into_view_if_needed(timeout=timeout_ms)
                else:
                    x = int(step.get("x", 0))
                    y = int(step.get("y", 900))
                    page.mouse.wheel(x, y)
            elif action == "scroll_to_bottom":
                auto_scroll_page(page, log, max_scrolls=int(step.get("max_scrolls", 18)))
            elif action == "screenshot":
                name = safe_slug(str(step.get("name") or f"step_{index}_screenshot"), 80)
                if not name.lower().endswith(".png"):
                    name += ".png"
                path = output_dir / name
                page.screenshot(path=str(path), full_page=bool(step.get("full_page", True)))
                record["path"] = str(path.relative_to(output_dir))
            elif action == "evaluate":
                script = str(step.get("script") or "")
                if not script:
                    raise ValueError("evaluate step requires script")
                result = page.evaluate(script)
                record["result"] = result if isinstance(result, (str, int, float, bool, type(None), list, dict)) else str(result)
            else:
                raise ValueError(f"Unsupported automation action: {action}")

            after_wait_ms = int(step.get("after_wait_ms", 0))
            if after_wait_ms:
                page.wait_for_timeout(after_wait_ms)
            handle_popups(page, popup_rules, log, rounds=int(step.get("popup_rounds", 1)))
            record["status"] = "ok"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            if not bool(step.get("continue_on_error", False)):
                log.append(record)
                raise
        finally:
            record["finished_at"] = now_utc().isoformat()
            if record not in log:
                log.append(record)


def collect_links_from_dom(html: str, base_url: str) -> Dict[str, List[str]]:
    soup = BeautifulSoup(html, "lxml")
    attrs = ["href", "src", "data-src", "data-lazy-src", "poster", "action"]
    links: set[str] = set()
    media: set[str] = set()
    for tag in soup.find_all(True):
        for attr in attrs:
            raw = tag.get(attr)
            if not raw or not isinstance(raw, str):
                continue
            absolute = urljoin(base_url, raw)
            if urlparse(absolute).scheme in {"http", "https"}:
                absolute, _ = urldefrag(absolute)
                links.add(absolute)
                ext = posixpath.splitext(urlparse(absolute).path.lower())[1]
                if ext in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".svg",
                    ".webp",
                    ".bmp",
                    ".ico",
                    ".avif",
                    ".mp3",
                    ".wav",
                    ".ogg",
                    ".flac",
                    ".aac",
                    ".pdf",
                    ".doc",
                    ".docx",
                    ".xls",
                    ".xlsx",
                    ".ppt",
                    ".pptx",
                    ".zip",
                    ".rar",
                    ".tar",
                    ".gz",
                    ".7z",
                }:
                    media.add(absolute)
        for attr in ["srcset", "data-srcset"]:
            raw = tag.get(attr)
            if not raw or not isinstance(raw, str):
                continue
            for candidate in raw.split(","):
                url_part = candidate.strip().split()[0] if candidate.strip() else ""
                if not url_part:
                    continue
                absolute = urljoin(base_url, url_part)
                if urlparse(absolute).scheme in {"http", "https"}:
                    absolute, _ = urldefrag(absolute)
                    links.add(absolute)
                    media.add(absolute)
    return {"all": sorted(links), "media": sorted(media)}


def save_mhtml(page: Page, output_dir: Path, log: List[Dict[str, Any]]) -> Optional[Path]:
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Page.enable")
        snapshot = cdp.send("Page.captureSnapshot", {"format": "mhtml"})
        data = snapshot.get("data") or ""
        path = output_dir / "offline" / "page.mhtml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        log.append({"kind": "offline", "action": "capture_mhtml", "status": "ok", "path": str(path.relative_to(output_dir))})
        return path
    except Exception as exc:
        log.append({"kind": "offline", "action": "capture_mhtml", "status": "failed", "error": str(exc)})
        return None


def write_index(
    output_dir: Path,
    original_url: str,
    final_url: str,
    session_path: Optional[Path],
    metadata: Dict[str, Any],
) -> None:
    screenshot_path = output_dir / "screenshot.png"
    offline_index = output_dir / "offline" / "index.html"
    mhtml_path = output_dir / "offline" / "page.mhtml"
    network_json = output_dir / "network" / "network.json"
    automation_json = output_dir / "automation-log.json"
    lines = [
        f"# Browser capture: {final_url}",
        "",
        f"- **Requested URL:** `{original_url}`",
        f"- **Final URL:** `{final_url}`",
        f"- **Time UTC:** `{metadata.get('captured_at_utc')}`",
        f"- **Domain:** `{metadata.get('domain')}`",
        "",
    ]
    if screenshot_path.exists():
        lines += ["## Screenshot", "", "![Screenshot](./screenshot.png)", ""]
    lines += [
        "## Offline files",
        "",
        f"- [Offline HTML](./offline/index.html){' ✅' if offline_index.exists() else ''}",
        f"- [MHTML snapshot](./offline/page.mhtml){' ✅' if mhtml_path.exists() else ' ⚠️ not created'}",
        "- [Original final DOM before rewrite](./offline/final_dom_before_rewrite.html)",
        "- [Offline asset report](./offline/assets.md)",
        "",
        "## Page source and links",
        "",
        "- [Final DOM](./source/final_dom.html)",
        "- [Visible text](./source/visible_text.txt)",
        "- [All DOM links](./source/all_links.txt)",
        "- [Media/document links](./source/media_links.txt)",
        "",
        "## Network / Ajax log",
        "",
        f"- [Network summary](./network/network.md){' ✅' if network_json.exists() else ''}",
        "- [Full JSON](./network/network.json)",
        "- [JSONL](./network/network.jsonl)",
        "- Response bodies, when available, are saved in `network/bodies/`.",
        "",
        "## Automation and session",
        "",
        f"- [Automation log](./automation-log.json){' ✅' if automation_json.exists() else ''}",
    ]
    if session_path:
        lines.append(f"- Session state: `{session_path.as_posix()}`")
    else:
        lines.append("- Session persistence was disabled.")
    proxy_info = metadata.get("proxy") or {}
    if isinstance(proxy_info, dict):
        if proxy_info.get("enabled"):
            lines += [
                "",
                "## Proxy",
                "",
                f"- Mode: `{proxy_info.get('mode')}`",
                f"- Server: `{proxy_info.get('server')}`",
                f"- Source: `{proxy_info.get('source', '')}`",
            ]
            if proxy_info.get("rank") is not None:
                lines.append(f"- Rank: `{proxy_info.get('rank')}`")
            if proxy_info.get("ping_ms") is not None:
                lines.append(f"- Proxy list ping_ms: `{proxy_info.get('ping_ms')}`")
        else:
            lines += ["", "## Proxy", "", f"- Mode: `{proxy_info.get('mode', 'none')}`"]
    lines += [
        "",
        "## Stats",
        "",
        f"- Network requests: `{metadata.get('network_request_count', 0)}`",
        f"- Offline assets saved: `{metadata.get('offline_assets_saved', 0)}`",
        f"- Offline assets skipped: `{metadata.get('offline_assets_skipped', 0)}`",
        f"- Offline assets failed: `{metadata.get('offline_assets_failed', 0)}`",
        "",
    ]
    (output_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def update_browse_md(browse_file: Path, output_dir: Path, slug: str, timestamp_value: str, media_count: int, request_count: int) -> None:
    if not browse_file.exists():
        browse_file.write_text("# Browsed Websites\n\n", encoding="utf-8")
    rel_index = output_dir / "index.md"
    line = f"- [{slug} ({timestamp_value})]({rel_index.as_posix()}) — {media_count} offline assets, {request_count} network requests"
    append_line(browse_file, line)


def make_output_dir(output_root: Path, url: str) -> Tuple[Path, str, str, str]:
    domain = domain_from_url(url)
    slug = safe_slug(url)
    stamp = timestamp()
    output_dir = output_root / domain / slug / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, domain, slug, stamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a webpage with a real browser and save offline/network/session artifacts.")
    parser.add_argument("--url", default=os.getenv("BROWSER_URL", ""), help="URL to visit")
    parser.add_argument("--automation-json", default=os.getenv("AUTOMATION_JSON", "[]"), help="JSON array of automation steps")
    parser.add_argument("--automation-file", default=os.getenv("AUTOMATION_FILE", ""), help="Path to JSON automation file")
    parser.add_argument("--popup-rules-json", default=os.getenv("POPUP_RULES_JSON", ""), help="JSON array of popup handling rules")
    parser.add_argument("--popup-rules-file", default=os.getenv("POPUP_RULES_FILE", ""), help="Path to JSON popup rules file")
    parser.add_argument("--session-key", default=os.getenv("SESSION_KEY", ""), help="Name for sessions/<key>.json. Defaults to current domain.")
    parser.add_argument("--output-root", default=os.getenv("OUTPUT_ROOT", "pages"), help="Root folder for captured pages")
    parser.add_argument("--sessions-dir", default=os.getenv("SESSIONS_DIR", "sessions"), help="Folder for persisted browser sessions")
    parser.add_argument("--wait-after-load", type=float, default=float(os.getenv("WAIT_AFTER_LOAD", "2")), help="Seconds to wait after initial load and automation")
    parser.add_argument("--navigation-timeout-ms", type=int, default=int(os.getenv("NAVIGATION_TIMEOUT_MS", "60000")))
    parser.add_argument("--max-response-body-mb", type=float, default=float(os.getenv("MAX_RESPONSE_BODY_MB", "2")))
    parser.add_argument("--max-asset-size-mb", type=float, default=float(os.getenv("MAX_ASSET_SIZE_MB", "25")))
    parser.add_argument("--save-response-bodies", dest="save_response_bodies", action="store_true", default=env_bool("SAVE_RESPONSE_BODIES", True))
    parser.add_argument("--no-save-response-bodies", dest="save_response_bodies", action="store_false")
    parser.add_argument("--persist-session", dest="persist_session", action="store_true", default=env_bool("PERSIST_SESSION", True))
    parser.add_argument("--no-persist-session", dest="persist_session", action="store_false")
    parser.add_argument("--auto-scroll", dest="auto_scroll", action="store_true", default=env_bool("AUTO_SCROLL", True))
    parser.add_argument("--no-auto-scroll", dest="auto_scroll", action="store_false")
    parser.add_argument("--include-videos", dest="include_videos", action="store_true", default=env_bool("INCLUDE_VIDEOS", False))
    parser.add_argument("--redact-sensitive", dest="redact_sensitive", action="store_true", default=env_bool("REDACT_SENSITIVE", False))
    parser.add_argument("--proxy-mode", default=os.getenv("PROXY_MODE", "none"), help="none/manual/fastest-from-file/rank-from-file/random-from-file")
    parser.add_argument("--proxy-server", default=os.getenv("PROXY_SERVER", ""), help="Manual proxy server, e.g. http://1.2.3.4:8080 or socks5://host:1080")
    parser.add_argument("--proxy-username", default=os.getenv("PROXY_USERNAME", ""), help="Manual proxy username, if needed")
    parser.add_argument("--proxy-password", default=os.getenv("PROXY_PASSWORD", ""), help="Manual proxy password, if needed")
    parser.add_argument("--proxy-server-secret", default=os.getenv("PROXY_SERVER_SECRET", ""), help=argparse.SUPPRESS)
    parser.add_argument("--proxy-username-secret", default=os.getenv("PROXY_USERNAME_SECRET", ""), help=argparse.SUPPRESS)
    parser.add_argument("--proxy-password-secret", default=os.getenv("PROXY_PASSWORD_SECRET", ""), help=argparse.SUPPRESS)
    parser.add_argument("--proxy-list-file", default=os.getenv("PROXY_LIST_FILE", "proxy-list.json"), help="proxy-list.json or proxy-list.md generated by workflow 05")
    parser.add_argument("--proxy-list-rank", type=int, default=int(os.getenv("PROXY_LIST_RANK", "1") or "1"), help="1 = fastest proxy in proxy-list.json")
    parser.add_argument("--proxy-allow-direct-fallback", dest="proxy_allow_direct_fallback", action="store_true", default=env_bool("PROXY_ALLOW_DIRECT_FALLBACK", False))
    parser.add_argument("--headless", dest="headless", action="store_true", default=env_bool("HEADLESS", True))
    parser.add_argument("--headed", dest="headless", action="store_false")
    return parser.parse_args()



def launch_chromium_with_fallback(playwright_obj: Any, headless: bool, proxy_config: Optional[Dict[str, str]] = None) -> Browser:
    launch_args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    launch_kwargs: Dict[str, Any] = {"headless": headless, "args": launch_args}
    if proxy_config:
        launch_kwargs["proxy"] = proxy_config
    try:
        return playwright_obj.chromium.launch(**launch_kwargs)
    except Exception as first_error:
        candidates = [
            os.getenv("CHROME_EXECUTABLE", ""),
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
            shutil.which("google-chrome") or "",
            shutil.which("google-chrome-stable") or "",
        ]
        for executable in [candidate for candidate in candidates if candidate]:
            try:
                print(f"Playwright bundled Chromium was not available; trying system browser: {executable}")
                fallback_kwargs = dict(launch_kwargs)
                fallback_kwargs["executable_path"] = executable
                return playwright_obj.chromium.launch(**fallback_kwargs)
            except Exception:
                continue
        raise first_error

def main() -> int:
    args = parse_args()
    if not args.url:
        print("ERROR: --url is required", file=sys.stderr)
        return 2

    requested_url = normalize_url(args.url)
    output_root = Path(args.output_root)
    output_dir, domain, slug, stamp = make_output_dir(output_root, requested_url)
    source_dir = output_dir / "source"
    network_dir = output_dir / "network"
    downloads_dir = output_dir / "downloads"
    offline_dir = output_dir / "offline"
    for directory in [source_dir, network_dir, downloads_dir, offline_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    automation_steps = load_json_argument(args.automation_json, args.automation_file or None, [], "automation")
    if isinstance(automation_steps, dict):
        automation_steps = automation_steps.get("steps", [])
    if not isinstance(automation_steps, list):
        raise ValueError("automation JSON must be an array or an object with a steps array")

    user_popup_rules = load_json_argument(args.popup_rules_json, args.popup_rules_file or None, [], "popup rules")
    if isinstance(user_popup_rules, dict):
        user_popup_rules = user_popup_rules.get("rules", [])
    if not isinstance(user_popup_rules, list):
        raise ValueError("popup rules JSON must be an array or an object with a rules array")
    popup_rules = list(user_popup_rules) + DEFAULT_POPUP_RULES

    session_key = sanitize_session_key(args.session_key or domain.replace(".", "_"))
    sessions_dir = Path(args.sessions_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path = sessions_dir / f"{session_key}.json"
    session_for_index: Optional[Path] = session_path if args.persist_session else None

    automation_log: List[Dict[str, Any]] = []
    final_url = requested_url
    metadata: Dict[str, Any] = {
        "requested_url": requested_url,
        "captured_at_utc": now_utc().isoformat(),
        "domain": domain,
        "slug": slug,
        "timestamp": stamp,
        "session_key": session_key,
        "persist_session": args.persist_session,
        "used_existing_session": session_path.exists() if args.persist_session else False,
        "save_response_bodies": args.save_response_bodies,
        "max_response_body_mb": args.max_response_body_mb,
        "max_asset_size_mb": args.max_asset_size_mb,
        "auto_scroll": args.auto_scroll,
        "include_videos": args.include_videos,
    }

    proxy_config, proxy_metadata = resolve_proxy_config(args)
    metadata["proxy"] = proxy_metadata

    network_logger = NetworkLogger(
        network_dir=network_dir,
        save_response_bodies=args.save_response_bodies,
        max_response_body_bytes=int(args.max_response_body_mb * 1024 * 1024),
        redact_sensitive=args.redact_sensitive,
    )

    error: Optional[str] = None
    with sync_playwright() as p:
        browser: Browser = launch_chromium_with_fallback(p, args.headless, proxy_config)
        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1365, "height": 900},
            "user_agent": USER_AGENT,
            "ignore_https_errors": True,
            "accept_downloads": True,
            "java_script_enabled": True,
        }
        if args.persist_session and session_path.exists() and session_path.stat().st_size > 0:
            context_kwargs["storage_state"] = str(session_path)
        context = browser.new_context(**context_kwargs)
        context.set_default_navigation_timeout(args.navigation_timeout_ms)
        context.set_default_timeout(15000)
        page = context.new_page()
        network_logger.attach(page)

        def on_dialog(dialog: Any) -> None:
            try:
                automation_log.append(
                    {
                        "kind": "dialog",
                        "type": dialog.type,
                        "message": dialog.message,
                        "default_value": dialog.default_value,
                        "action": "accept",
                        "time": now_utc().isoformat(),
                    }
                )
                dialog.accept()
            except Exception as exc:
                automation_log.append({"kind": "dialog", "action": "error", "error": str(exc), "time": now_utc().isoformat()})

        page.on("dialog", on_dialog)

        def on_download(download: Any) -> None:
            try:
                suggested = safe_slug(download.suggested_filename, 100) or "download"
                path = downloads_dir / suggested
                download.save_as(str(path))
                automation_log.append(
                    {
                        "kind": "download",
                        "url": download.url,
                        "suggested_filename": download.suggested_filename,
                        "path": str(path.relative_to(output_dir)),
                        "time": now_utc().isoformat(),
                    }
                )
            except Exception as exc:
                automation_log.append({"kind": "download", "url": getattr(download, "url", ""), "error": str(exc)})

        page.on("download", on_download)

        try:
            page.goto(requested_url, wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            if args.wait_after_load > 0:
                page.wait_for_timeout(int(args.wait_after_load * 1000))
            handle_popups(page, popup_rules, automation_log, rounds=4)
            run_automation(page, automation_steps, output_dir, popup_rules, automation_log)
            if args.auto_scroll:
                auto_scroll_page(page, automation_log)
                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass
            handle_popups(page, popup_rules, automation_log, rounds=2)
            if args.wait_after_load > 0:
                page.wait_for_timeout(int(args.wait_after_load * 1000))
            final_url = page.url
            metadata["final_url"] = final_url

            (source_dir / "final_dom.html").write_text(page.content(), encoding="utf-8")
            try:
                text = page.locator("body").inner_text(timeout=5000)
            except Exception:
                text = ""
            (source_dir / "visible_text.txt").write_text(text, encoding="utf-8")
            links = collect_links_from_dom(page.content(), final_url)
            (source_dir / "all_links.txt").write_text("\n".join(links["all"]) + "\n", encoding="utf-8")
            (source_dir / "media_links.txt").write_text("\n".join(links["media"]) + "\n", encoding="utf-8")

            page.screenshot(path=str(output_dir / "screenshot.png"), full_page=True)
            save_mhtml(page, output_dir, automation_log)
            offline_saver = OfflineSaver(
                context=context,
                base_url=final_url,
                offline_dir=offline_dir,
                include_videos=args.include_videos,
                max_asset_size_bytes=int(args.max_asset_size_mb * 1024 * 1024),
            )
            offline_stats = offline_saver.save(page)
            metadata["offline_assets_saved"] = offline_stats.get("downloaded_assets", 0)
            metadata["offline_assets_skipped"] = offline_stats.get("skipped_assets", 0)
            metadata["offline_assets_failed"] = offline_stats.get("failed_assets", 0)
            metadata["dom_link_count"] = len(links["all"])
            metadata["media_link_count"] = len(links["media"])

            if args.persist_session:
                context.storage_state(path=str(session_path))
                metadata["session_path"] = str(session_path)

        except Exception as exc:
            error = str(exc)
            metadata["error"] = error
            metadata["traceback"] = traceback.format_exc()
            try:
                page.screenshot(path=str(output_dir / "error_screenshot.png"), full_page=True)
            except Exception:
                pass
            raise
        finally:
            try:
                network_logger.finalize()
            finally:
                metadata["network_request_count"] = len(network_logger.entries)
                write_json(output_dir / "automation-log.json", automation_log)
                write_json(output_dir / "metadata.json", metadata)
                write_index(output_dir, requested_url, final_url, session_for_index, metadata)
                update_browse_md(Path("browse.md"), output_dir, slug, stamp, int(metadata.get("offline_assets_saved", 0)), len(network_logger.entries))
                write_github_env(
                    {
                        "BROWSER_OUTPUT_DIR": str(output_dir),
                        "BROWSER_DOMAIN": domain,
                        "BROWSER_SLUG": slug,
                        "BROWSER_TIMESTAMP": stamp,
                        "BROWSER_SESSION_KEY": session_key,
                    }
                )
                context.close()
                browser.close()

    print(json.dumps({"output_dir": str(output_dir), "final_url": final_url, "error": error}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
