# ADR 0007: LLM adapter implementation choices

- Status: accepted

## Decision
- `AnthropicAdapter` uses the official `anthropic` Python SDK (`AsyncAnthropic`, beta messages
  namespace), with SDK retries disabled.
- `OpenAIAdapter`, `GeminiAdapter` (Generative Language API, `generateContent`) and
  `OllamaAdapter` call the providers' HTTP APIs directly with `httpx`. Gemini's
  `thoughtSignature` parts are kept in `provider_state` and replayed so tool loops keep working.
- LiteLLM is not used. No vendor type escapes an adapter: orchestration only sees
  `app.llm.types`.

## Reason
The Anthropic API has model-specific behaviour that the SDK tracks (structured outputs
under `output_config`, signed thinking blocks that must be replayed verbatim, the
`block_binding` control for histories we rewrite, server-side fallbacks, forced tool choice
rejected on current models). Using the SDK keeps those request shapes correct and gives typed
exceptions that map one-to-one onto our error taxonomy.

The OpenAI adapter speaks the Chat Completions wire format so any OpenAI-compatible server
(vLLM, LM Studio, Groq, Together) works through `base_url`; it is ~150 lines and fully
testable with `httpx.MockTransport`. Ollama has no official async SDK of comparable scope.

Retries are owned by the execution engine (typed, budgeted), so SDK retries are off.

## Trade-off
Two styles of adapter. New provider features still need adapter changes. LiteLLM can be
wrapped as another adapter class without changing anything past the adapter boundary.
