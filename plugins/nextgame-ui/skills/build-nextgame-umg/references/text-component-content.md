# Text component content and granularity

These rules were explicitly supplied by the project owner on 2026-07-23. Treat them as authoritative.

## Text-only content

- Put only readable text in a `TextBlock`: Chinese characters, letters, numbers, whitespace between words, punctuation, and common textual symbols.
- Do not put icons, pictographs, arrows, geometric markers, controller glyphs, or decorative line characters in a `TextBlock`.
- Represent an icon or marker with a project `GameImage` component even when a Unicode character visually resembles it.
- Represent a horizontal rule, underline, divider, frame segment, or other decoration with a project `GameImage` component.
- Do not construct a divider by repeating hyphens, underscores, box-drawing glyphs, or similar characters.

Example:

```text
PanelTaskHeader
├─ TxtTaskTitle              text: 任务
└─ ImgTaskTitleSeparator     thin horizontal image
```

## One visual text block per component

- Create one `TextBlock` for every independently bounded text block recognized in the reference image.
- Split titles, descriptions, objective rows, player names, category names, item names, counts, timers, and navigation labels into separate components when they occupy separate visual bounds.
- Do not combine a menu, legend, task group, or row collection into one multiline `TextBlock`.
- Do not use tabs, manual line breaks, or repeated spaces to align multiple labels inside one component.
- Keep a continuous paragraph in one `TextBlock`; store its source text without manual line breaks and enable `autoWrap` when it must wrap within its bounds.
- Use separate components when different lines need independent layout, styling, visibility, data binding, or replacement.
- The same rule applies within one line: risk/category, message count/folding status, or separately authored objective phrases are independent fields, not one combined string. Split by meaning and control/layout responsibility, never merely by a slash, colon or middle dot. Keep a grammatical sentence, number with its unit, URL and continuous localized paragraph intact unless independently controlled parts are evidenced.
- For an accepted `semanticTextGroup` pair, create exactly the two reviewed TextBlocks directly under the reviewed HorizontalBox. Preserve distinct requirement/runtime mappings, source copy, order, capacity and explicit flow Slots. Use native content-driven right alignment for a right-edge group; do not add a SizeBox for alignment. A positive inter-field padding replaces a presentation-only separator when approved.
- Do not use a measured glyph-ink width as the available paragraph width. Fit against the actual parent allocation. A short pair intended as one row uses no wrapping and a width budget including both fields and the gap; a continuous description uses the full available width and explicit wrapping. Deliberately independent lines use independent TextBlocks and an explicit vertical layout, not embedded newlines.
- Include exact-length readable character-capacity samples in design evidence, for example a seven-character sample `这是五个字这是`. Character capacity is a design budget, not a claim of native font-metric validation; verify actual rendered fit after px-to-point conversion, empty/long values, and wider/taller layouts.
- Declare the source `fontSizeUnit` on each new text node. Preserve source px values and use positive even pt values; follow the 96 DPI conversion and compensation rule in `common-widget-rules.md` under `Even font sizes`.
- Set `Wrap Text At` to a concrete positive value whenever the text is intended to wrap; do not leave it at `0`.
- To turn wrapping off on an existing single-line component, explicitly lower both `autoWrap:false` and `wrapTextAt:0`. Omitting the width does not clear a previous positive Unreal width. Zero is valid only with explicit no-wrap; wrapped paragraphs still require a positive width.
- Plan expandable text bounds and related backgrounds for longer localized strings as defined in `common-widget-rules.md`.

## Validation expectations

- Reject tab and newline characters in authored TextBlock content.
- Reject repeated spaces used as layout.
- Reject icon-like or decorative Unicode glyphs.
- Reject repeated-character separators.
- Allow visual wrapping only through TextBlock layout such as `autoWrap`, not through manually authored line breaks.
