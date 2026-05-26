# Bezpieczny Kredyt 2% — Overpayment Mechanics

This document explains how Bezpieczny Kredyt 2% (BK2%) works, how it differs from a standard
consumer mortgage, how overpayments interact with the BGK subsidy, and what the optimal strategy
looks like depending on how much of the subsidised period remains.

This is the conceptual foundation for `bk2_overpayment()` in `agent/tools/calculator.py`.

---

## 1. Standard consumer mortgage (baseline)

A standard Polish variable-rate mortgage works like this:

```
Monthly installment = capital portion + interest portion
Interest portion    = Ks × rate / 12
```

Where `Ks` is the remaining balance and `rate` is the full contractual rate (e.g. WIRON 3M + margin
≈ 7–8%). The borrower pays the **full rate on every złoty** of remaining balance for the entire
loan term.

**Overpayment in a standard mortgage:**

When you overpay by X PLN, you reduce the balance by X. Every month thereafter you pay less
interest at the full rate. The guaranteed "return" on an overpayment equals the full loan rate —
if your rate is 7.5%, every PLN overpaid saves you 7.5% annually. This makes the comparison
simple: compare loan rate vs net investment return after Belka tax.

---

## 2. BK2% structure overview

BK2% is a two-phase loan. The phases are defined by the subsidy period, not by rate resets.

```
Phase 1  │  First 120 scheduled installments  │  BGK pays the spread above 2%
Phase 2  │  Remaining installments             │  Borrower pays full market rate
```

The loan has a **fixed interest rate for the first 120 months** (§2 ust. 15), reset every 60
months. The rate does not change — but the subsidy mechanic means the borrower's effective
cost is very different in Phase 1 vs Phase 2.

---

## 3. Phase 1: the subsidised period

### 3a. Amortisation type — raty malejące (declining instalments)

This is the most important structural difference from a standard mortgage.

During Phase 1, the capital repayment portion per month is **fixed and equal**, calculated across
the full loan term (§2 ust. 17):

```
capital_per_month = initial_balance / total_term_months     [constant throughout Phase 1]
```

The interest portion shrinks each month as the balance falls:

```
interest_per_month = Ks × 0.02 / 12                        [decreasing]
```

So the total instalment paid by the borrower **decreases over time** — unlike a standard
annuity where it stays flat. This is called *raty malejące* (declining instalments).

A standard mortgage uses *raty równe* (equal instalments, annuity). BK2% Phase 1 does not.

After Phase 1 ends, the loan switches to **standard annuity** (raty równe) based on the
remaining balance and remaining months (§2 ust. 17).

### 3b. The BGK subsidy formula

Each month, BGK pays a subsidy D to reduce the borrower's instalment (§3 ust. 2):

```
D = Ks × (W − 0.02) / 12
```

Where:
- `Ks` = remaining capital balance at the time of the instalment
- `W`  = BGK's market rate indicator (average rate on newly issued fixed-rate mortgages × 0.9,
         announced quarterly). Closely tracks the contractual loan rate.
- `0.02` = the 2% threshold the borrower is responsible for

The borrower's effective interest charge is therefore:

```
borrower_interest = Ks × 0.02 / 12          (their 2% portion)
BGK subsidy       = Ks × (W − 0.02) / 12    (covers the spread to market rate)
total_interest    = Ks × W / 12             (≈ full market rate interest)
```

**Both portions scale with Ks.** If the balance falls — whether through scheduled repayment
or overpayment — both the borrower's interest charge and the BGK subsidy shrink proportionally.

### 3c. What the borrower actually pays each month in Phase 1

```
instalment = capital_per_month + Ks × 0.02 / 12
           = initial_balance / total_months + Ks × 0.02 / 12
```

Example (500 000 PLN, 25 years, W ≈ 7.5%):

| Month | Ks (PLN)  | Capital portion | Borrower interest (2%) | BGK subsidy (5.5%) | Total borrower pays |
|-------|-----------|-----------------|------------------------|-------------------|---------------------|
| 1     | 500 000   | 1 667           | 833                    | 2 292             | 2 500               |
| 60    | 400 000   | 1 667           | 667                    | 1 833             | 2 334               |
| 120   | 300 000   | 1 667           | 500                    | 1 375             | 2 167               |

