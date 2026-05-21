# AI Story Studio

AI Story Studio unifies four related workflows in one repository:

- **Story**: brief → canonical → plain script + image prompt bundle
- **Audio**: plain script → WAV/MP3 + subtitles
- **Image**: Story handoff bundle → cover/scenes
- **Video**: audio/subtitles + cover/scenes → MP4

The repository is organized as a modular monorepo with focused packages:

- `story`
- `audio`
- `image`
- `video`
- `common`
- `studio`

## Current status

As of 2026-05-21, this repository is a unified AI Story Studio codebase with:

- Story, Audio, Image, Video, and unified Studio Streamlit launchers.
- Canonical GUI modules under `*/gui/app.py` plus package launchers in `*_entry.py`.
- Audio BGM assets packaged under `audio/assets/bgm` with `audio/assets/bgm_config.json`.
- Story-to-Audio, Story-to-Image, Audio-to-Video, and Image-to-Video handoff support in the unified GUI.
- Local/remote image provider plumbing, including Stable Diffusion and ComfyUI provider paths.
- Smoke and contract coverage for package contents, dependency direction, GUI state contracts, image workflows, audio rendering contracts, and handoff behavior.

## Quick start

Run the unified Studio GUI:

```bash
python -m streamlit run studio/gui_entry.py
```

Or use the installed console command:

```bash
ai-studio-gui
```

Recommended workflow:

1. Generate a story in Story.
2. Send the plain script to Audio and render narration/subtitles.
3. Send the image prompt bundle to Image and render cover/scenes.
4. Send Audio/Image outputs to Video and render the final MP4.

## Donation

If this project is useful to you, you can support continued development via VietQR:

- Account holder: `LE PHAM ANH KHOA`
- Bank: `MB Bank`
- Account number: `0914030780`
- Suggested content: `Donation AI Story`

![Donation VietQR](docs/assets/donation-mbb-0914030780.jpg)

## Install

Install from the merged requirements file:

```bash
python -m pip install -r requirements.txt
```

Install from package metadata:

```bash
python -m pip install .[all]
```

For image-local features, add the image-local extra:

```bash
python -m pip install .[all,image-local]
```

## Console entry points

- `generator-story`
- `generator-story-gui`
- `render-audio`
- `render-audio-gui`
- `render-image-gui`
- `render-video`
- `render-video-gui`
- `ai-studio-gui`

## Requirements

- `requirements.txt`: single all-in-one environment for local install, GUI use, tests, and release checks

## Package metadata alignment

`pyproject.toml` is aligned with `requirements.txt` as follows:

- base `project.dependencies` covers the runtime and GUI packages needed by the shipped launchers
- optional extras in `pyproject.toml` remain available for package installs, while `requirements.txt` is the single pip requirements file for this repo
- `.[image-local]` keeps heavyweight local image-generation dependencies optional

## Quality checks

