# UI/UX verification matrix

This document records the acceptance checks for the unified Streamlit Studio.

## Responsive layout

| Viewport | Expected behavior | Result |
| --- | --- | --- |
| 1440 × 900 | Sidebar visible, five-step rail fits, primary actions align | Pass |
| 1024 × 800 | Content retains readable width, controls do not overlap | Pass |
| 768 × 900 | Sidebar collapses, rail remains usable, columns wrap | Pass |

Temporary viewport overrides must be reset after visual testing.

## Project states

| State | Acceptance criteria |
| --- | --- |
| Empty | Calm empty states explain the next action; Render actions stay disabled without required input. |
| Partial | Missing assets and failed gates identify the affected section without hiding usable outputs. |
| Complete | Audio/video previews and downloads are primary; JSON, provenance, stdout, and stderr remain collapsed. |

## Accessibility

- Keyboard focus is visible on buttons, tabs, radio controls, and fields.
- Primary controls have a minimum height of 44 px.
- Status uses text and symbols in addition to color.
- The production rail exposes an accessible label and current step.
- Horizontal navigation remains scrollable at compact widths.

## Automated gates

Run before release:

```powershell
python -m ruff check .
python -m mypy
python -m pytest -q
```

If a repository-wide gate fails, run the reported test or file directly and distinguish
new UI regressions from pre-existing worktree changes before editing unrelated code.
