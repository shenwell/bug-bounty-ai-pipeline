"""Per-program constraints engine — priority over general scope guard."""

from __future__ import annotations

from urllib.parse import urlparse

from portfolio.common.models import Contract, ProgramConstraints
from portfolio.guardrails.scope import ScopeValidator, extract_host, host_matches_pattern


class ConstraintViolation(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ProgramConstraintsEngine:
    def __init__(self, scope_validator: ScopeValidator):
        self._scope = scope_validator

    def validate_network_request(
        self,
        url: str,
        contract: Contract,
        headers: dict[str, str] | None = None,
        action: str = "http_request",
    ) -> None:
        ok, msg = self._scope.validate_request(url, contract, action)
        if not ok:
            raise ConstraintViolation(msg)

        constraints = contract.constraints
        self._check_vpn(constraints)
        self._check_headers(constraints, headers or {})
        self._check_internal_hosts(url, constraints)

    def validate_rce_command(self, command: str, contract: Contract) -> None:
        allowed = contract.constraints.allowed_rce_commands
        if not allowed:
            return
        cmd = command.strip().split()[0] if command.strip() else ""
        if cmd not in allowed and command.strip() not in allowed:
            raise ConstraintViolation(
                f"RCE command not allowed by program rules: {command!r}. "
                f"Allowed: {allowed}"
            )

    def validate_file_read(self, path: str, contract: Contract) -> None:
        allowed = contract.constraints.allowed_file_reads
        if not allowed:
            return
        if path not in allowed:
            raise ConstraintViolation(
                f"File read not allowed: {path!r}. Allowed: {allowed}"
            )

    def validate_bulk_enumeration(self, contract: Contract, count: int, threshold: int = 500) -> None:
        if contract.constraints.no_bulk_enumeration and count > threshold:
            raise ConstraintViolation(
                f"Bulk enumeration blocked (count={count}, threshold={threshold})"
            )

    def should_stop_after_escape(self, contract: Contract) -> bool:
        return contract.constraints.stop_after_container_escape

    def _check_vpn(self, constraints: ProgramConstraints) -> None:
        if constraints.vpn_required:
            import os
            if os.environ.get("VPN_CONNECTED", "").lower() not in ("1", "true", "yes"):
                raise ConstraintViolation(
                    "Program requires VPN — set VPN_CONNECTED=true after connecting"
                )

    def _check_headers(self, constraints: ProgramConstraints, headers: dict[str, str]) -> None:
        for name, expected in constraints.required_headers.items():
            actual = headers.get(name) or headers.get(name.lower())
            if not actual:
                raise ConstraintViolation(f"Missing required header: {name}")
            if "{user}" in expected:
                import os
                user = os.environ.get("BUG_BOUNTY_USER", "")
                expected_val = expected.replace("{user}", user)
                if actual != expected_val:
                    raise ConstraintViolation(
                        f"Header {name} must be {expected_val!r}, got {actual!r}"
                    )
            elif actual != expected:
                raise ConstraintViolation(
                    f"Header {name} must be {expected!r}, got {actual!r}"
                )

    def _check_internal_hosts(self, url: str, constraints: ProgramConstraints) -> None:
        if not constraints.internal_test_hosts:
            return
        host = extract_host(url)
        port = urlparse(url).port
        target = f"{host}:{port}" if port else host
        for allowed in constraints.internal_test_hosts:
            allowed_host = allowed.split(":")[0]
            if host_matches_pattern(host, allowed_host) or target == allowed:
                return
        if host.startswith("192.168.") or host.startswith("10.") or host.startswith("172."):
            raise ConstraintViolation(
                f"Internal host {target} not in allowed test hosts: {constraints.internal_test_hosts}"
            )
