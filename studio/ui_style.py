"""Shared visual language for every workspace in the Studio shell."""
from __future__ import annotations

STUDIO_STYLE = """
<style>
:root {
    --studio-space-1: 0.5rem;
    --studio-space-2: 0.75rem;
    --studio-space-3: 1rem;
    --studio-space-4: 1.5rem;
    --studio-radius-control: 0.5rem;
    --studio-radius-surface: 0.75rem;
    --studio-border: color-mix(in srgb, currentColor 14%, transparent);
    --studio-border-soft: color-mix(in srgb, currentColor 9%, transparent);
    --studio-primary-soft: color-mix(in srgb, #4f7fc4 14%, transparent);
    --studio-success: #19733a;
    --studio-warning: #946200;
    --studio-error: #b42318;
}

/* Hide transitional copies when Streamlit reruns a workspace. */
[data-testid="stElementContainer"][data-stale="true"] {
    display: none !important;
}

/* Global rhythm and typography. */
[data-testid="stMainBlockContainer"] {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}
[data-testid="stMainBlockContainer"] > div {
    gap: var(--studio-space-3);
}
h1, h2, h3 {
    letter-spacing: -0.018em;
}
h1 { font-weight: 600; }
h2, h3 { font-weight: 600; }
[data-testid="stCaptionContainer"] {
    opacity: 0.78;
}

/* Sidebar: one navigation grammar across all modules. */
[data-testid="stSidebar"] [data-testid="stRadio"] > label {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    opacity: 0.7;
}
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
    gap: 0.2rem;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
    min-height: 2.5rem;
    padding: 0.55rem 0.7rem;
    border-radius: var(--studio-radius-control);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
    background: var(--studio-primary-soft);
    font-weight: 600;
}

/* Inputs and actions share the same geometry. */
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
[data-testid="stFileUploaderDropzone"],
[data-testid="stDateInput"] > div {
    border-radius: var(--studio-radius-control) !important;
}
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {
    min-height: 2.45rem;
    border-radius: var(--studio-radius-control);
    font-weight: 600;
}

/* Local navigation uses one compact selected state. */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 0.25rem;
    border-bottom: 1px solid var(--studio-border-soft);
}
[data-testid="stTabs"] button[role="tab"] {
    min-height: 2.5rem;
    padding-inline: 0.75rem;
    border-radius: var(--studio-radius-control) var(--studio-radius-control) 0 0;
}
[data-testid="stSegmentedControl"] {
    margin-bottom: 0.25rem;
}
[data-testid="stSegmentedControl"] button {
    min-height: 2.4rem;
}

/* Summary metrics are the only repeated card surface. */
[data-testid="stMetric"] {
    height: 100%;
    padding: 0.8rem 0.9rem;
    border: 1px solid var(--studio-border);
    border-radius: var(--studio-radius-surface);
    background: color-mix(in srgb, currentColor 2.5%, transparent);
}
[data-testid="stMetricLabel"] {
    font-size: 0.78rem;
    opacity: 0.76;
}
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] * {
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
    min-width: 0;
    max-width: none !important;
    font-size: clamp(1.15rem, 1.55vw, 1.55rem) !important;
    line-height: 1.2;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    overflow-wrap: anywhere;
    word-break: normal;
    -webkit-line-clamp: unset !important;
    -webkit-box-orient: initial !important;
    mask-image: none !important;
}

/* Status and bounded detail surfaces. */
[data-testid="stAlert"] {
    border-radius: var(--studio-radius-surface);
    border-width: 1px;
}
[data-testid="stExpander"] {
    border: 1px solid var(--studio-border) !important;
    border-radius: var(--studio-radius-surface) !important;
    overflow: hidden;
}
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border: 1px solid var(--studio-border-soft);
    border-radius: var(--studio-radius-surface);
    overflow: hidden;
}
[data-testid="stCodeBlock"] {
    border-radius: var(--studio-radius-surface);
}
hr {
    border-color: var(--studio-border-soft) !important;
}

/* Shared artifact/report masthead. */
.story-heading, .sv-heading, .pqr-heading, .sa-heading {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--studio-space-3);
    padding: 1rem 1.1rem;
    border: 1px solid var(--studio-border);
    border-radius: var(--studio-radius-surface);
    margin: 0.25rem 0 1rem;
}
.story-heading h2, .sv-heading h2, .pqr-heading h2, .sa-heading h2 {
    margin: 0.1rem 0 0.2rem;
    font-size: 1.45rem;
}
.story-eyebrow, .sv-eyebrow, .pqr-eyebrow, .sa-eyebrow {
    font-size: 0.75rem;
    opacity: 0.68;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.story-muted, .story-cue, .sv-muted, .pqr-muted, .sa-muted {
    font-size: 0.82rem;
    opacity: 0.7;
}
.story-duration, .sv-verdict, .pqr-verdict, .sa-verdict {
    white-space: nowrap;
    padding: 0.45rem 0.7rem;
    border-radius: 999px;
    font-weight: 600;
}
.story-duration {
    color: #725024;
    background: rgba(180, 130, 60, 0.14);
}
.sv-pass, .pqr-pass {
    color: var(--studio-success);
    background: rgba(50, 180, 90, 0.12);
}
.sv-fail, .pqr-fail {
    color: var(--studio-error);
    background: rgba(220, 50, 40, 0.12);
}
.sa-verdict {
    color: #1f5d9a;
    background: rgba(45, 125, 205, 0.12);
}
.sv-score, .pqr-score {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
}

/* Story reading pattern. */
.story-line {
    display: grid;
    grid-template-columns: 7rem 1fr;
    gap: 0.8rem;
    padding: 0.7rem 0.2rem;
    border-bottom: 1px solid var(--studio-border-soft);
}
.story-line-meta {
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    font-size: 0.75rem;
    opacity: 0.7;
}
.story-text { white-space: pre-wrap; }
.story-dialogue .story-text {
    padding: 0.65rem 0.8rem;
    border-radius: var(--studio-radius-control);
    background: rgba(180, 130, 60, 0.12);
}
.story-cue { margin-top: 0.3rem; }

@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] {
        padding-top: 1rem;
    }
    .story-heading, .sv-heading, .pqr-heading, .sa-heading {
        flex-direction: column;
    }
    .story-line {
        grid-template-columns: 1fr;
        gap: 0.25rem;
    }
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] * {
        font-size: 1.1rem !important;
    }
}
</style>
"""


def render_studio_style() -> None:
    """Inject the shared Studio theme once per Streamlit rerun."""
    import streamlit as st

    st.html(STUDIO_STYLE)


__all__ = ["STUDIO_STYLE", "render_studio_style"]
