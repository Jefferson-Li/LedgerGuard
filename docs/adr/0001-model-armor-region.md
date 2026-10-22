# ADR 0001: Model Armor region

## Status

Accepted for this scaffold.

## Context

Cloud Run, buckets, and Firestore in this stack use one region variable, default `us-central1`. Model Armor templates are regional, and `sanitizeUserPrompt` does not work on the global endpoint. The client builds `modelarmor.{location}.rep.googleapis.com` from the template resource name.

Australian data-residency options are limited. Sydney (`australia-southeast1`) is not a supported Model Armor region. Melbourne (`australia-southeast2`) supports prompt injection, responsible AI, and Sensitive Data Protection. With the data-residency control enabled it does not offer the malicious-URL filter. The product matrix changes; check the current Model Armor regional availability page before treating this as permanent.

Gemini on Vertex AI in this project uses location `global`, which is separate from the Model Armor region.

## Decision

Default the whole stack, including Model Armor templates, to `us-central1`, and enable the malicious-URI filter on both templates. Document Melbourne as the region to revisit if the deployment must keep invoice text in Australia and can drop that filter.

## Consequences

- Synthetic data is not real customer data, so the default does not move a production corpus.
- A later move to Melbourne requires new templates. Template names are region-scoped. Services must be updated to the new resource names.
- Do not point the Model Armor client at the global endpoint.
