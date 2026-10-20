# Review of the draft unanswerable questions

**Rule for this review: remove a question only if a passage actually answers it, never because it retrieved well.** A passage that is merely on the same topic, or that matched the question's words, is not a reason to remove it. These passages are what the current search (hybrid: vector + full text, fused by rank) returns as its top 2 for each question, shown as plain text. No scores or similarity values are shown. Questions, split rule and threshold are unchanged.

Source: `unanswerable_candidates.json` (status: draft for human review). Passages come from `eval/corpus/*.md` as chunked by the app's chunker.

## u-001: Is there a referral program that gives free storage for inviting friends?

Category: `near_miss`. Split: `dev`.

Passage 1 (`plans-and-pricing`):

> Acme Cloud has four plans. Prices are per member per month when billed annually; monthly billing costs 20 percent more.
>
> | Plan | Price | Storage per member | Members | Support |
> |---|---|---|---|---|
> | Free | 0 USD | 5 GB | up to 3 | community forum |
> | Team | 8 USD | 100 GB | up to 50 | email, 2 business days |
> | Business | 18 USD | 1 TB | unlimited | email and chat, 4 hours |
> | Enterprise | custom | pooled, negotiated | unlimited | named engineer, 1 hour |
>
> Storage add-ons. When a workspace runs short of space you can buy extra capacity without changing plan. Add-ons are sold as stock keeping units (SKUs): AB-1234-M adds 1 TB, AB-1234-L adds 10 TB and AB-1234-XL adds 50 TB of pooled storage. Add-ons renew with your plan and can be removed at the next renewal date.
>
> Security keys. The hardware security key for two-factor sign-in is SKU CD-7781-M and ships in a pack of two.

Passage 2 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-002: Can I pay my invoice through PayPal?

Category: `near_miss`. Split: `test`.

Passage 1 (`billing-faq`):

> Q: When am I charged?
> A: Annual plans are charged on the day you subscribe and every twelve months after. Monthly plans are charged on the same calendar day each month. If that day does not exist in a month, we charge on its last day.
>
> Q: How do I change my payment method?
> A: Open Settings, Billing, Payment methods and add a new card. Mark it as default and remove the old one. Only workspace owners and billing contacts can do this.
>
> Q: Where can I find my invoices?
> A: Invoices are listed under Billing, Invoice history. Each one is a PDF with your company name, address and tax number. To change those details, edit Billing contacts first; invoices already issued cannot be altered, but we can issue a corrected copy on request.

Passage 2 (`billing-faq`):

> Q: Why was my card declined?
> A: The most common reasons are an expired card, a billing address that does not match the bank's records, or a bank block on international payments. We retry a failed payment after three days and again after seven. If all attempts fail the workspace moves to read-only mode, and nothing is deleted.
>
> Q: Do you accept purchase orders?
> A: Enterprise customers can pay by invoice with net-30 terms. Contact sales to set this up.
>
> Q: Is tax included in the price?
> A: No. Sales tax or VAT is added at checkout based on the billing address.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-003: What is the maximum number of webhooks I can create in one workspace?

Category: `near_miss`. Split: `dev`.

Passage 1 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Passage 2 (`storage-quotas`):

> Each member of a paid plan contributes storage to a pool shared by the whole workspace. A Team workspace with ten members has 1 TB of pooled space, and a Business workspace with ten members has 10 TB. Free workspaces have a flat 5 GB.
>
> Checking usage. Settings, Storage shows total usage, the biggest folders and the members who upload the most. Usage counts the current version of every file plus old versions kept for history. The trash counts too, until it is emptied or the 30-day retention ends.
>
> Warnings. At 80 percent owners receive an email. At 95 percent every member sees a banner.
>
> Quota exceeded. When the pool is full the API and the apps return error E-5001 on upload. Existing files remain available and nothing is deleted. To continue you can delete files and empty the trash, shorten version history from 100 to 10 versions, upgrade the plan, or buy a storage add-on.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-004: How do I switch the desktop client to dark mode?

Category: `near_miss`. Split: `test`.

Passage 1 (`sync-client-troubleshooting`):

> The desktop sync client keeps your local folders identical to Acme Cloud. If sync stalls, open the tray icon, choose Activity and look for an error name.
>
> ERR_CONN_RESET. The connection to our servers was reset in the middle of a transfer. This is usually caused by a corporate proxy, an antivirus product that inspects encrypted traffic, or an unstable wireless network. Switch to a wired connection, add sync.acmecloud.example to the proxy allow-list and retry. The client resumes partial uploads automatically.
>
> ERR_SSL_PROTOCOL_ERROR. The secure handshake failed. Check that your computer's date and time are correct, and that no security software replaces our certificate. Update the client to v2.3.1 or newer.
>
> SYNC_ERR_409. The same file was changed in two places before they could sync. The client keeps both versions: yours is renamed with the suffix conflicted copy and the cloud version is downloaded. Compare them and delete the one you do not need.

Passage 2 (`changelog-v2-4`):

> Fixed: the Linux client now starts on distributions with an older graphics library, resolving the known issue from version 2.3.0. Fixed: comments with more than 10,000 characters were cut off. Fixed: some webhooks were delivered twice after a timeout.
>
> Upgrading. Desktop clients move to v2.4.0 automatically unless updates are paused. Versions older than 2.2 are no longer supported and show a banner asking you to update.
>
> Compatibility. The API remains backwards compatible within the v2 line.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-005: Does the desktop client run on ChromeOS?

Category: `near_miss`. Split: `dev`.

Passage 1 (`sync-client-troubleshooting`):

> The desktop sync client keeps your local folders identical to Acme Cloud. If sync stalls, open the tray icon, choose Activity and look for an error name.
>
> ERR_CONN_RESET. The connection to our servers was reset in the middle of a transfer. This is usually caused by a corporate proxy, an antivirus product that inspects encrypted traffic, or an unstable wireless network. Switch to a wired connection, add sync.acmecloud.example to the proxy allow-list and retry. The client resumes partial uploads automatically.
>
> ERR_SSL_PROTOCOL_ERROR. The secure handshake failed. Check that your computer's date and time are correct, and that no security software replaces our certificate. Update the client to v2.3.1 or newer.
>
> SYNC_ERR_409. The same file was changed in two places before they could sync. The client keeps both versions: yours is renamed with the suffix conflicted copy and the cloud version is downloaded. Compare them and delete the one you do not need.

Passage 2 (`desktop-client-install`):

