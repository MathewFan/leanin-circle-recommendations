# AI collaboration disclosure

This submission was built with Codex. The AI inspected the supplied data, proposed the ranking rules and schema, wrote the API and documentation, and ran the automated checks. No external AI service is used at runtime, and no synthetic profile or message data was sent to an embedding or language-model API by the application.

The work used an inspect → implement → test → revise workflow. Inspection identified the generator's fixed September 2026 anchor and the distinction between authoritative member counts and sampled memberships. Initial testing found that a chat-only test fixture could be displaced by the diversity rule; that test was isolated to check eligibility and explanation wording independently of ranking. Local HTTP tests were then run successfully after local network permission was granted.

The ranking weights, inactivity threshold, and two-per-topic cap are design choices to review and defend, not conclusions learned from user outcomes. The tests establish implementation behavior on this dataset; they do not validate recommendation quality in the real community.

Before submitting, the candidate should review the code and be able to explain the relevance/activity tradeoff, snapshot semantics, membership fallback, diversity limitations, missing geography, and production access controls. This file documents AI involvement and does not claim a human review has already occurred.
