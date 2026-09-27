# quarto-ooxml-editorial-marks

A Quarto 2 extension that translates Quarto's editorial-mark syntax
(insertions, deletions, highlights, and comments) into native Office Open XML
(OOXML) track-changes markup and comments for `docx` and `pptx` output.

```
[++ inserted text]   / ::: ++   ->  Word tracked insertion
[-- deleted text]    / ::: --   ->  Word tracked deletion
[!! highlighted]     / ::: !!   ->  Word highlight
[>> a comment]       / ::: >>   ->  Word/PowerPoint comment
```

## Status

**Infrastructure only — the actual OOXML translation is not implemented
yet.** This repo currently has:

- `_extensions/quarto-ooxml-editorial-marks/_extension.yml` — the extension
  manifest, contributing a single Lua filter at `at: post-quarto`.
- `_extensions/quarto-ooxml-editorial-marks/ooxml-editorial-marks.lua` — a
  filter skeleton. It format-gates on `docx`/`pptx`, dispatches `Span`/`Div`
  nodes by class, and has one `TODO`-documented no-op handler per mark type
  (`handle_insert`, `handle_delete`, `handle_highlight`,
  `handle_edit_comment`). Each stub's doc comment describes what OOXML it
  needs to emit and points at relevant precedent in the `q2` monorepo.
- `_quarto.yml` — activates the filter project-wide (`filters:
  [quarto-ooxml-editorial-marks]`), so every example under `examples/`
  already exercises the filter's format-gate/dispatch path once you run
  `quarto render`.
- `examples/*.qmd` — five documents (`format: docx`) exercising inline and
  block forms of every mark type, attributes (`author=`/`date=` on
  comments), nested marks, marks inside lists/quotes/tables/headings, and
  the "comment anchored to a code block" idiom.

## Background (from research against the q2 monorepo, 2026-09-27)

This extension targets **q2**, the Rust rewrite of Quarto at
`~/src/q2` — not Quarto 1 / the TypeScript `quarto-cli`. Some things that
research turned up, worth knowing before implementing:

- **AST shape**: q2's markdown parser (`pampa`) desugars all four mark
  syntaxes into plain Pandoc `Span` (inline) / `Div` (block) nodes whose
  first class is `quarto-insert`, `quarto-delete`, `quarto-highlight`, or
  `quarto-edit-comment`. User-supplied classes follow after. `id` and
  key-value attributes survive verbatim — comments commonly carry
  `author=`/`date=`. There is no separate "substitution" mark; a
  delete-then-insert pair (`[-- old][++ new]`) is the idiom for it.
  (q2: `crates/pampa/src/pandoc/treesitter_utils/postprocess.rs`,
  `editorial_div.rs`; class convention also documented in
  `crates/quarto-core/src/document_profile.rs`.)

- **Filter activation mechanism**: q2 has two different ways an extension
  can contribute a Lua filter — a top-level `contributes.filters:` (activated
  when the *consuming project* lists the extension by name in its own
  `filters:` metadata, regardless of output format) and a per-format
  `contributes.formats.<fmt>.filters:` (activated only when the format name
  itself references the extension, e.g. `format: someext-docx`). This
  extension uses the **top-level** mechanism — the per-format one would have
  required inventing a new format name, which is a much bigger ask of
  consuming projects than just adding `filters: [quarto-ooxml-editorial-marks]`.

- **The filter runs as real Lua in a real `pandoc` subprocess** for docx/pptx
  (q2's "Pandoc-hybrid render leg"), not through pampa's own restricted Lua
  engine — so ordinary Quarto 1 / Pandoc filter-authoring knowledge and Lua
  filter API docs apply directly.

- **`at: post-quarto`** was chosen (over `pre-render`/`post-render`) so the
  filter sees the fully quarto-preprocessed document (crossrefs resolved,
  etc.) before layout runs. Caveat: nested constructs — a comment wrapping a
  callout, panel, or tabset — are **not** guaranteed to already be in their
  final resolved AST shape at this point. If OOXML output for a mark wrapping
  one of those looks wrong, the fix is likely to move `at:` to `post-render`
  (after q2's layout/panel/callout processing), not to patch around it in
  this filter.

- **pptx sharp edge**: q2's PowerPoint post-processing
  (`render_pptx_fixups`, in the vendored filter tree) strips any
  `RawBlock`/`RawInline` that isn't tagged format `"openxml"`. Always emit
  `pandoc.RawBlock("openxml", ...)` / `pandoc.RawInline("openxml", ...)` —
  never a bare `"docx"` or generic raw format — or the output will be
  silently dropped for pptx.

- **Comments are the hard part.** Unlike insert/delete/highlight (which can
  plausibly be expressed as inline run markup — `<w:ins>`, `<w:del>`, run
  shading), a real Word/PowerPoint comment requires a `<w:commentReference>`
  anchor in the document body *and* a corresponding entry in
  `word/comments.xml`, plus content-type/relationship registrations in the
  `.docx` zip's `[Content_Types].xml` and `_rels`. Pandoc's Lua filter API has
  no first-class way to add new parts to the output zip archive. This will
  likely need a companion step outside the filter itself — e.g. a
  post-processing pass that unzips the produced `.docx`/`.pptx`, injects the
  comments part, fixes up relationships, and rezips. q2's
  `crates/quarto-core/src/document_profile.rs` already has comment
  *extraction* logic (`ProfileComment`, gathering text/author/date per
  comment for its hub-client review UI) that's a reasonable model for
  collecting the same data here — it does not currently write any OOXML.

- **No prior design work exists** for docx/OOXML export of these marks in
  the q2 monorepo — this is new ground, not a partially-done feature to pick
  up.

## Next steps for implementation

1. Confirm the `at: post-quarto` vs `post-render` choice against a real test
   case (a comment/insert/delete wrapping a callout or panel).
2. Implement `handle_insert`/`handle_delete`/`handle_highlight` — these only
   need to emit OOXML into the existing document body, no zip-level surgery.
3. Implement `handle_edit_comment` — this is the one that needs the
   zip-level comments-part injection described above; scope it as a
   post-render step (either inside this filter's Lua, if Pandoc's API turns
   out to support raw zip-entry injection some way, or as an external
   post-processing step invoked after `quarto render`).
4. Extend the `examples/` documents (or add new ones) as regression fixtures
   once real output can be diffed/inspected — e.g. via `docx2txt`/unzipping
   the produced file and asserting on `word/document.xml` /
   `word/comments.xml` contents.
