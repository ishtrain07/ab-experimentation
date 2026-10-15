# Market Excuse Auditor

An SME buying desk forwards a supplier quote and the last invoice. The app checks whether the supplier’s stated reason accounts for the price increase, then writes the reply.

This is a Best Apps and Agents project for the NVIDIA x Nebius hackathon. It uses NVIDIA Nemotron on Nebius Token Factory when an API key is present. Without a key, the same screen runs on the checked-in sample and the calculation, so the demo still works.

## What it answers

The supplier says the material is up 14% because of imports and freight. The sample series explain 8.3%. The unexplained gap is 5.7%. The reply offers the last price plus only the explained move.

The series in `samples/series.json` is a demonstration file with its source printed on screen. It is not a live mill price. Replace it with a series the business already trusts before using the result in a real negotiation.

## Run

```bash
cd auditor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src uvicorn excuse_auditor.api:app --reload
```

Open http://127.0.0.1:8000. The sample invoice and quote load on their own. Use the other buttons for a mismatched size and for WhatsApp wording.

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

## Layout

- `samples/` holds the invoice, the quote, the mismatched quote, the WhatsApp wording, and the demonstration series.
- `src/excuse_auditor/audit.py` computes the quote move, the explained move, and the gap.
- `src/excuse_auditor/note.py` writes the reply from those figures.
- `static/index.html` is the one screen.

## License

MIT. See `LICENSE`.
