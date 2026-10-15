# Market Excuse Auditor

An SME buying desk forwards a supplier quote and the last invoice. The app checks whether the supplier’s stated reason accounts for the price increase, then writes the reply.

This is a Best Apps and Agents project for the NVIDIA x Nebius hackathon. It uses NVIDIA Nemotron on Nebius Token Factory when an API key is present. Without a key, the same screen runs on the checked-in sample and the calculation, so the demo still works.

## What it answers

The supplier says the material is up 14% because of imports and freight. The sample series explain 8.3%. The unexplained gap is 5.7%. The reply offers the last price plus only the explained move.

## Material scope

- **Shipped demo series:** steel (CR sheet sample index) plus optional freight and FX add-ons. Not a live mill feed.
- **Calculation core:** material-agnostic. Any commodity works when the series JSON declares that material and the invoice/quote share grade, size, unit, and currency.
- **API honesty:** `/api/audits` returns `trust` (confidence, limitations, `material_scope`, `series_demo`, `live_feed`). `/api/health` and `/api/samples` echo the loaded scope so the UI does not imply broad live coverage.

Replace `samples/series.json` with a series the business already trusts before using the result in a real negotiation.

## Run

```bash
cd auditor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src uvicorn excuse_auditor.api:app --reload
```

Open http://127.0.0.1:8000. The sample invoice and quote load on their own. Use the other buttons for a mismatched size and for WhatsApp wording.

The public co-founder demo is meant to run **without** `NEBIUS_API_KEY` (`local-calculation` mode). Bundled series are synthetic/demo-only; the UI labels that clearly.

## How to use (on-page)

1. Load a sample or paste the last invoice.
2. Add today’s quote or WhatsApp-style message.
3. Press **Check the explanation**, then copy the reply.

## Tests

```bash
cd auditor
PYTHONPATH=src pytest
```

## Nemotron on Token Factory

Set these when you want the models to read a messy document and answer a follow-up:

```bash
export NEBIUS_API_KEY=your-key
export TOKEN_FACTORY_BASE_URL=https://api.tokenfactory.us-central1.nebius.com/v1/
```

- `nvidia/nemotron-3-nano-30b-a3b` extracts the supplier, date, grade, size, quantity, unit, price, currency, and stated reason.
- `nvidia/nemotron-3-super-120b-a12b` answers the optional follow-up from the calculated note. The prompt tells it not to invent a percentage.
- The percentages on the page come from `excuse_auditor.audit`, not from the model.
- Confirm the model ids in the Token Factory console. They change, and the README should match the ids that actually ran.

The health endpoint reports `local-calculation` or `token-factory`.

## Public demo hardening (practical, not production claims)

Focused protections for a temporary public tunnel:

- Request field limits and null-byte rejection on `/api/audits`
- Body size guard via `Content-Length` (413 when oversized)
- Simple per-IP rate limit on `/api/*` (burst-friendly, not a WAF)
- Security headers: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, CSP `frame-ancestors 'none'`
- `Cache-Control: no-store` on API responses
- Interactive OpenAPI docs disabled unless `AUDITOR_ENABLE_DOCS=1`
- No open CORS; browser UI talks same-origin only
- No file uploads; documents are pasted text only
- UI escapes audit text before `innerHTML` insertion

This is demo hygiene, not a production security posture.

## Future: WhatsApp Cloud API integration

Not wired yet (no Meta credentials). Planned path when credentials exist:

1. **Webhook verification** — Meta `GET` challenge with `hub.verify_token` matching a secret you set; respond with `hub.challenge`.
2. **Signature verification** — On every `POST`, validate `X-Hub-Signature-256` with the app secret before reading the body; reject mismatches.
3. **Inbound handling** — Parse `messages` for text (paste invoice/quote), documents (download media, extract text), and audio (download media, transcribe, then extract). Map phone number → buying-desk session.
4. **Media retrieval** — Use Graph API media id → temporary URL → download with the system user token; never store raw tokens in the client.
5. **Processing queue / idempotency** — Deduplicate on WhatsApp `message.id`; enqueue audits so retries do not double-reply; keep work off the webhook request thread.
6. **Outbound rules** — Prefer approved templates outside the 24-hour customer-care window; free-form session replies only while the window is open; send the audit note + fair price as the reply body.
7. **Secrets** — Store verify token, app secret, and long-lived tokens in env/secret manager only; never commit them; rotate after demos.
8. **Privacy / retention** — Treat supplier quotes as commercial confidential data: minimize logging, encrypt at rest if persisted, set a short retention TTL, and delete media blobs after extraction.

Until that lands, the web UI “WhatsApp wording” sample demonstrates the same audit path with pasted chat text.

## Layout

- `samples/` holds the invoice, the quote, the mismatched quote, the WhatsApp wording, and the demonstration series.
- `src/excuse_auditor/audit.py` computes the quote move, the explained move, and the gap.
- `src/excuse_auditor/note.py` writes the reply from those figures.
- `static/index.html` is the one screen.

## License

MIT. See `LICENSE`.
