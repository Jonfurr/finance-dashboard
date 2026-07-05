#!/usr/bin/env python3
"""
Build the encrypted data file for the finance dashboard.

Usage:
    python3 build.py                 # prompts for passphrase
    python3 build.py --pass "..."    # passphrase on command line

Reads every .csv in ./transactions/, categorizes via rules.csv,
deduplicates across files, and writes docs/data.enc (AES-256-GCM, PBKDF2).

Supported CSV formats (auto-detected by header):
  - Bank of America checking:  Date,Description,Amount,Running Bal.
  - Chase credit card:         Transaction Date,Post Date,Description,Category,Type,Amount
  - Citi credit card:          Date,Description,Debit,Credit
  - Generic:                   any file with Date/Description/Amount columns
Add new formats in parse_file() below.
"""
import argparse, base64, csv, getpass, hashlib, json, os, re, secrets, sys
from collections import Counter
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))
TXN_DIR = os.path.join(HERE, "transactions")
RULES = os.path.join(HERE, "rules.csv")
OUT = os.path.join(HERE, "docs", "data.enc")

# Categories treated as money movement, not real income/spending
TRANSFER_CATS = {"Credit Card Payments", "Savings & Investments",
                 "Transfers - TTFCU", "Transfers - Other"}
INCOME_PREFIXES = ("Paycheck", "Income -")


def money(s):
    s = (s or "").strip().replace(",", "").replace("$", "")
    if not s:
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def norm_date(s):
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_file(path):
    """Yield (date, description, amount, source) tuples."""
    name = os.path.basename(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None

    if "running bal." in header:                        # BofA checking
        for r in rows[1:]:
            if len(r) < 3:
                continue
            amt, d = money(r[2]), norm_date(r[0])
            if amt is None or d is None:                # skips beginning-balance line
                continue
            yield d, r[1].strip(), amt, "bofa-checking"
    elif col("debit") is not None:                      # Citi CC
        di, ci = col("debit"), col("credit")
        dd, dc = col("date"), col("description")
        for r in rows[1:]:
            d = norm_date(r[dd])
            if d is None:
                continue
            if money(r[di]) is not None:
                amt = -money(r[di])
            elif money(r[ci]) is not None:
                amt = money(r[ci])
            else:
                continue
            yield d, r[dc].strip(), amt, "citi-cc"
    elif col("transaction date") is not None:           # Chase CC
        dd = col("transaction date")
        dc, da = col("description"), col("amount")
        for r in rows[1:]:
            d, amt = norm_date(r[dd]), money(r[da])
            if d is None or amt is None:
                continue
            yield d, r[dc].strip(), amt, "chase-cc"
    else:                                               # generic
        dd, dc, da = col("date", "posted date"), col("description"), col("amount")
        if None in (dd, dc, da):
            print(f"  !! {name}: unrecognized format, skipped", file=sys.stderr)
            return
        for r in rows[1:]:
            d, amt = norm_date(r[dd]), money(r[da])
            if d is None or amt is None:
                continue
            yield d, r[dc].strip(), amt, "generic"


def load_rules():
    rules = []
    with open(RULES, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pat = row["pattern"].strip()
            if pat:
                rules.append((re.compile(pat, re.IGNORECASE), row["category"].strip()))
    return rules


def categorize(desc, rules):
    for rx, cat in rules:
        if rx.search(desc):
            return cat
    return "Uncategorized"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="passphrase")
    ap.add_argument("--plain", action="store_true",
                    help="also write docs/data.json unencrypted (debug only; never publish)")
    args = ap.parse_args()

    rules = load_rules()
    # Dedupe across files only: identical (date, desc, amount) rows WITHIN one
    # file are real repeat purchases and are kept. Across files (overlapping
    # exports) we keep the highest count seen in any single file.
    merged = Counter()
    for fn in sorted(os.listdir(TXN_DIR)):
        if not fn.lower().endswith(".csv"):
            continue
        counts = Counter(parse_file(os.path.join(TXN_DIR, fn)))
        print(f"  {fn}: {sum(counts.values())} transactions")
        for key, c in counts.items():
            merged[key] = max(merged[key], c)
    txns = []
    for (d, desc, amt, src), c in merged.items():
        for _ in range(c):
            txns.append({"d": d, "desc": desc, "amt": amt,
                         "cat": categorize(desc, rules), "src": src})

    txns.sort(key=lambda t: t["d"])
    uncat = [t for t in txns if t["cat"] == "Uncategorized"]
    uncat_spend = sum(t["amt"] for t in uncat if t["amt"] < 0)
    print(f"Total: {len(txns)} txns | uncategorized: {len(uncat)} (${-uncat_spend:,.2f} spend)")

    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "transferCats": sorted(TRANSFER_CATS),
        "incomePrefixes": list(INCOME_PREFIXES),
        "transactions": txns,
    }
    payload = json.dumps(data, separators=(",", ":")).encode()

    pw = args.passphrase or getpass.getpass("Passphrase for the dashboard: ")
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 310_000, dklen=32)
    ct = AESGCM(key).encrypt(iv, payload, None)
    blob = {"v": 1, "kdf": "PBKDF2-SHA256", "iter": 310_000,
            "salt": base64.b64encode(salt).decode(),
            "iv": base64.b64encode(iv).decode(),
            "ct": base64.b64encode(ct).decode()}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(blob, f)
    print(f"Wrote {OUT} ({os.path.getsize(OUT):,} bytes)")

    if args.plain:
        pj = os.path.join(HERE, "docs", "data.json")
        with open(pj, "wb") as f:
            f.write(payload)
        print(f"Wrote {pj} (DEBUG ONLY - do not commit/publish)")

    if uncat:
        agg = {}
        for t in uncat:
            k = re.sub(r"\d{2}/\d{2}.*", "", t["desc"]).strip()[:45]
            agg[k] = agg.get(k, 0) + t["amt"]
        print("\nTop uncategorized (add rules to rules.csv):")
        for k, v in sorted(agg.items(), key=lambda x: abs(x[1]), reverse=True)[:20]:
            print(f"  {v:>10,.2f}  {k}")


if __name__ == "__main__":
    main()
