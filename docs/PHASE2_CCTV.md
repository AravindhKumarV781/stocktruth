# Phase 2: CCTV-to-billing (wow factor)

**One line:** a shelf camera sees what left the shelf; billing says what was sold; the gap becomes evidence for the investigation.

## What it adds to StockTruth
- A new evidence source for the Evidence agent: `get_cctv_findings(location, sku)`, read-only like the other tools.
- Two finding types:
  - `UNBILLED_PICK`: units taken from the shelf with no matching sale (and no put-back) within 30 minutes.
  - `MISPLACED_ITEM`: units left on the wrong shelf, so the shelf looks empty while stock exists (a cause of false stock-outs).
- A "CCTV vs billing" tab in the console, and the agents see the findings on the next investigation run.
- It never decides a cause alone and never touches people: leads, not proof; product events only.

## Flow
```
CCTV clips (Blob / Cloud Shell)
  -> OpenCV samples a frame every 2 s (in memory only)
  -> vision model deployed in Foundry (gpt-4.1-mini reads images) returns product events as JSON
  -> validation: catalogue SKUs only, known actions, sane quantities, confidence 0..1
  -> reconcile with POS: pick explained by a put-back or a sale within 30 min, else UNBILLED_PICK
  -> cctv_findings.csv -> Evidence agent tool + console tab -> root-cause agent -> approval flow (unchanged)
```

## Where each file is
| File | Role |
|---|---|
| `src/stocktruth/cctv.py` | frame sampling, vision call, event validation, reconcile, sample-event maker |
| `scripts/10_cctv_make_sample.py` | rebuild the synthetic sample events (optional) |
| `scripts/11_cctv_analyze.py` | clips to `cctv/cctv_events.csv` |
| `scripts/12_cctv_reconcile.py` | events vs billing, prints findings |
| `scripts/13_cctv_render_samples.py` | re-create the 4 sample clips and manifest (clips are already in the zip) |
| `cctv/sample_events.csv` | ready-made synthetic events, so the demo works without video |
| `cctv/manifest.example.csv` | template for your clip list |

## Making the AI-generated CCTV clips (what makes the model succeed)
- Fixed camera, high angle, 10 to 20 seconds, one aisle, good lighting.
- Make the product readable: ask for large, clear product packs with the catalogue name on them (for example "Protein Bar 12pk", "Premium Razor Cartridges 8pk"). The model matches only products in `data/products.csv`.
- Scenarios to generate (one clip each): (1) shopper takes 1 unit and walks off, (2) shopper takes a unit and puts it back, (3) shopper puts a unit on the wrong shelf.
- Ask the generator for people without clear faces (back view, wide shot). The code never records identities anyway.
- Set `start_ts` in the manifest to control the story:
  - to show a matched sale, pick a time just before a real sale: `grep ",STORE_C,SKU011," data/pos_sales.csv | head`
  - to show an unbilled pick, pick a time with no sale for that SKU within 30 minutes after.

## Honest limits
- Vision on AI-generated video is the least predictable part. Test every clip, keep the ones that work, and keep the sample events as the fallback (say so if you use them).
- Real CCTV needs a pilot: camera placement, lighting, planogram so shelf labels map to SKUs, retention and privacy approval (store policy, local law, signage), a threshold tuned on real data.
- Findings are product-level leads. Do not present them as evidence about a person.

## Cost
About 15 frames per 20-second clip, roughly 1,000 tokens per frame: cents per clip on a mini model.

## Production path
Azure AI Video Indexer or Azure AI Vision for detection at scale, Event Hubs plus Fabric Real-Time Intelligence for streaming, shelf-to-SKU mapping from the planogram, edge processing in-store with blurring, same reconcile logic and same governance.
