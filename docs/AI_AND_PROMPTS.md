# AI gateway

`providers/ai.py` implements a configurable HTTPS OpenAI-compatible Chat Completions gateway with strict structured output (`text`, `citations`, `unverified_claims`), versioned source-grounding instructions, model selection, timeouts, bounded input/completion and safe provider errors. Unknown citation IDs are rejected. External content is data, never executable instructions. Results remain `unverified_suggestion`; no generated output triggers a send or publication.

`POST …/ai/generate` enqueues a durable request. Optional contact evidence is explicitly labelled as a user entry, not independently verified. Supported purposes include caption, research summary, qualification, outreach and reply drafting. The Recherche & KI UI can create text jobs and inspect their results; `/social/captions/generate` remains the separately labelled deterministic offline template workflow.

Real generation requires LLM_API_KEY, LLM_MODEL and explicit current input/output USD-per-million prices. Worst-case input/completion cost is reserved transactionally against a workspace budget in USD cents; usage events settle reservations once. Failed settled AI jobs cannot be retried using a released reservation. Unknown paid-call outcomes charge the conservative reservation and require manual review. Costs are estimates from configured prices, not provider invoices. Monthly rollover waits for outstanding reservations to settle.

No live model was invoked during verification. Transport-mocked tests validate schemas, unsupported claims/citation rejection, missing credentials, pricing, malformed responses and ambiguous timeouts. Real image generation and model-quality evaluations remain outstanding. See .env.example and STATUS.md.