Instalments decline over Phase 1 because the interest component shrinks. The borrower's
outgoing payments are always lower than on a standard mortgage at the same rate.

---

## 4. Phase 2: post-subsidy

When the 120th scheduled instalment is paid, subsidies stop. The loan continues at the full
contractual rate on the remaining balance, using standard equal instalments (annuity):

```
remaining_balance ≈ initial_balance × (1 − 120 / total_months)
                 = 500 000 × (1 − 120/300) = 500 000 × 0.6 = 300 000 PLN (approx)
```

From this point forward, the borrower pays the full market rate on every PLN remaining.
The instalment jumps relative to the subsidised period because:
1. The subsidy disappears
2. The switch from *raty malejące* to *raty równe* (annuity) changes the payment structure

---

## 5. Overpayment mechanics

### 5a. The 3-year lock-in

The programme's terms (§4 ust. 6 pkt 10) specify that early partial repayment triggers
**immediate loss of all remaining subsidies**, unless at least one of these conditions is met:

| Condition | Rule |
|-----------|------|
| Time lock | Overpayment made **more than 3 years** after loan origination |
| Guarantee | The repaid portion was covered by the BGK guarantee |
| Cumulative cap | Overpayment + original own contribution (**wkład własny**) ≤ 200 000 PLN |
| Monthly cap | Overpayment in a given month ≤ that month's net instalment (after subsidy) |

The 3-year time-lock condition is the one that matters most in practice. Borrowers who took
out BK2% loans in 2023 become eligible for safe overpayments in **2026**.

### 5b. What overpaying actually saves

Because the subsidy D scales with Ks (§3 ust. 2), reducing Ks through overpayment reduces
the BGK subsidy proportionally. The subsidy is not a fixed monthly grant — it shrinks when the
balance shrinks.

Consequence: **the borrower only saves interest on their 2% portion**, not on the full market rate.

```
overpayment X during Phase 1:
  interest saved per month = X × 0.02 / 12        (your 2% portion only)
  BGK subsidy lost per month = X × (W − 0.02) / 12  (this was always BGK's, not yours)
  net saving per PLN of overpayment = 0.02 / 12 per month = 2% / year
```

Compare this to a standard mortgage where overpaying X saves `X × 0.075 / 12` per month
(full 7.5%) — the effective return on the same overpayment is 3–4× higher in a standard mortgage.

### 5c. The Phase 2 bonus — the deferred saving

Overpaying during Phase 1 produces a second, larger effect: it lowers the balance at the start
of Phase 2. Because Phase 2 carries the full market rate (~7.5%), every PLN of lower balance
at Phase 2 entry generates savings at the full rate.

```
Phase 1 saving:  X × 0.02 × (months_remaining_in_phase_1 / 12)
Phase 2 saving:  X × full_rate × (loan_months_after_phase_2 / 12)   [approximate, ignores compounding]
```

The relative weight of these two effects depends entirely on how much of Phase 1 remains:

| Phase 1 remaining | Phase 2 length | Dominant saving | Effective overpayment return |
|-------------------|----------------|-----------------|------------------------------|
| 9 years           | 6 years        | Phase 1 (2%)   | ≈ 2–3%                       |
| 5 years           | 10 years       | Phase 2 (7.5%) | ≈ 4–5%                       |
| 1 year            | 14 years       | Phase 2 (7.5%) | ≈ 6–7%                       |

Early in the loan, overpaying competes with investing at 2% return — investing almost always wins.
Late in the subsidised period, the break-even shifts and overpaying can match or beat a 7% gross
investment return, especially after Belka tax.

### 5d. Monthly cap — safe micro-overpayments

The condition §4 ust. 6 pkt 10d creates a risk-free path: any additional payment that does not
exceed the net monthly instalment (after subsidy) in a given month does not trigger subsidy loss —
even within the 3-year lock-in window.

```
safe_monthly_extra ≤ instalment_net = capital_per_month + Ks × 0.02 / 12
```

