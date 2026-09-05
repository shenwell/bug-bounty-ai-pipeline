"""Scope validation — ported from bountyhunter scope-guard logic."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from portfolio.common.config import AppConfig
from portfolio.common.models import Contract


def normalize_host(host: str) -> str:
    host = host.lower().strip().rstrip(".")
    if host.startswith("*."):
        return host[2:]
    return host


def host_matches_pattern(host: str, pattern: str) -> bool:
    host = normalize_host(host)
    pattern = normalize_host(pattern)
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return host == suffix or host.endswith("." + suffix)
    return host == pattern


def extract_host(url_or_host: str) -> str:
    if "://" in url_or_host:
        parsed = urlparse(url_or_host)
        return normalize_host(parsed.hostname or "")
    return normalize_host(url_or_host.split(":")[0])


class ScopeValidator:
  def __init__(self, config: AppConfig):
    self._hard_oos = [normalize_host(h) for h in config.scope.hard_out_of_scope]
    self._forbidden = set(config.scope.forbidden_actions)

  def is_hard_out_of_scope(self, url_or_host: str) -> bool:
    host = extract_host(url_or_host)
    for pattern in self._hard_oos:
      if host_matches_pattern(host, pattern):
        return True
    return False

  def matches_scope(self, url_or_host: str, contract: Contract) -> bool:
    host = extract_host(url_or_host)
    if self.is_hard_out_of_scope(host):
      return False
    for oos in contract.out_of_scope:
      if host_matches_pattern(host, oos):
        return False
    if not contract.scope:
      return False
    for scope_entry in contract.scope:
      if host_matches_pattern(host, scope_entry):
        return True
      if re.match(r"^\d+\.\d+\.\d+\.\d+", scope_entry):
        if host == normalize_host(scope_entry.split(":")[0]):
          return True
    return False

  def validate_action(self, action: str) -> tuple[bool, str]:
    action_lower = action.lower()
    for forbidden in self._forbidden:
      if forbidden in action_lower:
        return False, f"Forbidden action: {forbidden}"
    return True, ""

  def validate_request(
    self,
    url: str,
    contract: Contract,
    action: str = "http_request",
  ) -> tuple[bool, str]:
    ok, msg = self.validate_action(action)
    if not ok:
      return False, msg
    if self.is_hard_out_of_scope(url):
      return False, f"Hard out-of-scope: {url}"
    if not self.matches_scope(url, contract):
      return False, f"Not in contract scope: {url}"
    return True, ""
