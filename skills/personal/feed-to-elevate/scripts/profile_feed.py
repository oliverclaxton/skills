#!/usr/bin/env python3
"""Profile a product feed (CSV/TSV/XLSX/JSON/XML) the way the Elevate import tool will see it.

Usage: profile_feed.py <file> [--sheet NAME] [--rows N]

Flattens the feed with the same rules as the tool's parsers (nested keys joined with
".", arrays joined with "|") and prints columns, fill rate, distinct counts and samples.
Needs pandas; XLSX also needs openpyxl.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET

import pandas as pd


def flatten(obj, prefix=""):
    out = {}
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, list):
            out[key] = "|".join(json.dumps(x) if isinstance(x, (dict, list)) else str(x) for x in v)
        else:
            out[key] = "" if v is None else str(v)
    return out


def strip_ns(tag):
    return tag.split("}", 1)[-1]


def xml_flatten(el, prefix=""):
    out = {}
    for child in el:
        key = f"{prefix}.{strip_ns(child.tag)}" if prefix else strip_ns(child.tag)
        if len(child):
            for k, v in xml_flatten(child, key).items():
                out[k] = f"{out[k]}|{v}" if k in out else v
        else:
            text = (child.text or "").strip()
            out[key] = f"{out[key]}|{text}" if key in out else text
    return out


def load(path, sheet):
    low = path.lower()
    if low.endswith((".xlsx", ".xlsm", ".xls")):
        xl = pd.ExcelFile(path)
        print(f"sheets: {xl.sheet_names}")
        return xl.parse(sheet or xl.sheet_names[0], dtype=str).fillna("")
    if low.endswith(".json"):
        data = json.load(open(path, encoding="utf-8"))
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list) and v), [])
        return pd.DataFrame([flatten(x) for x in data]).fillna("")
    if low.endswith(".xml"):
        root = ET.parse(path).getroot()
        counts = {}
        for el in root.iter():
            if len(el):
                counts[el.tag] = counts.get(el.tag, 0) + 1
        item_tag = max((t for t, n in counts.items() if n > 1), key=lambda t: counts[t], default=None)
        items = [e for e in root.iter(item_tag)] if item_tag else [root]
        print(f"xml item element: <{strip_ns(item_tag) if item_tag else root.tag}> x{len(items)}")
        return pd.DataFrame([xml_flatten(e) for e in items]).fillna("")
    return pd.read_csv(path, dtype=str, sep=None, engine="python", keep_default_na=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--sheet")
    ap.add_argument("--rows", type=int, default=3, help="sample values per column")
    a = ap.parse_args()

    df = load(a.file, a.sheet)
    df.columns = [str(c).strip() for c in df.columns]
    print(f"rows: {len(df)}  columns: {len(df.columns)}\n")
    for c in df.columns:
        col = df[c].astype(str).str.strip()
        filled = col[col != ""]
        samples = " | ".join(s[:60] for s in filled.drop_duplicates().head(a.rows))
        print(f"- {c}: {len(filled) * 100 // max(len(df), 1)}% filled, {filled.nunique()} distinct  e.g. {samples}")

    print("\nlikely id columns (distinct count vs rows):")
    for c in df.columns:
        n = df[c].astype(str).nunique()
        if 1 < n <= len(df) and any(w in c.lower() for w in ("id", "sku", "key", "parent", "group", "code", "ean", "mpn", "handle")):
            print(f"  {c}: {n} distinct / {len(df)} rows")


if __name__ == "__main__":
    sys.exit(main())
