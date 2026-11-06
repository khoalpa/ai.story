"""Citation exports and dependency invalidation for canonical summaries."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from studio.summary_schema import validate_summary_document


def _require(summary: Mapping[str, Any]) -> None:
    errors = validate_summary_document(summary)
    if errors:
        raise ValueError("summary.json không hợp lệ: " + "; ".join(errors))


def export_citations(summary: Mapping[str, Any], style: str | None = None) -> str:
    """Export conservative citations; never invent missing bibliographic fields."""
    _require(summary)
    selected = style or summary["meta"].get("citation_style") or "MARKDOWN"
    if selected not in {"MARKDOWN", "APA", "MLA", "CHICAGO", "BIBTEX"}:
        raise ValueError(f"Citation style không hỗ trợ: {selected}")
    rows: list[str] = []
    for index, source in enumerate(summary["sources"], 1):
        authors = list(source.get("authors") or [])
        author_text = ", ".join(authors) if authors else "Không rõ tác giả"
        title = str(source["title"])
        date = source.get("published_at") or "n.d."
        publisher = source.get("publisher")
        url = source.get("url")
        accessed = source.get("accessed_at")
        if selected == "MARKDOWN":
            suffix = f" [{url}]({url})" if url else ""
            rows.append(f"[^{index}]: {author_text}. *{title}*. {date}.{suffix}")
        elif selected == "APA":
            suffix = f" {publisher}." if publisher else ""
            suffix += f" {url}" if url else ""
            rows.append(f"{author_text}. ({date}). *{title}*.{suffix}")
        elif selected == "MLA":
            pieces = [f'{author_text}. "{title}."']
            if publisher:
                pieces.append(str(publisher) + ",")
            pieces.append(str(date) + ".")
            if url:
                pieces.append(str(url) + ".")
            if accessed:
                pieces.append(f"Accessed {accessed}.")
            rows.append(" ".join(pieces))
        elif selected == "CHICAGO":
            suffix = f" {publisher}," if publisher else ""
            suffix += f" {date}."
            suffix += f" {url}." if url else ""
            rows.append(f"{author_text}. *{title}*.{suffix}")
        else:
            key = f"source{index:03d}"
            fields = [f"  title = {{{title}}}", f"  year = {{{date}}}"]
            if authors:
                fields.insert(0, f"  author = {{{' and '.join(authors)}}}")
            if publisher:
                fields.append(f"  publisher = {{{publisher}}}")
            if url:
                fields.append(f"  url = {{{url}}}")
            rows.append("@misc{" + key + ",\n" + ",\n".join(fields) + "\n}")
    return "\n\n".join(rows) + ("\n" if rows else "")


DEPENDENCY_ORDER = (
    "summary.json",
    "summary_report.md",
    "summary_narration.txt",
    "story.json",
    "story.txt",
    "summary_visual_plan.json",
    "visual_plan.json",
    "summary_image_prompts.json",
    "image_prompts.json",
    "summary_video_prompts.json",
    "video_prompts.json",
    "summary_render_plan.json",
    "rendered_media",
    "summary_render_log.json",
    "summary_media_review.json",
    "summary_manifest.json",
    "summary_package.zip",
)


def affected_artifacts(changed_kinds: Iterable[str]) -> tuple[str, ...]:
    """Return the conservative rebuild set for changed canonical node kinds."""
    changed = set(changed_kinds)
    known = {
        "source",
        "locator",
        "section",
        "claim",
        "numeric_fact",
        "glossary",
        "narration",
        "scene",
        "style",
    }
    unknown = changed - known
    if unknown:
        raise ValueError("Dependency kind không hỗ trợ: " + ", ".join(sorted(unknown)))
    if changed & {"source", "locator", "section", "claim", "numeric_fact", "glossary"}:
        start = 0
    elif "narration" in changed:
        start = DEPENDENCY_ORDER.index("summary_narration.txt")
    elif changed & {"scene", "style"}:
        start = DEPENDENCY_ORDER.index("summary_visual_plan.json")
    else:
        return ()
    return DEPENDENCY_ORDER[start:]


__all__ = ["DEPENDENCY_ORDER", "affected_artifacts", "export_citations"]
