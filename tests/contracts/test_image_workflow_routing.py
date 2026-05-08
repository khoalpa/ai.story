from __future__ import annotations

from pathlib import Path


def test_comfyui_local_uses_bundled_workflow_when_unconfigured() -> None:
    from image.workflow_routing import resolve_workflow_file

    workflow = resolve_workflow_file(
        prompt_data={"kind": "scene"},
        prompt_path=None,
        settings={"provider": "comfyui_local"},
    )

    workflow_path = Path(workflow)
    assert workflow_path.name == "comfyui_minimal_t2i_workflow.json"
    assert workflow_path.is_file()


def test_comfyui_remote_prefers_configured_output_node_ids() -> None:
    from image.provider_runtime import _select_comfyui_output_image

    selected = _select_comfyui_output_image(
        {
            "3": {"images": [{"filename": "preview.png"}]},
            "9": {"images": [{"filename": "final.png"}]},
        },
        "9",
    )

    assert selected == ("9", {"filename": "final.png"})


def test_comfyui_remote_falls_back_when_output_node_id_missing() -> None:
    from image.provider_runtime import _select_comfyui_output_image

    selected = _select_comfyui_output_image(
        {
            "3": {"images": [{"filename": "preview.png"}]},
            "9": {"images": [{"filename": "final.png"}]},
        },
        "42",
    )

    assert selected == ("3", {"filename": "preview.png"})

