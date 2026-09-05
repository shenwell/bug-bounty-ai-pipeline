"""Fetch external links from contract description after human selection."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.common.models import Contract, ExternalReference
from portfolio.discovery.dossier import dossier_path, ensure_dossier
from portfolio.discovery.scope_match import is_in_scope, is_out_of_scope
from portfolio.guardrails.limits import RateLimiter

logger = get_logger(__name__)

URL_RE = re.compile(r"https?://[^\s\]\)\"'<>]+", re.IGNORECASE)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^\)]+)\)", re.IGNORECASE)

SKIP_HOST_SUFFIXES = (
    "t.me",
    "telegram.me",
    "twitter.com",
    "x.com",
    "facebook.com",
    "vk.com",
    "linkedin.com",
    "instagram.com",
)

SKIP_PATH_MARKERS = (
    "/account/login",
    "/disclosed-reports/",
    "/programs/?",
)

API_MARKERS = (
    "swagger",
    "openapi",
    "api-docs",
    "api.doc",
    "redoc",
    "/docs/api",
    "graphql",
    "postman",
    "stoplight",
)

DOC_HOST_MARKERS = (
    "github.com",
    "gitlab.",
    "confluence",
    "notion.",
    "readme.io",
    "gitbook",
)


def _normalize_url(url: str) -> str:
    url = url.rstrip(".,;)")
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path, "", parsed.query, ""))


def _contract_text_blocks(contract: Contract) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    if contract.acceptance_criteria:
        blocks.append(("acceptance_criteria", contract.acceptance_criteria))
    for label, content in contract.tab_sections.items():
        if content.strip():
            blocks.append((f"tab:{label}", content))
    for rule in contract.constraints.raw_rules:
        if "http" in rule.lower():
            blocks.append(("rules", rule))
    return blocks


def extract_urls_from_contract(contract: Contract) -> list[tuple[str, str, str]]:
    """Return (url, source, title) deduplicated."""
    found: dict[str, tuple[str, str, str]] = {}
    for source, text in _contract_text_blocks(contract):
        for match in MD_LINK_RE.finditer(text):
            title, url = match.group(1).strip(), _normalize_url(match.group(2))
            found.setdefault(url, (url, source, title))
        for url in URL_RE.findall(text):
            url = _normalize_url(url)
            found.setdefault(url, (url, source, ""))
    return [item for item in found.values() if _host_allowed(item[0])]


def _host_allowed(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return False
    if host.endswith("standoff365.com"):
        if host.startswith("api.") or "swagger" in url.lower() or "openapi" in url.lower():
            return True
        return False
    if any(host == suffix or host.endswith("." + suffix) for suffix in SKIP_HOST_SUFFIXES):
        return False
    if any(marker in url for marker in SKIP_PATH_MARKERS):
        return False
    return True


def classify_reference(url: str, title: str = "") -> str:
    lower = f"{url} {title}".lower()
    if any(marker in lower for marker in API_MARKERS):
        return "api_docs"
    if any(marker in lower for marker in DOC_HOST_MARKERS):
        return "documentation"
    if lower.endswith((".json", ".yaml", ".yml")) and ("openapi" in lower or "swagger" in lower):
        return "api_spec"
    return "generic"


def _priority_key(item: tuple[str, str, str], contract: Contract) -> tuple[int, str]:
    url, _, title = item
    host = urlparse(url).netloc
    ref_type = classify_reference(url, title)
    priority = 3
    if ref_type in ("api_docs", "api_spec"):
        priority = 0
    elif ref_type == "documentation":
        priority = 1
    elif is_in_scope(host, contract.scope, contract.out_of_scope):
        priority = 2
    return (priority, url)


def _extension_for(content_type: str, url: str) -> str:
    ct = content_type.lower()
    if "json" in ct or url.lower().endswith(".json"):
        return ".json"
    if "yaml" in ct or url.lower().endswith((".yaml", ".yml")):
        return ".yml"
    if "html" in ct:
        return ".html"
    if "markdown" in ct or url.lower().endswith(".md"):
        return ".md"
    if "text/plain" in ct:
        return ".txt"
    return ".bin"


def _text_preview(body: bytes, content_type: str, limit: int = 1500) -> str:
    if not body:
        return ""
    if "json" in content_type.lower() or body[:1] in (b"{", b"["):
        try:
            parsed = json.loads(body.decode("utf-8", errors="replace"))
            text = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, UnicodeDecodeError):
            text = body.decode("utf-8", errors="replace")
    elif "html" in content_type.lower():
        text = unescape(re.sub(r"<[^>]+>", " ", body.decode("utf-8", errors="replace")))
        text = re.sub(r"\s+", " ", text).strip()
    else:
        text = body.decode("utf-8", errors="replace")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _extract_nested_urls(body: bytes, content_type: str) -> list[str]:
    text = body.decode("utf-8", errors="replace")
    nested = [_normalize_url(u) for u in URL_RE.findall(text)]
    if "json" in content_type.lower() or text.strip().startswith("{"):
        try:
            data = json.loads(text)
            blob = json.dumps(data)
            nested.extend(_normalize_url(u) for u in URL_RE.findall(blob))
        except json.JSONDecodeError:
            pass
    return list(dict.fromkeys(nested))


def write_references_markdown(path: Path, contract: Contract, refs: list[ExternalReference]) -> None:
    lines = [
        f"# External references — {contract.name}",
        "",
        "> Загружено после выбора контракта человеком (ссылки из описания и вкладок).",
        "",
    ]
    grouped: dict[str, list[ExternalReference]] = {}
    for ref in refs:
        grouped.setdefault(ref.ref_type, []).append(ref)

    for ref_type in ("api_spec", "api_docs", "documentation", "generic"):
        items = grouped.get(ref_type, [])
        if not items:
            continue
        lines.append(f"## {ref_type}")
        lines.append("")
        for ref in items:
            status = f"HTTP {ref.status_code}" if ref.status_code else ref.error or "failed"
            scope_tag = "in-scope" if ref.in_scope else "external"
            lines.append(f"- [{ref.url}]({ref.url}) ({scope_tag}, {status})")
            if ref.title:
                lines.append(f"  - title: {ref.title}")
            if ref.preview:
                lines.append(f"  - preview: {ref.preview[:300]}")
            if ref.file_path:
                lines.append(f"  - file: `{ref.file_path}`")
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


async def enrich_contract_links(config: AppConfig, contract: Contract) -> list[ExternalReference]:
    if not config.recon.fetch_contract_links:
        return []

    candidates = extract_urls_from_contract(contract)
    candidates = [c for c in candidates if _host_allowed(c[0])]
    candidates.sort(key=lambda item: _priority_key(item, contract))

    rate = RateLimiter(config.limits)
    cookie = config.standoff.session_cookie()
    timeout = config.recon.link_fetch_timeout_sec
    max_bytes = config.recon.max_link_bytes
    max_fetches = config.recon.max_contract_links
    out_dir = ensure_dossier(config, contract.slug) / "external_refs"

    queue = candidates[:max_fetches]
    seen_urls = {item[0] for item in queue}
    refs: list[ExternalReference] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        while queue and len(refs) < max_fetches:
            url, source, title = queue.pop(0)
            rate.acquire(f"link:{contract.slug}")
            host = urlparse(url).netloc
            scoped = is_in_scope(host, contract.scope, contract.out_of_scope) and not is_out_of_scope(
                host, contract.out_of_scope
            )
            ref = ExternalReference(
                url=url,
                source=source,
                title=title,
                ref_type=classify_reference(url, title),
                in_scope=scoped,
                fetched_at=datetime.now(UTC).isoformat(),
            )
            headers: dict[str, str] = {}
            if cookie and host.endswith("standoff365.com"):
                headers["Cookie"] = f"sessionid={cookie}"

            try:
                response = await client.get(url, headers=headers)
                ref.status_code = response.status_code
                ref.content_type = response.headers.get("content-type", "")
                body = response.content[:max_bytes]
                ref.preview = _text_preview(body, ref.content_type)
                digest = hashlib.sha256(url.encode()).hexdigest()[:12]
                ext = _extension_for(ref.content_type, url)
                file_path = out_dir / f"{digest}{ext}"
                file_path.write_bytes(body)
                ref.file_path = str(file_path).replace("\\", "/")

                for nested in _extract_nested_urls(body, ref.content_type):
                    if nested in seen_urls or not _host_allowed(nested):
                        continue
                    nested_type = classify_reference(nested)
                    if nested_type in ("api_docs", "api_spec") and len(queue) + len(refs) < max_fetches:
                        seen_urls.add(nested)
                        queue.append((nested, f"nested:{url}", ""))
            except Exception as exc:
                ref.error = str(exc)
                logger.warning("contract_link_fetch_failed", url=url, error=str(exc))

            refs.append(ref)

    if not refs:
        logger.info("contract_links_none", slug=contract.slug)
        return []

    refs_path = dossier_path(config, contract.slug, "references.json")
    refs_path.parent.mkdir(parents=True, exist_ok=True)
    refs_path.write_text(
        json.dumps([r.model_dump(mode="json") for r in refs], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md_path = dossier_path(config, contract.slug, "references.md")
    write_references_markdown(md_path, contract, refs)
    logger.info("contract_links_enriched", slug=contract.slug, count=len(refs), path=str(refs_path))
    return refs
