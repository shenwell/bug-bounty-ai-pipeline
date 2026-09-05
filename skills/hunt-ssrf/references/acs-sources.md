# ACS reference whitelist (audit-only, no phishing/C2)

Use as secondary workflow hints after writeup-search MCP and this SKILL.md.

| ACS skill path | Use for |
|----------------|---------|
| `analyzing-cloud-storage-access-patterns` | S3/Azure blob access pattern review after SSRF lands in storage |
| `auditing-aws-s3-bucket-permissions` | Post-SSRF credential use on bucket enumeration |
| `analyzing-network-traffic-for-incidents` | Blind SSRF timing/oracle methodology |

Do **not** use device-code phishing, C2, or red-team exfil skills from ACS in bug bounty scope.
