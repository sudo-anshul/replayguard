# Rendered repair-bench review

Reviewed September 19, 2026 using the local site. The visual direction retains ReplayGuard's mist, ink, forest and rust palette. The primary comparison uses candidate columns and business-order rows; it exposes both duplicate receipts and the missing receipt for a different valid order.

## What changed after inspection

- Replaced the old home route with the repair bench, preserving the recorded comparison on its own route.
- Used 18px body text, prominent outcome numerals, and a clear heading hierarchy. Secondary metadata remains smaller than the reading text.
- Ordered the built-in columns as no key, SKU-only key, then business-order key so the loss of ORDER-B is visible beside both alternatives.
- Corrected a narrow-screen grid overflow in the run-kit section. Code and the comparison table scroll within their own regions.
- Fixed missing spaces when responsive CSS hides heading line breaks, retained View JSON at tablet widths, and made the command block keyboard-focusable.
- Preserved imported report bytes and the preceding view after an invalid import. Unknown receipt counts use a dash and explanatory text; they are never shown as zero.

## Verification

The main page was inspected at desktop and narrow sizes, including the populated comparison, candidate finding, missing-observation and unsupported-effect states, run-kit section, and the adapter guide. Automated browser captures and responsive checks cover 320, 390, 768 and 1440 CSS pixels; manual browser inspection also checked the guide at 390px and the main page at 325px. The horizontal comparison region on narrow screens is intentional, with a selected-candidate inspector below it.

The independent browser tests exercised report selection, genuine generated imports, rejected contradictory imports, original-byte downloads, and desktop/narrow rendering. Native edge reports included wrong payloads, repeated receipt reuse, timeout and incomplete executions. The preserved original journey also passed its targeted regression checks. See [transfer evidence](transfer.md) and the [capture manifest](media/capture-manifest.json) for actual test outputs and image provenance.

Three opaque text/background spot checks passed the 4.5:1 normal-text threshold: muted text on paper 5.10:1, violation text on its surface 6.28:1, and success text on its surface 5.94:1. These are individual color-pair checks, not a complete accessibility certification. Native controls, semantic table headings, visible focus, status words/symbols and reduced-motion styling are present. No screen-reader study, human usability test or full cross-browser certification is claimed.

The browser is a report inspector, not the Python execution environment. Evidence badges describe the supplied run; origin remains unauthenticated. The default local sample and dated AWS archive are visibly distinguished.
