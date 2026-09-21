from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewSpec:
    id: str
    label: str
    description: str


AUDIO_VIEW_SPECS = (
    ViewSpec("inputs", "Đầu vào", "Chuẩn bị và kiểm tra kịch bản dùng để tạo âm thanh."),
    ViewSpec("test", "Nghe thử", "Nghe thử nhà cung cấp và giọng đọc trước khi render toàn bộ."),
    ViewSpec("doctor", "Kiểm tra", "Kiểm tra runtime, nhà cung cấp, tài nguyên và cấu hình."),
    ViewSpec("run", "Render", "Xác thực và render tác vụ âm thanh hiện tại."),
    ViewSpec("results_logs", "Kết quả & nhật ký", "Xem đầu ra, bản nghe và nhật ký sự kiện gần nhất."),
    ViewSpec("history", "Lịch sử", "Xem các tác vụ âm thanh đã hoàn tất hoặc thất bại."),
    ViewSpec("batch", "Hàng loạt", "Chạy manifest và thử lại các tác vụ đủ điều kiện."),
    ViewSpec("voices", "Giọng đọc", "Tạo và quản lý giọng VieNeu đã clone."),
    ViewSpec("models", "Mô hình", "Kiểm tra và bảo trì mô hình âm thanh cục bộ."),
)

AUDIO_VIEW_IDS = tuple(spec.id for spec in AUDIO_VIEW_SPECS)
AUDIO_VIEW_BY_ID = {spec.id: spec for spec in AUDIO_VIEW_SPECS}

_LEGACY_VIEW_IDS = {
    "Input": "inputs",
    "Inputs": "inputs",
    "Run": "run",
    "Batch": "batch",
    "Doctor": "doctor",
    "Test TTS": "test",
    "Test": "test",
    "Preview & Logs": "results_logs",
    "Results & Logs": "results_logs",
    "History": "history",
    "Models": "models",
    "Voices": "voices",
    "Đầu vào": "inputs",
    "Nghe thử": "test",
    "Kiểm tra": "doctor",
    "Render": "run",
    "Kết quả & nhật ký": "results_logs",
    "Lịch sử": "history",
    "Hàng loạt": "batch",
    "Giọng đọc": "voices",
    "Mô hình": "models",
}


def normalize_audio_view_id(value: str, default: str = "inputs") -> str:
    candidate = _LEGACY_VIEW_IDS.get(str(value or "").strip(), str(value or "").strip())
    return candidate if candidate in AUDIO_VIEW_BY_ID else default