> The desktop client is available for Windows 10 and 11, macOS 12 and newer, and Linux (Debian, Ubuntu and Fedora packages).
>
> Windows. Download the installer from Settings, Devices, and run it. If your organisation restricts software installation, an administrator can deploy the MSI package silently with msiexec. After installation sign in and choose the folder to sync; the default is Acme Cloud in your user folder. If the installer stops with error 0x80070005, the account does not have permission to write to the target folder. Run the installer as an administrator or pick a folder you own, and make sure antivirus software is not blocking the installer.
>
> macOS. Open the disk image and drag Acme Cloud into Applications. The first time you start it, macOS asks for permission to access files and, on newer versions, to enable the file provider extension. Allow both in System Settings, Privacy and Security.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-006: How do I connect Acme Cloud to Jira so tasks link to tickets?

Category: `near_miss`. Split: `test`.

Passage 1 (`password-reset`):

> If you forgot your password, you can set a new one yourself. This takes about two minutes.
>
> 1. Open the sign-in page and click Forgot password.
> 2. Enter the email address you use for Acme Cloud and press Send reset link.
> 3. Open the email titled Reset your Acme Cloud password. The link is valid for 60 minutes and can be used once.
> 4. Choose a new password. It must have at least 12 characters and must not be one of your last five passwords.
> 5. You are signed out of all other devices and sent back to the sign-in page.
>
> If the email does not arrive, check your spam folder and make sure you typed the right address. Messages can take up to ten minutes. Requesting a new link makes the previous link stop working.
>
> Members who sign in with single sign-on do not have an Acme Cloud password. They reset their password with their company identity provider instead.

Passage 2 (`sso-saml-setup`):

> 1. Open Settings, Security, Single sign-on and choose Set up SAML.
> 2. Copy the Acme Cloud values shown on screen: the entity ID, the assertion consumer service (ACS) URL and the certificate fingerprint. Paste them into a new application in your identity provider.
> 3. In your identity provider, map the NameID to the member's email address. Optionally map first name, last name and group claims.
> 4. Back in Acme Cloud, upload the metadata file or paste the metadata URL, then press Test connection.
> 5. When the test succeeds, enable Require SSO for all members. Members who already have passwords keep them until you switch enforcement on.
>
> Always keep one owner account that can still log in with a password. If the identity provider is misconfigured and enforcement is on, that account is the only way back in. When login fails, see the SSO error reference.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-007: Is there a Windows Phone version of the mobile app?

Category: `near_miss`. Split: `dev`.

Passage 1 (`changelog-v2-3`):

> Version 2.3.0 (March)
> New: shared drafts let several people edit a page at once with live cursors. New: project templates can be saved and reused across the workspace. New: the search bar now finds text inside PDF and Office documents. Improved: uploads of many small files are up to three times faster. Improved: the mobile app opens large folders without freezing. Changed: the default share link expiry is now 30 days instead of never; existing links are not affected.
>
> Version 2.3.1 (April)
> Fixed: files with accents or emoji in their names failed to sync on Windows. Fixed: the sync client sometimes reported ERR_CONN_RESET after waking from sleep; it now reconnects quietly. Fixed: single sign-on users were shown E-4013 when their clock was slightly ahead; we now accept a skew of five minutes. Fixed: invoice PDFs showed the wrong tax number for some European customers. Security: updated a third-party library used for image previews.

Passage 2 (`mobile-app-offline-mode`):

> The Acme Cloud app for iOS and Android lets you work on trains, planes and anywhere the signal is weak. Files you mark as available offline are stored on your phone and updated whenever you are connected.
>
> Making files available offline. Open a file or folder, tap the three dots and choose Keep offline. A small tick shows that the item is stored. Folders can be kept offline too, and new files in them are downloaded automatically over Wi-Fi.
>
> Storage control. Open Profile, Offline storage to see how much space is used. You can set a limit between 1 and 50 GB and choose whether downloads are allowed on mobile data. When the limit is reached, the files you opened least recently are removed from the phone first, while your pinned items are always kept.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-008: Can I schedule a file to be deleted automatically on a chosen date?

Category: `near_miss`. Split: `test`.

Passage 1 (`mobile-app-offline-mode`):

> The Acme Cloud app for iOS and Android lets you work on trains, planes and anywhere the signal is weak. Files you mark as available offline are stored on your phone and updated whenever you are connected.
>
> Making files available offline. Open a file or folder, tap the three dots and choose Keep offline. A small tick shows that the item is stored. Folders can be kept offline too, and new files in them are downloaded automatically over Wi-Fi.
>
> Storage control. Open Profile, Offline storage to see how much space is used. You can set a limit between 1 and 50 GB and choose whether downloads are allowed on mobile data. When the limit is reached, the files you opened least recently are removed from the phone first, while your pinned items are always kept.

Passage 2 (`storage-quotas`):

> Each member of a paid plan contributes storage to a pool shared by the whole workspace. A Team workspace with ten members has 1 TB of pooled space, and a Business workspace with ten members has 10 TB. Free workspaces have a flat 5 GB.
>
> Checking usage. Settings, Storage shows total usage, the biggest folders and the members who upload the most. Usage counts the current version of every file plus old versions kept for history. The trash counts too, until it is emptied or the 30-day retention ends.
>
> Warnings. At 80 percent owners receive an email. At 95 percent every member sees a banner.
>
> Quota exceeded. When the pool is full the API and the apps return error E-5001 on upload. Existing files remain available and nothing is deleted. To continue you can delete files and empty the trash, shorten version history from 100 to 10 versions, upgrade the plan, or buy a storage add-on.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-009: How do I set up SCIM user provisioning for my identity provider?

Category: `near_miss`. Split: `dev`.

Passage 1 (`sso-saml-setup`):

> 1. Open Settings, Security, Single sign-on and choose Set up SAML.
> 2. Copy the Acme Cloud values shown on screen: the entity ID, the assertion consumer service (ACS) URL and the certificate fingerprint. Paste them into a new application in your identity provider.
> 3. In your identity provider, map the NameID to the member's email address. Optionally map first name, last name and group claims.
> 4. Back in Acme Cloud, upload the metadata file or paste the metadata URL, then press Test connection.
> 5. When the test succeeds, enable Require SSO for all members. Members who already have passwords keep them until you switch enforcement on.
>
> Always keep one owner account that can still log in with a password. If the identity provider is misconfigured and enforcement is on, that account is the only way back in. When login fails, see the SSO error reference.

Passage 2 (`sso-saml-setup`):

> Single sign-on lets members log in through your company identity provider instead of with a separate Acme Cloud password. It is available on the Business and Enterprise plans, and only workspace owners can configure it.
>
> Before you start, have your identity provider's metadata URL or XML file ready. Supported providers include Okta, Microsoft Entra ID, Google Workspace and any provider that speaks SAML 2.0.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-010: Does Acme Cloud support Kerberos authentication for the desktop client?

Category: `near_miss`. Split: `test`.

