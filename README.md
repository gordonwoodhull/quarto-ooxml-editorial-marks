# quarto-ooxml-editorial-marks

A Quarto 2 extension that translates Quarto's editorial-mark syntax
(insertions, deletions, highlights, and comments) into native Office Open XML
track changes and comments for `docx` output, with a visual fallback for
`pptx`.

```
[++ inserted text]   / ::: ++   ->  Word tracked insertion
[-- deleted text]    / ::: --   ->  Word tracked deletion
[!! highlighted]     / ::: !!   ->  Word highlight
[>> a comment]       / ::: >>   ->  Word comment
```

## Usage

Copy `_extensions/quarto-ooxml-editorial-marks/` into your project and list
the extension in the project's `filters:` (see `_quarto.yml`). It requires
Quarto 2.

### Authors and dates

Any mark except a highlight can carry `author=` and `date=` (an ISO 8601
timestamp), which become `w:author` and `w:date` in the docx:

```
Bob changes [-- old]{author="Bob Builder" date="2026-02-11T11:30:00Z"}[++ new]{author="Bob Builder"} text.

::: >> {author="Carol Critic"}
A block comment.
:::
```

Without `author=`, Word shows the author as "unknown" for insertions and
deletions.

### Authors from git

Rendering with q2's git attribution fills in the author and date of every
mark that doesn't set them itself, from `git blame` on the mark's source
lines:

```
q2 render doc.qmd --to docx --attribution=git
```

Each person who committed marks then appears as a separate author in Word's
Review pane. The name defaults to the local part of the committer's email;
to use full names, map the emails in the document or project metadata
(both `name` and `color` are required, or the entry is ignored):

```yaml
attribution:
  identities:
    bob@example.com: {name: Bob Builder, color: "#cc0000"}
```

Attribution data is available to docx and pptx from the q2 release that
includes
[q2 #781](https://github.com/quarto-dev/q2/pull/781) onwards. Without
`--attribution=git`, or where a mark's lines can't be blamed (uncommitted
text), the mark is left as written. Explicit `author=` and `date=`
attributes always win. Highlights have no author in OOXML, and pptx output
ignores authors.

## Layout

- `_extensions/quarto-ooxml-editorial-marks/_extension.yml` — the manifest.
  It contributes two filters:
  - `ooxml-editorial-marks.lua` at `post-quarto` rewrites the marks. It
    handles docx and pptx and does nothing for other formats.
  - `stamp-attribution.lua` at `pre-quarto` copies git-blamed author and
    date onto the marks (see below).
- `_quarto.yml` — activates the filters project-wide.
- `examples/*.qmd` — documents exercising the marks: inline and block forms,
  attributes, nesting (including a comment inside another mark), marks inside
  lists, quotes, tables and headings, a comment on a code block, explicit
  authors (`07`, `08`), and one pptx document (`06`).
- `tests/run-tests.py` — renders every example with `q2 render` and asserts
  on the structure of the produced OOXML: mark counts, authors,
  `comments.xml` registration, and well-formed XML in every part.

```
python3 tests/run-tests.py --q2 /path/to/q2/target/debug/q2
```

## How it works

### docx

Pandoc's docx writer has native support, not described in its manual, for
exactly the classes needed:

- A `Span` whose classes include `insertion` becomes `<w:ins>`, and
  `deletion` becomes `<w:del>`/`<w:delText>`. `w:id` is numbered by pandoc;
  `w:author` and `w:date` come from the span's `author=` and `date=`
  attributes. Other classes and attributes on the span pass through.
- A **bare** `Span` — no id, a single class `mark`, no attributes — becomes
  a run with `<w:highlight w:val="yellow"/>`. Any extra id, class or
  attribute makes it fall through with no highlight, so the highlight
  handler drops them.
- A `Span` with class `comment-start` emits `<w:commentRangeStart>`, and its
  *content* becomes the comment text in `word/comments.xml`. A matching
  `comment-end` span (same `id`) emits `<w:commentRangeEnd>` and the
  `<w:commentReference>`. Pandoc generates `comments.xml`, its content-type
  override and the relationship itself.

So the filter only ever returns AST nodes; there is no zip-level
post-processing.

The writer ignores the classes on a `Div`. Block marks are therefore handled
by wrapping the inline content of each leaf paragraph (or header) in the same
span. A block comment is the exception: its content is also kept as the
comment's message, with the range markers spliced onto its first and last
blocks.

### Nesting

- A mark nested inside an insertion, deletion or highlight is converted
  independently. A comment inside a block insertion is a real, separate Word
  comment.
- A mark nested inside a **comment** folds into the comment's plain-text
  message. This matches q2's `document_profile.rs`, which treats everything
  inside a `quarto-edit-comment` as a leaf.

Pandoc's `traverse = "topdown"` walk does not descend into a `Blocks` or
`Inlines` list returned as a replacement, and most handlers return such a
list. The block-wrapping helper (`wrap_blocks_with_span`) therefore
dispatches nested marks itself instead of leaving them to the walker.
Comments rely on the opposite: they keep their original content unvisited,
so nested marks are left with their `quarto-*` class, which neither this
filter nor pandoc recognises, and render as text.

### A comment on a code block

`.quarto-edit-comment-container` has no special meaning. The extractor in
`document_profile.rs` treats a `[>> ... ]` mark after a code block as its own
independent comment, with no text from the code block. This filter does the
same: the code block renders untouched, with its syntax highlighting, and the
comment becomes a standalone `<w:comment>`. See `examples/05-comment-on-code.qmd`.

### Authorship stamping

The docx filter runs in a real `pandoc` subprocess (q2's Pandoc-hybrid
render path), which has neither `quarto.attribution` nor source positions.
`stamp-attribution.lua` runs earlier, at `pre-quarto`, inside q2's own Lua
engine where both exist. For each insertion, deletion and comment it calls
`quarto.attribution.lookup(el)` and, on a hit, sets `author` (the identity's
`name`) and `date` (`time`, epoch seconds, as UTC ISO 8601) unless the
source already set them. The docx filter then carries those attributes into
OOXML like any others. When `lookup` returns nil the mark is untouched.

Block insertions and deletions carry `author` and `date` onto their wrapping
span too, since the Div's own attributes are otherwise ignored by the writer.

### pptx

The pptx writer has no handling for any of these classes, and PowerPoint
comments are anchored to a slide position rather than a text range, which an
AST filter can't express. The filter instead emits raw OOXML runs
(`pandoc.RawInline("openxml", ...)`):

- insertion → underlined run (`u="sng"`)
- deletion → strikethrough run (`strike="sngStrike"`)
- highlight → `<a:highlight>` with `FFFF00`
- comment → a bracketed, italic, dark-red inline annotation, not a real
  PowerPoint comment

Each is a single flattened run built with `pandoc.utils.stringify`, so
rich formatting inside a pptx mark is lost. See `examples/06-pptx-marks.qmd`.

## AST shape

q2's markdown parser (`pampa`) turns each mark into a Pandoc `Span` (inline)
or `Div` (block) whose first class is `quarto-insert`, `quarto-delete`,
`quarto-highlight` or `quarto-edit-comment`; user classes follow. The id and
key-value attributes are preserved. There is no substitution mark; a
deletion followed by an insertion (`[-- old][++ new]`) serves as one.

The docx and pptx filter is registered at `post-quarto`, after crossref and
other preprocessing but before layout. A comment wrapping a callout, panel or
tabset may not be in its final form there; no example covers that case. If
it matters, move `at:` to `post-render`.
