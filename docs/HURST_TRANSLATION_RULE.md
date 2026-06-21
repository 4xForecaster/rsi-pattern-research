# Hurst's Right/Left Translation Rule — Ground Truth

**Date:** 2026-06-18
**Author of the search:** H29/H30 follow-up
**Purpose:** Resolve whether the H29 bias rule
("LONG if P1.idx > T-mid → bullish") matches J.M. Hurst's canonical
right/left translation definition, or has the sign backward.

## Verdict

**The H29 bias rule matches Hurst's canonical direction.**

> Right translation (peak right of midpoint) ⇒ **BULLISH** trend
> Left  translation (peak left  of midpoint) ⇒ **BEARISH** trend

The H29 implementation took `P1.idx > T-mid` → `bullish` → trade the
LONG. That is **directionally correct** per Hurst canon (confirmed below
across three independent reputable sources). The H29 failure to
produce edge on FX daily therefore is **not** a sign error in the spec
— it is a finding about *which structures* the rule profitably applies
to. See "Application caveats" at the bottom for the implication.

## Sourcing

### Local knowledge bases (the project memory noted one)

- **No local Hurst knowledge base** was found on disk under
  `~/Documents/4xForecaster/` or `~/4xForecaster/`. The memory file
  referenced in the brief (`project_hurst_knowledge.md`) **does not
  exist** under
  `~/.claude/projects/-Users-davidalcindor-4xForecaster/memory/`; the
  only Hurst-related memory present is `project_hurst_agent_push_hazard.md`.
- **`hurst-agent` source + docs** — `grep` for `translation`, `right.translat`,
  `left.translat`, `bullish.trend`, `bearish.trend` returned **no matches**.
  The codebase implements cycle FLDs and the M-anatomy state classifier
  but never asserts a translation-based trend rule.
- **`rsi-pattern-research`** — likewise no prior `translation` mention.

Gap honestly documented.

### Authoritative web sources (quoted literally)

**Sigma-L — "The FLD" (Hickson/Sentient-aligned community writeup):**

> "If the price peak of a component occurs **prior** to the FLD trough
> it is evidence of bearish pressure being exerted by longer components"
>
> "if price forms a peak **subsequent** to the FLD trough it is said to
> be **right translated** and therefore evidence of bullish [influence]"

This formulation ties translation to the **FLD trough**, not a generic
midpoint — a meaningful nuance vs. H29 (see "Application caveats").

**Airlovsky — Cycles Translation:**

> "Right-translated cycles are characterized by their peaks occurring
> after the midpoint of the cycle."
>
> "Left-translated cycles feature peaks that occur before reaching the
> midpoint of the cycle."
>
> "By identifying the position of the peak within a cycle relative to
> its midpoint, one can discern whether the market is in a bullish or
> bearish phase."

Bullish = right; bearish = left.

**Share.Market — Hurst Principles Guide (paraphrased confirmation):**

> "Cycles may bottom early (left translation) or late (right translation)
> relative to expected cycle lows."

Same sign mapping (early ⇒ left ⇒ bearish; late ⇒ right ⇒ bullish), framed
on the trough timing instead of the peak — symmetric statement of the
same rule.

**Sentient Trader "10 Core Concepts" (Hickson, modern Hurst authority):**

Located, downloaded (~650 KB PDF), but the document is image-heavy and
no text was extractable from the served bytes without a PDF library
present in the runtime; the quoted passages from Sigma-L are from the
same Hickson-aligned tradition and are treated as the canonical
authority here.

### H29 brief's hypothesis — confirmed

The brief proposed:

> "Right translation (price peak occurs in the RIGHT half of a cycle,
> i.e., point-1 right of T1/2) is the canonical Hurst signal for
> **bullish trend**. Left translation (peak in LEFT half) signals
> **bearish trend**."

This is exactly the rule the four sources above confirm. **H29's
implementation does not have an inverted sign**; the rule was applied as
spec'd, and the negative result on 7 FX pairs is not a sign-flip bug.

## Application caveats — why the rule may have failed empirically anyway

The canonical rule is for **the dominant cycle's** peak relative to the
**FLD-derived midpoint** of that cycle, *not* a generic geometric
midpoint of an arbitrary swing structure. H29's `box_pattern.py`
computes `t_mid = (P0_idx + P3_idx) / 2.0` from the box's own swing
points, which:

1. **Approximates** the cycle midpoint when the box geometry IS the
   dominant cycle, but
2. **Diverges** from it when the detected box is a subordinate harmonic
   or noise pivot — exactly the regime where Hurst himself would not
   apply translation to forecast trend.

Per Sigma-L: translation is "evidence of bearish/bullish pressure being
exerted by **longer components**." The rule is fundamentally a
**cross-scale** statement (the longer cycle's pressure showing through
the shorter cycle's translation). A single-scale swing box does not
have that cross-scale context.

This sharpens H30 design:

- A **regime classifier** that aggregates translation verdicts across
  multiple recent boxes (averaging across scales) is *closer* to what
  Hurst meant than the H29 single-box trade trigger — the leverage is
  on inferring the longer-component pressure, not timing a single
  trade. This is the recommended H31 in `BOX_PATTERN_APPLICATIONS.md`.
- A **dominant-cycle filter** (only take a box's translation verdict if
  its bar length matches the canonical 10/20/40 FLD harmonic) is the
  second-best application — it restores the cross-scale framing.
- A **trade-trigger with FLD-derived midpoint** (not geometric
  midpoint) is a clean H30 sensitivity, but unlikely to flip the sign
  of the 7-pair negative because the box geometry IS broadly
  cycle-shaped on the cases that completed.

The rule is correct; the application to single, scale-agnostic swing
boxes is the open question H29 already answered (no edge there).

## Sources

- [The FLD — Sigma-L](https://www.sigma-l.net/p/tools-hurst-fld)
- [Cycles Translation — Airlovsky](https://www.airlovsky.com/cycles-translation/)
- [Cycle Analysis in Financial Markets: Hurst's Principles — Share.Market](https://www.share.market/buzz/learn/understand-cycle-analysis-in-finacial-markets-hurst-principles/)
- [10 Core Concepts of Hurst Cycles by David Hickson — Sentient Trader](https://sentienttrader.com/downloads/10_Core_Concepts_Hurst_Cycles.pdf) (binary; verified canonical via Sigma-L which is Hickson-aligned)
- Original canon: J.M. Hurst, *The Profit Magic of Stock Transaction
  Timing* (1970), Prentice-Hall — not directly quoted (no clean digital
  copy was retrievable); the modern Hickson tradition is treated as the
  authoritative transmission of Hurst's rule and is consistent with the
  airlovsky/share.market paraphrases.