The standard local/CI checks are:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy
python scripts/check_dependency_direction.py
python scripts/check_wheel_contents.py
```

`mypy` is configured to scan the shipped packages (`audio`, `story`, `image`, `video`, `common`, `studio`) plus `scripts`. Modules with existing type debt are listed explicitly in the `pyproject.toml` mypy override baseline; remove modules from that list as their annotations are cleaned up.

## Audio assets

Bundled audio BGM assets live under `audio/assets/bgm`, with runtime defaults resolved through `audio.paths.DEFAULT_BGM_DIR`. The packaged wheel is expected to include `audio/assets/bgm_config.json` and representative BGM files checked by `scripts/check_wheel_contents.py`.

## Consolidated project notes

The sections below merge the content that previously lived across the repository markdown files.


---

## Source document: `AUDIT_REPORT.md`

### Audit Report

## Current summary

The repository is now normalized around canonical GUI modules:

- `story.gui.app`
- `audio.gui.app`
- `image.gui.app`
- `video.gui.app`

and the supported Streamlit launcher modules:

- `story.gui_entry`
- `audio.gui_entry`
- `image.gui_entry`
- `video.gui_entry`
- `studio.gui_entry`

## Resolved cleanup items

- Removed legacy `video.gui_app` wrapper.
- Removed package-level `_streamlit_app` shims.
- Removed package-level `gui_launcher` shims.
- Removed committed `__pycache__` directories.
- Removed committed runtime artifact `.render_audio_gui/jobs.json`.
- Replaced the `video` package `sys.path` hack with a normal package export surface.
- Fixed root pytest discovery so smoke tests run from the repository root.
- Added the `image` branch to packaging metadata and console scripts.
- Moved cross-app image-sequence constants into `common` so Story does not depend on `video`.
- Added release smoke coverage for installed-wheel entrypoints, including `ai-studio-gui` and `render-image-gui`.

## Current architectural notes

- `story`, `audio`, `image`, and `video` now follow the same GUI entrypoint pattern.
- Package GUI entry modules are the public Streamlit start points.
- Canonical package GUI modules remain the only supported import targets for embedded studio integration.
- Top-level dependency direction is constrained to app packages importing `common`, not each other.
- `scripts/check_dependency_direction.py` and `package_api_policy.json` should remain aligned with the real package graph.

## Current release notes

- Wheel packaging now includes `image*` packages.
- Wheel packaging checks include bundled audio BGM config and BGM files under `audio/assets`.
- Console scripts now cover Story, Audio, Image, Video, and the unified Studio shell.
- Runtime, GUI, test, and dev dependencies are consolidated in the single `requirements.txt` file.
- Mypy runs across shipped packages, with an explicit override baseline for modules that still carry type debt.
- Repository hygiene checks are hardened to avoid false positives caused by the current pytest run itself.


---

## Source document: `DEPENDENCY_DIRECTION.md`

### Package dependency direction

This repository uses a one-way package dependency rule among the main packages.

## Allowed directions

- `audio -> common`
- `story -> common`
- `image -> common`
- `video -> common`

## Forbidden directions

The following are forbidden unless the policy manifest is explicitly changed:
- `audio -> story`
- `audio -> image`
- `audio -> video`
- `story -> audio`
- `story -> image`
- `story -> video`
- `image -> audio`
- `image -> story`
- `image -> video`
- `video -> audio`
- `video -> story`
- `video -> image`
- `common -> audio`
- `common -> story`
- `common -> image`
- `common -> video`

## Rationale

- `common` provides shared runtime and utility concerns.
- `audio`, `story`, `image`, and `video` are sibling feature packages.
- Sibling packages must not depend on each other directly because that creates hidden coupling and makes refactors harder.

## Enforcement

CI validates dependency direction from `package_api_policy.json` and fails when:
- a package imports another package not listed in its allowed dependency list,
- or a package starts depending on a sibling package directly instead of routing shared concerns through `common`.

Tests are excluded from this direction check so integration tests can probe package behavior without being blocked by architecture policy.


---

## Source document: `DEPRECATIONS.md`

### Deprecations Status

## Current state

GUI entrypoints are now standardized on two layers only:

- package Streamlit launcher modules:
  - `audio.gui_entry`
  - `story.gui_entry`
  - `image.gui_entry`
  - `video.gui_entry`
  - `studio.gui_entry`
- canonical package GUI modules:
  - `audio.gui.app`
  - `story.gui.app`
  - `image.gui.app`
  - `video.gui.app`

The following legacy compatibility layers have been removed from the repository:

- `video.gui_app`
- `audio._streamlit_app`
- `story._streamlit_app`
- `video._streamlit_app`
- `audio.gui_launcher`
- `story.gui_launcher`
- `video.gui_launcher`

## Import policy

Use these imports in code and documentation:

```python
from audio.gui.app import main as audio_main
from story.gui.app import main as story_main
from video.gui.app import main as video_main
from video.gui.app import render_video_studio
```

Do not add any new package-level GUI wrappers unless there is a release-critical backward-compatibility need.

## Operational policy

- Canonical GUI logic lives only under `package/gui/app.py` plus sibling GUI modules.
- Package `*.gui_entry` launchers are the supported Streamlit entrypoints.
- Embedded studio integration must call `render_*_studio(embedded=True)` from the canonical package GUI modules.

## Verification checklist

A clean repo should satisfy all of the following:

- No source file imports `video.gui_app`.
- No source file imports `_streamlit_app`.
- No source file imports `gui_launcher`.
- Unified GUI documentation references `video.gui.app`.
- `pytest -q` discovers and runs the smoke tests from the repository root.

## Runtime cleanup

- Removed dead `common.runtime.launch_streamlit_app()` helper after all package-level `_streamlit_app.py` shims were deleted.


---

## Source document: `GUI_ARCHITECTURE.md`

### GUI Architecture

Tài liệu này mô tả chuẩn kiến trúc GUI hiện tại của studio để các lần sửa sau không làm trôi cấu trúc.

## Mục tiêu

Chuẩn hóa GUI theo các lớp nhỏ, rõ trách nhiệm, giảm:
- raw `st.session_state[...]` rải rác
- file `settings.py` / `tabs.py` quá lớn
- coupling giữa Story / Audio / Image / Video
- lỗi Streamlit do mutate state sai thời điểm

Nguyên tắc chính:
- `state_keys.py` giữ constants
- `state.py` giữ defaults + wrappers/accessors
- `sidebar.py` render cấu hình
- `config_mapper.py` map state -> config
- `main_panel.py` điều phối panel chính
- `tabs/*.panel` hoặc panel modules giữ UI theo màn hình
- `tabs.py` chỉ là facade mỏng nếu cần tương thích ngược

---

## 1. `state_keys.py`

### Vai trò
Giữ toàn bộ session-state key constants của từng workspace.

### Mục tiêu
- tránh hardcode string key ở nhiều nơi
- dễ rename / migrate key
- giúp `state.py` gọn hơn

### Ví dụ nội dung
- input keys
- result keys
- handoff keys
- provider test keys
- legacy key aliases nếu cần tương thích ngược

### Quy ước
- đặt theo prefix workspace rõ ràng
- key name phải phản ánh domain, không phản ánh widget text

Ví dụ:
```python
STORY_PLAIN_SCRIPT_TEXT_KEY = "story_plain_script_text"
VIDEO_AUTO_AUDIO_INPUT_KEY = "video_auto_audio_input"
IMAGE_LAST_COVER_OUTPUT_KEY = "image_last_cover_output"
```

---

## 2. `state.py`

### Vai trò
Giữ defaults, migration nhẹ, và wrappers/accessors cho session state.

### Nên có
- `*_DEFAULTS` theo từng domain nhỏ
- `ensure_session_defaults(...)`
- `WorkspaceSession` hoặc `*Session`
- các sub-state wrappers nếu workspace đủ lớn

### Không nên có
- render widget Streamlit
- business logic chạy pipeline
- config mapping phức tạp
- ghi raw state rải rác ngoài wrappers

### Cấu trúc khuyến nghị
```python
EDITOR_DEFAULTS = {...}
RESULT_DEFAULTS = {...}
HANDOFF_DEFAULTS = {...}


def ensure_session_defaults(state):
    ...


@dataclass
class StoryEditorState:
    ...


@dataclass
class StorySession:
    state: MutableMapping[str, Any]
```

### Quy tắc
- defaults chia theo domain, không dồn một dict rất lớn
- wrapper nên expose property có nghĩa nghiệp vụ
- legacy migration chỉ giữ ở mức tối thiểu

---

## 3. `sidebar.py`

### Vai trò
Render toàn bộ cấu hình ở sidebar cho từng workspace.

### Nên có
- `ensure_*_sidebar_defaults()` nếu cần
- `*SidebarState` dataclass
- `render_*_sidebar(...)`
- các `expander` theo nhóm: Provider / Runtime / Output / Handoff

### Không nên có
- chạy pipeline
- mutate lại `st.session_state[key]` sau khi widget cùng key đã render
- map config sâu
- xử lý kết quả/output lớn

### Quy tắc Streamlit quan trọng
Sai:
```python
model_name = st.text_input("Model", key="vieneu_model_name")
st.session_state["vieneu_model_name"] = model_name
```

Đúng:
```python
if "vieneu_model_name" not in st.session_state:
    st.session_state["vieneu_model_name"] = default_model

model_name = st.text_input("Model", key="vieneu_model_name")
```

### Đầu ra chuẩn
`render_*_sidebar()` nên trả về một object state rõ ràng:
```python
@dataclass
class AudioSidebarState:
    provider: str
    model_name: str
    api_base: str
    output_dir: str
```

---

## 4. `config_mapper.py`

### Vai trò
Map từ sidebar/session state sang config object hoặc settings dict mà app/runtime cần.

### Nên có
- `build_*_config_from_state(...)`
- chuẩn hóa kiểu dữ liệu
- strip path/text
- áp dụng fallback hợp lý

### Không nên có
- Streamlit widgets
- side effects
- update session state

### Ví dụ
```python
def build_audio_config_from_state(state: AudioSidebarState) -> AppConfig:
    return AppConfig(
        provider=state.provider,
        model_name=state.model_name.strip(),
        api_base=state.api_base.strip(),
        output_dir=state.output_dir.strip(),
    )
```

---

## 5. `main_panel.py`

### Vai trò
Điều phối phần UI chính của workspace.

### Nên có
- chọn view cho embedded mode
- dispatch sang các panel / tab renderer
- nhận `settings/config` từ `app.py`
- giữ shell logic của workspace

### Không nên có
- sidebar config rendering
- session defaults phức tạp
- provider-specific low-level diagnostics nếu đã có helper riêng

### Pattern chuẩn
```python
def render_audio_main_panel(*, settings, embedded: bool = False) -> None:
    if embedded:
        ...
    else:
        ...
```

---

## 6. `tabs/*.panel` và facades

### Vai trò
Chia UI lớn thành các panel nhỏ theo màn hình/chức năng.

### Panel modules điển hình
- `inputs_panel.py`
- `run_panel.py`
- `preview_panel.py`
- `test_panel.py`
- `history_panel.py`

### Khi nào cần facade `tabs.py`
Giữ `tabs.py` làm facade mỏng khi:
- cần backward compatibility với import cũ
- test cũ còn import `workspace.gui.tabs`
- muốn tránh thay đổi call site quá rộng trong một lần refactor

### Quy tắc
- panel module giữ logic hiển thị của đúng một màn hình
- `tabs.py` chỉ re-export hoặc delegate
- không đưa business logic lớn quay lại `tabs.py`

---

## 7. Module chung trong `common/gui/`

Các helper dùng chung nên chia theo chủ đề nhỏ, không gom quá tay.

### Đã chuẩn hóa
- `panel_utils.py`
- `handoff_utils.py`
- `provider_actions.py`
- `result_panels.py`
- `view_model_utils.py`
- `history_utils.py`
- `diagnostics_blocks.py`
- `workspace_handoff.py`
- `workspace_navigation.py`
- `global_run_monitor.py`
- `lock_flags.py`
- `pipeline_status.py`
- `workspace_source_outputs.py`

### Nguyên tắc tách helper chung
Chỉ gom khi:
- lặp ở từ 2 workspace trở lên
- cùng domain trách nhiệm
- không kéo coupling ngược vào core logic

Không gom nếu:
- helper còn đặc thù một provider duy nhất
- tên chưa ổn định
- logic còn đang thay đổi mạnh

---

## 8. Luồng dữ liệu chuẩn

### Từ UI đến runtime
1. `state.py` đảm bảo defaults
2. `sidebar.py` render widget và trả về `SidebarState`
3. `config_mapper.py` map sang config/settings
4. `main_panel.py` điều phối panel tương ứng
5. panel module gọi service/runtime
6. kết quả ghi ngược qua wrappers trong `state.py` hoặc `common/gui/*`

### Với handoff pipeline
1. workspace A ghi source output qua `workspace_source_outputs.py`
2. `sync_pipeline_handoff_state()` đồng bộ sang handoff wrapper
3. workspace B đọc qua `workspace_handoff.py`
4. navigation/lock flags được xử lý qua wrappers riêng

---

## 9. Quy ước đặt tên

### File
- `state_keys.py`: constants
- `state.py`: defaults + wrappers
- `sidebar.py`: sidebar UI
- `config_mapper.py`: state -> config
- `main_panel.py`: orchestration của main area
- `*_panel.py`: từng màn hình UI

### Dataclass / wrappers
- `StorySidebarState`
- `ImagePathsState`
- `VideoResultsState`
- `WorkspaceHandoffState`
- `GlobalRunMonitorState`

### Hàm
- `ensure_*_defaults(...)`
- `render_*_sidebar(...)`
- `build_*_config_from_state(...)`
- `render_*_main_panel(...)`

---

## 10. Checklist khi sửa GUI

Trước khi thêm code mới, kiểm tra:

### State
- key mới đã nằm trong `state_keys.py` chưa?
- default mới đã nằm trong nhóm defaults đúng domain chưa?
- có cần wrapper/property mới không?

### Sidebar
- widget có đang dùng key ổn định không?
- có gán lại `st.session_state[key]` sau khi widget render không?

### Mapping
- logic chuyển state -> config đã nằm trong `config_mapper.py` chưa?

### Panel
- UI mới thuộc `inputs/run/preview/test/history` panel nào?
- có đang nhồi lại logic vào `tabs.py` hoặc `app.py` không?

### Shared helpers
- logic mới có lặp ở >= 2 workspace không?
- nếu có, có nên đưa vào `common/gui/` không?

---

## 11. Anti-pattern cần tránh

- hardcode raw string keys nhiều nơi
- `settings.py` vừa render widget vừa map config vừa chạy logic
- `tabs.py` phình to trở lại
- `app.py` ôm chi tiết UI từng tab
- helper chung quá “thông minh” và biết quá nhiều về provider cụ thể
- mutate session state sau khi widget cùng key đã tạo
- dùng `st.session_state.get(...)` rải rác thay vì wrapper có nghĩa nghiệp vụ

---

## 12. Mẫu skeleton tối thiểu cho một workspace mới

```python
# state_keys.py
INPUT_TEXT_KEY = "demo_input_text"
OUTPUT_PATH_KEY = "demo_output_path"
```

```python
# state.py
DEFAULTS = {
    INPUT_TEXT_KEY: "",
    OUTPUT_PATH_KEY: "",
}


def ensure_session_defaults(state):
    for key, value in DEFAULTS.items():
        state.setdefault(key, value)
```

```python
# sidebar.py
@dataclass
class DemoSidebarState:
    provider: str


def render_demo_sidebar() -> DemoSidebarState:
    provider = st.selectbox("Provider", ["local", "remote"], key="demo_provider")
    return DemoSidebarState(provider=provider)
```

```python
# config_mapper.py
def build_demo_config_from_state(state: DemoSidebarState) -> dict:
    return {"provider": state.provider}
```

```python
# main_panel.py
def render_demo_main_panel(*, settings: dict, embedded: bool = False) -> None:
    ...
```

```python
# app.py
def render_demo_workspace(*, embedded: bool = False) -> None:
    ensure_session_defaults(st.session_state)
    sidebar_state = render_demo_sidebar()
    settings = build_demo_config_from_state(sidebar_state)
    render_demo_main_panel(settings=settings, embedded=embedded)
```

---

## Kết luận

Chuẩn hiện tại của studio là:
- key constants tách riêng
- state có wrapper rõ nghĩa
- sidebar/config/main-panel/tabs tách lớp
- helper chung chia theo domain nhỏ
- raw session access được giảm tối đa

Khi thêm tính năng mới, ưu tiên giữ đúng phân lớp này thay vì thêm nhanh vào `settings.py`, `tabs.py`, hoặc `app.py`.

---

## 7. Thông báo / hướng dẫn thay vì bung lỗi

### Mục tiêu
Khi có lỗi hoặc thiếu cấu hình, GUI phải ưu tiên:
- giải thích ngắn gọn vấn đề
- chỉ rõ người dùng cần làm gì tiếp theo
- giữ app tiếp tục chạy được nếu có thể
- chỉ hiện traceback thô ở chế độ debug

### Nguyên tắc
- **Không bung traceback trực tiếp cho người dùng cuối** trong luồng bình thường.
- Dùng `st.error`, `st.warning`, `st.info`, `st.success` với câu chữ hành động được.
- Thông báo phải trả lời 3 câu hỏi:
  1. Điều gì đang sai?
  2. Ảnh hưởng là gì?
  3. Người dùng cần làm gì tiếp theo?
- Nếu có thể tiếp tục với degraded mode, hãy cho phép tiếp tục thay vì `raise` ngay.
- Chỉ `raise` khi không còn cách render an toàn hoặc dữ liệu có nguy cơ sai nghiêm trọng.

### Thứ tự ưu tiên khi xử lý lỗi GUI
1. **Validate sớm** ở `sidebar.py` hoặc `config_mapper.py`
2. **Hiển thị hướng dẫn sửa** trong sidebar hoặc main panel
3. **Chặn đúng hành động lỗi** (ví dụ disable nút Run/Test)
4. **Ghi chi tiết kỹ thuật vào diagnostics/logs**
5. Chỉ ở debug mode mới cho phép xem exception/raw details

### Mẫu thông điệp chuẩn
#### Thiếu cấu hình bắt buộc
```python
st.warning("Chưa có API base cho Vieneu. Hãy nhập API base trong Provider settings rồi thử lại.")
```

#### Thiếu dependency
```python
st.error("Chưa cài Streamlit dependency cần thiết cho màn hình này.")
st.info("Cách xử lý: cài gói còn thiếu rồi chạy lại ứng dụng.")
```

#### Thiếu file đầu vào
```python
st.warning("Chưa tìm thấy file audio đầu vào gần nhất.")
st.info("Hãy render Audio trước hoặc chọn file thủ công trong Inputs.")
```

#### Provider test thất bại
```python
st.error("Không kết nối được tới provider hiện tại.")
st.info("Kiểm tra API base, model name, network access, rồi bấm Test lại.")
```

#### Hoàn tất nhưng có cảnh báo
```python
st.success("Render hoàn tất.")
st.warning("Một số file phụ không được tạo, nhưng output chính vẫn dùng được.")
```

### Vị trí hiển thị thông báo
#### Trong `sidebar.py`
Dùng cho:
- thiếu provider config
- test connection status
- refresh/update model status
- warning về local/remote mode

#### Trong `main_panel.py`
Dùng cho:
- thiếu input trước khi Run
- không có output để preview
- handoff chưa sẵn sàng
- thông báo kết quả tổng quát sau khi chạy

#### Trong `tabs/*.panel`
Dùng cho:
- cảnh báo đặc thù từng màn hình
- preview không mở được
- history rỗng
- test panel không đủ dữ liệu

#### Trong `diagnostics blocks`
Dùng cho:
- chi tiết kỹ thuật
- unsupported nodes
- ignored nodes
- raw metadata
- exception text rút gọn nếu cần

#### Trong `common/gui/user_messages.py`
Dùng cho:
- user-facing workflow messages
- thiếu input/cấu hình cần thiết trước khi chạy action
- provider/config/runtime errors cần wording thân thiện
- preview/batch/history/workspace warnings cần format thống nhất

Quy ước:
- Đây là lớp chuẩn cho **workflow feedback** hướng người dùng.
- Không dùng lớp này cho shell-level monitor/status thuần runtime.

#### Trong `common/gui/shell.py`
Được phép giữ trực tiếp:
- pipeline status bar
- global run monitor
- handoff status
- timeline / empty-state của monitor

Quy ước:
- `shell.py` là **workspace composition + shell-level observability**.
- Các `st.info/st.warning/st.error/st.success` ở đây được chấp nhận khi chúng biểu diễn **runtime status**, không phải guidance cho một action cụ thể của người dùng.
- Nếu cần hiện chi tiết kỹ thuật, ưu tiên `expander` / diagnostics block thay vì bung raw exception vào vùng chính.
- Chỉ tách riêng `monitor_panel.py` hoặc lớp tương tự khi shell-level observability trở nên đủ lớn hoặc được tái sử dụng rộng hơn.

### Pattern xử lý khuyến nghị
#### 1. Validate trước khi chạy action
```python
def can_run_video(settings) -> tuple[bool, str | None]:
    if not settings.audio_input:
        return False, "Chưa có audio input. Hãy render Audio trước hoặc chọn file thủ công."
    if not settings.output_input:
        return False, "Chưa có output path. Hãy kiểm tra Output settings."
    return True, None
```

```python
ok, message = can_run_video(settings)
if not ok:
    st.warning(message)
    st.stop()
```

#### 2. Bọc action bằng thông báo thân thiện
```python
try:
    result = run_provider_test(...)
except Exception as exc:
    st.error("Không thể kiểm tra provider.")
    st.info("Hãy kiểm tra cấu hình provider rồi thử lại.")
    record_diagnostics("provider_test", str(exc))
else:
    st.success("Provider phản hồi bình thường.")
```

#### 3. Không làm app chết vì lỗi preview phụ
```python
try:
    render_preview(path)
except Exception as exc:
    st.warning("Không mở được preview cho output này.")
    st.info("Bạn vẫn có thể tải file xuống hoặc xem trong thư mục output.")
    record_diagnostics("preview", str(exc))
```

### Quy ước mức thông báo
- `st.success`: thao tác hoàn tất, trạng thái tốt
- `st.info`: hướng dẫn trung tính, bước tiếp theo
- `st.warning`: thiếu cấu hình, thiếu input, fallback mode, degraded mode
- `st.error`: action thất bại hoặc không thể tiếp tục ở màn hình hiện tại

### Khi nào dùng `st.stop()`
Chỉ dùng khi:
- màn hình hiện tại không thể render đúng nếu thiếu dữ liệu bắt buộc
- tiếp tục render sẽ tạo lỗi dây chuyền hoặc thông tin sai

Không dùng `st.stop()` cho:
- preview lỗi nhẹ
- history rỗng
- diagnostics phụ
- thiếu output phụ nhưng output chính vẫn còn

### Debug mode
Nếu cần xem lỗi kỹ thuật chi tiết, chỉ hiển thị khi có cờ debug, ví dụ:
```python
if st.session_state.get("workspace_debug_mode"):
    st.exception(exc)
```

Mặc định production/dev bình thường nên dùng:
- thông báo thân thiện
- diagnostics rút gọn
- event log nội bộ

### Checklist khi sửa GUI
Trước khi merge một màn hình mới hoặc sửa một action cũ, kiểm tra:
- có validate input/config trước khi chạy chưa?
- có thông báo người dùng hiểu được không?
- có hướng dẫn bước tiếp theo không?
- có fallback/degraded mode không?
- có chặn đúng action thay vì làm sập cả app không?
- exception kỹ thuật đã được đưa vào diagnostics thay vì bung thẳng ra UI chưa?

### Anti-pattern cần tránh
- `raise` trực tiếp từ UI callback cho lỗi cấu hình dự đoán được
- show raw traceback cho lỗi người dùng có thể tự sửa
- thông báo kiểu chung chung: `Something went wrong`
- warning nhưng không nói người dùng phải làm gì tiếp theo
- bắt exception rồi im lặng hoàn toàn

### Quy ước ngắn cho team
- **User-facing UI:** thân thiện, hành động được
- **Diagnostics:** kỹ thuật, ngắn gọn, có ngữ cảnh
- **Exceptions:** chỉ bung thẳng trong debug mode hoặc lỗi không thể phục hồi


---

## Source document: `INTEGRATED_IMAGE_BRANCH_NOTES.md`

### Integrated build notes

This integrated build adds:

- Story image prompt generation for:
  - cover
  - scene overview
  - intro
  - intro_card
  - greeting
  - opening
  - introduction
  - development
  - climax
  - falling
  - ending
  - farewell
  - outro_card
- Story handoff bundle with `kind`, `slot`, and `image_key`
- Image studio branch with providers:
  - `stable_diffusion_local` = headless/local runtime qua Python (không cần URL)
  - `stable_diffusion_remote`
  - `comfyui_local`
  - `comfyui_remote`
- Auto workflow routing in Image studio:
  - cover -> hires cover workflow
  - scenes -> standard scene workflow
- Unified studio shell updated to include Image
- Video input prefill from Image handoff
- Included ComfyUI workflow presets under `image/_shared/assets/workflows/`

## Recommended quick start

1. Run Story GUI or unified studio and generate a story.
2. Click `Send to Image`.
3. In Image studio, choose either:
   - A1111-compatible provider, or
   - ComfyUI provider with:
     - cover workflow = `image/_shared/assets/workflows/comfyui_story_cover_9x16_hires_v2_workflow.json`
     - scene workflow = `image/_shared/assets/workflows/comfyui_story_9x16_cover_scene_workflow.json`
4. Generate images.
5. Click `Send to Video`.
6. Render video in slideshow mode.

## Important setup note

For ComfyUI workflows, replace `PUT_YOUR_CHECKPOINT_HERE.safetensors` with a real checkpoint name available on your ComfyUI server.


## Local headless Stable Diffusion provider

`stable_diffusion_local` nay chạy trực tiếp trong process Python qua `diffusers`/`torch`, không gọi A1111 bằng HTTP.

Gợi ý cài thêm dependency cho local provider:

```bash
pip install torch diffusers transformers accelerate safetensors
```

Ví dụ model:
- `runwayml/stable-diffusion-v1-5`
- `stabilityai/stable-diffusion-xl-base-1.0`
- hoặc đường dẫn local tới model/checkpoint

Có thể dùng biến môi trường `AI_STUDIO_IMAGE_MODEL` để khai báo model mặc định.

## Patch 2: Stable Diffusion local nâng cao

Bổ sung trong `stable_diffusion_local`:
- ưu tiên GPU mặc định (`prefer_gpu` -> `cuda` -> `mps` -> `cpu`)
- preload model lúc startup để tránh cold start ở lần generate đầu
- UI ẩn hoàn toàn phần ComfyUI khi chọn `stable_diffusion_local`
- thêm mode local `txt2img` / `img2img` / `controlnet`
- thêm local ADetailer-like pass để refine face/manual regions bằng một img2img pass cục bộ sau generate

### Ghi chú triển khai
- `img2img` cần `local_init_image` hoặc `init_image` / `image` trong `provider_payload` hay prompt JSON.
- `controlnet` cần `local_controlnet_model_id_or_path` và `local_control_image` / `control_image`.
- `local_control_preprocessor` hiện hỗ trợ `none` và `canny`.
- "ADetailer local" ở patch này là bản headless tương đương theo hướng practical:
  - detector `face_haar` (nếu có OpenCV)
  - hoặc `manual_regions` bằng JSON
  - sau đó refine từng region qua img2img pipeline và paste ngược vào ảnh gốc
- Đây không phải bản clone 1:1 của extension ADetailer trong AUTOMATIC1111, nhưng đáp ứng được luồng local/headless cùng mục tiêu refine chi tiết mà không cần web UI.

## Patch 3 additions
- Thêm tab `Prompt` trong Image workspace để xem/sửa `prompt` và `negative_prompt` trước khi render.
- `prompt_overrides` giờ hỗ trợ payload dạng dict (`prompt`, `negative_prompt`) nhưng vẫn tương thích với override chuỗi cũ.
- `stable_diffusion_local` hỗ trợ thêm `inpaint` local.
- `img2img` / `controlnet` / `inpaint` có thể tự resolve asset từ prompt bundle + `manifest.json`, không bắt buộc nhập path tay.
- Local ADetailer detector mặc định chuyển sang `cascade_combo` (frontal face + profile face + upper body + full body) để mạnh hơn `face_haar`.


## Patch 5
- Chuẩn hóa thông báo UI trong nhánh Image theo prefix `Image:` cho các lỗi/trạng thái chính.
- Thêm mask editor controls: brush / eraser / undo / clear.
- Thêm detector preview boxes cho local ADetailer trong tab Inpaint và tab Test.
- Cho phép chuyển preview boxes sang `manual_regions` để fine-tune trước khi render.

## Patch 7
- Thêm `Mask overlay opacity` và `Mask overlay color` ngay trong tab Inpaint để chỉnh trực tiếp preview mask.
- Overlay mới được áp dụng cho preview đang vẽ và cả `Saved mask overlay`.
- Thêm nút `Export preview sheet to bundle` để lưu một ảnh tổng hợp phục vụ debug nhanh.
- Preview sheet gồm các panel: source, mask overlay, detector boxes, mask, và crop theo từng region detector.
- Ảnh export được lưu vào `debug_previews/<image_key>_preview_sheet.png` trong prompt bundle hiện tại.

## Patch 8
- Model/cache ???c ??t theo module t?i `audio/models/`, `story/local_models/`, `image/local_models/`, `video/local_models/` ?? tr?nh l?n v?i m? ngu?n.
- Image local dùng offline-first; chỉ cho phép tải online khi action Update gọi local runtime với `local_allow_network=True`.
- Story/Audio/Image/Video sidebar đều có bộ nút Refresh / Test / Update theo provider/runtime hiện tại.

## Patch 10
- comfyui_local chạy headless/local qua workflow interpreter nội bộ, không gọi URL.
- Sidebar Image bỏ field Negative prompt; Negative prompt được chỉnh trong tab Prompt.
- Thêm Open target folder / Copy target path cho local model targets.
- Thêm auto-detect model type để gợi ý provider/mode phù hợp.


---

## Source document: `TYPED_SESSION_ALIGNMENT_NOTES.md`

### Typed session alignment

This patch aligns Audio and Video session access with the same typed-access pattern now present in Story.

## Added
- `story.gui.state.StorySession` + `story_session()`
- `audio.gui.state.AudioSession` + `audio_session()`
- `video.gui.state.VideoSession` + `video_session()`
- constants for the main session keys in each state module
- headless smoke tests in `tests/smoke/test_typed_sessions.py`

## Updated
- `audio/gui/workspace.py` now uses `AudioSession` for pending plain-script and Story handoff sync paths
- `video/gui/tabs.py` now uses `VideoSession` for Audio handoff sync paths

## Validation
- `python -m py_compile $(find audio story video common tests -name '*.py' -type f)`
- `python -m unittest tests.smoke.test_typed_sessions -v`

## Note
The broader Video GUI split is still incomplete in this codebase: `video/gui/app.py` references `.settings` and `.tabs` that are not present. This patch did not broaden scope to fix that legacy/package split, because the request here was limited to typed state alignment.


---

## Source document: `UNIFIED_GUI.md`

### Unified GUI

## Mục tiêu

Tạo một giao diện Streamlit chung cho toàn bộ project để người dùng đi theo một luồng thống nhất:
- Story
- Audio
- Image
- Video

## Entry point mới

- `studio.gui_entry`
- `studio/studio_gui.bat`
- console script: `ai-studio-gui`

Chạy bằng:

```bash
py -m streamlit run studio/gui_entry.py
```

## Kiến trúc

### Shell dùng chung
- `common.gui.shell.render_workspace_shell()`
- `common.gui.state.ensure_workspace_shell_state()`

### Embedded renderers
- `story.gui.app.render_story_workspace(embedded=True)`
- `audio.gui.app.render_audio_workspace(embedded=True)`
- `image.gui.app.render_image_workspace(embedded=True)`
- `video.gui.app.render_video_workspace(embedded=True)`

Mỗi studio vẫn giữ `main()` riêng để tương thích với launcher cũ và console script riêng.

## Lợi ích
- Một workspace duy nhất cho toàn bộ pipeline
- Giữ console scripts tương thích qua các launcher module `story.gui_entry`, `audio.gui_entry`, `image.gui_entry`, `video.gui_entry`
- Tách rõ shell chung và module UI theo app
- Có sidebar chung để điều hướng và theo dõi handoff output

## Hướng phát triển tiếp
- Đồng bộ state contract giữa Story / Audio / Image / Video sâu hơn
- Tự động prefill đầu vào Audio từ output Story
- Tự động prefill đầu vào Image từ handoff bundle của Story
- Tự động prefill đầu vào Video từ output Audio và output Image
- Gom component sidebar lặp lại vào `common.gui`
- Bổ sung Run Monitor chung cho toàn bộ pipeline

## Auto-prefill behavior

Unified Workspace now supports handoff prefill:

- **Story → Audio**
  - Sau khi Story generate thành công, plain script gần nhất sẽ được lưu trong studio state.
  - Audio sẽ tự điền `Plain Script` và `Script sẽ dùng để chạy` nếu các ô này còn trống hoặc vẫn đang giữ giá trị auto của lần trước.
  - Nếu người dùng đã sửa tay nội dung trong Audio, handoff mới sẽ **không** ghi đè.

- **Story → Image**
  - Sau khi Story generate thành công, GUI có thể lưu handoff bundle prompt ảnh gần nhất.
  - Image nhận bundle này để render cover/scenes mà không cần copy tay giữa hai app.

- **Audio → Video**
  - Sau khi Audio render thành công, GUI sẽ lưu:
    - đường dẫn audio output gần nhất
    - đường dẫn subtitle `.srt` gần nhất (nếu có)
  - Video sẽ tự điền:
    - `Audio file`
    - `Subtitle file`
    - `Output MP4` (gợi ý theo stem của audio output)
  - Prefill chỉ xảy ra khi ô đích còn trống hoặc vẫn đang mang giá trị auto trước đó.

This behavior keeps the workflow smooth while preserving manual user edits.

## Manual handoff controls

Unified Workspace now also supports explicit handoff buttons:

- **Story**
  - `Send to Audio`
  - gửi plain script hiện tại sang Audio
  - đồng thời bật `Lock input to Story handoff`

- **Story**
  - `Send to Image`
  - gửi bundle prompt ảnh hiện tại sang Image

- **Audio**
  - `Send to Video`
  - gửi audio output + subtitle gần nhất sang Video
  - đồng thời bật `Lock input to Audio handoff`

## Lock behavior

- Khi lock bật, bước nhận sẽ tiếp tục bám theo handoff mới nhất từ bước trước.
- Khi lock tắt, hệ thống chỉ prefill theo kiểu best-effort và sẽ không dễ dàng ghi đè phần người dùng sửa tay.
- Nút handoff cũng tự chuyển focus workspace sang bước tiếp theo trong Unified Workspace.

## Pipeline status bar

Unified Workspace now shows a pipeline status bar at the top of the page:

- `Story: ready / sent`
- `Audio: ready / sent`
- `Image: ready / rendered`
- `Video: rendered`

Current semantics:
- **Story = ready**
  - có plain script hoặc handoff bundle sẵn sàng trong shared studio state
- **Story = sent**
  - người dùng đã gửi handoff sang Audio hoặc Image
- **Audio = ready**
  - đã có audio output gần nhất sẵn sàng cho Video
- **Audio = sent**
  - người dùng đã gửi handoff sang Video và đang bật lock theo handoff đó
- **Image = ready / rendered**
  - đã có handoff bundle để render hoặc đã có output cover/scenes gần nhất
- **Video = rendered**
  - đã có output MP4 gần nhất trong studio state

## Clickable pipeline status bar

The pipeline status bar at the top of Unified Workspace is now clickable.

- Click **Story** status to jump to Story studio
- Click **Audio** status to jump to Audio studio
- Click **Image** status to jump to Image studio
- Click **Video** status to jump to Video studio

This turns the status bar into both:
- a quick pipeline monitor
- a fast navigation control

## Deep-link tab navigation

The clickable pipeline status bar now opens the target studio **and** selects a relevant sub-view:

- **Story**
  - opens `Preview & Logs` when story output is already ready/sent
  - otherwise opens `Run`
- **Audio**
  - opens `Run`
- **Image**
  - opens the primary render/import view used for handoff bundles
- **Video**
  - opens `Inputs` when preparing a new render
  - opens `Run` when a video has already been rendered

In Unified Workspace embedded mode, Story / Audio / Image / Video now use a state-driven view selector so the shell can deep-link into the correct sub-view.

## Global run monitor

Unified Workspace now includes a global run monitor at the shell level.

It shows the latest job across the whole pipeline:
- app
- stage
- status
- progress
- output path
- last error
- last summary

Current sources:
- **Story**: generate success/failure
- **Audio**: render/validate success-failure and latest output
- **Image**: render success/failure and latest outputs
- **Video**: render success/failure and latest MP4

The monitor stays visible no matter which studio is currently open.

## Pipeline timeline

The global monitor now also includes a pipeline timeline.

It keeps the latest events across Story / Audio / Image / Video, for example:
- job started
- job completed
- job failed
- output produced

Current timeline fields:
- time
- app
- stage
- status
- message
- output

The timeline is capped to the latest 20 events in session state.

## Timeline controls

The pipeline timeline now supports session-level controls:

- filter by app:
  - `All`
  - `Story`
  - `Audio`
  - `Image`
  - `Video`
- `Failed only`
  - only show failed/error events
- `Clear timeline`
  - clears the current session timeline

These controls only affect the current Streamlit session state.


---

## Source document: `audio/API_SURFACE.md`

### audio package API surface

## Public modules
- `audio.render_audio_app`
- `audio.app_config`
- `audio.profile_config`
- `audio.tts_provider`
- `audio.voice_catalog`
- `audio.cli`
- `audio.entrypoints`
- `audio.doctor`
- `audio.gui_entry`
- `audio.gui`

## Internal subpackages
- `audio.adapters`
- `audio.models`
- `audio.pipeline`
- `audio.services`

Code outside `audio/` should avoid importing internal subpackages directly unless
there is a deliberate extension point and the dependency is pinned.

---

## Source document: `image/_shared/assets/profiles/demo/manifest.json`

### demo

Minimal committed asset profile for tests and runtime defaults.

Default Vietnamese voice presets in this demo profile are aligned with VieNeu TTS core canonical names: Thục Đoan, Phạm Tuyên, Bích Ngọc, Xuân Vĩnh.
