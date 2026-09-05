# MCP threat checklist (reference: AI-Infra-Guard / MCPGuard taxonomy)

Use when threat model flags `llm-ai`, `mcp`, or `agent-workflow`, or recon finds MCP/chatbot surface.

## T01 — Tool definition exposure

- [ ] MCP tool list reachable without auth (`tools/list`, OpenAPI, debug UI)
- [ ] Tool schemas leak internal paths, env var names, or shell commands

## T02 — Tool poisoning / spoofing

- [ ] Tool description field accepts attacker-controlled text (indirect injection)
- [ ] Duplicate tool names across servers — wrong tool invoked
- [ ] Tool metadata rendered in HTML without encoding (XSS → token theft)

## T03 — Credential exfiltration

- [ ] MCP server returns secrets in tool output (API keys, connection strings)
- [ ] OAuth callback accepts `javascript:` or attacker origin
- [ ] `window.open` with untrusted MCP server URL (H1 #3211031 pattern)

## T04 — Command injection via tools

- [ ] Shell/exec/python tools without argument allowlist
- [ ] File-read tools with path traversal (`../../etc/passwd`)
- [ ] SSRF via URL-accepting tools (fetch, browse, webhook)

## T05 — Localhost / DNS rebinding

- [ ] MCP server bound to 127.0.0.1 without rebinding protection (H1 #3176157)
- [ ] Browser can reach localhost MCP from malicious page

## T06 — Privilege boundary

- [ ] Agent granted tools beyond task scope (excessive agency)
- [ ] Cross-tenant tool invocation (wrong `tenant_id` / `appId`)

## T07 — Supply chain

- [ ] Remote skill/MCP install from URL without signature check
- [ ] n8n/Dify workflow imports untrusted nodes

## T08 — Output handling

- [ ] LLM output rendered via `innerHTML` / `new Function()` (Open WebUI CVE-2025-64496)
- [ ] SSE `execute` events from untrusted model server

## Dispatch

When ≥2 categories apply: dispatch `llm-ai-hunter` with `subtype=mcp` and this checklist in preamble.

Never-submit alone: jailbreak demo, system prompt leak without sensitive content, tool list without exploit path.
