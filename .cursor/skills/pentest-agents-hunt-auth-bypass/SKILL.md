---
name: hunt-auth-bypass
description: >-
  Hunting skill for authentication bypass — session/JWT abuse, password reset
  poisoning, MFA step skip, host-header reset, IDOR on auth endpoints. OAuth/OIDC/SAML
  deep testing → dispatch oauth-hunter. Use with auth-tester agent.
generated_at: 2026-08-06
---

## Scope boundary vs oauth-hunter

| This skill (auth-tester) | oauth-hunter |
|--------------------------|--------------|
| Login/session/MFA/reset | OAuth/OIDC/SAML/JWT protocol |
| Host-header reset poison | redirect_uri, PKCE, XSW |
| Direct URL to post-MFA page | Token exchange, mix-up |
| JWT claim without sig break | alg confusion, kid/jku |

## Crown Jewel Targets

1. **Password reset token leak** — Host header poison, predictable token, no expiry.
2. **MFA bypass** — skip step via `/dashboard` direct, `mfa_verified: true` in JSON.
3. **Session fixation / swap** — login sets session without rotation.
4. **JWT role claim** — unsigned or `none` alg (verify with oauth-hunter if OIDC).
5. **Registration → privileged role** — `role:admin` in signup body.

## Role matrix (mandatory)

Test each action ×: unauth, userA, userB, admin, expired token, no cookie.

## Workflow

### Password reset
1. Request reset for victim email
2. Inspect reset link Host / X-Forwarded-Host reflection
3. Token entropy — UUIDv1 = predict (see hunt-idor)
4. Reuse token after password change
5. **Read-back**: login with new password

### MFA
1. Complete login through MFA once — capture all cookies/tokens
2. Replay pre-MFA session to post-MFA endpoints
3. PATCH profile to disable MFA without re-auth
4. **Read-back**: access protected resource without second factor

### Session
1. Logout — replay old cookie from second browser
2. Password change — old session still valid?
3. Concurrent sessions — sensitive action from both

## Kill Signals

- Logout CSRF alone
- Username enumeration without chain
- Missing HttpOnly on non-session cookie
- Rate limit on login without account lock bypass proof

## References

- `rules/payloads.md` JWT Attacks
- `skills/hunt-auth-bypass/references/acs-sources.md`
