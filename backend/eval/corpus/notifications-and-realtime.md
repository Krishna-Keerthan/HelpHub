# Notifications and real-time updates

Acme Cloud keeps your screen up to date without refreshing the page. Updates such as new comments, finished uploads and presence indicators arrive over a persistent WebSocket connection to our servers.

If the connection drops, the web app shows a yellow banner saying Reconnecting and tries again with increasing delays. In the browser developer tools you may see close code 1006, which means the connection ended abnormally without a proper closing message. The most frequent causes are a proxy or firewall that removes idle WebSocket connections after 60 seconds, a VPN that changes network routes, or a laptop that went to sleep. Ask your network team to allow wss://rt.acmecloud.example on port 443 and to keep connections open for at least five minutes. If WebSockets are blocked completely, the app falls back to polling every 20 seconds; everything still works, only with a small delay.

Notification channels. You can receive notifications in the app, by email, on your phone as push messages or in a chat tool through the Slack and Teams integrations. Open Profile, Notifications to choose, per project, which events you want: mentions, replies, assigned tasks, file changes or a daily digest.

Quiet hours pause push notifications between times you choose. Mentions marked urgent can break through if you allow it.
