from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


MODULES = [
    'common.gui.state',
    'audio.gui.run_panel',
    'image.gui.tabs',
    'video.gui.tabs',
    'audio.gui.state',
    'image.gui.state',
    'video.gui.state',
]


def _load_modules(session_state: SessionState):
    sys.modules['streamlit'] = types.SimpleNamespace(session_state=session_state)
    for name in MODULES:
        sys.modules.pop(name, None)
    return {name: importlib.import_module(name) for name in MODULES}


def test_story_to_audio_handoff_prefills_run_text_and_navigation() -> None:
    state = SessionState()
    mods = _load_modules(state)
    shell = mods['common.gui.state']
    audio_run = mods['audio.gui.run_panel']

    shell.send_story_to_audio(plain_script_text='[VO] hello story')

    assert state['workspace_story_plain_script_text'] == '[VO] hello story'
    assert state['audio_lock_to_story_handoff'] is True
    assert state['workspace_pending_app'] == 'Audio'
    assert state['workspace_pending_view'] == 'Run'

    audio_run._apply_story_handoff_prefill_to_run()
    assert state['run_plain_text'] == '[VO] hello story'
    assert state['last_plain_script'] == '[VO] hello story'
    assert state['audio_last_auto_plain_script'] == '[VO] hello story'


def test_story_to_image_handoff_prefills_inputs_and_output_dir() -> None:
    state = SessionState()
    mods = _load_modules(state)
    shell = mods['common.gui.state']
    image_tabs = mods['image.gui.tabs']

    shell.send_story_to_image(handoff_dir='output/story/image_bundle')

    assert state['workspace_story_image_handoff_dir'] == 'output/story/image_bundle'
    assert state['image_lock_to_story_handoff'] is True
    assert state['workspace_pending_app'] == 'Image'
    assert state['workspace_pending_view'] == 'Inputs'

    image_tabs._prefill_from_story_handoff()
    assert state['image_handoff_dir'] == 'output/story/image_bundle'
    assert Path(state['image_output_dir']).as_posix().endswith('output/story/image_bundle/generated')


def test_audio_and_image_handoff_prefill_video_inputs() -> None:
    state = SessionState()
    mods = _load_modules(state)
    shell = mods['common.gui.state']
    video_tabs = mods['video.gui.tabs']

    shell.send_audio_to_video(audio_output_path='output/story.wav', srt_output_path='output/story.srt')
    shell.send_image_to_video(
        cover_image_path='output/images/cover.png',
        scene_images_dir='output/images',
        manifest_path='output/manifest.json',
    )

    settings = {'output_dir': 'video_out', 'defaults': {'cover': None, 'scenes_dir': None}, 'mode': 'slideshow', 'ffmpeg_exe': 'ffmpeg', 'ffprobe_exe': 'ffprobe'}
    video_tabs._apply_audio_handoff_prefill(settings)
    video_tabs._apply_image_handoff_prefill(settings)

    assert state['video_lock_to_audio_handoff'] is True
    assert state['video_lock_to_image_handoff'] is True
    assert state['workspace_pending_app'] == 'Video'
    assert state['workspace_pending_view'] == 'Inputs'
    assert state['video_audio_input'] == 'output/story.wav'
    assert state['video_subtitle_input'] == 'output/story.srt'
    assert Path(state['video_output_input']).as_posix().endswith('video_out/story.mp4')
    assert state['video_cover_input'] == 'output/images/cover.png'
    assert state['video_scenes_input'] == 'output/images'
    assert state['workspace_video_last_auto_audio_input'] == 'output/story.wav'
    assert state['workspace_video_last_auto_subtitle_input'] == 'output/story.srt'
    assert state['workspace_video_last_auto_cover_input'] == 'output/images/cover.png'
    assert state['workspace_video_last_auto_scenes_input'] == 'output/images'

