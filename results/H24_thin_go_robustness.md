# H24 — OOS Robustness Pass on the Thin GO Pairs (GBPUSD, NZDUSD)

**Date:** 2026-05-19
**Script:** [`scripts/h24_thin_go_robustness.py`](../scripts/h24_thin_go_robustness.py)
**Run dump:** [`results/_h24_run.json`](_h24_run.json)
**Figures:** [`figures/14_robustness_bootstrap.png`](../figures/14_robustness_bootstrap.png),
[`figures/15_robustness_rolling.png`](../figures/15_robustness_rolling.png)

## Why this exists

H23 labelled GBPUSD (9 OOS trades) and NZDUSD (4 OOS trades) **GO** by
the locked mechanical rule but explicitly flagged both as thin-OOS and
**not safe to flip live** without this pass. H24 is the same discipline
that caught USDMXN's IS-bias in H16: do not ship on thin evidence. Either
a pair survives stress and graduates to solid GO, or it fails and is
downgraded. Both are wins — the point is to *know*.

No new parameters. The OOS trade list is reconstructed through the
identical H23/H16 engine path (loose-M `PatternConfig` dip=50, `fld_bias`
(10,20,40), Scheme D 0/1/3, `rm.build_equity_curve → rm.sortino`, 70/30
split by bars). Reconstruction reproduced the H23 baselines exactly
(GBPUSD +5.57 / 9, NZDUSD +5.34 / 4) before any test ran — foundation
gate passed.

## Tests and locked decision precedence

| Test | Pass condition |
|---|---|
| 1. Bootstrap (N=10,000, `seed=42`) | decision p5 (nan→0) ≥ +3.0 |
| 2. Rolling windows (50% of OOS span, 4 windows) | ≥ 3 of 4 ≥ +3.0 |
| 3. Trade clustering | Gini(contribution) ≤ 0.7 |
| 4. Per-trade sensitivity (drop-one) | min Sortino ≥ +2.5 |

Precedence: **SOLID GO** = all 4 hold · **THIN GO** = 2–3 hold ·
**DOWNGRADE → SWEEP** = 0–1 hold. `enabled` stays `false` either way.

*Load-bearing methodology choices (documented, not asked):*
(a) Sortino is the equity-curve annualized figure (`rm.sortino`),
identical scale to the +3.0 floor used in H12/H16/H23 — comparability
preserved. (b) Degenerate bootstrap resamples (Sortino undefined: no
downside, or <2 daily returns) are mapped to **0.0** for the decision
percentile — the conservative reading, since an undefined Sortino is not
evidence of a +3 edge. Finite-only percentiles and the nan-rate are
reported alongside for transparency. (c) Rolling windows: 4 windows of
width = 50% of the OOS calendar span, starting at span-fractions
{0, 1/6, 1/3, 1/2} so the last window ends exactly at span end.

---

## GBPUSD — **THIN GO** (2/4 conditions hold)

OOS 2019-08-23 → 2026-05-18, 9 trades, baseline Sortino **+5.57**.
7 winners / 2 full losers. The single 3×-sized trade
(2025-11-25, +4.08R → contribution +12.24) is ~half of total profit.

| Test | Result | Pass? |
|---|---|:--:|
| 1. Bootstrap | decision p5 **+0.00** (finite p5 +0.90), p50 +4.07, p95 +16.46, 10.7% degenerate | ❌ |
| 2. Rolling | windows `[0.02, n<2, 6.42, 13.84]` → **2/4** ≥ +3.0 | ❌ |
| 3. Gini | contribution **0.697** ≤ 0.7 (profit-only 0.584; best 30-day share 52%) | ✅ |
| 4. Per-trade | min Sortino **+2.84** (worst = drop 2025-11-25 +4.08×3) ≥ +2.5 | ✅ |

**Read.** GBPUSD is *not* a one-trade artifact — dropping even its single
largest trade leaves Sortino +2.84, and contribution is spread broadly
enough that Gini sits right at the 0.7 line. But the edge is **not
time-stable**: the first OOS window (2019→2023) has essentially no edge
(Sortino +0.02), and the bootstrap 5th percentile collapses to ≤ +0.9.
The strong +5.57 headline is carried by the 2023–2026 sub-period. That is
a real but **regime-concentrated** edge, not a broadly stationary one.

**Verdict: stays THIN GO. Do NOT flip `enabled: true`.** It is tradeable
with lower confidence; a clean flip needs the post-2023 behaviour to
persist into a *future* (true forward) OOS window — i.e. revisit after
~12 months of live-paper observation, not via more in-sample slicing.

---

## NZDUSD — **DOWNGRADE → SWEEP** (0/4 conditions hold)

OOS 2019-08-28 → 2026-05-18, **4 trades**, baseline Sortino +5.34.

| # | Entry → Exit | R | mult | contribution |
|---|---|---:|---:|---:|
| 1 | 2021-10-04 → 2021-11-26 | −1.000 | 3.0 | −3.00 |
| 2 | 2024-05-01 → 2024-09-24 | **+17.407** | 3.0 | **+52.22** |
| 3 | 2024-05-09 → 2024-11-14 | −1.000 | 1.0 | −1.00 |
| 4 | 2025-11-24 → 2025-11-25 | −1.000 | 3.0 | −3.00 |

| Test | Result | Pass? |
|---|---|:--:|
| 1. Bootstrap | decision p5 **−0.74**, p50 +5.34, p95 +88.22 | ❌ |
| 2. Rolling | `[n<2, n<2, 88.77, 15.73]` → only windows containing trade #2 have an edge | ❌ |
| 3. Gini | contribution **0.927**, profit-only 0.75, **100% of profit in one 30-day window** → cluster-dependent | ❌ |
| 4. Per-trade | drop trade #2 → Sortino **−0.66** (min) — well below +2.5 | ❌ |

**Read.** Three of four OOS trades are full −1R losers. The entire
positive Sortino is the *single* 2024-05-01 trade (+17.4R, 3×-sized).
Remove it and the strategy is a net loser (Sortino −0.66). 100% of profit
falls in one 30-day window; Gini 0.93. This is the textbook small-sample
artifact the no-spurious-ship doctrine exists to catch — exactly the
failure shape H23 pre-flagged as "must not go live without H24".

**Verdict: DOWNGRADE.** `status: GO → sweep_needed` in the hurst-agent
config. The H23 GO label was a 4-sample mirage. NZDUSD is not rejected
outright (full-sample H23 was +4.42 / 35, genuinely positive) — it is
parked at SWEEP pending a real follow-up (more history / forward OOS),
**not** a parameter re-tune (out of scope).

---

## Summary & ledger delta

| Pair | H23 label | H24 conditions held | H24 verdict | config `status` | `enabled` |
|---|---|:--:|---|---|---|
| GBPUSD | GO ⚠ thin | 2/4 (Gini, per-trade) | **THIN GO** | `GO` (notes updated) | `false` |
| NZDUSD | GO ⚠⚠ provisional | 0/4 | **DOWNGRADE → SWEEP** | `sweep_needed` | `false` |

EURUSD / USDCAD (solid GO) were not in scope — their OOS samples (12, 15)
were already healthy in H23. AUDUSD / USDJPY SWEEPs are out of scope:
they need a regime overlay, not robustness testing.

**Net:** the H23 → H24 pipeline did its job. NZDUSD's headline edge was
one trade and is now correctly parked. GBPUSD's edge is real but
regime-concentrated post-2023; it stays tradeable-but-not-yet-live with
the reason recorded so the next agent does not re-litigate it from the
+5.57 headline alone.
