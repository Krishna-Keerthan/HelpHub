# Day 4 plan

## Provisional min_retrieval_score (seed for Day 6 evaluation)

**Provisional `min_retrieval_score = 0.59`** (midpoint of the gap below).

Measured with `backend/scripts/calibrate_threshold.py` (run from `backend/`:
`uv run python scripts/calibrate_threshold.py`). Model: `BAAI/bge-small-en-v1.5`,
score = cosine similarity of the top hit (same as `/search`'s `1 - cosine distance`).
Corpus: 8 inline demo support passages (password reset, invites, billing, cancel,
2FA, CSV export, API rate limit, uploads); in-memory, no DB.

| Group (10 queries each) | min | mean | max |
|---|---|---|---|
| Relevant (paraphrased) | 0.6836 | 0.7813 | 0.8846 |
| Irrelevant | 0.3965 | 0.4657 | 0.4952 |

Gap: (0.4952, 0.6836). Lowest relevant: "How do I turn on 2FA for my account?" (0.6836).
Highest irrelevant: "What's the best way to train for a marathon?" (0.4952).

Caveats: tiny corpus and hand-written queries, so this is a seed, not a verdict.
Real tenant corpora are larger and noisier, and near-miss off-topic questions
(e.g. other-product support questions) will score higher than these. Day 6 should
re-measure with harder negatives and tune.

### Per-query top-hit scores

Relevant: 0.7820, 0.7302, 0.7778, 0.7836, 0.6836, 0.8450, 0.7770, 0.7873, 0.8846, 0.7621
Irrelevant: 0.3965, 0.4844, 0.4636, 0.4947, 0.4833, 0.4952, 0.4878, 0.4832, 0.4089, 0.4598

## Day 4 checklist
- [x] Commit 0: hygiene (PDF queue wait 503 + Retry-After; worker import isolation; chunks-list tenant bind; no planner flags in app/)
- [x] Commit 1: schema (0006) + providers (one existing assertion changed: SecretStr count 3 -> 4, approved)
- [x] Commit 2: prompt + orchestration
- [x] Commit 3: API (POST /chat/stream, conversations)

## Chat design notes
- `POST /chat/stream` uses native `fastapi.sse` (`EventSourceResponse`, `ServerSentEvent`); POST works. Events: `sources` (first, with `conversation_id`), `token`, then `done` (`status`, `cited`) or `error` (generic `code`: `internal_error`, `llm_unavailable`, `llm_timeout`, `llm_rate_limited`, `llm_bad_request`, `llm_model_unavailable`, `llm_empty_response`).
- Conversation ownership is checked in a dependency (`get_chat_context`) before the stream starts, so an unknown or foreign `conversation_id` is a real HTTP 404.
- How tests read the stream: streams are finite, so `client.post` returns the whole body and `tests/chat/test_chat_api.py` parses the SSE text. httpx's ASGITransport may buffer, so disconnect behaviour is tested on the orchestrator generator directly: cancel the consuming task and `aclose()` after N tokens (`tests/chat/test_chat_service.py`); both leave an `interrupted` row with the partial text.
- Output-token parameter: the installed groq 1.7.0 `chat.completions.create` has both `max_completion_tokens` and `max_tokens` (documented as deprecated); we send `max_completion_tokens`.
- `scripts/smoke_groq.py` is a manual real-Groq check, not part of pytest.

## Mutation results (chat)
Killed: 1 gate removed; 2 escaping skipped; 3a transaction held in service (pool counter + pg_stat_activity, service and HTTP); 4 user_id filter dropped (RLS alone does not catch it; user-level tests do); 5 unvalidated [n]; 6 save before stream completes; 7 provider text in error event; 8 tokens before sources; 9 ownership check moved into the generator.
3b: adding the `TenantSession` alias to the route is a no-op (it is `scope="function"`, closed before the stream starts), so it survives by design. Redefined as the request-scoped `Depends(get_tenant_session)`, which is killed by the HTTP-level test. `tests/chat/test_chat_route_guard.py` additionally bans session dependencies in `app/api/chat.py` statically.

## 4c: live-model fix, reasoning safety, repository ownership
- Groq retired llama-3.3-70b-versatile / llama-3.1-8b-instant. Default `groq_model` is `openai/gpt-oss-20b` (checked against GET /models by `scripts/smoke_groq.py`, which fails clearly if the configured model is absent). `openai/gpt-oss-120b` is also served.
- Real gpt-oss chunks (smoke, `include_reasoning` omitted): delta fields `channel`, `content`, `reasoning`, `role`; most chunks were reasoning. With `include_reasoning=False`: `content`, `role` only. Reasoning tokens still count against `max_completion_tokens` (usage: reasoning_tokens 5-7 of ~17 at effort "low" for a greeting).
- Sent to gpt-oss models only: `reasoning_effort=<llm_reasoning_effort, "low">`, `include_reasoning=False` (mutually exclusive with `reasoning_format`, which is never sent), `max_completion_tokens = max_answer_tokens + llm_reasoning_token_headroom (800 + 512)`. Only `delta.content` is ever read. A stream with zero content tokens raises `LLMEmptyResponseError` (`llm_empty_response`); HTTP 404 raises `LLMModelUnavailableError` (an `LLMBadRequestError`, `llm_model_unavailable`) and logs the model id only.
- Repositories enforce ownership: `recent_history`, `list_for_conversation` join conversations on `user_id`; `touch` filters on `user_id` and returns rows affected; `add` raises `ConversationNotOwned`.
- Mutations killed: reasoning forwarded; empty stream accepted; reasoning params sent to every model; `groq_api_key` as plain str; lifespan not closing the client; user filter dropped in recent_history / list_for_conversation / touch; ownership check dropped in add.
- 3b re-run exactly (function-scoped `TenantSession` added to the chat route): the held-connection test still passes (pool checked out 0, pg_stat_activity shows only `idle`, never `idle in transaction`, at every token) because the dependency is closed before streaming; only `test_chat_route_guard` kills it. The request-scoped `Depends(get_tenant_session)` variant is killed by both tests (observed `(1, 1)` instead of `(0, 0)`).
