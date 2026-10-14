# API error reference

Every error response from the Acme Cloud API has a JSON body with a code, a human readable message and a request ID. Quote the request ID when you contact support.

| Status | Meaning | What to do |
|---|---|---|
| 400 | The request body is not valid | Check required fields and types |
| 401 | Missing, invalid or expired token | Send a valid token; see ACME-AUTH-0042 |
| 403 | Token lacks the required scope | Add the scope or use another token |
| 404 | The file, project or member does not exist | Check the ID and the workspace |
| 409 | Conflict, for example a file edited by someone else | Fetch the latest version and merge |
| 413 | Payload larger than 5 GB | Use multipart upload |
| 429 | Rate limit exceeded | Wait for Retry-After; see the rate limit guide |
| 500 | Unexpected error on our side | Retry later and report the request ID |
| 503 | Service temporarily unavailable, usually during maintenance | Retry with backoff |

HTTP 503 responses include a Retry-After header. Planned maintenance is announced seven days ahead on the status page and normally lasts less than ten minutes.

Idempotency. Create and upload requests accept an Idempotency-Key header. If a network failure leaves you unsure whether a request succeeded, repeat it with the same key within 24 hours; the original result is returned and nothing is created twice.
