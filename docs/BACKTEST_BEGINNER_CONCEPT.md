# Backtest — Beginner Concept

> This document is a **design reference**, not an implementation. No code, table, or
> Supabase data changes because of this file. It records the ideas that must be
> agreed on before the Backtest tab is rewritten for beginners.

Related references: `docs/PRODUCT_CONTEXT.md` (tone and philosophy),
`docs/BACKTEST_ARCHITECTURE.md` (the exact calculation rules),
`docs/CONSENSUS_ARCHITECTURE.md` (which consensus is stored vs computed).

---

## 1. The one idea to plant in the user's head

> **The backtest is a framework's report card on this stock.**
> It is historical evidence, not a forecast. It shows what actually happened to the
> price after the framework called a stock cheap or expensive.

Everything else in the tab exists to support that sentence. If an element does not
help the user understand it, that element is out of scope.

## 2. Mental model — the time machine

The simplest way to explain the backtest to a beginner:

1. **Rewind** to each past quarter of this stock (for example, 2022-Q1).
2. **Freeze** the situation as it was then: five methods estimate fair value, and
   each is compared with the price on that date.
3. **Ask the framework:** "Is this cheap or not?"
4. **Fast-forward 12 months** and look at what the price actually did.
5. **Record the result** as one of the verdicts below.

The list of historical cases is simply a row per "turn of the time machine".

## 3. How the framework decides

The framework is not a single magic formula — it is a process that can be tested.
That is exactly why a backtest exists.

1. **Five estimators.** Five different methods estimate "fair value", each from a
   different angle (Peter Lynch / Adaptive, Type & Sector Weighted,
   Mean-Reversion PBV, Dividend Discount, Discounted Earnings).
2. **Compare to price.** Each fair value is compared with the price at that time.
   A method whose value is above the price says "cheap". A method whose value is
   zero is skipped (for example, DDM for a company that pays no dividend).
3. **Majority vote.** If at least three valid methods say "cheap", the framework
   concludes **UNDERVALUED**; otherwise **OVERVALUED**. The `3|5` figure means
   "3 of 5 valid methods said cheap".
4. **Backup check.** The framework also reads the *Margin of Safety* of the main
   method. If the margin is **30% or higher**, it reads UNDERVALUED; otherwise
   OVERVALUED.
5. **Two signals, one judgement.** When both checks agree the stock is cheap, the
   signal is strongest. When they disagree, it is a mixed signal — which is itself
   worth studying.

## 4. The two signals are different (By Method vs By MoS)

This is the part beginners miss, and it is why the tab shows **two** panels instead
of one.

The framework answers the same question — "is it cheap?" — in two independent ways,
and they can disagree:

- **By Method (consensus of the five estimators).** Counts how many of the valid
  methods value the stock above its price. It is broad: it looks at the whole panel
  of methods, so it captures the overall weight of opinion. It reads UNDERVALUED
  when at least three valid methods say cheap.
- **By MoS (the main method's Margin of Safety).** Looks at only the *single* main
  method and how wide its safety cushion is. It is narrow and stricter: it cares
  about how much discount one trusted method offers, not how many methods agree.

They can, and do, point different ways. A stock can have most methods agreeing it
is cheap while its main method's cushion is still thin (By Method says cheap,
By MoS does not) — or the reverse, a wide cushion on the main method even though
the broader panel is split. **Neither signal is universally "better".** Some stocks
have a higher historical success rate when read by MoS; others by Method. That is
the reason the tab keeps both: the user should see which lens has been more reliable
for *this specific stock*, rather than trusting one blind rule. Showing both is a
feature, not a contradiction.

## 5. Verdict glossary (required — the badges are meaningless without it)

When the framework says **CHEAP (UNDERVALUED):**

| Verdict | Plain meaning | Tone |
|---|---|---|
| **WIN** | The price reached the upside target before the downside target. The framework was right. | Green |
| **RECOVERED** | The price fell to the downside target first, then still rose to the upside target. "Lost first, won later." | Light blue |
| **RISK** | The price fell to the downside target and never reached the upside target. The framework was wrong. | Red |
| **FLAT** | Within 12 months the price touched neither target. Nothing decisive happened. | Grey |

When the framework says **EXPENSIVE (OVERVALUED):**

| Verdict | Plain meaning | Tone |
|---|---|---|
| **CONFIRMED** | The price did fall to the downside target. The framework was right that it was expensive. | Blue |
| **REPRICE** | The price instead rose to the upside target. The market re-rated it; the framework was wrong. | Purple |
| **OBSERVE** | The price moved to neither target. Neutral, nothing to conclude. | Grey |

> "Win or lose" is decided by **which target is touched first** within the 12-month
> window. The upside/downside targets follow the workbook rule (roughly +20% / −20%,
> or +15% / −10% for blue-chip types); see `docs/BACKTEST_ARCHITECTURE.md` for the
> exact per-type figures.

## 6. The summary paragraph (the headline insight)

The single most valuable element: turn the table into plain sentences that read the
evidence back to the user. It must be generated from the actual numbers, and it
must cover **both signals** so the Method/MoS difference is visible.

**Placement:** the paragraph is shown *inside each signal card* (By Method and By
MoS), under a divider line — so the words sit right beside the numbers they explain.
Each card carries its OWN paragraph, and the method name is spelled out inline.

Layout: one plain paragraph, a single text style and a single colour (no per-word
highlighting):

> when StockLens said cheap with **{method phrase}**, the price rose to target
> **{a} times ({a%})**, fell first but eventually recovered **{b} times**, and failed
> (risk) **{c} times**. When it said expensive, the price did fall **{d} times**, and
> instead rose **{e} times**.

`{method phrase}` is `combined valuation methods` on the By-Method card and
`MoS main method` on the By-MoS card.

Rules for this paragraph:

- Numbers are filled from the real data — never hardcoded.
- If the sample is small, the surrounding text says so (see guardrails).
- One short paragraph per card. No per-quarter walkthrough is needed.

The tab header carries the one-line framing (the "Backtest" heading itself is
removed, so the banner is the first thing on the tab):

> **The backtest is a framework's report card on this stock.**
> (sub-line) It is historical evidence, not a forecast. It shows what actually
> happened to the price after the framework called a stock cheap or expensive.

The verdict glossary (§5) is reached from the **Historical Cases** card subtitle, as
a "What each verdict means" link that opens a popup — so it stays available without
taking any permanent vertical space.

## 7. Guardrails (what must be avoided)

Following `docs/PRODUCT_CONTEXT.md`:

- ❌ Never use the words "prediction", "profit", or "buy signal". Use **"historical
  evidence"** and **"past outcomes"** instead.
- ❌ Never hide a small sample — show it. A 3-case record must read as weak evidence,
  not as a track record.
- ❌ Never claim "this framework is accurate". Show the numbers and let the user judge.
- ✅ Always remind the reader: **past outcomes are not a guarantee of the future.**

## 8. Explicitly out of scope (for now)

- No per-quarter, step-by-step worked example in the beginner view. The one summary
  paragraph per signal is enough.
- No change to any calculation rule — this document only describes how the existing
  results should be *explained*.
- No new data source; everything is derived from what the backtest already stores.

