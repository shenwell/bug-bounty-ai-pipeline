# Cache Deception / Web Cache Poisoning (surface probe C)

Reference for `cache-deception` gate class. Not a full hunt-skill — coverage via SURFACE PROBE C in `/autopilot`.

## When probe C runs

Target returns cache headers (`cf-cache-status`, `x-cache`, `age`, `x-varnish`) on any path variant.

## Test matrix (record in `evidence/<host>/surface/cache-deception.txt`)

1. **Path extension trick** — `/account` vs `/account.css` vs `/account/..%2faccount` — compare cache HIT and body.
2. **Unkeyed headers** — `X-Forwarded-Host`, `X-Original-URL`, `X-Rewrite-URL` on cacheable GET.
3. **Vary confusion** — responses that vary on `Cookie` but cache key ignores it.
4. **Delimiter** — `;/cache.css`, `%0d%0a`, `?cb=1` on sensitive paths.

## Escalation

If credentialed response cached for unauth user → dispatch `auth-tester` + document chain to session theft.

## Kill

No caching layer on any tested path → `not-applicable: no cache headers across method-matrix probes`.

## Never-submit

Cache key reflection without credentialed body leakage PoC.
