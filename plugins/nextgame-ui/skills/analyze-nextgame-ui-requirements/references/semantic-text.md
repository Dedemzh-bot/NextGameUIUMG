# Semantic text granularity

First identify meaning, then choose components. Separate fields when their data, replacement, style, alignment, visibility or authored objective meaning is independent, even on one visual line. Keep continuous prose, units attached to numbers and punctuation inside grammatical phrases intact. Punctuation is evidence to inspect, not a splitter algorithm. Do not create one Widget per character.

Examples: `风险：中等 / 标准探索` is risk information plus exploration category; `3 条 · 已折叠` is a count plus presentation status. `探索边境 · 收集余波` may be two independently authored objectives when the user confirms that reading. Conversely a sentence explaining one event is normally one full-width paragraph.

## Machine-readable single-row pair

For an explicitly accepted two-field row, add this closed object to its semantic horizontal panel's `properties.semanticTextGroup`:

```json
{
  "kind": "semantic-pair",
  "reason": "Two independently authored objective fields; user-authorized display split.",
  "sourceCombinedText": "探索边境 · 收集余波",
  "partNames": ["TxtObjectiveA", "TxtObjectiveB"],
  "gapPx": 16,
  "availableWidthPx": 416,
  "maxChars": [8, 8],
  "capacitySamples": ["这是五个字这是五", "这是五个字这是五"]
}
```

These are instance-reviewed values, not universal hardcoded coordinates. The owning panel has `kind: panel`, `layoutRole: container.horizontal` and exactly two direct text elements named by `partNames`. Each child declares `wrap: false`, its own `runtimeControlled` decision, explicit alignment and `panelSlotIntent`; first child Padding is zero, second left Padding equals `gapPx`, other sides zero. Count the capacity sample exactly. Do not fill production content with the capacity sample unless producing a dedicated capacity-test preview.

The Requirement validator checks this contract whenever declared. Bundle coverage checks enforce two distinct, ordered, same-parent TextBlock realizations and exact sample/no-wrap lowering. An old requirement without this metadata remains readable, but new paired fields must declare it. These checks supplement semantic review; they do not discover every compound sentence automatically or prove actual glyph fit.

Use the full allowed width of the immediate parent; never treat screenshot ink width as a text-box width limit. Reserve enough width for both fields plus spacing. Prefer native Slot alignment/Auto Size, use weighted Fill only for actual remaining-space allocation, and add no alignment-only SizeBox. If capacity changes, revise the accepted budget and verify live layout; do not silently force short wrapping or truncate critical numeric data.

Continuous paragraphs are outside this pair contract: keep one TextBlock, natural text without manually authored line breaks, explicit positive wrap width and a content-height growth policy. More than two fields or a deliberate multiline group requires a separately reviewed composition rather than disguising it as a pair. No new runtime API, callback, state machine, collection, or asset boundary is implied by splitting display fields.
