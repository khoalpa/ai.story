from __future__ import annotations

import importlib
import sys
import types


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _install_streamlit(session_state: SessionState) -> None:
    sys.modules['streamlit'] = types.SimpleNamespace(session_state=session_state)
    for name in ['common.gui.state', 'story.gui.state', 'audio.gui.state', 'image.gui.state', 'video.gui.state']:
        sys.modules.pop(name, None)


def test_shell_state_defaults_and_status_contract() -> None:
    state = SessionState()
    _install_streamlit(state)
    shell = importlib.import_module('common.gui.state')

    shell.ensure_workspace_shell_state()
    assert state['workspace_story_target_view'] == 'Inputs'
    snapshot = shell.get_pipeline_status_snapshot()
    assert snapshot == {'story': 'idle', 'audio': 'idle', 'image': 'idle', 'video': 'idle'}

    shell.set_story_handoff(plain_script_text='plain script')
    shell.set_story_image_handoff(handoff_dir='story_bundle')
    shell.set_audio_handoff(audio_output_path='output/story.mp3', srt_output_path='output/story.srt')
    shell.set_image_handoff(cover_image_path='image/cover.png', scene_images_dir='image/scenes', manifest_path='image/manifest.json')
    shell.set_video_handoff(video_output_path='video/story.mp4')

    assert shell.get_pipeline_status_snapshot() == {
        'story': 'ready',
        'audio': 'ready',
        'image': 'ready',
        'video': 'rendered',
    }


def test_workspace_handoff_readiness_does_not_show_story_content() -> None:
    state = SessionState({
        'workspace_story_plain_script_text': 'SECRET STORY CONTENT',
        'workspace_last_story_output': 'Plain script ready to send to Audio',
    })
    _install_streamlit(state)
    sys.modules.pop('common.gui.shell', None)
    shell = importlib.import_module('common.gui.shell')

    rows = shell._build_handoff_readiness_rows()
    story_row = next(row for row in rows if row['handoff'] == 'Story -> Audio - plain script')

    assert story_row['status'] == 'ready'
    assert story_row['detail'] == 'Plain script ready for Audio.'
    assert 'SECRET STORY CONTENT' not in story_row['detail']


def test_session_default_initializers_do_not_clobber_existing_values() -> None:
    state = SessionState({
        'story_brief_text': 'existing brief',
        'plain_script_text': 'existing plain',
        'image_output_dir': 'custom_image_out',
        'video_audio_input': 'custom.mp3',
        'voice_narrator_speed': 7,
    })
    _install_streamlit(state)
    story_state = importlib.import_module('story.gui.state')
    audio_state = importlib.import_module('audio.gui.state')
    image_state = importlib.import_module('image.gui.state')
    video_state = importlib.import_module('video.gui.state')

    story_state.ensure_session_defaults(state)
    audio_state.ensure_session_defaults(state)
    image_state.ensure_session_defaults(state)
    video_state.ensure_session_defaults(state)

    assert state['story_brief_text'] == 'existing brief'
    assert state['plain_script_text'] == 'existing plain'
    assert state['image_output_dir'] == 'custom_image_out'
    assert state['video_audio_input'] == 'custom.mp3'
    assert state['voice_narrator_speed'] == 7
    assert state['voice_female_speed'] == 13
    assert state['voice_male_speed'] == 11


def test_image_session_round_trip_contract() -> None:
    state = SessionState()
    _install_streamlit(state)
    image_state = importlib.import_module('image.gui.state')

    session = image_state.image_session()
    assert session.handoff_dir == ''
    assert session.output_dir == 'output'

    session.handoff_dir = 'output/story/image_bundle'
    session.output_dir = 'custom_output'

    assert state[image_state.IMAGE_HANDOFF_DIR_KEY] == 'output/story/image_bundle'
    assert state[image_state.IMAGE_OUTPUT_DIR_KEY] == 'custom_output'


def test_image_session_defaults_disable_auto_shorten_by_default() -> None:
    state = SessionState()
    _install_streamlit(state)
    image_state = importlib.import_module('image.gui.state')

    image_state.ensure_session_defaults(state)

    assert state['image_local_auto_shorten_prompt'] is True
    assert state['image_local_auto_shorten_negative_prompt'] is True

