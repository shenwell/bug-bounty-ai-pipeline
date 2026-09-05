"""Corpus v2 schema and seed adapters."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

SCHEMA_VERSION = 2
CORPUS_DEFAULT = Path("recon/fuzz-corpus.json")

REQUIRED_FIELDS = (
    "schema_version",
    "endpoint",
    "method",
    "seed_source",
    "mutation_tier",
    "auth_role",
    "cross_role_required",
    "headers_template",
    "body_template",
    "owned_object_ids",
    "scope_check_ok",
    "policy_hash",
)


def policy_hash(root: Path) -> str:
    parts: list[str] = []
    for rel in ("policy.md", "scope.yaml", ".scope.txt"):
        p = root / rel
        if p.exists():
            parts.append(p.read_text(encoding="utf-8", errors="replace")[:2000])
    if not parts:
        return "none"
    return hashlib.sha256("".join(parts).encode()).hexdigest()[:12]


def empty_seed(
    endpoint: str,
    *,
    method: str = "GET",
    seed_source: str = "mirror",
    mutation_tier: str = "read-only",
    auth_role: str = "A",
    cross_role_required: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "endpoint": endpoint.strip(),
        "method": method.upper(),
        "seed_source": seed_source,
        "mutation_tier": mutation_tier,
        "auth_role": auth_role,
        "cross_role_required": cross_role_required,
        "headers_template": {},
        "body_template": {},
        "owned_object_ids": [],
        "scope_check_ok": True,
        "policy_hash": policy_hash(root) if root else "",
        "class_hint": "idor",
    }


def validate_seed(seed: dict[str, Any]) -> tuple[bool, str]:
    for field in REQUIRED_FIELDS:
        if field not in seed:
            return False, f"missing field: {field}"
    if seed.get("schema_version") != SCHEMA_VERSION:
        return False, f"schema_version must be {SCHEMA_VERSION}"
    if not str(seed.get("endpoint") or "").strip():
        return False, "empty endpoint"
    return True, "ok"


def _method_from_path_kind(kind: str, path: str) -> str:
    k = (kind or "").lower()
    if "post" in k:
        return "POST"
    if "put" in k:
        return "PUT"
    if "patch" in k:
        return "PATCH"
    if "delete" in k:
        return "DELETE"
    return "GET"


def adapter_cabinet_mirror(root: Path, origin: str = "") -> list[dict[str, Any]]:
    """Load seeds from recon/cabinet-mirror.json + recon/endpoints-auth.txt."""
    seeds: list[dict[str, Any]] = []
    ph = policy_hash(root)
    endpoints_file = root / "recon" / "endpoints-auth.txt"
    if endpoints_file.exists():
        for line in endpoints_file.read_text(encoding="utf-8").splitlines():
            ep = line.strip()
            if ep and not ep.startswith("#"):
                seeds.append(
                    {
                        **empty_seed(ep, seed_source="mirror", root=root),
                        "policy_hash": ph,
                    }
                )
    mirror = root / "recon" / "cabinet-mirror.json"
    if mirror.exists():
        try:
            data = json.loads(mirror.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        base = origin or "https://setka.ru"
        for acct in (data.get("accounts") or {}).values():
            for page, meta in (acct.get("pages") or {}).items():
                for sample in meta.get("sample") or []:
                    path = sample.get("path") or page
                    if not path:
                        continue
                    url = urljoin(base, path) if path.startswith("/") else path
                    method = _method_from_path_kind(sample.get("kind", ""), path)
                    tier = "owned-write" if method != "GET" else "read-only"
                    seeds.append(
                        {
                            **empty_seed(
                                url,
                                method=method,
                                seed_source="mirror",
                                mutation_tier=tier,
                                root=root,
                            ),
                            "policy_hash": ph,
                            "class_hint": "business-logic" if method != "GET" else "idor",
                        }
                    )
    return _dedupe_seeds(seeds)


def adapter_traffic_exercised(root: Path) -> list[dict[str, Any]]:
    path = root / "recon" / "traffic-exercised.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    ph = policy_hash(root)
    rows: list[dict[str, Any]] = []
    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [{"endpoint": k, "request_count": v} for k, v in data.items()]
    for row in items:
        if isinstance(row, str):
            ep = row
        elif isinstance(row, dict):
            ep = str(row.get("endpoint") or row.get("url") or "")
        else:
            continue
        if not ep:
            continue
        seeds = empty_seed(ep, method="GET", seed_source="traffic", root=root)
        seeds["policy_hash"] = ph
        rows.append(seeds)
    return rows


def adapter_siblings(root: Path, endpoints: list[str], *, read_only: bool = True) -> list[dict[str, Any]]:
    if not read_only:
        return []
    try:
        from traffic_informed import expand_sibling_endpoints
    except ImportError:
        return []
    expanded = expand_sibling_endpoints(endpoints, limit=30)
    ph = policy_hash(root)
    return [
        {**empty_seed(ep, seed_source="sibling", root=root), "policy_hash": ph}
        for ep in expanded
        if ep not in endpoints
    ]


def adapter_field_bva(root: Path) -> list[dict[str, Any]]:
    """Parse Field BVA table from hunt/07-shared-sandbox-intel.md."""
    intel = root / "hunt" / "07-shared-sandbox-intel.md"
    if not intel.exists():
        return []
    text = intel.read_text(encoding="utf-8")
    if "## Field BVA" not in text:
        return []
    section = text.split("## Field BVA", 1)[1]
    rows: list[dict[str, Any]] = []
    ph = policy_hash(root)
    for line in section.splitlines():
        if not line.startswith("|") or line.count("|") < 5:
            continue
        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) < 5 or cols[0].startswith("Field") or cols[0].startswith("("):
            continue
        field, endpoint, ftype, limits, probes = cols[:5]
        if endpoint in ("—", "-", ""):
            continue
        ep = endpoint if "://" in endpoint else f"https://setka.ru{endpoint}"
        method = "POST" if endpoint.upper().startswith("POST") else "GET"
        if endpoint.upper().startswith(("GET ", "POST ", "PUT ", "PATCH ", "DELETE ")):
            parts = endpoint.split(None, 1)
            method = parts[0].upper()
            ep = parts[1] if len(parts) > 1 else ep
        seed = empty_seed(ep, method=method, seed_source="bva", mutation_tier="read-only", root=root)
        seed["policy_hash"] = ph
        seed["body_template"] = {field: probes.split(",")[0].strip() if probes else "0"}
        seed["class_hint"] = "business-logic"
        seed["bva"] = {"field": field, "type": ftype, "limits": limits, "probes": probes}
        rows.append(seed)
    return rows


def _dedupe_seeds(seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for s in seeds:
        key = f"{s.get('method','GET')}:{str(s.get('endpoint','')).lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def build_corpus(
    root: Path,
    *,
    write_mode: str = "read-only",
    merge_existing: Path | None = None,
) -> list[dict[str, Any]]:
    """Build corpus v2 from adapters (priority order)."""
    root = Path(root)
    seeds: list[dict[str, Any]] = []
    seeds.extend(adapter_cabinet_mirror(root))
    seeds.extend(adapter_traffic_exercised(root))
    base_eps = [s["endpoint"] for s in seeds]
    seeds.extend(adapter_siblings(root, base_eps, read_only=(write_mode == "read-only")))
    seeds.extend(adapter_field_bva(root))

    if write_mode == "read-only":
        seeds = [s for s in seeds if s.get("method", "GET") == "GET" and s.get("mutation_tier") != "hunter-only"]

    seeds = _dedupe_seeds(seeds)
    for i, s in enumerate(seeds):
        s["corpus_seed_id"] = f"cs-{i+1:04d}"

    if merge_existing and merge_existing.exists():
        try:
            existing = json.loads(merge_existing.read_text(encoding="utf-8"))
            if isinstance(existing, list):
                merged = _dedupe_seeds(list(existing) + seeds)
                for i, s in enumerate(merged):
                    s.setdefault("corpus_seed_id", f"cs-{i+1:04d}")
                return merged
        except json.JSONDecodeError:
            pass
    return seeds


def save_corpus(root: Path, seeds: list[dict[str, Any]], output: Path | None = None) -> Path:
    out = output or (root / CORPUS_DEFAULT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(seeds, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def load_corpus(root: Path, path: Path | None = None) -> list[dict[str, Any]]:
    p = path or (root / CORPUS_DEFAULT)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def host_from_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint if "://" in endpoint else f"https://{endpoint}")
    return parsed.netloc or "unknown"
