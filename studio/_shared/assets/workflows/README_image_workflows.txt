ComfyUI workflow presets for the integrated image branch.

Suggested defaults in Image studio:
- Cover workflow JSON file: image/_shared/assets/workflows/comfyui_story_cover_9x16_hires_v2_workflow.json
- Scene workflow JSON file: image/_shared/assets/workflows/comfyui_story_9x16_cover_scene_workflow.json
- Positive prompt node id: 2
- Negative prompt node id: 3
- Sampler node id: 5
- Latent size node id: 4
- Output node ids: 7 for scene workflow, 11 for cover hires workflow

Before first use, replace PUT_YOUR_CHECKPOINT_HERE.safetensors with a real checkpoint name on your ComfyUI server.