Passage 1 (`desktop-client-install`):

> The desktop client is available for Windows 10 and 11, macOS 12 and newer, and Linux (Debian, Ubuntu and Fedora packages).
>
> Windows. Download the installer from Settings, Devices, and run it. If your organisation restricts software installation, an administrator can deploy the MSI package silently with msiexec. After installation sign in and choose the folder to sync; the default is Acme Cloud in your user folder. If the installer stops with error 0x80070005, the account does not have permission to write to the target folder. Run the installer as an administrator or pick a folder you own, and make sure antivirus software is not blocking the installer.
>
> macOS. Open the disk image and drag Acme Cloud into Applications. The first time you start it, macOS asks for permission to access files and, on newer versions, to enable the file provider extension. Allow both in System Settings, Privacy and Security.

Passage 2 (`sync-client-troubleshooting`):

> The desktop sync client keeps your local folders identical to Acme Cloud. If sync stalls, open the tray icon, choose Activity and look for an error name.
>
> ERR_CONN_RESET. The connection to our servers was reset in the middle of a transfer. This is usually caused by a corporate proxy, an antivirus product that inspects encrypted traffic, or an unstable wireless network. Switch to a wired connection, add sync.acmecloud.example to the proxy allow-list and retry. The client resumes partial uploads automatically.
>
> ERR_SSL_PROTOCOL_ERROR. The secure handshake failed. Check that your computer's date and time are correct, and that no security software replaces our certificate. Update the client to v2.3.1 or newer.
>
> SYNC_ERR_409. The same file was changed in two places before they could sync. The client keeps both versions: yours is renamed with the suffix conflicted copy and the cloud version is downloaded. Compare them and delete the one you do not need.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-011: What uptime percentage does the Enterprise service level agreement guarantee?

Category: `near_miss`. Split: `dev`.

Passage 1 (`api-rate-limits`):

> To keep the service fast for everyone, the Acme Cloud API limits how many requests a token can make. Limits apply per token, not per IP address.
>
> | Plan | Requests per minute | Burst | Daily limit |
> |---|---|---|---|
> | Free | 60 | 10 | 5,000 |
> | Team | 300 | 50 | 50,000 |
> | Business | 1,200 | 200 | 500,000 |
> | Enterprise | custom | custom | custom |
>
> When you exceed a limit the API answers with HTTP 429 Too Many Requests. The response includes a Retry-After header with the number of seconds to wait. Every response carries X-RateLimit-Limit, X-RateLimit-Remaining and X-RateLimit-Reset headers so a client can slow down before it is blocked.

Passage 2 (`plans-and-pricing`):

> Acme Cloud has four plans. Prices are per member per month when billed annually; monthly billing costs 20 percent more.
>
> | Plan | Price | Storage per member | Members | Support |
> |---|---|---|---|---|
> | Free | 0 USD | 5 GB | up to 3 | community forum |
> | Team | 8 USD | 100 GB | up to 50 | email, 2 business days |
> | Business | 18 USD | 1 TB | unlimited | email and chat, 4 hours |
> | Enterprise | custom | pooled, negotiated | unlimited | named engineer, 1 hour |
>
> Storage add-ons. When a workspace runs short of space you can buy extra capacity without changing plan. Add-ons are sold as stock keeping units (SKUs): AB-1234-M adds 1 TB, AB-1234-L adds 10 TB and AB-1234-XL adds 50 TB of pooled storage. Add-ons renew with your plan and can be removed at the next renewal date.
>
> Security keys. The hardware security key for two-factor sign-in is SKU CD-7781-M and ships in a pack of two.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-012: How do I change the language of the web interface to German?

Category: `near_miss`. Split: `test`.

Passage 1 (`getting-started`):

> Tip: you can change the workspace name later, but the web address you picked at sign-up is permanent. If you picked a typo, contact support and we will help you migrate to a new address.
>
> New workspaces start on the Free plan with 5 GB of storage and three members. Upgrade at any time from Settings, Billing.

Passage 2 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-013: How do I transfer ownership of a workspace to another member?

Category: `near_miss`. Split: `dev`.

Passage 1 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Passage 2 (`sharing-and-permissions`):

> Access in Acme Cloud is controlled at three levels: the workspace, the project and the individual file or folder.
>
> Workspace roles. Owners manage billing, security and members. Admins manage projects and members but not billing. Members create and edit within projects they belong to. Guests see only what is explicitly shared with them and never appear in the member count of a plan.
>
> Project roles. Each project has Editors, Commenters and Viewers. Editors can change and delete files. Commenters can add comments and tasks. Viewers can only read and download.
>
> Share links. Any file or folder can have a link. You choose whether anyone with the link can open it or only signed-in members, whether it can be downloaded, and when it expires. You can protect a link with a password. Links are revoked instantly when you press Remove link.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-014: Is there an official Python SDK for the Acme Cloud API?

Category: `near_miss`. Split: `test`.

Passage 1 (`webhooks`):

> Webhooks let Acme Cloud call your server when something happens, so you do not have to poll the API. Create one under Developer, Webhooks, New webhook. Enter the URL, choose the events and copy the signing secret.
>
> Events include file.created, file.updated, file.deleted, comment.created, task.completed and member.added. Each delivery is an HTTPS POST with a JSON body containing the event ID, the type, the time and the object.
>
> Verifying signatures. Every request has an X-Acme-Signature header, an HMAC-SHA256 of the raw body computed with your signing secret. Compare it in constant time and reject requests that do not match. Also check the X-Acme-Timestamp header and ignore deliveries older than five minutes to prevent replays.
>
> Responding. Return any 2xx status within ten seconds. Do the heavy work after replying, for example by putting the event on a queue.

Passage 2 (`desktop-client-install`):

> The desktop client is available for Windows 10 and 11, macOS 12 and newer, and Linux (Debian, Ubuntu and Fedora packages).
>
> Windows. Download the installer from Settings, Devices, and run it. If your organisation restricts software installation, an administrator can deploy the MSI package silently with msiexec. After installation sign in and choose the folder to sync; the default is Acme Cloud in your user folder. If the installer stops with error 0x80070005, the account does not have permission to write to the target folder. Run the installer as an administrator or pick a folder you own, and make sure antivirus software is not blocking the installer.
>
> macOS. Open the disk image and drag Acme Cloud into Applications. The first time you start it, macOS asks for permission to access files and, on newer versions, to enable the file provider extension. Allow both in System Settings, Privacy and Security.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-015: How many personal access tokens can one user have at the same time?

Category: `near_miss`. Split: `dev`.

Passage 1 (`api-authentication`):

