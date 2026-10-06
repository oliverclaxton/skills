---
name: feed-to-elevate
description: Reshape a raw product feed (CSV, XLSX, XML, JSON) into a CSV the Voyado Elevate any-feed import tools ingest with zero manual mapping. Use when the user has a feed, export or spreadsheet to load into Elevate, or the feed tool rejects or mis-groups their data.
---

# Feed to Elevate

Two tools (`vibe-any-feed-to-elevate`, `any-feed-to-voyado`) turn a feed into an Elevate 4 catalog import. Both auto-map any column named `Elevate <field>`. So the job here is **the remap**: reshape the customer's file into a **contract CSV** whose headers the tool recognises, so the upload's mapping step is a no-op. The original file is never modified.

The full column contract, grouping model and limits live in [REFERENCE.md](REFERENCE.md). Read it before step 2.

## Process

### 1. Profile the feed

Run `python3 scripts/profile_feed.py <file>` (add `--sheet NAME` for a specific Excel sheet). It prints row count, per-column fill rate, distinct counts and samples, in the tool's own flattening (XML/JSON nested keys joined with `.`, arrays with `|`).

**Done when:** you can state the grain (one row per product, per colour, or per size), and which columns hold identity, grouping, size, price, stock, images, URL, category.

### 2. Decide the shape

Settle these before writing code, in this order — each later one depends on the earlier:

1. **Group Key** — the parent that owns all colours/sizes of one style.
2. **Product Key** — one per colour (or per style if there's no colour split). Must differ from the Group Key.
3. **Variant identity** — `Elevate Size`, unique within each product (a repeated size fails import even with distinct Variant SKUs; collapse or rename, and report it). `Elevate Variant SKU` for a stable id.
4. **Every other column** — map, derive, or leave out.

Derive keys from the data, not from column names: check that a candidate parent really has several children (`groupby().nunique()`), and that a "SKU minus last segment" trick only collapses rows within one parent. If the grain is genuinely ambiguous (e.g. two plausible parent columns), ask the user one question with the counts as evidence; otherwise decide and state the choice.

**Done when:** every contract column is either sourced from a named feed column, derived by a stated rule, or deliberately omitted.

### 3. Write the transform

Write a pandas script next to the input (`<feed>-to-elevate.py`), reading everything as strings (`dtype=str`) and writing `<feed>-elevate.csv` with UTF-8 and the contract headers. Keep the script — the customer sends the same feed again.

Common reshapes and where they go are in REFERENCE.md ("Reshape recipes"): wide size columns to rows, comma-separated size lists exploded, category levels joined, prices and stock cleaned, colours to hex, multi-market rows filtered, duplicate ids resolved.

**Done when:** the script runs end to end from the original file with no manual edits.

### 4. Check

Run `python3 scripts/check_output.py <feed>-elevate.csv`. Fix every ERROR in the transform, not in the CSV, and re-run. Treat each WARN as a question about the feed: confirm it is real (e.g. genuinely no sale prices) or fix it.

Then sample three or four rows across a multi-variant product and compare against the source by eye.

**Done when:** the checker exits 0 and every WARN is explained or fixed.

### 5. Hand over

Tell the user, briefly:
- rows in → groups / products / variants out, and any rows dropped (with reason and count);
- the non-obvious decisions (which column became the Group Key, how colours were handled, any synthesised values);
- the CSV and script paths;
- what to set in the tool itself, since none of it lives in the file: Elevate API key, cluster ID, market, locale, currency.

## Judgement calls to flag, never make silently

- **Invented values.** Stock or prices the feed lacks: leave the column out or ask. The tool's own default fills random stock/prices, which is only right for demos.
- **Dropped rows.** Any row removed (inactive, no price, duplicate) is counted and reported.
- **Merged products.** Grouping rows the feed did not link (matching on title, say) is a guess; say so and give the match count.
