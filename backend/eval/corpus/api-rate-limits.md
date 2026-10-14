# API rate limits

To keep the service fast for everyone, the Acme Cloud API limits how many requests a token can make. Limits apply per token, not per IP address.

| Plan | Requests per minute | Burst | Daily limit |
|---|---|---|---|
| Free | 60 | 10 | 5,000 |
| Team | 300 | 50 | 50,000 |
| Business | 1,200 | 200 | 500,000 |
| Enterprise | custom | custom | custom |

When you exceed a limit the API answers with HTTP 429 Too Many Requests. The response includes a Retry-After header with the number of seconds to wait. Every response carries X-RateLimit-Limit, X-RateLimit-Remaining and X-RateLimit-Reset headers so a client can slow down before it is blocked.

Recommended handling
- Read Retry-After and pause that long; do not retry immediately.
- Use exponential backoff with jitter: wait 1, 2, 4 and 8 seconds plus a random fraction.
- Cache responses that rarely change, such as the member list.
- Prefer webhooks over polling for changes.
- Batch requests with the bulk endpoints, which count as a single request.

Upload and download endpoints have separate bandwidth limits and do not use the request counter. Repeated HTTP 429 responses for more than an hour may lead to the token being suspended; the owner is notified by email. To raise your limits permanently, upgrade your plan or contact sales for a custom quota.
