#!/usr/bin/env python3
"""Regression tests for the OOXML editorial-marks filter.

Renders every `examples/*.qmd` via `q2 render`, unzips the resulting
docx/pptx, and asserts on the structural shape of the produced OOXML
(counts of w:ins/w:del/w:highlight/comment markers, well-formed XML in
every part, and the docx comments.xml content-type/relationship
registrations).

There is no existing test harness in this repo, so this establishes the
precedent: expectations are hand-verified against the actual rendered
output (see the commit history / README for how each was confirmed --
including a LibreOffice headless round-trip and, for docx, visual
inspection of the exported PDF), not derived from the filter's own logic.

Usage: python3 tests/run-tests.py [--q2 PATH_TO_Q2_BINARY]
"""

import argparse
import collections
import re
import shutil
import subprocess
import sys
import tempfile
import xml.dom.minidom
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"


def count(pattern, text):
    return len(re.findall(pattern, text))


def check_xml_well_formed(zf, errors, label):
    for name in zf.namelist():
        if name.endswith(".xml") or name.endswith(".rels"):
            try:
                xml.dom.minidom.parseString(zf.read(name))
            except Exception as e:
                errors.append(f"{label}: {name} is not well-formed XML: {e}")


def docx_assertions(path, expected):
    errors = []
    with zipfile.ZipFile(path) as zf:
        check_xml_well_formed(zf, errors, path.name)
        document_xml = zf.read("word/document.xml").decode("utf-8")
        names = zf.namelist()

        actual = {
            "ins": count(r"<w:ins\b", document_xml),
            "delete": count(r"<w:del\b", document_xml),
            "highlight": count(r'<w:highlight w:val="yellow"', document_xml),
            "comment_range_start": count(r"<w:commentRangeStart\b", document_xml),
            "comment_range_end": count(r"<w:commentRangeEnd\b", document_xml),
            "authors": sorted(re.findall(r'<w:(?:ins|del) [^>]*w:author="([^"]*)"', document_xml)),
        }
        for key, expected_value in expected.items():
            if key == "comments" or key == "comment_ids":
                continue
            if actual.get(key) != expected_value:
                errors.append(
                    f"{path.name}: expected {key}={expected_value}, got {actual.get(key)}"
                )

        expected_comments = expected.get("comments", 0)
        if expected_comments > 0:
            if "word/comments.xml" not in names:
                errors.append(f"{path.name}: expected word/comments.xml to exist")
            else:
                comments_xml = zf.read("word/comments.xml").decode("utf-8")
                actual_comments = count(r"<w:comment\b", comments_xml)
                if actual_comments != expected_comments:
                    errors.append(
                        f"{path.name}: expected {expected_comments} <w:comment> "
                        f"entries, got {actual_comments}"
                    )
                content_types = zf.read("[Content_Types].xml").decode("utf-8")
                if "word/comments.xml" not in content_types:
                    errors.append(
                        f"{path.name}: word/comments.xml missing from [Content_Types].xml"
                    )
                rels = zf.read("word/_rels/document.xml.rels").decode("utf-8")
                if "relationships/comments" not in rels:
                    errors.append(
                        f"{path.name}: comments relationship missing from document.xml.rels"
                    )
                for comment_id in expected.get("comment_ids", []):
                    if f'w:id="{comment_id}"' not in comments_xml:
                        errors.append(
                            f"{path.name}: expected comment id {comment_id!r} in comments.xml"
                        )
        else:
            if "word/comments.xml" in names:
                errors.append(f"{path.name}: unexpected word/comments.xml (no comments expected)")

    return errors


def pptx_assertions(path, expected):
    errors = []
    with zipfile.ZipFile(path) as zf:
        check_xml_well_formed(zf, errors, path.name)
        slide_names = sorted(
            n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)
        )
        combined = "".join(zf.read(n).decode("utf-8") for n in slide_names)

        actual = {
            "underline": count(r'u="sng"', combined),
            "strike": count(r'strike="sngStrike"', combined),
            "highlight": count(r"<a:highlight>", combined),
            "comment_fallback": count(r"C00000", combined),
        }
        for key, expected_value in expected.items():
            if actual.get(key) != expected_value:
                errors.append(
                    f"{path.name}: expected {key}={expected_value}, got {actual.get(key)}"
                )
    return errors


# One entry per example. `docx`/`pptx` map to the assertion dicts checked
# above; omit a format key entirely for examples that don't render it.
EXPECTATIONS = {
    "01-inline-marks.qmd": {
        "docx": dict(ins=2, delete=2, highlight=2, comment_range_start=2,
                      comment_range_end=2, comments=2),
    },
    "02-inline-marks-attributes.qmd": {
        "docx": dict(ins=2, delete=2, highlight=1, comment_range_start=2,
                      comment_range_end=2, comments=2,
                      comment_ids=["comment-id"]),
    },
    "03-block-marks.qmd": {
        "docx": dict(ins=4, delete=2, highlight=5, comment_range_start=2,
                      comment_range_end=2, comments=2),
    },
    "04-mixed-contexts.qmd": {
        "docx": dict(ins=2, delete=3, highlight=2, comment_range_start=2,
                      comment_range_end=2, comments=2),
    },
    "05-comment-on-code.qmd": {
        "docx": dict(ins=0, delete=0, highlight=0, comment_range_start=3,
                      comment_range_end=3, comments=3),
    },
    "07-authors.qmd": {
        "docx": dict(ins=2, delete=2, comment_range_start=1, comment_range_end=1,
                      comments=1, authors=["Eve", "Frank", "Gina", "Hal"]),
    },
    "06-pptx-marks.qmd": {
        "pptx": dict(underline=1, strike=1, highlight=1, comment_fallback=1),
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--q2", default=None, help="path to the q2 binary")
    args = parser.parse_args()

    q2_bin = args.q2
    if q2_bin is None:
        candidate = REPO_ROOT.parent / "q2" / "target" / "debug" / "q2"
        if candidate.exists():
            q2_bin = str(candidate)
        else:
            found = shutil.which("q2")
            if found is None:
                print("error: could not find a q2 binary; pass --q2 PATH", file=sys.stderr)
                return 1
            q2_bin = found

    all_errors = []
    for qmd_name, expected_formats in EXPECTATIONS.items():
        qmd_path = EXAMPLES_DIR / qmd_name
        if not qmd_path.exists():
            all_errors.append(f"{qmd_name}: example file not found")
            continue

        result = subprocess.run(
            [q2_bin, "render", str(qmd_path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            all_errors.append(
                f"{qmd_name}: q2 render failed (exit {result.returncode}):\n"
                f"{result.stdout}\n{result.stderr}"
            )
            continue

        for fmt, expected in expected_formats.items():
            output_path = qmd_path.with_suffix(f".{fmt}")
            if not output_path.exists():
                all_errors.append(f"{qmd_name}: expected output {output_path.name} not found")
                continue
            if fmt == "docx":
                all_errors.extend(docx_assertions(output_path, expected))
            elif fmt == "pptx":
                all_errors.extend(pptx_assertions(output_path, expected))

    if all_errors:
        print(f"FAILED ({len(all_errors)} issue(s)):\n")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print(f"PASSED: {len(EXPECTATIONS)} example(s) rendered and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
