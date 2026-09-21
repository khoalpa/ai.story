"""Shared visual language for every workspace in the Studio shell."""
from __future__ import annotations

STUDIO_STYLE = """
<style>
:root {
    color-scheme: light dark;
    --studio-font-sans: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
    --studio-font-mono: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
    --studio-font-size-xs: 0.75rem;
    --studio-font-size-sm: 0.875rem;
    --studio-font-size-md: 1rem;
    --studio-font-size-lg: 1.25rem;
    --studio-font-size-xl: clamp(1.65rem, 3vw, 2.25rem);
    --studio-space-1: 0.5rem;
    --studio-space-2: 0.75rem;
    --studio-space-3: 1rem;
    --studio-space-4: 1.5rem;
    --studio-space-5: 2rem;
    --studio-radius-control: 0.5rem;
    --studio-radius-surface: 0.75rem;
    --studio-radius-pill: 999px;
    --studio-control-min-height: 2.75rem;
    --studio-surface: color-mix(in srgb, currentColor 3%, transparent);
    --studio-surface-raised: color-mix(in srgb, currentColor 5%, transparent);
    --studio-text-muted: color-mix(in srgb, currentColor 68%, transparent);
    --studio-border: color-mix(in srgb, currentColor 14%, transparent);
    --studio-border-soft: color-mix(in srgb, currentColor 9%, transparent);
    --studio-primary: #2563eb;
    --studio-primary-strong: #1d4ed8;
    --studio-primary-soft: color-mix(in srgb, var(--studio-primary) 14%, transparent);
    --studio-focus: #60a5fa;
    --studio-success: #18733b;
    --studio-success-soft: color-mix(in srgb, var(--studio-success) 13%, transparent);
    --studio-warning: #8a5a00;
    --studio-warning-soft: color-mix(in srgb, #d99800 16%, transparent);
    --studio-error: #b42318;
    --studio-error-soft: color-mix(in srgb, var(--studio-error) 12%, transparent);
    --studio-info: #245ea8;
    --studio-info-soft: color-mix(in srgb, var(--studio-info) 12%, transparent);
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
html, body, input, button, textarea, select {
    font-family: var(--studio-font-sans);
}
h1, h2, h3 {
    letter-spacing: -0.018em;
}
h1 { font-size: var(--studio-font-size-xl); font-weight: 650; }
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
    min-height: var(--studio-control-min-height);
    border-radius: var(--studio-radius-control);
    font-weight: 600;
}
button:focus-visible,
input:focus-visible,
textarea:focus-visible,
select:focus-visible,
[role="tab"]:focus-visible,
[role="radio"]:focus-visible,
[role="button"]:focus-visible {
    outline: 3px solid color-mix(in srgb, var(--studio-focus) 68%, transparent) !important;
    outline-offset: 2px !important;
}
[data-testid="stButton"] button:hover:not(:disabled),
[data-testid="stDownloadButton"] button:hover:not(:disabled) {
    border-color: var(--studio-primary);
}
[data-testid="stButton"] button:disabled,
[data-testid="stDownloadButton"] button:disabled {
    cursor: not-allowed;
    opacity: 0.58;
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

/* Reusable application-level patterns. */
.studio-workspace-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--studio-space-4);
    padding: var(--studio-space-3) 0 var(--studio-space-2);
    border-bottom: 1px solid var(--studio-border-soft);
}
.studio-workspace-header__eyebrow {
    margin-bottom: 0.25rem;
    color: var(--studio-text-muted);
    font-size: var(--studio-font-size-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.studio-workspace-header__title {
    margin: 0;
    font-size: clamp(1.35rem, 2.2vw, 1.75rem);
    line-height: 1.2;
}
.studio-workspace-header__description {
    max-width: 70ch;
    margin: 0.4rem 0 0;
    color: var(--studio-text-muted);
    font-size: var(--studio-font-size-sm);
}
.studio-status-badge {
    display: inline-flex;
    align-items: center;
    min-height: 1.75rem;
    padding: 0.2rem 0.65rem;
    border-radius: var(--studio-radius-pill);
    font-size: var(--studio-font-size-xs);
    font-weight: 700;
    line-height: 1.2;
    white-space: nowrap;
}
.studio-status-badge--neutral { background: var(--studio-surface-raised); }
.studio-status-badge--info { color: var(--studio-info); background: var(--studio-info-soft); }
.studio-status-badge--success { color: var(--studio-success); background: var(--studio-success-soft); }
.studio-status-badge--warning { color: var(--studio-warning); background: var(--studio-warning-soft); }
.studio-status-badge--error { color: var(--studio-error); background: var(--studio-error-soft); }
.studio-empty-state {
    padding: var(--studio-space-5) var(--studio-space-4);
    border: 1px dashed var(--studio-border);
    border-radius: var(--studio-radius-surface);
    background: var(--studio-surface);
    text-align: center;
}
.studio-empty-state__icon { font-size: 1.5rem; line-height: 1; }
.studio-empty-state__title { margin: 0.65rem 0 0.25rem; font-weight: 700; }
.studio-empty-state__description {
    max-width: 62ch;
    margin: 0 auto;
    color: var(--studio-text-muted);
    font-size: var(--studio-font-size-sm);
}
.studio-summary-card {
    height: 100%;
    padding: var(--studio-space-3);
    border: 1px solid var(--studio-border);
    border-radius: var(--studio-radius-surface);
    background: var(--studio-surface);
}
.studio-summary-card__label { color: var(--studio-text-muted); font-size: var(--studio-font-size-xs); }
.studio-summary-card__value { margin-top: 0.3rem; font-size: var(--studio-font-size-lg); font-weight: 700; }
.studio-summary-card__detail { margin-top: 0.35rem; color: var(--studio-text-muted); font-size: var(--studio-font-size-xs); }
.studio-action-bar {
    position: sticky;
    bottom: 0;
    z-index: 20;
    padding: var(--studio-space-2);
    border: 1px solid var(--studio-border);
    border-radius: var(--studio-radius-surface);
    background: color-mix(in srgb, var(--background-color, white) 92%, transparent);
    backdrop-filter: blur(12px);
}
.studio-progress {
    margin: 0.1rem 0 var(--studio-space-2);
    padding: 0.7rem 0.85rem;
    border: 1px solid var(--studio-border-soft);
    border-radius: var(--studio-radius-surface);
    background: var(--studio-surface);
}
.studio-progress__list {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0;
    margin: 0;
    padding: 0;
    list-style: none;
}
.studio-progress__item {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.45rem;
    min-width: 0;
    color: var(--studio-text-muted);
    font-size: var(--studio-font-size-xs);
    font-weight: 650;
}
.studio-progress__item:not(:last-child)::after {
    content: "";
    position: absolute;
    right: 0.45rem;
    left: 2rem;
    top: 50%;
    height: 1px;
    background: var(--studio-border);
}
.studio-progress__marker {
    z-index: 1;
    display: inline-grid;
    place-items: center;
    width: 1.55rem;
    height: 1.55rem;
    flex: 0 0 auto;
    border: 1px solid var(--studio-border);
    border-radius: var(--studio-radius-pill);
    background: var(--background-color, white);
}
.studio-progress__label { z-index: 1; padding-right: 0.5rem; background: var(--studio-surface); }
.studio-progress__item--active { color: var(--studio-primary); }
.studio-progress__item--active .studio-progress__marker {
    color: white;
    border-color: var(--studio-primary);
    background: var(--studio-primary);
}
.studio-progress__item--complete { color: var(--studio-success); }
.studio-progress__item--complete .studio-progress__marker {
    border-color: var(--studio-success);
    background: var(--studio-success-soft);
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
    .studio-workspace-header {
        flex-direction: column;
        gap: var(--studio-space-2);
    }
    .studio-empty-state {
        padding: var(--studio-space-4) var(--studio-space-3);
    }
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
    }
    [data-testid="column"] {
        min-width: min(100%, 16rem) !important;
        flex: 1 1 16rem !important;
    }
    .studio-progress { overflow-x: auto; }
    .studio-progress__list { min-width: 34rem; }
    .story-line {
        grid-template-columns: 1fr;
        gap: 0.25rem;
    }
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] * {
        font-size: 1.1rem !important;
    }
}

@media (max-width: 1024px) {
    [data-testid="stMainBlockContainer"] {
        padding-inline: 1.25rem;
    }
    .studio-workspace-header__description {
        max-width: 58ch;
    }
}

@media (max-width: 768px) {
    [data-testid="stMainBlockContainer"] {
        padding-inline: 0.9rem;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"],
    [data-testid="stSegmentedControl"] > div {
        overflow-x: auto;
        scrollbar-width: thin;
    }
    [data-testid="stTabs"] button[role="tab"],
    [data-testid="stSegmentedControl"] button {
        flex: 0 0 auto;
        white-space: nowrap;
    }
    .studio-summary-card {
        min-height: 6rem;
    }
}
</style>
"""


def render_studio_style() -> None:
    """Inject the shared Studio theme once per Streamlit rerun."""
    import streamlit as st

    st.html(STUDIO_STYLE)


__all__ = ["STUDIO_STYLE", "render_studio_style"]
