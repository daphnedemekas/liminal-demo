# Freelance Finance System — Notion Setup Guide

## Overview

This system uses **5 interconnected Notion databases** to track your freelance finances end-to-end: from client management through expense tracking to quarterly tax estimates. The CSV files in this folder are your starter data — import them into Notion, then wire up the relations and formulas below.

---

## Step 1: Create the Databases (in this order)

### Database 1: Clients
Import `01-clients-database.csv` into a new Notion database.

**Add these properties after import:**
| Property | Type | Purpose |
|----------|------|---------|
| Invoices | Relation → Invoices DB | Link to all invoices for this client |
| Total Billed | Rollup → Invoices → Amount → Sum | Auto-total of all invoices |
| Total Paid | Rollup → Invoices → Amount → Sum (filtered: Status = Paid) | Revenue actually received |

### Database 2: Invoices / Income
Import `02-invoices-income.csv`.

**Add these properties after import:**
| Property | Type | Purpose |
|----------|------|---------|
| Client | Relation → Clients DB | Link each invoice to a client |
| Quarter | Relation → Quarterly Tax DB | Link to the quarter this payment falls in |
| Overdue Alert | Formula (see below) | Auto-flags overdue invoices |

**Overdue Alert formula:**
```
if(prop("Status") != "Paid" and prop("Due Date") < now(), "⚠️ OVERDUE", if(prop("Status") != "Paid" and dateBetween(prop("Due Date"), now(), "days") <= 7, "📅 Due Soon", ""))
```

### Database 3: Expenses
Import `03-expenses.csv`.

**Key:** The "Schedule C Category" select property should have these exact options (matching `05-schedule-c-categories.csv`):
- Advertising (Line 8)
- Car & Truck Expenses (Line 9)
- Commissions & Fees (Line 10)
- Contract Labor (Line 11)
- Depreciation / Section 179 (Line 13)
- Insurance (Line 15)
- Interest - Mortgage (Line 16a)
- Interest - Other (Line 16b)
- Legal & Professional Services (Line 17)
- Office Expenses (Line 18)
- Rent - Vehicles/Equipment (Line 20a)
- Rent - Other Property (Line 20b)
- Repairs & Maintenance (Line 21)
- Supplies (Line 22)
- Taxes & Licenses (Line 23)
- Travel (Line 24a)
- Meals - 50% Deductible (Line 24b)
- Utilities (Line 25)
- Other Expenses (Line 27)
- Home Office (Form 8829)
- Health Insurance (Form 1040 Line 17)
- Retirement Contributions (Schedule 1)

**Add these properties:**
| Property | Type | Purpose |
|----------|------|---------|
| Quarter | Relation → Quarterly Tax DB | Link to the relevant quarter |
| Receipt | Files & media | Upload photo/PDF of receipt |

### Database 4: Quarterly Tax Tracker
Import `04-quarterly-tax-tracker.csv`.

**Add these properties and formulas:**
| Property | Type | Purpose |
|----------|------|---------|
| Invoices | Relation → Invoices DB | All invoices paid in this quarter |
| Expenses | Relation → Expenses DB | All expenses in this quarter |
| Gross Income | Rollup → Invoices → Amount → Sum | Auto-total income |
| Total Expenses | Rollup → Expenses → Amount → Sum | Auto-total expenses |

**Tax estimation formulas (add as formula properties):**

**Net Profit:**
```
prop("Gross Income") - prop("Total Expenses")
```

**SE Tax Estimate** (15.3% on 92.35% of net profit):
```
round(prop("Net Profit") * 0.9235 * 0.153 * 100) / 100
```

**Half SE Tax Deduction** (deductible from income):
```
round(prop("SE Tax Estimate") / 2 * 100) / 100
```

