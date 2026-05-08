from __future__ import annotations

import re
from typing import Any

_SCRIPT_ITEM_RE = re.compile(
    r"script\[(?P<index>\d+)\]\.text phải chứa đúng 1 câu(?:\.\s*text=(?P<preview>.*))?",
    re.IGNORECASE,
)


class StoryGenerationError(Exception):
    def __init__(self, message: str, *, authoring: dict[str, Any] | None = None, plain_script: str = "") -> None:
        super().__init__(message)
        self.authoring = authoring
        self.plain_script = plain_script


class StoryLLMOutputError(ValueError):
    def __init__(self, message: str, *, raw_response: str = "") -> None:
        super().__init__(message)
        self.raw_response = raw_response


def split_runtime_error_details(message: str) -> tuple[str, str]:
    text = str(message or "").strip()
    marker = "Chi tiết kỹ thuật:"
    if marker not in text:
        return text, ""
    friendly, technical = text.split(marker, 1)
    return friendly.strip(), technical.strip()


def extract_script_item_error_details(text: str) -> dict[str, Any] | None:
    source = str(text or "").strip()
    if not source:
        return None
    match = _SCRIPT_ITEM_RE.search(source)
    if not match:
        return None
    preview = (match.group("preview") or "").strip().strip('"\'')
    return {"index": int(match.group("index")), "preview": preview, "raw": source}


def build_error_context(exc: Exception) -> dict[str, Any]:
    raw_text = str(exc).strip() or exc.__class__.__name__
    details = extract_script_item_error_details(raw_text) or {}
    authoring = getattr(exc, "authoring", None)
    plain_script = str(getattr(exc, "plain_script", "") or "")
    raw_response = str(getattr(exc, "raw_response", "") or "")
    item_index = details.get("index")
    script_item = None
    script_excerpt: list[str] = []
    if isinstance(authoring, dict):
        script = authoring.get("script")
        if isinstance(script, list) and isinstance(item_index, int) and 0 <= item_index < len(script):
            script_item = script[item_index]
            start = max(0, item_index - 2)
            end = min(len(script), item_index + 3)
            for idx in range(start, end):
                item = script[idx]
                marker = ">>>" if idx == item_index else "   "
                zone = item.get("zone") if isinstance(item, dict) else "?"
                text = item.get("text") if isinstance(item, dict) else str(item)
                script_excerpt.append(f"{marker} script[{idx}] [{zone}] {text}")
    plain_excerpt: list[str] = []
    if plain_script and isinstance(item_index, int):
        lines = plain_script.splitlines()
        start = max(0, item_index - 2)
        end = min(len(lines), item_index + 3)
        for idx in range(start, end):
            marker = ">>>" if idx == item_index else "   "
            plain_excerpt.append(f"{marker} line {idx + 1}: {lines[idx]}")
    return {
        "raw_text": raw_text,
        "item_index": item_index,
        "preview": details.get("preview") or "",
        "script_item": script_item,
        "script_excerpt": script_excerpt,
        "plain_excerpt": plain_excerpt,
        "authoring": authoring,
        "plain_script": plain_script,
        "raw_response": raw_response,
        "raw_response_excerpt": raw_response[:2000],
    }


def format_runtime_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    lower = text.lower()

    if "message content must be a non-empty string" in lower or "response was empty" in lower:
        return f"Model không trả nội dung trong message response. Hãy thử chạy lại, kiểm tra model local có đang sinh output, hoặc tăng nhẹ Max tokens nếu cần. Chi tiết kỹ thuật: {text}"
    if "outline response is not valid json" in lower:
        return f"Model trả về outline chưa đúng định dạng JSON. App đã yêu cầu JSON ngắn hơn; hãy thử chạy lại, hoặc tăng Max tokens lên 2048-3072 nếu model vẫn bị cắt output. Chi tiết kỹ thuật: {text}"
    if "yaml" in lower or "mapping values are not allowed" in lower or "scannererror" in lower or "parsererror" in lower:
        return f"Brief YAML chưa hợp lệ. Hãy kiểm tra lại thụt dòng, dấu ':' và cấu trúc danh sách. Chi tiết kỹ thuật: {text}"
    if "timeout" in lower or "timed out" in lower:
        return f"Hết thời gian chờ khi gọi model/endpoint. Hãy tăng Timeout hoặc kiểm tra máy chủ LLM. Chi tiết kỹ thuật: {text}"
    if "connection refused" in lower or "failed to establish a new connection" in lower or "name or service not known" in lower:
        return f"Không kết nối được tới LLM base URL. Hãy kiểm tra địa chỉ máy chủ, cổng và tình trạng service. Chi tiết kỹ thuật: {text}"
    if "could not extract json array" in lower:
        return f"Model có phản hồi nhưng phần chunk không ra JSON array đúng schema. Hãy bật chunked nếu đang tắt, hoặc nếu đã bật thì giảm chunk size và thử lại. Chi tiết kỹ thuật: {text}"
    if "expecting" in lower or "json" in lower:
        return f"Model trả về dữ liệu không đúng định dạng JSON mong đợi. Hãy thử prompt chặt hơn hoặc bật chế độ chunked. Chi tiết kỹ thuật: {text}"
    if "không tạo được item hợp lệ" in lower:
        return f"Model có phản hồi nhưng không tạo được script item hợp lệ cho một zone. Hãy giảm chunk size hoặc thử lại với mode khác. Chi tiết kỹ thuật: {text}"
    return f"Đã xảy ra lỗi khi chạy pipeline. Chi tiết kỹ thuật: {text}"


def summarize_settings_for_logs(settings: dict[str, Any]) -> dict[str, Any]:
    safe = dict(settings)
    if safe.get("api_key"):
        safe["api_key"] = "***"
    return safe
