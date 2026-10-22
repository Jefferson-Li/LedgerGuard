# ADR 0003: Screen invoice paragraphs in invoice-mcp

## Status

Accepted. Checked against ADK 2.12.0.

## Context

An invoice is untrusted text that reaches the model as a tool result, not as the clerk's prompt. The Model Armor codelab showed that screening a whole document at once can dilute a short injection so the filter does not match, while the same paragraph screened alone matches at high confidence.

Older ADK notes said `ModelArmorPlugin` skipped tool results. In ADK 2.12 the plugin's `after_tool_callback` does screen tool output when `tool_output_template_name` is set. It sends character windows of 65,536 with a 4,096-character overlap to `sanitizeUserPrompt`. It does not split paragraphs.

Two gaps remain:

1. The plugin runs in the agent process. `ap-orchestrator` and `matching-agent` are different Cloud Run services. `to_a2a` does not forward the orchestrator's plugin into the matching process. Tool results from `invoice-mcp` are already on the wire before the matching agent, let alone the orchestrator, can screen them.
2. A character window large enough to hold a normal invoice will reintroduce the dilution the codelab demonstrated.

## Decision

- Screen each blank-line-separated paragraph inside `invoice-mcp` before `get_invoice` returns. Any match or any screening failure withholds the whole document. The body is not included in the quarantine payload. Logs store a 12-character SHA-256 prefix, not the paragraph.
- When a template is set, also attach `ModelArmorPlugin` on the matching agent's runner with `tool_output_template_name`. That is a second layer for anything else the tools return. It is not the control that stops `INV-1010`.
- Keep a whole-document function only for the dilution stand-in in tests. The request path does not use it.
- Fail closed when no template is configured. `MODEL_ARMOR_ALLOW_UNSCREENED` is local only.

## Consequences

- Offline tests can prove the withhold behaviour with a marker stand-in. They do not prove a live Model Armor score.
- Very short paragraphs are still sent. The filter may return `NO_MATCH_FOUND` for them. That is a product limit.
- Screening cost scales with paragraph count, not with one call per invoice.
