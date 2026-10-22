# ADR 0004: AI judges exceptions, code computes the money

## Status

Accepted. This is a learning design, not a claim that the two models agree on a measured set.

## Context

Accounts-payable exceptions need a judgement ("hold this quantity difference, reject this ABN") and they also need arithmetic (GST, unit-price variance, tolerance). Mixing those in one prompt lets a model invent a number, or lets a paragraph in the invoice talk the model into approving itself.

The GDG DevFest Brisbane 2026 talk *Algorithmic Triage* (reference repository [algorithmic-triage](https://github.com/geekaara/algorithmic-triage), MIT) separates the two jobs: **AI for judgement, code for arithmetic.** A written policy is the only source of citable rules. Each line gets a stable label. The model must cite a label that exists. Plain code then does the maths, and a human sees a plan before anything is written down.

That repository's faster "combined" mode sends the classification to a TypeSafe decision model (Jev) through Vercel AI Gateway, and uses Gemini when the decision model is unsure. LedgerGuard already runs on Google Cloud: Vertex AI Gemini, Model Armor, and Cloud Run. Adding Vercel and a second vendor would be a new trust boundary for invoice text, and it would not reuse the screening path this repo already has.

## Decision

- Keep a trusted, versioned policy at `policy/ap-policy.md`. `parse_policy` (the same shape as the reference `ParsePolicy`) labels each bullet `auto-approve-N`, `hold-N`, `reject-N`, `always-escalate-N`, or `rule-N`. Invoice text is untrusted and is not part of the policy.
- Judge only inside `matching-agent`. Do not add a service. Only invoices the deterministic three-way match marks as exceptions are sent to a model. Matched invoices are approved by code, citing an auto-approve label, with no model call.
- The model's structured output orders `reason` and `rule` before `verdict` (`APPROVE`, `HOLD`, `REJECT`, `ESCALATE`) and `confidence`. Code computes every amount, GST figure, variance, and tolerance, and passes those facts in. Amounts in the model payload are ignored.
- A cited label that is not in the policy is treated as confidence 0 and escalated. Gemini Flash answers first. Gemini Pro answers when Flash is below `LEDGERGUARD_TRIAGE_CONFIDENCE_THRESHOLD` (default `0.8`) or when the citation is unknown. A valid Pro citation stands. An unknown Pro citation becomes `ESCALATE`.
- Hard rules in code win over both models. A Model Armor match, a screening failure, a bank-detail change, or bank details found in free text (`always-escalate-4`) is `ESCALATE`, and that case is not sent to a model. Screening is the existing `invoice-mcp` paragraph path and fails closed. The free-text flag is a boolean. The account number is masked before a model can read the released invoice text.
- `plan` writes JSON and a table and changes nothing. `apply` records the plan in a local JSON store. A Firestore collection is previewed unless `--firestore-apply` is set. `reset` previews unless `-yes` is passed. Decisions are cached by a hash of the computed facts and the policy text.
- The default judge is an offline stub, in the same spirit as the Model Armor marker stand-in, so tests and CI need no credentials.

Flash-to-Pro replaces the reference combined mode because both tiers stay on Vertex AI, the policy file stays the trusted input, and citation checks stay in this repository's code. The decision model in the reference can only pick a label that was offered. A general Gemini model can invent one, so the check cannot be left to the prompt.

## Consequences

- Offline tests prove the parser, the citation check, the hard rules, the threshold hand-off, cache invalidation, and plan/apply/reset. They do not measure live agreement between Flash and Pro.
- `INV-1010` is escalated by the Model Armor hard rule under the marker stand-in. That is not a live Model Armor score.
- Editing the policy changes the cache key, so the next `plan` re-judges. Editing a prompt without editing the policy does not.
- Firestore remains optional and dry-run by default. The running MCP servers do not read triage decisions.
