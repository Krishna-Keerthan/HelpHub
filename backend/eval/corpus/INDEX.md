# Acme Cloud evaluation corpus

Fictional support knowledge base used for retrieval evaluation (24 documents). No real company text.

| Title | Slug | Summary |
|---|---|---|
| Recovering a locked or inaccessible account | `account-recovery` | Forgot password, locked account, lost second factor and backup codes, owner verification. (Overlaps password-reset.) |
| API authentication and tokens | `api-authentication` | Personal access tokens, scopes, OAuth with PKCE, 401/403, ACME-AUTH-0042 expired token. |
| API error reference | `api-error-reference` | HTTP status table (400..503), HTTP 503 maintenance, request IDs, Idempotency-Key. |
| API rate limits | `api-rate-limits` | Per-plan request limits table, HTTP 429, Retry-After and X-RateLimit headers, backoff advice. |
| Audit logs | `audit-logs` | What the audit log records, retention by plan, search, export, streaming, alerts. |
| Billing frequently asked questions | `billing-faq` | When you are charged, payment methods, invoices, declined cards, purchase orders, tax. |
| Release notes for version 2.3 | `changelog-v2-3` | Release notes 2.3.0 and 2.3.1: shared drafts, faster uploads, fixes incl. ERR_CONN_RESET and E-4013 skew. |
| Release notes for version 2.4 | `changelog-v2-4` | Release notes 2.4.0: AI assistant, guest accounts, pagination, deprecations, password length 12. |
| Exporting your data | `data-export` | Workspace, project and personal data export; formats, timing, 90-day export window after cancelling. |
| Installing the desktop client | `desktop-client-install` | Install on Windows/macOS/Linux, MSI deployment, error 0x80070005, requirements. |
| Getting started with Acme Cloud | `getting-started` | Ten-minute setup: workspace, invites, first project, first upload, client, 2FA. |
| Using the mobile app offline | `mobile-app-offline-mode` | Keeping files offline, storage limits, offline edits and conflicts, remote wipe, camera upload. |
| Notifications and real-time updates | `notifications-and-realtime` | WebSocket real-time updates, close code 1006 causes, polling fallback, notification channels. |
| Resetting your password | `password-reset` | Self-service password reset steps, link validity, requirements, SSO members. (Overlaps account-recovery.) |
| Plans and pricing | `plans-and-pricing` | Free/Team/Business/Enterprise table, storage add-on SKUs (AB-1234-M/L/XL), security key SKU CD-7781-M. |
| Refunds and cancellations | `refunds-and-cancellations` | Cancelling, 30-day money-back guarantee, refund exceptions, downgrade credit, data retention after cancel. |
| Security overview | `security-overview` | Encryption, regions, backups, staff access, compliance (SOC 2, ISO 27001, GDPR), vulnerability reports. |
| Sharing and permissions | `sharing-and-permissions` | Workspace/project roles, guests, share links with passwords and expiry, inheritance, external domains. |
| Single sign-on error reference | `sso-error-reference` | SSO error table E-4011..E-4014; E-4012 (signature/certificate) vs E-4013 (clock skew) near pair. |
| Setting up single sign-on with SAML | `sso-saml-setup` | Steps to configure SAML single sign-on (Business/Enterprise), metadata, NameID mapping, keeping a password owner. |
| Storage quotas and what happens when you run out | `storage-quotas` | Pooled storage per plan, usage warnings, E-5001 upload failure, add-on SKU AB-1234-XL, version history, trash. |
| Troubleshooting the sync client | `sync-client-troubleshooting` | Desktop sync errors: ERR_CONN_RESET, ERR_SSL_PROTOCOL_ERROR, SYNC_ERR_409 conflicts, selective sync. |
| Two-factor authentication | `two-factor-authentication` | Authenticator app, FIDO2 key (SKU CD-7781-M), SMS, backup codes, requiring 2FA, trusted devices. |
| Webhooks | `webhooks` | Creating webhooks, events, HMAC signature verification, retries and failure handling. |