> The Acme Cloud REST API accepts personal access tokens and OAuth 2.0 access tokens. Send the token in the Authorization header: Authorization: Bearer YOUR_TOKEN.
>
> Personal access tokens. Create one under Profile, Developer, New token. Choose a name and the scopes it needs. The token is displayed once; store it securely. Tokens can be given an expiry of 7, 30 or 90 days, or no expiry on Business and Enterprise plans.
>
> Scopes. files:read lets the token list and download files. files:write adds upload and delete. projects:read and projects:write cover projects and tasks. admin:members is restricted to owners and lets the token invite and remove members. Give a token the smallest set of scopes that works.
>
> OAuth. Register an application under Developer, Applications to get a client ID and secret. Use the authorization code flow with PKCE for browser and mobile apps. Access tokens last one hour; refresh tokens last 60 days.

Passage 2 (`api-rate-limits`):

> To keep the service fast for everyone, the Acme Cloud API limits how many requests a token can make. Limits apply per token, not per IP address.
>
> | Plan | Requests per minute | Burst | Daily limit |
> |---|---|---|---|
> | Free | 60 | 10 | 5,000 |
> | Team | 300 | 50 | 50,000 |
> | Business | 1,200 | 200 | 500,000 |
> | Enterprise | custom | custom | custom |
>
> When you exceed a limit the API answers with HTTP 429 Too Many Requests. The response includes a Retry-After header with the number of seconds to wait. Every response carries X-RateLimit-Limit, X-RateLimit-Remaining and X-RateLimit-Reset headers so a client can slow down before it is blocked.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-016: Does the Acme Cloud API offer a GraphQL endpoint?

Category: `near_miss`. Split: `test`.

Passage 1 (`changelog-v2-4`):

> Version 2.4.0 (June)
> New: the Acme AI assistant can summarise long discussions and answer questions about the files you can open. It is off by default; owners switch it on in Settings, Features. New: audit log streaming for Enterprise workspaces. New: guest accounts, which can be invited to a single project without counting towards your plan's member limit. Improved: the API now supports cursor-based pagination on every list endpoint, and the page size can be up to 200. Improved: faster sign-in for members using single sign-on.
>
> Changed: the minimum password length is raised from 10 to 12 characters. Existing passwords keep working until they are next changed.
>
> Deprecated: API tokens without an expiry will stop being created on Free and Team plans in version 2.5. Existing tokens continue to work. The old v1 file listing endpoint will be removed in December; use the v2 listing instead.

Passage 2 (`api-error-reference`):

> Every error response from the Acme Cloud API has a JSON body with a code, a human readable message and a request ID. Quote the request ID when you contact support.
>
> | Status | Meaning | What to do |
> |---|---|---|
> | 400 | The request body is not valid | Check required fields and types |
> | 401 | Missing, invalid or expired token | Send a valid token; see ACME-AUTH-0042 |
> | 403 | Token lacks the required scope | Add the scope or use another token |
> | 404 | The file, project or member does not exist | Check the ID and the workspace |
> | 409 | Conflict, for example a file edited by someone else | Fetch the latest version and merge |
> | 413 | Payload larger than 5 GB | Use multipart upload |
> | 429 | Rate limit exceeded | Wait for Retry-After; see the rate limit guide |
> | 500 | Unexpected error on our side | Retry later and report the request ID |
> | 503 | Service temporarily unavailable, usually during maintenance | Retry with backoff |

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-017: Can I receive invoices in euros instead of US dollars?

Category: `near_miss`. Split: `dev`.

Passage 1 (`billing-faq`):

> Q: When am I charged?
> A: Annual plans are charged on the day you subscribe and every twelve months after. Monthly plans are charged on the same calendar day each month. If that day does not exist in a month, we charge on its last day.
>
> Q: How do I change my payment method?
> A: Open Settings, Billing, Payment methods and add a new card. Mark it as default and remove the old one. Only workspace owners and billing contacts can do this.
>
> Q: Where can I find my invoices?
> A: Invoices are listed under Billing, Invoice history. Each one is a PDF with your company name, address and tax number. To change those details, edit Billing contacts first; invoices already issued cannot be altered, but we can issue a corrected copy on request.

Passage 2 (`refunds-and-cancellations`):

> You can cancel your subscription at any time from Settings, Billing, Cancel plan. Cancellation takes effect at the end of the period you have already paid for, and you keep full access until then.
>
> Money-back guarantee. The first purchase of any paid plan is covered by a 30-day money-back guarantee. Ask for a refund within 30 days of the charge and we return the full amount to the original payment method. Refunds take five to ten business days to appear, depending on your bank.
>
> After 30 days. Payments are not refundable after the guarantee period, with two exceptions: duplicate charges, and charges made after you cancelled because of an error on our side. In both cases we refund the affected amount in full.
>
> Downgrading. If you move to a cheaper plan in the middle of a period, we credit the unused portion to your next invoice instead of paying it out.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-018: How do I turn on end-to-end encryption for a single folder?

Category: `near_miss`. Split: `test`.

Passage 1 (`security-overview`):

> Security at Acme Cloud rests on a few simple principles: encrypt everything, give people the least access they need, and keep a record of what happened.
>
> Encryption. Data is encrypted in transit with TLS 1.2 or newer and at rest with AES-256. Encryption keys are stored in a dedicated key management service and rotated every year. Enterprise customers can bring their own key.
>
> Infrastructure. Workspaces are hosted in the region you pick at sign-up: United States, European Union or Asia-Pacific. Data stays in that region, including backups. Backups are taken every hour and kept for 35 days.
>
> Access control. Staff cannot open customer files. Support engineers can see metadata such as file names only after the owner approves a time-limited support access request in Settings, Security.
>
> Authentication. We support two-factor authentication, hardware keys and single sign-on. Passwords are stored as salted hashes.

Passage 2 (`mobile-app-offline-mode`):

> The Acme Cloud app for iOS and Android lets you work on trains, planes and anywhere the signal is weak. Files you mark as available offline are stored on your phone and updated whenever you are connected.
>
> Making files available offline. Open a file or folder, tap the three dots and choose Keep offline. A small tick shows that the item is stored. Folders can be kept offline too, and new files in them are downloaded automatically over Wi-Fi.
>
> Storage control. Open Profile, Offline storage to see how much space is used. You can set a limit between 1 and 50 GB and choose whether downloads are allowed on mobile data. When the limit is reached, the files you opened least recently are removed from the phone first, while your pinned items are always kept.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-019: What is the longest file name Acme Cloud accepts?

Category: `near_miss`. Split: `dev`.

Passage 1 (`desktop-client-install`):

