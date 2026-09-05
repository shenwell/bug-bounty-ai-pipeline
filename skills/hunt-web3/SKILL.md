---
name: hunt-web3
description: >-
  Gate-class reference for smart contract hunting. Full audit via web3-auditor.
  Skip when scope.yaml has no contract addresses / DeFi protocol in scope.
generated_at: 2026-08-06
---

## Skip criteria

No `contract`, `ethereum`, `solidity`, `immunefi`, or protocol address in `scope.yaml` → `not-applicable`.

## Workflow

1. Map in-scope contracts from scope file.
2. Run web3-auditor grep arsenal + Foundry PoC per program policy.
3. Focus: reentrancy, access control, oracle manipulation, flash loan logic.

## ACS

`analyzing-ethereum-smart-contract-vulnerabilities`, `auditing-foundry-smart-contract-security` (reference only).
