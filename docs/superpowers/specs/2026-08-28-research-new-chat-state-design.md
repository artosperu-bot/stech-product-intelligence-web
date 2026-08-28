# STECH Research New-Chat + Explicit-State Design

## Goal

Make each ChatGPT research turn deterministic and isolated while preserving the existing legacy research engines and their JSON contracts.

## Approved architecture

Each workflow (`characteristics`, `prices`, `images`, `videos`) keeps its existing legacy runner. The remote ChatGPT facade enriches each outgoing prompt with compact research guidance and an explicit `research_state` built from prior responses inside the same workflow session. Each remote task is executed in a fresh ChatGPT conversation by the Windows worker.

For prices, the existing three calls become:

1. Pass 1: exact identity + broad Peru commercial recall.
2. Pass 2: expansion from prior discoveries (aliases, sellers, marketplaces, codes/domains visible in prior result).
3. Pass 3: long-tail recovery, `site:.pe`/`site:.com.pe`, unresolved offers and missing commercial coverage.

The official manufacturer page is useful for identity, but does not count as sufficient commercial price coverage unless it actually sells the exact product in Peru with a public price.

## State model

State is owned by the Render-side `RemoteChatGPTBrowserSession`, not by ChatGPT conversation history. After each successful response, the facade retains a bounded representation of that response and appends it to the next prompt as `STECH_RESEARCH_STATE`. This allows a later pass to be claimed by another worker without losing context.

The state must never change the legacy JSON output contract. Guidance explicitly instructs ChatGPT to keep the exact original schema requested by the base prompt.

## Browser isolation

Before every worker-side `session.ask()`:

1. recover a live `chatgpt.com` page or create one;
2. navigate to `https://chatgpt.com/` to start from a clean conversation;
3. execute the prompt;
4. if the ask fails or times out, retry exactly once after opening a fresh chat again;
5. if retry fails, return the error through the existing worker failure endpoint.

No CDP port is exposed publicly. The worker continues to connect only to local Chrome on `127.0.0.1:9222` and makes outbound authenticated requests to Render.

## Prompt enrichment rules

### Prices

- Pass 1: resolve exact identity; seek commercial offers in Peru; do not stop at the official page.
- Pass 2: use prior state to expand aliases, sellers, marketplaces, alternate codes and domains; seek new offers only where appropriate.
- Pass 3: recover gaps; explore Peru long-tail, `site:.pe` and `site:.com.pe`, unresolved/weak URLs and missing prices; preserve strong earlier evidence.
- Never loosen product identity merely to increase result count.
- Never overwrite stronger verified evidence with weaker evidence.

### Characteristics

- Resolve exact product identity first.
- Prefer official/manual/support/regulatory evidence.
- Never infer missing specifications.
- Later turns focus on missing/rejected fields using prior state.

### Images

- Exact variant first.
- Prefer official/manufacturer/CDN/support sources.
- Seek angle/content diversity; reject placeholders and wrong variants.

### Videos

- Exact product identity first.
- Prefer official product/tutorial/campaign content, then authorized/retailer/review sources.
- Reject family-only or wrong-generation matches.

## Reliability

- Existing worker page-recovery remains in place.
- A transient Render `502`/timeout remains handled by the worker claim loop.
- ChatGPT execution errors get one fresh-chat retry.
- Prior successful research state remains available even when a subsequent browser attempt fails.

## Non-goals

- Do not replace ChatGPT web with OpenAI API or a search API.
- Do not redesign legacy validators/parsers/exporters.
- Do not change price verifier semantics.
- Do not weaken identity or evidence gates.
