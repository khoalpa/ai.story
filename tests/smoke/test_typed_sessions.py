from __future__ import annotations

import importlib
import sys
import types
import unittest


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class TypedSessionSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session_state = SessionState()
        streamlit_stub = types.SimpleNamespace(session_state=self.session_state)
        sys.modules['streamlit'] = streamlit_stub
        for name in [
            'audio.gui.state',
            'video.gui.state',
            'story.gui.state',
        ]:
            sys.modules.pop(name, None)

    def tearDown(self) -> None:
        sys.modules.pop('streamlit', None)

    def test_story_session_defaults_and_round_trip(self) -> None:
        module = importlib.import_module('story.gui.state')
        session = module.story_session()
        self.assertEqual(session.brief_text, '')
        session.brief_text = 'brief-1'
        session.last_plain_script_path = 'output/story.txt'
        self.assertEqual(self.session_state[module.STORY_BRIEF_TEXT_KEY], 'brief-1')
        self.assertEqual(self.session_state[module.STORY_LAST_PLAIN_SCRIPT_PATH_KEY], 'output/story.txt')

    def test_audio_session_defaults_and_round_trip(self) -> None:
        module = importlib.import_module('audio.gui.state')
        session = module.audio_session()
        self.assertEqual(session.plain_script_text, '')
        self.assertFalse(session.lock_to_story_handoff)
        session.plain_script_text = 'plain'
        session.run_plain_text = 'run'
        session.lock_to_story_handoff = True
        session.auto_plain_script = 'auto'
        self.assertEqual(self.session_state[module.PLAIN_SCRIPT_TEXT_KEY], 'plain')
        self.assertEqual(self.session_state[module.RUN_PLAIN_TEXT_KEY], 'run')
        self.assertTrue(self.session_state[module.AUDIO_LOCK_TO_STORY_HANDOFF_KEY])
        self.assertEqual(self.session_state[module.STUDIO_AUDIO_LAST_AUTO_PLAIN_SCRIPT_KEY], 'auto')

    def test_video_session_defaults_and_round_trip(self) -> None:
        module = importlib.import_module('video.gui.state')
        session = module.video_session()
        self.assertEqual(session.audio_input, 'output/story.mp3')
        self.assertFalse(session.lock_to_audio_handoff)
        session.audio_input = 'output/custom.mp3'
        session.subtitle_input = 'output/custom.srt'
        session.output_input = 'output/custom.mp4'
        session.lock_to_audio_handoff = True
        session.auto_audio_input = 'auto.mp3'
        session.auto_subtitle_input = 'auto.srt'
        session.auto_output_input = 'auto.mp4'
        self.assertEqual(self.session_state[module.VIDEO_AUDIO_INPUT_KEY], 'output/custom.mp3')
        self.assertEqual(self.session_state[module.VIDEO_SUBTITLE_INPUT_KEY], 'output/custom.srt')
        self.assertEqual(self.session_state[module.VIDEO_OUTPUT_INPUT_KEY], 'output/custom.mp4')
        self.assertTrue(self.session_state[module.VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY])
        self.assertEqual(self.session_state[module.STUDIO_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY], 'auto.mp3')
        self.assertEqual(self.session_state[module.STUDIO_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY], 'auto.srt')
        self.assertEqual(self.session_state[module.STUDIO_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY], 'auto.mp4')


if __name__ == '__main__':
    unittest.main()

