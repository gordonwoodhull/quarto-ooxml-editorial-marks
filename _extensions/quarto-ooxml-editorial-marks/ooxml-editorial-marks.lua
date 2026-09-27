-- ooxml-editorial-marks.lua
--
-- Translates Quarto's editorial-mark AST nodes into native Office Open XML
-- (OOXML) comments and track-changes markup for docx, and their PowerPoint
-- equivalent for pptx.
--
-- Quarto's qmd syntax --
--   [++ text]   / ::: ++   -> insertion
--   [-- text]   / ::: --   -> deletion
--   [!! text]   / ::: !!   -> highlight
--   [>> text]   / ::: >>   -> comment
-- -- is desugared by pampa (see q2's crates/pampa/src/pandoc/treesitter_utils/
-- postprocess.rs and editorial_div.rs) into plain Pandoc Span (inline) or Div
-- (block) nodes whose *first* class is one of:
--   quarto-insert | quarto-delete | quarto-highlight | quarto-edit-comment
-- Any user-supplied classes follow after that first class. id and key-value
-- attributes survive verbatim -- quarto-edit-comment spans/divs commonly
-- carry author= and date= (see q2's crates/quarto-core/src/document_profile.rs
-- for the canonical shape hub-client relies on).
--
-- This filter is registered at `at: post-quarto` in _extension.yml, i.e.
-- after Quarto's own crossref/preprocessing but before layout. Nested
-- constructs (a comment wrapping a callout, panel, or tabset) are NOT
-- guaranteed to be in their final resolved form at this point -- if that
-- turns out to matter, move the `at:` entry point to `post-render` instead
-- (see the extension's README for the tradeoff).
--
-- pptx note: Pandoc's PowerPoint writer path (render_pptx_fixups in the
-- vendored quarto-post filters) strips any RawBlock/RawInline that isn't
-- tagged "openxml". Always emit `pandoc.RawBlock("openxml", ...)` /
-- `pandoc.RawInline("openxml", ...)` here, never a bare "docx"/"raw" format.

if not (FORMAT == "docx" or FORMAT == "pptx") then
  return {}
end

-- TODO(next session): implement the actual OOXML translation below. Each
-- handler currently passes the element through unchanged (Pandoc's docx/pptx
-- writers already render Span/Div content and silently drop unknown classes,
-- so leaving these as no-ops is safe, just not yet doing the real job).

local function first_class(el)
  return el.classes[1]
end

--- TODO: emit a Word `<w:ins>` run (docx) wrapping el.content, with
--- w:author/w:date/w:id taken from el.attributes.author / el.attributes.date
--- when present. See resources/pandoc-filters/filters/layout/docx.lua in q2
--- (calloutDocx) for the closest existing precedent for hand-built OOXML via
--- pandoc.RawBlock("openxml", ...) / pandoc.RawInline("openxml", ...).
--- pptx has no native "tracked insertion" concept -- decide on a fallback
--- (e.g. a run with a distinct highlight color, or a plain pass-through).
local function handle_insert(el)
  return nil
end

--- TODO: emit a Word `<w:del>` run wrapping a `<w:delText>` (docx). Deleted
--- content must NOT appear as ordinary visible text once this is implemented.
--- pptx: decide on a fallback, as with insertions above.
local function handle_delete(el)
  return nil
end

--- TODO: emit a Word run with `<w:highlight w:val="..."/>` shading (docx),
--- or the pptx run-properties equivalent.
local function handle_highlight(el)
  return nil
end

--- TODO: emit an OOXML comment anchor + `<w:commentReference>` (docx), or
--- the pptx comment equivalent, using el.attributes.author / .date for the
--- comment's metadata. Requires also emitting the referenced `w:comment`
--- into word/comments.xml (and its relationship/content-type entries) --
--- Pandoc's Lua filter API has no first-class support for adding new parts
--- to the docx zip archive, so this will likely need a companion
--- post-processing step outside the filter itself (e.g. a q2 stage that
--- unzips the produced .docx, injects comments.xml, and rezips). See
--- q2's crates/quarto-core/src/document_profile.rs for the existing
--- quarto-edit-comment extraction logic (ProfileComment) as a model for
--- collecting comment text/author/date; it does NOT currently write OOXML,
--- but its extraction shape is a reasonable starting point.
---
--- Also note the "comment on a code block" idiom: a
--- `.quarto-edit-comment-container` Div wrapping a CodeBlock plus a trailing
--- `[>> ... ]` mark represents one comment anchored to that code, not a
--- comment-about-itself (see document_profile.rs's nested-comment test).
--- Word has no native concept of commenting on a fenced code block; the
--- rendered code text is the most likely anchor range.
local function handle_edit_comment(el)
  return nil
end

local dispatch = {
  ["quarto-insert"] = handle_insert,
  ["quarto-delete"] = handle_delete,
  ["quarto-highlight"] = handle_highlight,
  ["quarto-edit-comment"] = handle_edit_comment,
}

local function dispatch_element(el)
  local handler = dispatch[first_class(el)]
  if handler then
    return handler(el)
  end
  return nil
end

return {
  {
    Span = dispatch_element,
    Div = dispatch_element,
  },
}