> The desktop client is available for Windows 10 and 11, macOS 12 and newer, and Linux (Debian, Ubuntu and Fedora packages).
>
> Windows. Download the installer from Settings, Devices, and run it. If your organisation restricts software installation, an administrator can deploy the MSI package silently with msiexec. After installation sign in and choose the folder to sync; the default is Acme Cloud in your user folder. If the installer stops with error 0x80070005, the account does not have permission to write to the target folder. Run the installer as an administrator or pick a folder you own, and make sure antivirus software is not blocking the installer.
>
> macOS. Open the disk image and drag Acme Cloud into Applications. The first time you start it, macOS asks for permission to access files and, on newer versions, to enable the file provider extension. Allow both in System Settings, Privacy and Security.

Passage 2 (`api-error-reference`):

> Every error response from the Acme Cloud API has a JSON body with a code, a human readable message and a request ID. Quote the request ID when you contact support.
>
> | Status | Meaning | What to do |
> |---|---|---|
> | 400 | The request body is not valid | Check required fields and types |
> | 401 | Missing, invalid or expired token | Send a valid token; see ACME-AUTH-0042 |
> | 403 | Token lacks the required scope | Add the scope or use another token |
> | 404 | The file, project or member does not exist | Check the ID and the workspace |
> | 409 | Conflict, for example a file edited by someone else | Fetch the latest version and merge |
> | 413 | Payload larger than 5 GB | Use multipart upload |
> | 429 | Rate limit exceeded | Wait for Retry-After; see the rate limit guide |
> | 500 | Unexpected error on our side | Retry later and report the request ID |
> | 503 | Service temporarily unavailable, usually during maintenance | Retry with backoff |

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-020: Can I embed a shared folder on my website with an iframe?

Category: `near_miss`. Split: `test`.

Passage 1 (`sharing-and-permissions`):

> Inheritance. A folder passes its permissions to everything inside it. A file can be given stricter rules than its folder, which then override the inherited ones.
>
> External sharing can be limited by owners to an approved list of email domains in Settings, Security. Every share creates an entry in the audit log, so you can later see who gave access and when.

Passage 2 (`sharing-and-permissions`):

> Access in Acme Cloud is controlled at three levels: the workspace, the project and the individual file or folder.
>
> Workspace roles. Owners manage billing, security and members. Admins manage projects and members but not billing. Members create and edit within projects they belong to. Guests see only what is explicitly shared with them and never appear in the member count of a plan.
>
> Project roles. Each project has Editors, Commenters and Viewers. Editors can change and delete files. Commenters can add comments and tasks. Viewers can only read and download.
>
> Share links. Any file or folder can have a link. You choose whether anyone with the link can open it or only signed-in members, whether it can be downloaded, and when it expires. You can protect a link with a password. Links are revoked instantly when you press Remove link.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-021: Can the desktop sync client be limited to Wi-Fi networks only?

Category: `near_miss`. Split: `dev`.

Passage 1 (`sync-client-troubleshooting`):

> The desktop sync client keeps your local folders identical to Acme Cloud. If sync stalls, open the tray icon, choose Activity and look for an error name.
>
> ERR_CONN_RESET. The connection to our servers was reset in the middle of a transfer. This is usually caused by a corporate proxy, an antivirus product that inspects encrypted traffic, or an unstable wireless network. Switch to a wired connection, add sync.acmecloud.example to the proxy allow-list and retry. The client resumes partial uploads automatically.
>
> ERR_SSL_PROTOCOL_ERROR. The secure handshake failed. Check that your computer's date and time are correct, and that no security software replaces our certificate. Update the client to v2.3.1 or newer.
>
> SYNC_ERR_409. The same file was changed in two places before they could sync. The client keeps both versions: yours is renamed with the suffix conflicted copy and the cloud version is downloaded. Compare them and delete the one you do not need.

Passage 2 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-022: In which city is the Asia-Pacific data center located?

Category: `near_miss`. Split: `test`.

Passage 1 (`security-overview`):

> Security at Acme Cloud rests on a few simple principles: encrypt everything, give people the least access they need, and keep a record of what happened.
>
> Encryption. Data is encrypted in transit with TLS 1.2 or newer and at rest with AES-256. Encryption keys are stored in a dedicated key management service and rotated every year. Enterprise customers can bring their own key.
>
> Infrastructure. Workspaces are hosted in the region you pick at sign-up: United States, European Union or Asia-Pacific. Data stays in that region, including backups. Backups are taken every hour and kept for 35 days.
>
> Access control. Staff cannot open customer files. Support engineers can see metadata such as file names only after the owner approves a time-limited support access request in Settings, Security.
>
> Authentication. We support two-factor authentication, hardware keys and single sign-on. Passwords are stored as salted hashes.

Passage 2 (`mobile-app-offline-mode`):

> The Acme Cloud app for iOS and Android lets you work on trains, planes and anywhere the signal is weak. Files you mark as available offline are stored on your phone and updated whenever you are connected.
>
> Making files available offline. Open a file or folder, tap the three dots and choose Keep offline. A small tick shows that the item is stored. Folders can be kept offline too, and new files in them are downloaded automatically over Wi-Fi.
>
> Storage control. Open Profile, Offline storage to see how much space is used. You can set a limit between 1 and 50 GB and choose whether downloads are allowed on mobile data. When the limit is reached, the files you opened least recently are removed from the phone first, while your pinned items are always kept.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-023: How do I export the audit log to Splunk?

Category: `near_miss`. Split: `dev`.

Passage 1 (`audit-logs`):

> Searching. Open Settings, Security, Audit log. Filter by actor, action or date, and search for a file name. Large investigations can use the export button, which produces a CSV file.
>
> Streaming. Enterprise customers can send the log to their own systems in real time. Choose a destination under Audit log, Streaming, and Acme Cloud will post signed JSON batches every 30 seconds.
>
> Alerts can be configured for sensitive actions such as a new owner being added.

Passage 2 (`data-export`):

> You own your data and can take a complete copy at any time. There are three ways to export.
>
> Workspace export. Owners open Settings, Data, Export workspace. Choose what to include: files, version history, comments, tasks and member list. We prepare an archive and send a download link to the owner's email. Exports of up to 100 GB are ready within 24 hours; larger ones can take up to three days. The link is valid for seven days.
>
> Project export. Project editors can export a single project from the project menu. Tasks are delivered as CSV and JSON, comments as JSON, and files in their folder structure.
>
> Personal data request. Any member can ask for the personal data we hold about them from Profile, Privacy, Request my data. We respond within 30 days, in line with data protection law. Members can also ask for their personal data to be deleted; owners are told if that would affect shared work.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-024: Can I lock a single file so nobody else can edit it while I work on it?

Category: `near_miss`. Split: `test`.

Passage 1 (`mobile-app-offline-mode`):

