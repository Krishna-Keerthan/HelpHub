# Release notes for version 2.4

Version 2.4.0 (June)
New: the Acme AI assistant can summarise long discussions and answer questions about the files you can open. It is off by default; owners switch it on in Settings, Features. New: audit log streaming for Enterprise workspaces. New: guest accounts, which can be invited to a single project without counting towards your plan's member limit. Improved: the API now supports cursor-based pagination on every list endpoint, and the page size can be up to 200. Improved: faster sign-in for members using single sign-on.

Changed: the minimum password length is raised from 10 to 12 characters. Existing passwords keep working until they are next changed.

Deprecated: API tokens without an expiry will stop being created on Free and Team plans in version 2.5. Existing tokens continue to work. The old v1 file listing endpoint will be removed in December; use the v2 listing instead.

Fixed: the Linux client now starts on distributions with an older graphics library, resolving the known issue from version 2.3.0. Fixed: comments with more than 10,000 characters were cut off. Fixed: some webhooks were delivered twice after a timeout.

Upgrading. Desktop clients move to v2.4.0 automatically unless updates are paused. Versions older than 2.2 are no longer supported and show a banner asking you to update.

Compatibility. The API remains backwards compatible within the v2 line.
