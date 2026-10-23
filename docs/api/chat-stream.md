# `POST /chat/stream` (Server-Sent Events)

Derived from `backend/app/api/chat.py`, `backend/app/services/chat.py`, `backend/app/services/llm.py` and `backend/app/services/prompts.py` at the commit that added this file. The machine-readable contract for every other route is `docs/api/openapi.json`; for this route it only says "event stream" with `event`/`data` strings, so the event payloads are documented here.

## Request
`Authorization: Bearer <access token>`, `Content-Type: application/json`.

```json
{ "conversation_id": "<uuid or omitted/null>", "message": "<1..2000 chars after trimming>" }
```
`message` is stripped; empty after stripping, or longer than `max_message_chars` (2000), is HTTP 422. Without `conversation_id` a new conversation is created.

## Errors before the stream starts (plain HTTP, JSON `{"detail": ...}`)
| Status | When |
|---|---|
| 401 | missing, invalid or expired token |
| 404 | `conversation_id` unknown or not the caller's (`"Conversation not found"`) |
| 422 | invalid body |
| 429 | per-user chat limit (default 10 per 60 s); header `Retry-After` in seconds |

Once the response is `200` with `Content-Type: text/event-stream`, failures arrive as an `error` event, not as an HTTP status.

## Events
Each SSE message has `event: <name>` and `data: <one JSON object>`. Field names below are exact.

| event | data | notes |
|---|---|---|
| `sources` | `{"conversation_id": str, "sources": [Source...]}` | always the first event of an answer that got past retrieval. `sources` is `[]` for a refusal. |
| `token` | `{"text": str}` | zero or more. Concatenate `text` in order. |
| `done` | `{"conversation_id": str, "status": "complete" \| "no_answer", "cited": [int...]}` | last event on success. |
| `error` | `{"conversation_id": str, "code": str}` | last event on failure; no `done` follows. |

`Source` = `{"index": int, "chunk_id": uuid str, "document_id": uuid str, "document_title": str, "chunk_index": int, "score": float}`. `index` starts at 1 and is the `n` in the model's `[n]` citations. `score` is the cosine similarity of the chunk to the question. No chunk text or character offsets are sent.

### Sequences
- **Answer:** `sources` (1+ items) -> `token`* -> `done` (`status: "complete"`). `cited` is the sorted unique list of `index` values the answer text cites as `[n]` or `[n, m]`; numbers that do not match a source are dropped. It can be `[]` even when sources were sent.
- **Refusal (nothing relevant):** when no retrieved chunk reaches `min_retrieval_score` (0.59, a provisional value, see AR-10) the LLM is not called: `sources` (`[]`) -> one `token` carrying the fixed text "I couldn't find anything in your knowledge base that answers this question." -> `done` (`status: "no_answer"`, `cited: []`). Use `status`, not the text, to detect it.
- **Failure:** `error`. It may come after some `token` events (an LLM failure mid-answer) or straight after `sources`, or alone (embedding failure: no `sources` event). The partial text is stored as a message with status `failed`.
- **Client disconnect:** nothing is sent; the server stores the partial answer with status `interrupted`.

### `error.code` values
`llm_unavailable`, `llm_timeout`, `llm_rate_limited`, `llm_bad_request`, `llm_model_unavailable`, `llm_empty_response` (the model produced no answer text), `embedding_unavailable` (the hosted embedding provider failed or its quota is exhausted), `internal_error` (anything else, including a failure to save the answer). The code is the whole message: no provider text is ever included.

## Reading the history later
`GET /conversations` and `GET /conversations/{conversation_id}/messages` return stored messages with `role`, `content`, `status` (`complete`, `no_answer`, `failed`, `interrupted`, and `complete` for user messages), `sources` (the same Source objects, as stored) and `model`.

## What the frontend might need that the code does not provide
- **Escalation / hand-off:** there is no escalation event, status or field anywhere in the code. A refusal is only `done.status == "no_answer"`.
- **Chunk text, snippets or character offsets for citations:** the stream gives title, ids, chunk index and score only. Text would need `POST /search` (which does return `content`, `char_start`, `char_end`) or a new route.
- **Conversation title in the stream:** `title` exists on `GET /conversations` (nullable) but is not sent in any event; how it is set was not checked here.
- **Stable event ids / resume:** no SSE `id` or `retry` is sent; a dropped connection cannot be resumed, and a retry creates a new user message.
- **Machine-readable per-error retry hints** (only the 429 `Retry-After` header exists, before the stream).
- **A browser-friendly request method:** the endpoint is `POST` with a bearer header, so the browser `EventSource` API cannot be used; use `fetch` with a stream reader.
- **Typed OpenAPI for the events:** the generated schema describes only the generic SSE item, not the four payloads above.
