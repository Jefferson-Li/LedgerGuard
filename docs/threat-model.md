# Threat model

This is the design the scaffold is built toward. Controls that are only declared, or only tested with a stand-in, are marked.

## Assets

- Supplier master data, including the synthetic bank details used to prove redaction.
- Invoice text, which is untrusted even when the supplier is known.
- Model responses shown to a clerk, which must not become a channel for hidden instructions or for payment details.
- Deploy credentials. The pipeline must not hold a long-lived JSON key.

## Adversaries

- A supplier, or anyone who can edit an invoice file, who hides instructions in a paragraph or a line description.
- A clerk who pastes a jailbreak or a malicious URL into the chat.
- A failed dependency. If Model Armor cannot be called, the system must not treat the document as clean.

The scaffold does not try to stop a person who already has the service-account privileges of `invoice-mcp` or the deployer.

## Controls

| Threat | Control | Status |
| --- | --- | --- |
| Direct prompt injection or jailbreak in the chat | Orchestrator `ModelArmorPlugin`, prompt template, fail closed on screening errors | Code and Terraform exist. Live verdicts are not part of the offline suite. |
| Instructions hidden in an invoice | Paragraph `sanitizeUserPrompt` inside `invoice-mcp`; whole document withheld | Offline tests use a marker stand-in. Live mode is gated. |
| Injection diluted by a long benign document | Paragraph split, plus a dilution stand-in with an 80-word limit | The stand-in is not Model Armor. ADK's in-process tool screen uses large character windows and is not a substitute. |
| Model repeats a bank account | ERP tools drop `bank`, `bsb`, `account_number`, `account_name`, `bank_account`. Response template can de-identify. Exception packets run the same redaction. | Redaction is unit-tested. De-identify depends on the response template and has not been executed here. |
| Tool result crosses the network before the orchestrator plugin runs | Screening happens in `invoice-mcp` before the body is returned | Implemented. See ADR 0003. |
| Public Cloud Run service | No `allUsers` invoker. Service-to-service ID tokens. | Terraform and client code exist. Not deployed by this scaffold. |
| Stolen CI key | Workload Identity Federation, repository attribute condition | Pool is created by Terraform, but the first apply cannot use the workflow that depends on the pool. |
| Bad revision takes all traffic | `--no-traffic` tag, smoke test, then traffic shift. Terraform ignores image, env, and traffic. | Workflow exists. Smoke checks `/health` and, for matching, the agent card. It does not call Gemini. |
| Unbounded spend | `max_instance_count` 2, min instances 0, budget resource when a billing account is set | Budget amount is a ceiling you choose, not a measurement of spend. |

## Known gaps

- Short prompts of only a few words are still sent. Model Armor's prompt-injection filter is documented to return `NO_MATCH_FOUND` for very short text. This code does not special-case that.
- The global Model Armor endpoint cannot sanitize. Clients use `modelarmor.{location}.rep.googleapis.com`.
- The clean bucket is not populated. Granting `invoice-mcp` read access does not, by itself, de-identify anything.
- The offline red-team will stay green even if a future Model Armor template is misconfigured. Turn on `RUN_LIVE_REDTEAM` after the templates exist if you want the cloud verdicts in CI.
- Log field paths for screening failures are unconfirmed. An alert that never fires is not evidence that screening works.
