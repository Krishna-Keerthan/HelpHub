# API authentication and tokens

The Acme Cloud REST API accepts personal access tokens and OAuth 2.0 access tokens. Send the token in the Authorization header: Authorization: Bearer YOUR_TOKEN.

Personal access tokens. Create one under Profile, Developer, New token. Choose a name and the scopes it needs. The token is displayed once; store it securely. Tokens can be given an expiry of 7, 30 or 90 days, or no expiry on Business and Enterprise plans.

Scopes. files:read lets the token list and download files. files:write adds upload and delete. projects:read and projects:write cover projects and tasks. admin:members is restricted to owners and lets the token invite and remove members. Give a token the smallest set of scopes that works.

OAuth. Register an application under Developer, Applications to get a client ID and secret. Use the authorization code flow with PKCE for browser and mobile apps. Access tokens last one hour; refresh tokens last 60 days.

Authentication errors. A missing or malformed header returns HTTP 401. A valid token without the required scope returns HTTP 403. The error body contains a machine-readable code; ACME-AUTH-0042 means the token has expired, and the fix is to create a new token or refresh the OAuth token.

Revoke a token at any time from the same page. Revocation takes effect within a minute.
