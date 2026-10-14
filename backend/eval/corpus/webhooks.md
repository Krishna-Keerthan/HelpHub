# Webhooks

Webhooks let Acme Cloud call your server when something happens, so you do not have to poll the API. Create one under Developer, Webhooks, New webhook. Enter the URL, choose the events and copy the signing secret.

Events include file.created, file.updated, file.deleted, comment.created, task.completed and member.added. Each delivery is an HTTPS POST with a JSON body containing the event ID, the type, the time and the object.

Verifying signatures. Every request has an X-Acme-Signature header, an HMAC-SHA256 of the raw body computed with your signing secret. Compare it in constant time and reject requests that do not match. Also check the X-Acme-Timestamp header and ignore deliveries older than five minutes to prevent replays.

Responding. Return any 2xx status within ten seconds. Do the heavy work after replying, for example by putting the event on a queue.

Retries. If your server times out or returns an error, we retry up to eight times with growing delays: one minute, five minutes, thirty minutes, then every few hours for up to 24 hours. After that the delivery is marked failed and shown in the delivery log. Because retries happen, the same event may arrive more than once; use the event ID to deduplicate.

If an endpoint fails continuously for three days it is disabled and the owner is emailed.
