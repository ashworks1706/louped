---
name: ground-claims
description: Ground every number and citation in a louped write-up in the project's runs and sources/, then run check. Use whenever you state a result, cite a paper, or look something up for the person.
---

A claim the reader cannot follow back to its evidence is not finished. Each number points at the
run or file it came from, and each citation points at a pinned passage.

## Find the source before the web

1. Search the project first. Call `search_sources` with the paper's words or title, then
   `source_page` to read the page.
2. If the paper is not there, fetch it from its primary source only: its arXiv page, the ACL
   Anthology, or the publisher's open PDF. Keep it with `add_source` (the URL is recorded with the
   file). Never cite a blog post, a summary or your memory of a paper.
3. If you cannot get the paper, say so and leave the claim out or mark it "not checked".

## Pin what a claim rests on

- `pin` the exact words the claim rests on, as `source_page` shows them. Add a note that says
  what they support, and `links` to the experiment or run (`experiment:<name>`, `run:<id>`). A
  paraphrase is refused.
- Cite the page in Markdown as `[@<key> p<page>]`. The app shows the pinned words on hover.
- Quote no more than the claim needs.

## Put the ref beside the number

- Put the ref of a result number (0.92, 78%, 12/40) in the same paragraph, list item or table
  (a table counts with the paragraph above it). The ref is where the number came from:
  `run:<id>`, `run:<id>/<file>`, or a figure's `run:<id>/views/<name>.json`. For a number taken
  from a paper, the citation is the source.
- `trace` a ref when you need its rows, script or commit, and quote them exactly.
- Whole numbers (counts, years, layer indices) need no ref. But say where a count came from.
- Write versions, paths and ids in `code` (`torch 2.1`, `layer 12/32`): check reads only prose.

## Check before handing over

Run `check` (or `louped check`) on what you wrote. Fix every issue: add the ref, pin the passage,
or correct the ref. If you cannot source a number, remove it, or tell the person which numbers
you could not source. Do not reword a number to get past the check.