> Editing offline. You can read files, add comments and tick off tasks without a connection. Changes are queued and sent when the phone is back online. If someone else changed the same task in the meantime, the most recent change wins and you receive a notification. Documents edited offline create a new version rather than overwriting the old one.
>
> Security. Offline files are encrypted on the device and are removed if you sign out or if an administrator wipes the device remotely from Settings, Devices.
>
> Camera upload can be switched on to back up photos automatically.

Passage 2 (`mobile-app-offline-mode`):

> The Acme Cloud app for iOS and Android lets you work on trains, planes and anywhere the signal is weak. Files you mark as available offline are stored on your phone and updated whenever you are connected.
>
> Making files available offline. Open a file or folder, tap the three dots and choose Keep offline. A small tick shows that the item is stored. Folders can be kept offline too, and new files in them are downloaded automatically over Wi-Fi.
>
> Storage control. Open Profile, Offline storage to see how much space is used. You can set a limit between 1 and 50 GB and choose whether downloads are allowed on mobile data. When the limit is reached, the files you opened least recently are removed from the phone first, while your pinned items are always kept.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-025: How long should I boil an egg for a soft yolk?

Category: `off_topic`. Split: `dev`.

Passage 1 (`api-rate-limits`):

> Recommended handling
> - Read Retry-After and pause that long; do not retry immediately.
> - Use exponential backoff with jitter: wait 1, 2, 4 and 8 seconds plus a random fraction.
> - Cache responses that rarely change, such as the member list.
> - Prefer webhooks over polling for changes.
> - Batch requests with the bulk endpoints, which count as a single request.
>
> Upload and download endpoints have separate bandwidth limits and do not use the request counter. Repeated HTTP 429 responses for more than an hour may lead to the token being suspended; the owner is notified by email. To raise your limits permanently, upgrade your plan or contact sales for a custom quota.

Passage 2 (`changelog-v2-4`):

> Version 2.4.0 (June)
> New: the Acme AI assistant can summarise long discussions and answer questions about the files you can open. It is off by default; owners switch it on in Settings, Features. New: audit log streaming for Enterprise workspaces. New: guest accounts, which can be invited to a single project without counting towards your plan's member limit. Improved: the API now supports cursor-based pagination on every list endpoint, and the page size can be up to 200. Improved: faster sign-in for members using single sign-on.
>
> Changed: the minimum password length is raised from 10 to 12 characters. Existing passwords keep working until they are next changed.
>
> Deprecated: API tokens without an expiry will stop being created on Free and Team plans in version 2.5. Existing tokens continue to work. The old v1 file listing endpoint will be removed in December; use the v2 listing instead.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-026: What is the capital city of Australia?

Category: `off_topic`. Split: `test`.

Passage 1 (`getting-started`):

> Acme Cloud is a shared workspace where your team stores files, tracks tasks and talks about work in one place. This guide takes about ten minutes.

Passage 2 (`data-export`):

> Formats. Documents keep their original format. Native Acme pages are exported as HTML and Markdown. Dates use ISO 8601 and all timestamps are in UTC.
>
> Using the API. If you need regular backups, use the files:read scope and the bulk download endpoint, mindful of the rate limits.
>
> After you cancel, the export option stays available for 90 days.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-027: Who won the football World Cup in 2014?

Category: `off_topic`. Split: `dev`.

Passage 1 (`changelog-v2-4`):

> Fixed: the Linux client now starts on distributions with an older graphics library, resolving the known issue from version 2.3.0. Fixed: comments with more than 10,000 characters were cut off. Fixed: some webhooks were delivered twice after a timeout.
>
> Upgrading. Desktop clients move to v2.4.0 automatically unless updates are paused. Versions older than 2.2 are no longer supported and show a banner asking you to update.
>
> Compatibility. The API remains backwards compatible within the v2 line.

Passage 2 (`webhooks`):

> Responding. Return any 2xx status within ten seconds. Do the heavy work after replying, for example by putting the event on a queue.
>
> Retries. If your server times out or returns an error, we retry up to eight times with growing delays: one minute, five minutes, thirty minutes, then every few hours for up to 24 hours. After that the delivery is marked failed and shown in the delivery log. Because retries happen, the same event may arrive more than once; use the event ID to deduplicate.
>
> If an endpoint fails continuously for three days it is disabled and the owner is emailed.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-028: How do I knit a scarf for a beginner?

Category: `off_topic`. Split: `test`.

Passage 1 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Passage 2 (`data-export`):

> You own your data and can take a complete copy at any time. There are three ways to export.
>
> Workspace export. Owners open Settings, Data, Export workspace. Choose what to include: files, version history, comments, tasks and member list. We prepare an archive and send a download link to the owner's email. Exports of up to 100 GB are ready within 24 hours; larger ones can take up to three days. The link is valid for seven days.
>
> Project export. Project editors can export a single project from the project menu. Tasks are delivered as CSV and JSON, comments as JSON, and files in their folder structure.
>
> Personal data request. Any member can ask for the personal data we hold about them from Profile, Privacy, Request my data. We respond within 30 days, in line with data protection law. Members can also ask for their personal data to be deleted; owners are told if that would affect shared work.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-029: What are the symptoms of the common cold?

Category: `off_topic`. Split: `dev`.

Passage 1 (`billing-faq`):

> Q: Why was my card declined?
> A: The most common reasons are an expired card, a billing address that does not match the bank's records, or a bank block on international payments. We retry a failed payment after three days and again after seven. If all attempts fail the workspace moves to read-only mode, and nothing is deleted.
>
> Q: Do you accept purchase orders?
> A: Enterprise customers can pay by invoice with net-30 terms. Contact sales to set this up.
>
> Q: Is tax included in the price?
> A: No. Sales tax or VAT is added at checkout based on the billing address.

Passage 2 (`api-error-reference`):

> Every error response from the Acme Cloud API has a JSON body with a code, a human readable message and a request ID. Quote the request ID when you contact support.
>
> | Status | Meaning | What to do |
> |---|---|---|
> | 400 | The request body is not valid | Check required fields and types |
> | 401 | Missing, invalid or expired token | Send a valid token; see ACME-AUTH-0042 |
> | 403 | Token lacks the required scope | Add the scope or use another token |
> | 404 | The file, project or member does not exist | Check the ID and the workspace |
> | 409 | Conflict, for example a file edited by someone else | Fetch the latest version and merge |
> | 413 | Payload larger than 5 GB | Use multipart upload |
> | 429 | Rate limit exceeded | Wait for Retry-After; see the rate limit guide |
> | 500 | Unexpected error on our side | Retry later and report the request ID |
> | 503 | Service temporarily unavailable, usually during maintenance | Retry with backoff |

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-030: How do I convert Celsius to Fahrenheit?

