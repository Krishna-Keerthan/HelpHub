# Troubleshooting the sync client

The desktop sync client keeps your local folders identical to Acme Cloud. If sync stalls, open the tray icon, choose Activity and look for an error name.

ERR_CONN_RESET. The connection to our servers was reset in the middle of a transfer. This is usually caused by a corporate proxy, an antivirus product that inspects encrypted traffic, or an unstable wireless network. Switch to a wired connection, add sync.acmecloud.example to the proxy allow-list and retry. The client resumes partial uploads automatically.

ERR_SSL_PROTOCOL_ERROR. The secure handshake failed. Check that your computer's date and time are correct, and that no security software replaces our certificate. Update the client to v2.3.1 or newer.

SYNC_ERR_409. The same file was changed in two places before they could sync. The client keeps both versions: yours is renamed with the suffix conflicted copy and the cloud version is downloaded. Compare them and delete the one you do not need.

Files stuck on Waiting. Large folders are scanned first, which can take several minutes. Pause and resume sync if the count does not change for 15 minutes.

Selective sync. If your disk is nearly full, open Preferences, Selective sync and untick folders you do not need offline. They stay in the cloud.

Still stuck? Export the diagnostic report from Help, Diagnostics and attach it to your support ticket.