**Federal Income Tax Estimate** (progressive brackets, 2026 single filer):
```
lets(
  income, prop("Net Profit") - prop("Half SE Tax Deduction"),
  if(income <= 0, 0,
    if(income <= 11600, round(income * 0.10 * 100) / 100,
      if(income <= 47150, round((1160 + (income - 11600) * 0.12) * 100) / 100,
        if(income <= 100525, round((5426 + (income - 47150) * 0.22) * 100) / 100,
          if(income <= 191950, round((17168.50 + (income - 100525) * 0.24) * 100) / 100,
            round(income * 0.24 * 100) / 100
          )
        )
      )
    )
  )
)
```

**State Tax Estimate** — pick YOUR state formula:

| State | Formula |
|-------|---------|
| California | `round(prop("Net Profit") * 0.093 * 100) / 100` |
| New York (state only) | `round(prop("Net Profit") * 0.065 * 100) / 100` |
| New York + NYC | `round(prop("Net Profit") * 0.10 * 100) / 100` |
| Texas | `0` |
| Florida | `0` |

**Total Estimated Tax Due:**
```
prop("SE Tax Estimate") + prop("Federal Income Tax Est") + prop("State Tax Est")
```

**Remaining Balance:**
```
prop("Total Estimated Tax Due") - prop("Amount Paid")
```

**Days Until Deadline:**
```
if(prop("Payment Status") == "Paid", 0, dateBetween(prop("Payment Deadline"), now(), "days"))
```

### Database 5: Deductions Checklist (optional but recommended)
Create a new database manually with this structure:

| Property | Type |
|----------|------|
| Deduction Name | Title |
| Category | Select: Schedule C / Above-the-Line / Itemized |
| Annual Amount | Number (currency) |
| Frequency | Select: Monthly / Quarterly / Annual / One-time |
| Status | Select: Claiming / Not Sure / Need to Research |
| Notes | Text |

**Pre-populate with commonly missed deductions:**
- Self-employment tax deduction (50% of SE tax) — Above-the-Line
- Self-employed health insurance (100% of premiums) — Above-the-Line
- Home office ($5/sq ft simplified, max $1,500) — Schedule C
- Retirement contributions (SEP-IRA/Solo 401k) — Above-the-Line
- QBI deduction (up to 20% of qualified business income) — Below-the-Line
- HSA contributions (if on HDHP) — Above-the-Line
- Business phone/internet (business % only) — Schedule C
- Professional development & courses — Schedule C
- Software subscriptions — Schedule C
- Mileage ($0.725/mile in 2026) — Schedule C

---

## Step 2: Wire Up Relations

Connect the databases in this order:

```
Clients ←→ Invoices ←→ Quarterly Tax Tracker ←→ Expenses
```

1. In **Invoices**, add a Relation to **Clients** (two-way)
2. In **Invoices**, add a Relation to **Quarterly Tax Tracker** (two-way)
3. In **Expenses**, add a Relation to **Quarterly Tax Tracker** (two-way)
4. In **Clients**, add Rollups that sum related Invoice amounts

---

## Step 3: Create Dashboard Views

### Income Dashboard (Invoices DB views)
- **All Invoices**: Table view, sorted by Date Issued descending
- **Unpaid/Overdue**: Table view, filtered: Status ≠ Paid, sorted by Due Date
- **By Client**: Board view, grouped by Client relation
- **By Quarter**: Table view, grouped by Quarter relation

### Expense Dashboard (Expenses DB views)
- **All Expenses**: Table view, sorted by Date descending
- **By Category**: Board view, grouped by Schedule C Category
- **Missing Receipts**: Table view, filtered: Receipt Uploaded = No
- **Monthly Totals**: Table view, grouped by month

### Tax Dashboard (Quarterly Tax DB views)
- **Current Year**: Table view, filtered: Tax Year = 2026
- **Payment Calendar**: Calendar view, using Payment Deadline date

---

## Step 4: Set Up Recurring Reminders

In Notion, set reminders on these dates:

| When | What |
|------|------|
| 1st of each month | Enter previous month's income and expenses |
| March 15, June 1, Aug 15, Dec 1 | Calculate quarterly estimate (2 weeks before deadline) |
| April 15 | Q1 estimated tax payment due |
| June 15 | Q2 estimated tax payment due |
| September 15 | Q3 estimated tax payment due |
| January 15 (next year) | Q4 estimated tax payment due |