Category: `off_topic`. Split: `test`.

Passage 1 (`data-export`):

> Formats. Documents keep their original format. Native Acme pages are exported as HTML and Markdown. Dates use ISO 8601 and all timestamps are in UTC.
>
> Using the API. If you need regular backups, use the files:read scope and the bulk download endpoint, mindful of the rate limits.
>
> After you cancel, the export option stays available for 90 days.

Passage 2 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-031: What is a good name for a golden retriever puppy?

Category: `off_topic`. Split: `dev`.

Passage 1 (`changelog-v2-3`):

> Version 2.3.0 (March)
> New: shared drafts let several people edit a page at once with live cursors. New: project templates can be saved and reused across the workspace. New: the search bar now finds text inside PDF and Office documents. Improved: uploads of many small files are up to three times faster. Improved: the mobile app opens large folders without freezing. Changed: the default share link expiry is now 30 days instead of never; existing links are not affected.
>
> Version 2.3.1 (April)
> Fixed: files with accents or emoji in their names failed to sync on Windows. Fixed: the sync client sometimes reported ERR_CONN_RESET after waking from sleep; it now reconnects quietly. Fixed: single sign-on users were shown E-4013 when their clock was slightly ahead; we now accept a skew of five minutes. Fixed: invoice PDFs showed the wrong tax number for some European customers. Security: updated a third-party library used for image previews.

Passage 2 (`sso-saml-setup`):

> 1. Open Settings, Security, Single sign-on and choose Set up SAML.
> 2. Copy the Acme Cloud values shown on screen: the entity ID, the assertion consumer service (ACS) URL and the certificate fingerprint. Paste them into a new application in your identity provider.
> 3. In your identity provider, map the NameID to the member's email address. Optionally map first name, last name and group claims.
> 4. Back in Acme Cloud, upload the metadata file or paste the metadata URL, then press Test connection.
> 5. When the test succeeds, enable Require SSO for all members. Members who already have passwords keep them until you switch enforcement on.
>
> Always keep one owner account that can still log in with a password. If the identity provider is misconfigured and enforcement is on, that account is the only way back in. When login fails, see the SSO error reference.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-032: How many calories are in a banana?

Category: `off_topic`. Split: `test`.

Passage 1 (`api-rate-limits`):

> To keep the service fast for everyone, the Acme Cloud API limits how many requests a token can make. Limits apply per token, not per IP address.
>
> | Plan | Requests per minute | Burst | Daily limit |
> |---|---|---|---|
> | Free | 60 | 10 | 5,000 |
> | Team | 300 | 50 | 50,000 |
> | Business | 1,200 | 200 | 500,000 |
> | Enterprise | custom | custom | custom |
>
> When you exceed a limit the API answers with HTTP 429 Too Many Requests. The response includes a Retry-After header with the number of seconds to wait. Every response carries X-RateLimit-Limit, X-RateLimit-Remaining and X-RateLimit-Reset headers so a client can slow down before it is blocked.

Passage 2 (`changelog-v2-3`):

> Version 2.3.0 (March)
> New: shared drafts let several people edit a page at once with live cursors. New: project templates can be saved and reused across the workspace. New: the search bar now finds text inside PDF and Office documents. Improved: uploads of many small files are up to three times faster. Improved: the mobile app opens large folders without freezing. Changed: the default share link expiry is now 30 days instead of never; existing links are not affected.
>
> Version 2.3.1 (April)
> Fixed: files with accents or emoji in their names failed to sync on Windows. Fixed: the sync client sometimes reported ERR_CONN_RESET after waking from sleep; it now reconnects quietly. Fixed: single sign-on users were shown E-4013 when their clock was slightly ahead; we now accept a skew of five minutes. Fixed: invoice PDFs showed the wrong tax number for some European customers. Security: updated a third-party library used for image previews.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-033: Explain how photosynthesis works in plants.

Category: `off_topic`. Split: `dev`.

Passage 1 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Passage 2 (`data-export`):

> You own your data and can take a complete copy at any time. There are three ways to export.
>
> Workspace export. Owners open Settings, Data, Export workspace. Choose what to include: files, version history, comments, tasks and member list. We prepare an archive and send a download link to the owner's email. Exports of up to 100 GB are ready within 24 hours; larger ones can take up to three days. The link is valid for seven days.
>
> Project export. Project editors can export a single project from the project menu. Tasks are delivered as CSV and JSON, comments as JSON, and files in their folder structure.
>
> Personal data request. Any member can ask for the personal data we hold about them from Profile, Privacy, Request my data. We respond within 30 days, in line with data protection law. Members can also ask for their personal data to be deleted; owners are told if that would affect shared work.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-034: What time does the sun set in Reykjavik in June?

Category: `off_topic`. Split: `test`.

Passage 1 (`webhooks`):

> Responding. Return any 2xx status within ten seconds. Do the heavy work after replying, for example by putting the event on a queue.
>
> Retries. If your server times out or returns an error, we retry up to eight times with growing delays: one minute, five minutes, thirty minutes, then every few hours for up to 24 hours. After that the delivery is marked failed and shown in the delivery log. Because retries happen, the same event may arrive more than once; use the event ID to deduplicate.
>
> If an endpoint fails continuously for three days it is disabled and the owner is emailed.

Passage 2 (`changelog-v2-3`):

> Version 2.3.0 (March)
> New: shared drafts let several people edit a page at once with live cursors. New: project templates can be saved and reused across the workspace. New: the search bar now finds text inside PDF and Office documents. Improved: uploads of many small files are up to three times faster. Improved: the mobile app opens large folders without freezing. Changed: the default share link expiry is now 30 days instead of never; existing links are not affected.
>
> Version 2.3.1 (April)
> Fixed: files with accents or emoji in their names failed to sync on Windows. Fixed: the sync client sometimes reported ERR_CONN_RESET after waking from sleep; it now reconnects quietly. Fixed: single sign-on users were shown E-4013 when their clock was slightly ahead; we now accept a skew of five minutes. Fixed: invoice PDFs showed the wrong tax number for some European customers. Security: updated a third-party library used for image previews.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-035: How do I change the oil in a 2012 Honda Civic?

Category: `off_topic`. Split: `dev`.

Passage 1 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Passage 2 (`billing-faq`):

> Q: When am I charged?
> A: Annual plans are charged on the day you subscribe and every twelve months after. Monthly plans are charged on the same calendar day each month. If that day does not exist in a month, we charge on its last day.
>
> Q: How do I change my payment method?
> A: Open Settings, Billing, Payment methods and add a new card. Mark it as default and remove the old one. Only workspace owners and billing contacts can do this.
>
> Q: Where can I find my invoices?
> A: Invoices are listed under Billing, Invoice history. Each one is a PDF with your company name, address and tax number. To change those details, edit Billing contacts first; invoices already issued cannot be altered, but we can issue a corrected copy on request.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-036: Recommend a good science fiction novel from the 1980s.

