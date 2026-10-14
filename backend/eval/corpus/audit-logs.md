# Audit logs

The audit log records who did what and when in your workspace. It is available on the Business and Enterprise plans and can be read by owners and by admins who were granted the Security auditor permission.

What is recorded. Sign-ins and failed sign-ins, password and two-factor changes, member invitations and removals, role changes, permission changes, share links created or removed, file downloads over 1 GB, exports, API token creation and deletion, and changes to security settings such as single sign-on.

Each entry holds a timestamp in UTC, the actor, the IP address, the action, the target and the result. Entries cannot be edited or deleted by anyone, including owners.

Retention. Business plans keep 180 days of history. Enterprise plans keep 13 months by default and up to seven years by arrangement. Entries older than the limit are removed permanently.

Searching. Open Settings, Security, Audit log. Filter by actor, action or date, and search for a file name. Large investigations can use the export button, which produces a CSV file.

Streaming. Enterprise customers can send the log to their own systems in real time. Choose a destination under Audit log, Streaming, and Acme Cloud will post signed JSON batches every 30 seconds.

Alerts can be configured for sensitive actions such as a new owner being added.