---

## Key Tax Numbers for 2026

| Item | Amount |
|------|--------|
| Self-employment tax rate | 15.3% (on 92.35% of net profit) |
| Social Security wage base | $184,500 |
| Standard mileage rate | $0.725/mile |
| Simplified home office | $5/sq ft, max $1,500 |
| Business meals deduction | 50% |
| SEP-IRA max contribution | $72,000 (or 25% of net SE income) |
| Solo 401(k) employee deferral | $24,500 |
| Solo 401(k) total max | $72,000 |
| Standard deduction (single) | $16,100 |
| Safe harbor: prior year ≤$150K AGI | Pay 100% of prior year tax |
| Safe harbor: prior year >$150K AGI | Pay 110% of prior year tax |
| Safe harbor: current year | Pay 90% of current year tax |

---

## State-Specific Notes

### If you're in California
- State income tax: 1%–12.3% progressive (effective ~9.3% for mid-income)
- You must also make CA estimated tax payments (Form 540-ES) on the same quarterly schedule
- Consider opting into SDI (State Disability Insurance) — premiums are 1.2% with no wage cap
- Self-employed health insurance deduction applies at both federal AND state level

### If you're in New York
- State income tax: 4%–10.9%
- NYC income tax: additional 3.078%–3.876%
- **Watch out for the Unincorporated Business Tax (UBT)**: 4% on net SE income if you're in NYC. Credit available for income ≤$100K, partial credit $100K–$150K
- MCTMT tax: 0.34% on SE income >$50K in the metro commuter district

### If you're in Texas or Florida
- No state income tax — you only owe federal + SE tax
- Claim the **federal sales tax deduction** (Schedule A) instead of state income tax deduction
- TX: Watch for sales tax obligations if your freelance services are taxable (info services, data processing)
- FL: Commercial rent tax (2%) if you rent office space (unique to FL)

---

## Safe Harbor Strategy

To avoid underpayment penalties, use this approach:
1. Look at your **prior year's total tax** (from your 1040, line 24)
2. If your prior year AGI was ≤$150K: divide that number by 4 → pay that each quarter
3. If your prior year AGI was >$150K: multiply by 1.10, divide by 4 → pay that each quarter
4. This guarantees no penalty regardless of what you earn this year
5. If you earn significantly more, adjust up to avoid a large April balance

---

## Monthly Workflow

1. **Week 1 of each month**: Enter all prior month's invoices (paid amounts) and expenses
2. **Link** each entry to the correct quarter in Quarterly Tax Tracker
3. **Upload receipts** for any expense over $75 (IRS requires documentation)
4. **Review** the Quarterly Tax Tracker totals — are you on track with your safe harbor payments?
5. **Before each quarterly deadline**: Verify the estimate, pay via [IRS Direct Pay](https://www.irs.gov/payments/direct-pay) or [EFTPS](https://www.eftps.gov/), enter confirmation number

---

## Sources

- [IRS Schedule C Instructions](https://www.irs.gov/instructions/i1040sc)
- [IRS Estimated Tax FAQ](https://www.irs.gov/faqs/estimated-tax)
- [IRS Self-Employment Tax](https://www.irs.gov/businesses/small-businesses-self-employed/self-employment-tax-social-security-and-medicare-taxes)
- [IRS 2026 Mileage Rate](https://www.irs.gov/newsroom/irs-sets-2026-business-standard-mileage-rate-at-725-cents-per-mile-up-25-cents)
- [IRS 2026 Retirement Limits](https://www.irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500)
- [NerdWallet: Estimated Tax Guide](https://www.nerdwallet.com/taxes/learn/estimated-quarterly-taxes)
- [TurboTax: Self-Employed Deductions](https://turbotax.intuit.com/tax-tips/self-employment-taxes/top-tax-write-offs-for-the-self-employed/L7xdDG7JL)
