from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewSpec:
    id: str
    label: str
    description: str


VIDEO_VIEW_SPECS = (
    ViewSpec("inputs", "Đầu vào", "Chuẩn bị và kiểm tra tài nguyên dùng để tạo video."),
    ViewSpec("test", "Xem trước", "Đối chiếu đầu vào và xem trước kế hoạch video thực tế."),
    ViewSpec("doctor", "Kiểm tra", "Kiểm tra runtime, đầu vào và mức sẵn sàng của hình ảnh."),
    ViewSpec("run", "Render", "Xác thực và render tác vụ video hiện tại."),
    ViewSpec("results_logs", "Kết quả & nhật ký", "Xem video đầu ra và nhật ký chạy gần nhất."),
    ViewSpec("history", "Lịch sử", "Xem các lần render video trong phiên hiện tại."),
    ViewSpec("concat", "Ghép clip", "Join numbered video clips into one MP4."),
    ViewSpec("models", "Mô hình", "Kiểm tra và bảo trì mô hình video cục bộ."),
)

VIDEO_VIEW_IDS = tuple(spec.id for spec in VIDEO_VIEW_SPECS)
VIDEO_VIEW_BY_ID = {spec.id: spec for spec in VIDEO_VIEW_SPECS}

_LEGACY_VIEW_IDS = {
    "Input": "inputs",
    "Inputs": "inputs",
    "Run": "run",
    "Ghép clip": "concat",
    "Doctor": "doctor",
    "Test": "test",
    "Preview & Logs": "results_logs",
    "Results & Logs": "results_logs",
    "History": "history",
    "Models": "models",
    "Đầu vào": "inputs",
    "Xem trước": "test",
    "Kiểm tra": "doctor",
    "Render": "run",
    "Kết quả & nhật ký": "results_logs",
    "Lịch sử": "history",
    "Mô hình": "models",
}


def normalize_video_view_id(value: str, default: str = "inputs") -> str:
    candidate = _LEGACY_VIEW_IDS.get(str(value or "").strip(), str(value or "").strip())
    return candidate if candidate in VIDEO_VIEW_BY_ID else default