This is rarely more than 2 500–3 000 PLN/month in the early years of a 500k loan. For
borrowers who want to overpay before 2026, this path is worth modelling.

---

## 6. Comparison: BK2% vs standard mortgage

| Property | Standard mortgage | BK2% Phase 1 | BK2% Phase 2 |
|----------|-------------------|--------------|--------------|
| Instalment type | Annuity (equal) | Declining (equal capital) | Annuity (equal) |
| Effective rate | Full (7–8%) | 2% | Full (7–8%) |
| Overpayment saves at | Full rate | 2% only | Full rate |
| Subsidy | None | BGK covers spread | None |
| Overpayment restriction | None | 3-yr lock-in + exceptions | None |
| Balance at 10 years | Higher (slower early payoff) | Lower (equal-capital schedule) | — |

Note: the *raty malejące* structure in Phase 1 means the borrower actually reduces their balance
**faster** than in a standard mortgage annuity over the first 10 years (capital repayment is the
same every month regardless of interest level, rather than being crowded out by interest).

---

## 7. Optimal strategy

### Rule 1: Before year 3 — do not overpay above the monthly cap

Unless the overpayment qualifies under the cumulative cap (≤200k total), any early repayment
kills subsidies worth thousands of PLN per month. The monthly cap path is low-leverage and
only worth it if you have excess liquidity and no better option.

### Rule 2: After year 3, compare against what you'd actually earn

The effective return on overpaying is not 2% and not 7.5% — it's the blended rate:

```
effective_return = (phase1_months × 2% + phase2_months × full_rate) / total_remaining_months
```

Compare this to `compare_return × (1 − 0.19)` (investing in taxable account, net of Belka).
In IKE, compare to the gross `compare_return` since there's no Belka.

### Rule 3: Timing matters more than amount

A 50 000 PLN overpayment made with 9 years of subsidies remaining delivers about half the
interest saving of the same overpayment made with 1 year remaining. If you expect Phase 1 to
end soon, waiting until just before Phase 2 and then overpaying may outperform overpaying now.

### Rule 4: Account for the instalment jump at Phase 2

At Phase 2 entry, the monthly payment increases significantly (subsidy stops + switch to
annuity). Liquidity planning should model this jump. Overpaying ahead of Phase 2 reduces the
Phase 2 instalment directly.

---

## 8. What `bk2_overpayment()` models

The calculator implements the two-phase model:

1. **Phase 1 simulation** (from today to `subsidy_end`):
   - Amortise using *raty malejące* (`capital_per_month = balance / remaining_months`)
   - With and without overpayment
   - Interest savings at `monthly_rate = 0.02/12` only

2. **Phase 2 simulation** (from `subsidy_end` to loan end):
   - Switch to annuity at `full_monthly_rate`
   - Different starting balance depending on whether overpayment was made
   - Interest savings at `full_monthly_rate`

3. **Outputs**:
   - `interest_saved_phase1` and `interest_saved_phase2` (separate so it's transparent)
   - `months_shortened` (total)
   - `equivalent_annual_return` (blended, annualised over full remaining term)
   - `subsidy_at_risk` (True if overpayment is within 3-year lock-in and exceeds monthly cap)
   - `recommendation` (invest / overpay) vs `compare_return`

**Inputs the LLM extracts from the question or profile:**
- `balance` — current remaining principal (PLN)
- `monthly_rate` — effective rate during subsidy = `0.02/12` ≈ 0.001667 (always for BK2%)
- `full_monthly_rate` — full contractual rate / 12 (WIRON + margin; read from profile)
- `overpayment` — one-time or monthly extra (PLN)
- `subsidy_end` — ISO date when the 120th instalment is expected to be paid
- `loan_end` — ISO date of final scheduled instalment
- `origination_date` — ISO date of loan origination (for lock-in check)
- `own_contribution` — wkład własny at origination (for 200k cumulative cap check)
- `compare_return` — annual gross investment return for comparison (default `0.07`)
- `in_ike` — whether comparison investment is inside IKE (no Belka, default `False`)