Category: `off_topic`. Split: `test`.

Passage 1 (`api-rate-limits`):

> Recommended handling
> - Read Retry-After and pause that long; do not retry immediately.
> - Use exponential backoff with jitter: wait 1, 2, 4 and 8 seconds plus a random fraction.
> - Cache responses that rarely change, such as the member list.
> - Prefer webhooks over polling for changes.
> - Batch requests with the bulk endpoints, which count as a single request.
>
> Upload and download endpoints have separate bandwidth limits and do not use the request counter. Repeated HTTP 429 responses for more than an hour may lead to the token being suspended; the owner is notified by email. To raise your limits permanently, upgrade your plan or contact sales for a custom quota.

Passage 2 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-037: What is the difference between a violin and a viola?

Category: `off_topic`. Split: `dev`.

Passage 1 (`sso-error-reference`):

> E-4012 and E-4013 look similar but have different causes. E-4012 is about trust, a certificate that was rotated or copied incorrectly. E-4013 is about time. Do not rotate certificates to fix E-4013, and do not adjust clocks to fix E-4012.
>
> If members see E-4012 right after your identity provider renewed its certificate, upload the new metadata file. Old and new certificates can be active together for up to 30 days so that logins keep working during the change.

Passage 2 (`sso-error-reference`):

> When SAML login fails, Acme Cloud shows an error code on the sign-in page. Codes beginning with E-40 relate to the assertion your identity provider sends.
>
> | Code | Meaning | Usual fix |
> |---|---|---|
> | E-4011 | The ACS URL in the response does not match the one we expect | Re-copy the ACS URL into the identity provider |
> | E-4012 | Assertion signature invalid: the signing certificate does not match the fingerprint stored for your workspace | Upload the current certificate in Settings, Security, Single sign-on |
> | E-4013 | Assertion expired or not yet valid: the clocks of the identity provider and Acme Cloud differ by more than five minutes | Synchronise the identity provider's server time (NTP), then retry |
> | E-4014 | The NameID is missing or is not an email address | Map NameID to the user's email |

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-038: How do I grow tomatoes on a balcony?

Category: `off_topic`. Split: `test`.

Passage 1 (`webhooks`):

> Responding. Return any 2xx status within ten seconds. Do the heavy work after replying, for example by putting the event on a queue.
>
> Retries. If your server times out or returns an error, we retry up to eight times with growing delays: one minute, five minutes, thirty minutes, then every few hours for up to 24 hours. After that the delivery is marked failed and shown in the delivery log. Because retries happen, the same event may arrive more than once; use the event ID to deduplicate.
>
> If an endpoint fails continuously for three days it is disabled and the owner is emailed.

Passage 2 (`getting-started`):

> 1. Create your workspace. Go to the sign-up page, enter your work email and choose a workspace name. We send a confirmation link; open it within 24 hours.
> 2. Invite teammates. Open Settings, choose Members and click Invite. You can paste up to 50 addresses at once. Invitations expire after seven days.
> 3. Create your first project. Click New project, pick a template (Team board, Client folder or Blank) and give it a name. Every project has its own folder, task list and discussion thread.
> 4. Upload files. Drag files into the project window or use the Upload button. Files up to 5 GB are supported on every plan.
> 5. Install the desktop client. The client keeps a local copy of your folders and syncs changes in the background. See the installation guide for Windows, macOS and Linux.
> 6. Turn on two-factor authentication. We recommend this for every member, and administrators can require it for the whole workspace.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-039: Translate 'good morning' into Japanese.

Category: `off_topic`. Split: `dev`.

Passage 1 (`security-overview`):

> Authentication. We support two-factor authentication, hardware keys and single sign-on. Passwords are stored as salted hashes.
>
> Compliance. Acme Cloud holds SOC 2 Type II and ISO 27001 certificates, and offers a data processing agreement for GDPR. Reports are available under NDA from the trust page.
>
> Vulnerability reports. Researchers can write to the security team; we answer within two business days and do not take legal action against good-faith reports. Penetration tests by independent firms are carried out twice a year.
>
> Incidents. If personal data is affected we notify the owner within 72 hours.

Passage 2 (`changelog-v2-3`):

> Version 2.3.0 (March)
> New: shared drafts let several people edit a page at once with live cursors. New: project templates can be saved and reused across the workspace. New: the search bar now finds text inside PDF and Office documents. Improved: uploads of many small files are up to three times faster. Improved: the mobile app opens large folders without freezing. Changed: the default share link expiry is now 30 days instead of never; existing links are not affected.
>
> Version 2.3.1 (April)
> Fixed: files with accents or emoji in their names failed to sync on Windows. Fixed: the sync client sometimes reported ERR_CONN_RESET after waking from sleep; it now reconnects quietly. Fixed: single sign-on users were shown E-4013 when their clock was slightly ahead; we now accept a skew of five minutes. Fixed: invoice PDFs showed the wrong tax number for some European customers. Security: updated a third-party library used for image previews.

Decision: [ ] keep  [ ] remove (a passage answers it)

## u-040: How do I train for a half marathon in twelve weeks?

Category: `off_topic`. Split: `test`.

Passage 1 (`mobile-app-offline-mode`):

> The Acme Cloud app for iOS and Android lets you work on trains, planes and anywhere the signal is weak. Files you mark as available offline are stored on your phone and updated whenever you are connected.
>
> Making files available offline. Open a file or folder, tap the three dots and choose Keep offline. A small tick shows that the item is stored. Folders can be kept offline too, and new files in them are downloaded automatically over Wi-Fi.
>
> Storage control. Open Profile, Offline storage to see how much space is used. You can set a limit between 1 and 50 GB and choose whether downloads are allowed on mobile data. When the limit is reached, the files you opened least recently are removed from the phone first, while your pinned items are always kept.

Passage 2 (`billing-faq`):

> Q: When am I charged?
> A: Annual plans are charged on the day you subscribe and every twelve months after. Monthly plans are charged on the same calendar day each month. If that day does not exist in a month, we charge on its last day.
>
> Q: How do I change my payment method?
> A: Open Settings, Billing, Payment methods and add a new card. Mark it as default and remove the old one. Only workspace owners and billing contacts can do this.
>
> Q: Where can I find my invoices?
> A: Invoices are listed under Billing, Invoice history. Each one is a PDF with your company name, address and tax number. To change those details, edit Billing contacts first; invoices already issued cannot be altered, but we can issue a corrected copy on request.

Decision: [ ] keep  [ ] remove (a passage answers it)
