#!/usr/bin/env python3
"""Check a reshaped CSV against what the Elevate import tool needs.

Usage: check_output.py <elevate.csv>

Exit 0 = ready to upload. Exit 1 = errors printed (warnings never fail the run).
Mirrors the tool's key regex, price/cost rules, variant-identifier rule, and limits.
"""
import re
import sys
from collections import Counter, defaultdict

import pandas as pd

KEY_RE = re.compile(r"^[A-Za-z0-9#+./_-]{1,47}$")  # tool truncates to 47 to leave room for _p/_v1
HEX_RE = re.compile(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
NAMED_COLOURS = {"gold", "silver", "multi", "transparent"}
NUM_RE = re.compile(r"^\d+(\.\d+)?$")

REQUIRED = ["Elevate Product Key", "Elevate Title", "Elevate URL", "Elevate Stock",
            "Elevate List Price", "Elevate Selling Price"]
LIMITS = {"Elevate Category": 100, "Elevate Age": 20, "Elevate Department": 20, "Elevate Product Type": 20}


def main(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    errors, warnings = [], []
    err = lambda m, rows=None: errors.append(m + (f"  (rows {sorted(rows)[:8]}{'…' if rows and len(rows) > 8 else ''})" if rows else ""))
    warn = lambda m: warnings.append(m)
    cols = {c.lower(): c for c in df.columns}
    has = lambda name: name in df.columns
    line = lambda idx: [i + 2 for i in idx]  # spreadsheet row numbers

    for c in REQUIRED:
        if not has(c):
            err(f"missing required column '{c}'")
    if errors:
        return report(df, errors, warnings)

    # Headers that look like an Elevate column but won't be auto-detected
    known = {c.lower() for c in REQUIRED} | {"elevate group key", "elevate group id", "elevate brand", "elevate description",
             "elevate category", "elevate age", "elevate gender", "elevate department", "elevate pattern",
             "elevate product type", "elevate series", "elevate name", "elevate ontology", "elevate release date",
             "elevate colour", "elevate color", "elevate cost", "elevate size", "elevate variant url",
             "elevate variant sku", "elevate images"}
    for c in df.columns:
        if c.lower().startswith("elevate ") and c.lower() not in known:
            warn(f"'{c}' is not a recognised Elevate column name — it will not be auto-mapped")

    key = df["Elevate Product Key"].str.strip()
    grp = df["Elevate Group Key"].str.strip() if has("Elevate Group Key") else pd.Series([""] * len(df))
    if not has("Elevate Group Key") and has("Elevate Group ID"):
        grp = df["Elevate Group ID"].str.strip()

    bad = key.index[~key.str.match(KEY_RE)]
    if len(bad): err("Product Key empty or has characters outside A-Za-z0-9#+./_- or is >47 chars", line(bad))
    same = key.index[(grp != "") & (grp == key)]
    if len(same): err("Group Key equals Product Key — a group can't hold variants of itself", line(same))
    if has("Elevate Group Key") or has("Elevate Group ID"):
        blank = grp.index[grp == ""]
        if 0 < len(blank) < len(df): warn(f"{len(blank)} rows have no group key while others do — they become single-product groups")
    # a product key must live in exactly one group
    pk_groups = defaultdict(set)
    for k, g in zip(key, grp):
        pk_groups[k].add(g)
    multi = [k for k, g in pk_groups.items() if len(g) > 1]
    if multi: err(f"Product Key spans several groups: {multi[:5]}")

    for c in ("Elevate Title", "Elevate URL"):
        e = df.index[df[c].str.strip() == ""]
        if len(e): err(f"{c} empty", line(e))
    nonrel = df.index[~df["Elevate URL"].str.startswith("/") & (df["Elevate URL"].str.strip() != "")]
    if len(nonrel): err("Elevate URL must be a relative path starting with '/'", line(nonrel))

    for c in ("Elevate List Price", "Elevate Selling Price"):
        b = df.index[~df[c].str.strip().str.match(NUM_RE)]
        if len(b): err(f"{c} must be a plain decimal like 19.95 (no currency, no thousands separator)", line(b))
    st = df.index[~df["Elevate Stock"].str.strip().str.match(r"^\d+$")]
    if len(st): err("Elevate Stock must be a whole number >= 0", line(st))
    if not errors:
        lp = pd.to_numeric(df["Elevate List Price"]); sp = pd.to_numeric(df["Elevate Selling Price"])
        r = df.index[sp > lp]
        if len(r): err("Selling Price > List Price", line(r))
        if (lp == 0).any(): warn(f"{int((lp == 0).sum())} rows have a 0 price")
        if has("Elevate Cost"):
            cost = pd.to_numeric(df["Elevate Cost"].replace("", pd.NA), errors="coerce")
            r = df.index[cost.notna() & ((cost <= 0) | (cost >= sp))]
            if len(r): err("Cost must be > 0 and < Selling Price (leave blank otherwise)", line(r))
        if len(df) > 20 and sp.nunique() == 1: warn("every row has the same Selling Price — wrong column?")
        if len(df) > 20 and (sp == lp).all(): warn("Selling Price equals List Price on every row — sale price column missed?")

    # Variants: same Product Key more than once => each row needs a distinguishing size or label
    size = df["Elevate Size"].str.strip() if has("Elevate Size") else pd.Series([""] * len(df))
    label = df["Elevate Variant SKU"].str.strip() if has("Elevate Variant SKU") else pd.Series([""] * len(df))
    dup_keys = [k for k, n in Counter(key).items() if n > 1]
    for k in dup_keys[:1000]:
        idx = key.index[key == k]
        ids = [(size[i] or label[i]) for i in idx]
        if "" in ids:
            err(f"Product '{k}' has {len(idx)} variants but some lack Size/Variant SKU", line(idx)); break
        if len(set(ids)) < len(ids) and len({label[i] for i in idx}) < len(idx):
            err(f"Product '{k}' has variants with the same size and no unique Variant SKU", line(idx)); break
    if not has("Elevate Variant SKU") and dup_keys:
        warn("no 'Elevate Variant SKU' column — the tool falls back to Product Key as variant label, which collides for sibling rows")
    if has("Elevate Group Key") and (grp != "").any():
        if not has("Elevate Size") and not has("Elevate Variant SKU"):
            err("grouped feed needs 'Elevate Size' or 'Elevate Variant SKU' so variants are distinguishable")

    if has("Elevate Colour") or has("Elevate Color"):
        c = df[cols.get("elevate colour") or cols["elevate color"]]
        bad = [v for cell in c for v in cell.split("|") if v.strip() and not (HEX_RE.match(v.strip()) or v.strip().lower() in NAMED_COLOURS)]
        if bad: err(f"Elevate Colour must be hex (#RRGGBB) or Gold/Silver/Multi/Transparent — e.g. {sorted(set(bad))[:5]}; put colour names in a customLabel:colour column")
    if has("Elevate Images"):
        n = df["Elevate Images"].apply(lambda s: len([u for u in s.split("|") if u.strip()]))
        if (n > 25).any(): err("more than 25 images in a row", line(df.index[n > 25]))
        badu = [u for s in df["Elevate Images"] for u in s.split("|") if u.strip() and not re.match(r"^(https?:)?//", u.strip())]
        if badu: err(f"image URLs must be absolute — e.g. {badu[:3]}")
        if (n == 0).all(): warn("no images on any row")
    else:
        warn("no 'Elevate Images' column")
    for c, lim in LIMITS.items():
        if has(c):
            n = df[c].apply(lambda s: len([x for x in s.split("|") if x.strip()]))
            if (n > lim).any(): err(f"{c} has more than {lim} values on a row", line(df.index[n > lim]))
    if has("Elevate Series") and (df["Elevate Series"].str.len() > 20).any(): err("Elevate Series longer than 20 chars")
    for c in df.columns:
        if c.lower().startswith("customlabel"):
            m = re.match(r"^customlabel\s*[:.]\s*([A-Za-z_][A-Za-z0-9_.-]*)$", c, re.I)
            if not m: err(f"custom label header '{c}' must be customLabel:<name> where name is XML-safe (letters, digits, _ . -; not starting with a digit)")
    if df.duplicated(subset=["Elevate Product Key"] + (["Elevate Size"] if has("Elevate Size") else []) + (["Elevate Variant SKU"] if has("Elevate Variant SKU") else [])).any():
        err("duplicate rows for the same Product Key + Size + Variant SKU")
    return report(df, errors, warnings, key, grp)


def report(df, errors, warnings, key=None, grp=None):
    print(f"{len(df)} rows", end="")
    if key is not None:
        products = key.nunique()
        groups = grp.where(grp != "", key).nunique()
        print(f" -> {groups} groups, {products} products, {len(df)} variants", end="")
    print()
    for w in warnings: print("WARN ", w)
    for e in errors: print("ERROR", e)
    if not errors: print("OK — ready to upload")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
