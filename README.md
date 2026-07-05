# Furr Family Finance Dashboard

Passcode-protected spending dashboard for GitHub Pages. Only the encrypted
`data.enc` and `index.html` get published — transaction data is unreadable
without the passphrase.

## Folder layout

```
finance-dashboard/
├── transactions/   <- drop bank/credit-card CSV exports here
├── rules.csv       <- merchant pattern -> category (edit freely)
├── build.py        <- rebuilds docs/data.enc from the CSVs
└── docs/           <- the publishable site (index.html + data.enc)
```

## Updating the dashboard

1. Export new CSVs from Bank of America (or Chase/Citi credit cards) into `transactions/`.
   Overlapping date ranges are fine — duplicates are removed automatically.
2. Run:
   ```
   python3 build.py
   ```
   It prompts for the passphrase (this is what you and Madison will type on the site).
   Requires Python 3 with the `cryptography` package (`pip install cryptography`).
3. Review the "uncategorized" list it prints. To fix one, add a line to `rules.csv`:
   `SOME MERCHANT TEXT,Category Name` (first matching rule wins, patterns are
   case-insensitive regex). Re-run `build.py`.
4. Commit and push `docs/` to GitHub.

## Publishing to GitHub Pages (one-time)

1. Create a repo (private or public — Pages works either way on a Pro account;
   on a free account the repo must be public, which is fine since data is encrypted).
2. Push this folder to it.
3. Repo Settings -> Pages -> Source: "Deploy from a branch" -> branch `main`, folder `/docs`.
4. Site appears at `https://<username>.github.io/<repo>/`. Share the URL and
   passphrase with Madison. "Remember on this device" saves it in her browser.

## Changing the passphrase

Just re-run `build.py` and type a new one. The old file is overwritten; anyone
with the old passphrase can no longer decrypt the new data file.

## Credit cards and double counting

Right now, "Credit Card Payments" (Chase/Citi autopay from checking) is shown
as a spending category, because that's where card spending is hiding.
As soon as you drop a Chase or Citi credit-card CSV into `transactions/`,
the dashboard automatically reclassifies those payments as transfers and uses
the individual card transactions (properly categorized) instead — no double
counting.

## Notes on specific categories

- **Checks & Cash** — checks written and banking-center withdrawals; the bank
  doesn't say what they were for. Add rules like `^Check 126,Home & Garden`
  if you remember specific ones.
- **Transfers - TTFCU / Transfers - Other / Savings & Investments** — money moving
  between your own accounts; excluded from income and spending.
- **Income - Deposits** — mobile check deposits. If some of these are really
  transfers from another account, tell me / recategorize.
