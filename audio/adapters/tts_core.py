import asyncio
import importlib.util
import inspect
import logging
import os
import shutil
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from audio.env_runtime import bootstrap_vieneu_runtime, prefer_gpu_enabled
from audio.exceptions import TtsDependencyError, TtsError
from audio.pipeline.segment_planner import Segment
from audio.pipeline.flow_state import normalize_rate_value
from audio.pipeline.segment_planner import rate_str_to_factor
from audio.model_store import list_local_targets, provider_cache_dir, provider_target_dir

DEFAULT_VIENEU_MODE = "standard"
SUPPORTED_VIENEU_MODES = (
    "turbo",
    "standard",
    "remote",
    "api",
    "fast",
    "cuda",
    "turbo_gpu",
    "xpu",
)
DEFAULT_VIENEU_TURBO_MODEL_NAME = "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF"
DEFAULT_VIENEU_STANDARD_MODEL_NAME = "pnnbao-ump/VieNeu-TTS"
DEFAULT_VIENEU_MODEL_NAME = DEFAULT_VIENEU_STANDARD_MODEL_NAME
DEFAULT_VIENEU_STANDARD_CODEC_REPO = "neuphonic/distill-neucodec"
DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO = "ntu-spml/distilhubert"
DEFAULT_VIENEU_API_BASE = "http://127.0.0.1:23333/v1"
DEFAULT_VIENEU_DEVICE = "cuda"

_ENGINE_LOCK = threading.Lock()
_ENGINE_CACHE: dict[tuple[str, str, str, bool], Any] = {}
_LOG = logging.getLogger(__name__)
_VIENEU_STANDARD_OFFLINE_PATCHED = False
_TRANSFORMERS_META_TO_EMPTY_PATCHED = False


def _vieneu_models_root() -> Path:
    return provider_target_dir("audio", "vieneu", __file__)


def get_default_vieneu_local_target(mode: object = DEFAULT_VIENEU_MODE) -> str:
    resolved_mode = normalize_vieneu_mode(mode)
    if resolved_mode == "standard":
        return "VieNeu-TTS"
    return "VieNeu-TTS-v2-Turbo-GGUF"


def _vieneu_codec_root() -> Path:
    return provider_target_dir("audio", "vieneu_codec", __file__)


def _vieneu_distilhubert_root() -> Path:
    return provider_target_dir("audio", "vieneu_distilhubert", __file__)


def _hf_repo_cache_snapshot(repo_id: object) -> Path | None:
    raw = str(repo_id or "").strip().strip("/")
    if not raw or "/" not in raw:
        return None
    org, name = raw.split("/", 1)
    hub_root = provider_cache_dir("audio", __file__) / "hub"
    repo_root = hub_root / f"models--{org}--{name}" / "snapshots"
    if not repo_root.exists():
        return None
    candidates = [
        item
        for item in sorted(repo_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if item.is_dir()
    ]
    for candidate in candidates:
        if (candidate / "config.json").exists() or (candidate / "meta.yaml").exists() or any(candidate.iterdir()):
            return candidate
    return None


def _local_dependency_source_root(target_root: Path, repo_id: object) -> Path | None:
    repo_label = str(repo_id or "").strip().replace("/", "__")
    candidates: list[Path] = []
    if repo_label:
        candidates.append((target_root / repo_label).resolve())
    candidates.append(target_root.resolve())

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if not candidate.exists():
            continue
        if candidate.is_dir() and any(candidate.iterdir()):
            direct_files = {child.name for child in candidate.iterdir() if child.is_file()}
            if direct_files.intersection({"config.json", "meta.yaml", "tokenizer_config.json", "preprocessor_config.json"}):
                return candidate
            child_dirs = [
                item
                for item in sorted(candidate.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
                if item.is_dir()
            ]
            for child in child_dirs:
                try:
                    if any(child.iterdir()):
                        return child
                except Exception:
                    continue
    return None


def _ensure_local_repo_snapshot(repo_id: object, source_root: Path | None) -> Path | None:
    existing = _hf_repo_cache_snapshot(repo_id)
    if existing is not None:
        return existing
    if source_root is None or not source_root.exists() or not source_root.is_dir():
        return None
    raw = str(repo_id or "").strip().strip("/")
    if not raw or "/" not in raw:
        return None
    org, name = raw.split("/", 1)
    hub_root = provider_cache_dir("audio", __file__) / "hub"
    snapshot_root = (hub_root / f"models--{org}--{name}" / "snapshots" / "local-adopted").resolve()
    snapshot_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, snapshot_root, dirs_exist_ok=True)
    return snapshot_root if snapshot_root.exists() else None


def _ensure_vieneu_standard_dependency_snapshots() -> tuple[str, ...]:
    missing: list[str] = []

    codec_source = _local_dependency_source_root(_vieneu_codec_root(), DEFAULT_VIENEU_STANDARD_CODEC_REPO)
    codec_snapshot = _ensure_local_repo_snapshot(DEFAULT_VIENEU_STANDARD_CODEC_REPO, codec_source)
    if codec_snapshot is None:
        missing.append(
            f"codec '{DEFAULT_VIENEU_STANDARD_CODEC_REPO}' (hãy đặt local snapshot vào {_vieneu_codec_root()})"
        )

    distilhubert_source = _local_dependency_source_root(
        _vieneu_distilhubert_root(),
        DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO,
    )
    distilhubert_snapshot = _ensure_local_repo_snapshot(
        DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO,
        distilhubert_source,
    )
    if distilhubert_snapshot is None:
        missing.append(
            f"distilhubert '{DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO}' "
            f"(hãy đặt local snapshot vào {_vieneu_distilhubert_root()})"
        )

    return tuple(missing)


def _resolve_vieneu_dependency_snapshot(repo_id: object, *, source_root: Path) -> Path | None:
    snapshot = _hf_repo_cache_snapshot(repo_id)
    if snapshot is not None:
        return snapshot.resolve()
    source = _local_dependency_source_root(source_root, repo_id)
    if source is None:
        return None
    adopted = _ensure_local_repo_snapshot(repo_id, source)
    return adopted.resolve() if adopted is not None else source.resolve()


def _patch_vieneu_standard_offline_dependencies() -> None:
    global _VIENEU_STANDARD_OFFLINE_PATCHED
    if _VIENEU_STANDARD_OFFLINE_PATCHED:
        return

    import torch
    import torch.nn as nn
    from transformers import AutoFeatureExtractor, HubertModel

    import vieneu.base as vieneu_base
    import neucodec.model as neucodec_model
    from neucodec.codec_decoder_vocos import CodecDecoderVocos
    from neucodec.codec_encoder_distill import DistillCodecEncoder
    from neucodec.module import SemanticEncoder

    original_neucodec_from_pretrained = neucodec_model.NeuCodec._from_pretrained.__func__
    original_load_codec = vieneu_base.BaseVieneuTTS._load_codec

    def _build_local_codec_instance(model_id: str, *, map_location: str = "cpu"):
        snapshot = _resolve_vieneu_dependency_snapshot(model_id, source_root=_vieneu_codec_root())
        if snapshot is None:
            return None

        ignore_keys = ["fc_post_s", "SemanticDecoder"] if model_id == "neuphonic/neucodec" else []
        ckpt_path = snapshot / "pytorch_model.bin"
        meta_path = snapshot / "meta.yaml"
        if not ckpt_path.exists() or not meta_path.exists():
            raise FileNotFoundError(
                f"VieNeu standard local/offline is missing codec files for '{model_id}' in {snapshot}."
            )

        model_cls = neucodec_model.NeuCodec if model_id == "neuphonic/neucodec" else neucodec_model.DistillNeuCodec
        model = model_cls(24_000, 480)
        state_dict = torch.load(ckpt_path, map_location)
        contains_list = lambda s, items: any(item in s for item in items)
        state_dict = {
            key: value
            for key, value in state_dict.items()
            if not contains_list(key, ignore_keys)
        }
        model.load_state_dict(state_dict, strict=False)
        return model

    def _patched_neucodec_from_pretrained(
        cls,
        *,
        model_id: str,
        revision: str | None = None,
        cache_dir: str | None = None,
        force_download: bool = False,
        proxies: dict | None = None,
        resume_download: bool = False,
        local_files_only: bool = False,
        token: str | None = None,
        map_location: str = "cpu",
        strict: bool = True,
        **model_kwargs,
    ):
        if model_id not in {"neuphonic/neucodec", "neuphonic/distill-neucodec"}:
            return original_neucodec_from_pretrained(
                cls,
                model_id=model_id,
                revision=revision,
                cache_dir=cache_dir,
                force_download=force_download,
                proxies=proxies,
                resume_download=resume_download,
                local_files_only=local_files_only,
                token=token,
                map_location=map_location,
                strict=strict,
                **model_kwargs,
            )

        snapshot = _resolve_vieneu_dependency_snapshot(model_id, source_root=_vieneu_codec_root())
        if snapshot is None:
            return original_neucodec_from_pretrained(
                cls,
                model_id=model_id,
                revision=revision,
                cache_dir=cache_dir,
                force_download=force_download,
                proxies=proxies,
                resume_download=resume_download,
                local_files_only=True,
                token=token,
                map_location=map_location,
                strict=strict,
                **model_kwargs,
            )

        model = _build_local_codec_instance(model_id, map_location=map_location)
        if model is None:
            raise FileNotFoundError(
                f"VieNeu standard local/offline could not resolve codec snapshot for '{model_id}'."
            )
        return model

    def _patched_distill_init(self, sample_rate: int, hop_length: int):
        nn.Module.__init__(self)
        self.sample_rate = sample_rate
        self.hop_length = hop_length

        distilhubert_path = _resolve_vieneu_dependency_snapshot(
            DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO,
            source_root=_vieneu_distilhubert_root(),
        )
        distilhubert_ref = str(distilhubert_path) if distilhubert_path is not None else DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO

        self.semantic_model = HubertModel.from_pretrained(
            distilhubert_ref,
            output_hidden_states=True,
            local_files_only=True,
        )
        self.feature_extractor = AutoFeatureExtractor.from_pretrained(
            distilhubert_ref,
            local_files_only=True,
        )
        self.SemanticEncoder_module = SemanticEncoder(768, 768, 1024)
        self.codec_encoder = DistillCodecEncoder()
        self.generator = CodecDecoderVocos(hop_length=hop_length)
        self.fc_prior = nn.Linear(768 + 768, 2048)
        self.fc_sq_prior = nn.Linear(512, 768)
        self.fc_post_a = nn.Linear(2048, 1024)

    def _patched_load_codec(self, codec_repo: str, codec_device: str) -> None:
        if codec_repo in {"neuphonic/neucodec", "neuphonic/distill-neucodec"}:
            logger = logging.getLogger("Vieneu")
            logger.info(f"Loading codec from local snapshot: {codec_repo} on {codec_device} ...")
            try:
                codec = _build_local_codec_instance(codec_repo, map_location="cpu")
            except Exception:
                codec = None
            if codec is not None:
                self.codec = codec.eval().to(codec_device)
                self._is_onnx_codec = False
                return
        return original_load_codec(self, codec_repo, codec_device)

    neucodec_model.NeuCodec._from_pretrained = classmethod(_patched_neucodec_from_pretrained)
    neucodec_model.DistillNeuCodec._from_pretrained = classmethod(_patched_neucodec_from_pretrained)
    neucodec_model.DistillNeuCodec.__init__ = _patched_distill_init
    vieneu_base.BaseVieneuTTS._load_codec = _patched_load_codec

    _VIENEU_STANDARD_OFFLINE_PATCHED = True


def _patch_transformers_meta_to_empty() -> None:
    global _TRANSFORMERS_META_TO_EMPTY_PATCHED
    if _TRANSFORMERS_META_TO_EMPTY_PATCHED:
        return

    try:
        import torch
        from transformers.modeling_utils import PreTrainedModel
    except Exception:
        return

    original_to = PreTrainedModel.to

    def _patched_to(self, *args, **kwargs):
        try:
            return original_to(self, *args, **kwargs)
        except NotImplementedError as exc:
            if "meta tensor" not in str(exc).lower():
                raise

            device = kwargs.get("device")
            if device is None and args:
                first_arg = args[0]
                if isinstance(first_arg, (str, torch.device)):
                    device = first_arg
            if device is None:
                device = "cpu"

            if hasattr(self, "to_empty"):
                try:
                    return self.to_empty(device=device)
                except TypeError:
                    return self.to_empty(device=torch.device(device))
            raise

    PreTrainedModel.to = _patched_to
    _TRANSFORMERS_META_TO_EMPTY_PATCHED = True


def get_vieneu_cached_codec_snapshot(repo_id: object = DEFAULT_VIENEU_STANDARD_CODEC_REPO) -> str:
    snapshot = _hf_repo_cache_snapshot(repo_id)
    return str(snapshot.resolve()) if snapshot else ""


def get_vieneu_cached_distilhubert_snapshot(
    repo_id: object = DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO,
) -> str:
    snapshot = _hf_repo_cache_snapshot(repo_id)
    return str(snapshot.resolve()) if snapshot else ""


def adopt_vieneu_cached_codec(
    repo_id: object = DEFAULT_VIENEU_STANDARD_CODEC_REPO,
    *,
    dest_name: object | None = None,
) -> str:
    snapshot = _hf_repo_cache_snapshot(repo_id)
    if snapshot is None:
        raise FileNotFoundError(
            f"Cached codec for '{repo_id}' was not found in audio/models/_cache/audio/hub. "
            "Run Update or Preview once while the machine has network access."
        )
    target_root = _vieneu_codec_root()
    raw_name = str(dest_name or "").strip() or str(repo_id).strip().replace("/", "__")
    target = (target_root / raw_name).resolve()
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot, target, dirs_exist_ok=True)
    return str(target)


def adopt_vieneu_cached_distilhubert(
    repo_id: object = DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO,
    *,
    dest_name: object | None = None,
) -> str:
    snapshot = _hf_repo_cache_snapshot(repo_id)
    if snapshot is None:
        raise FileNotFoundError(
            f"Cached distilhubert for '{repo_id}' was not found in audio/models/_cache/audio/hub. "
            "Run Preview in standard mode once while the machine has network access."
        )
    target_root = _vieneu_distilhubert_root()
    raw_name = str(dest_name or "").strip() or str(repo_id).strip().replace("/", "__")
    target = (target_root / raw_name).resolve()
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot, target, dirs_exist_ok=True)
    return str(target)


def _candidate_vieneu_local_paths(model_ref: object) -> tuple[Path, ...]:
    raw = str(model_ref or "").strip()
    if not raw:
        return tuple()
    models_root = _vieneu_models_root()
    expanded = Path(raw).expanduser()
    normalized = raw.rstrip("/\\")
    candidates = [expanded]
    if normalized:
        candidates.append((models_root / normalized).resolve())
        candidates.append((models_root / normalized.replace("/", os.sep)).resolve())
        candidates.append((models_root / normalized.replace("/", "__")).resolve())
    seen: set[str] = set()
    deduped: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return tuple(deduped)


def _normalize_vieneu_local_target(target: object, mode: object | None = None) -> str:
    raw = str(target or "").strip().replace("\\", "/")
    if not raw:
        return ""
    lowered = raw.lower().rstrip("/")
    resolved_mode = normalize_vieneu_mode(mode) if mode is not None else None

    if lowered.endswith('/config.json'):
        return raw.rsplit('/', 1)[0]
    if lowered.endswith('/generation_config.json'):
        return raw.rsplit('/', 1)[0]
    if lowered.endswith('/voices.json'):
        return raw.rsplit('/', 1)[0]

    path = Path(raw)
    suffix = path.suffix.lower()
    if suffix == ".gguf":
        if resolved_mode in {None, "turbo", "fast", "turbo_gpu", "xpu", "remote"}:
            return raw.rstrip("/")
        parent = str(path.parent).replace("\\", "/").strip()
        return parent or raw
    if suffix in {'.gguf', '.json', '.model', '.bin', '.safetensors', '.pt', '.pth', '.onnx'}:
        parent = str(path.parent).replace("\\", "/").strip()
        return parent or raw

    if resolved_mode == "standard":
        if suffix in {".json", ".model", ".bin", ".safetensors", ".pt", ".pth", ".onnx"}:
            parent = str(path.parent).replace("\\", "/").strip()
            return parent or raw
    return raw.rstrip("/")


def _vieneu_model_basename(target: object) -> str:
    raw = str(target or "").strip().replace("\\", "/").rstrip("/")
    if not raw:
        return ""
    name = Path(raw).name.strip()
    return name or raw


def _vieneu_model_sort_key(target: object, mode: object | None = None) -> tuple[int, int, str]:
    resolved_mode = normalize_vieneu_mode(mode) if mode is not None else None
    basename = _vieneu_model_basename(target)
    lowered = basename.lower()
    exact_default = get_default_vieneu_local_target(resolved_mode or DEFAULT_VIENEU_MODE).lower()
    starts_with_family = lowered.startswith("vieneu-tts")
    has_turbo_marker = "turbo" in lowered
    has_gguf_marker = lowered.endswith(".gguf") or "gguf" in lowered

    if resolved_mode == "standard":
        if lowered == exact_default:
            return (0, 0, lowered)
        if starts_with_family and not has_turbo_marker and not has_gguf_marker:
            return (1, 0, lowered)
        if not has_turbo_marker and not has_gguf_marker:
            return (2, 0, lowered)
        return (3, 0, lowered)

    if resolved_mode in {"turbo", "fast", "turbo_gpu", "xpu"}:
        if lowered == exact_default:
            return (0, 0, lowered)
        if starts_with_family and has_turbo_marker:
            return (1, 0, lowered)
        if starts_with_family and has_gguf_marker:
            return (2, 0, lowered)
        if has_turbo_marker:
            return (3, 0, lowered)
        if has_gguf_marker:
            return (4, 0, lowered)
        return (5, 0, lowered)

    return (0, 0, lowered)


def list_vieneu_local_models(mode: object | None = None, *, max_depth: int = 4) -> tuple[str, ...]:
    resolved_mode = normalize_vieneu_mode(mode) if mode is not None else None
    models_root = _vieneu_models_root()
    raw_targets = tuple(list_local_targets("audio", __file__, provider_id="vieneu", max_depth=max_depth))

    normalized: list[str] = []
    seen: set[str] = set()

    for item in raw_targets:
        label = _normalize_vieneu_local_target(item, resolved_mode)
        if not label:
            continue

        candidate = Path(label)
        if not candidate.is_absolute():
            candidate = (models_root / label).resolve()
        if candidate.is_file():
            if candidate.suffix.lower() == ".gguf":
                normalized_label = str(candidate).replace("\\", "/")
                if normalized_label not in seen:
                    seen.add(normalized_label)
                    normalized.append(normalized_label)
            continue
        if not candidate.is_dir():
            continue

        try:
            child_names = {child.name.lower() for child in candidate.iterdir()}
        except Exception:
            continue

        has_model_marker = (
            "voices.json" in child_names
            or "config.json" in child_names
            or "generation_config.json" in child_names
            or any(name.endswith(".gguf") for name in child_names)
        )
        if not has_model_marker:
            continue

        normalized_label = str(candidate).replace("\\", "/").rstrip("/")
        if normalized_label in seen:
            continue

        seen.add(normalized_label)
        normalized.append(normalized_label)

    normalized.sort(key=lambda item: _vieneu_model_sort_key(item, resolved_mode))
    targets = tuple(normalized)
    if resolved_mode is None:
        return targets

    compatible = tuple(item for item in targets if is_vieneu_mode_model_compatible(resolved_mode, item))
    return compatible or targets


def get_first_vieneu_local_model(mode: object | None = None) -> str:
    targets = list_vieneu_local_models(mode=mode)
    return str(targets[0]) if targets else ""


def resolve_vieneu_model_for_runtime(
    value: object,
    mode: object = DEFAULT_VIENEU_MODE,
    *,
    allow_network: bool = False,
) -> str:
    resolved_mode = normalize_vieneu_mode(mode)
    clean_model = _normalize_vieneu_local_target(
        validate_vieneu_mode_model_compatibility(resolved_mode, value),
        resolved_mode,
    )
    if resolved_mode == "remote":
        return clean_model

    for candidate in _candidate_vieneu_local_paths(clean_model):
        if candidate.exists():
            resolved_candidate = candidate.resolve()
            if resolved_candidate.is_file() and resolved_candidate.name.lower() in {"config.json", "generation_config.json"}:
                resolved_candidate = resolved_candidate.parent.resolve()
            return str(resolved_candidate)

    first_local = get_first_vieneu_local_model(resolved_mode)
    default_model = get_default_vieneu_model_name(resolved_mode)
    if first_local and str(clean_model or "").strip() in {"", default_model}:
        first_local_path = Path(str(first_local).strip()).expanduser()
        if not first_local_path.is_absolute():
            first_local_path = (_vieneu_models_root() / str(first_local).strip().rstrip("/\\")).resolve()
        else:
            first_local_path = first_local_path.resolve()
        return str(first_local_path)

    if allow_network:
        return clean_model

    raise FileNotFoundError(
        f"VieNeu local/offline could not find the model '{clean_model}' under {_vieneu_models_root()}. "
        "To fix this, place a local model in audio/models/vieneu/, select it from the Local model target dropdown, or run Update while the machine has network access."
    )


def get_default_vieneu_model_name(mode: object = DEFAULT_VIENEU_MODE) -> str:
    resolved_mode = normalize_vieneu_mode(mode)
    if resolved_mode == "standard":
        return DEFAULT_VIENEU_STANDARD_MODEL_NAME
    return DEFAULT_VIENEU_TURBO_MODEL_NAME


def resolve_vieneu_model_name(value: object, mode: object = DEFAULT_VIENEU_MODE) -> str:
    clean_value = str(value or "").strip()
    if clean_value:
        return clean_value
    return get_default_vieneu_model_name(mode)


def is_vieneu_mode_model_compatible(mode: object, model_name: object) -> bool:
    resolved_mode = normalize_vieneu_mode(mode)
    clean_model = str(model_name or "").strip().lower()
    if not clean_model or resolved_mode == "remote":
        return True
    if resolved_mode == "standard":
        return "turbo" not in clean_model and "gguf" not in clean_model
    if resolved_mode == "turbo":
        return "turbo" in clean_model or "gguf" in clean_model
    return True


def validate_vieneu_mode_model_compatibility(mode: object, model_name: object) -> str:
    resolved_mode = normalize_vieneu_mode(mode)
    resolved_model = resolve_vieneu_model_name(model_name, resolved_mode)
    if not is_vieneu_mode_model_compatible(resolved_mode, resolved_model):
        if resolved_mode == "standard":
            raise TtsError(
                "VieNeu standard mode yêu cầu model Standard/PyTorch-compatible, không dùng repo Turbo/GGUF."
            )
        if resolved_mode == "turbo":
            raise TtsError(
                "VieNeu turbo mode nên dùng model Turbo/GGUF để khớp runtime local hiện tại."
            )
    return resolved_model


def normalize_vieneu_mode(value: object) -> str:
    normalized = str(value or DEFAULT_VIENEU_MODE).strip().lower().replace("-", "_")
    aliases = {
        "local": "turbo",
        "default": "turbo",
        "turbo": "turbo",
        "standard": "standard",
        "remote": "remote",
        "api": "remote",
        "fast": "fast",
        "gpu": "fast",
        "cuda": "fast",
        "turbo_gpu": "turbo_gpu",
        "xpu": "xpu",
    }
    mode = aliases.get(normalized)
    if mode:
        return mode
    raise TtsError(
        f"VieNeu TTS core mode không hợp lệ: {value!r}. Hỗ trợ: {', '.join(SUPPORTED_VIENEU_MODES)}"
    )


def resolve_vieneu_effective_mode(core: object, mode: object, device: object | None = None) -> str:
    selected_core = str(core or "local").strip().lower().replace("-", "_").replace(" ", "_")
    selected_mode = normalize_vieneu_mode(mode)
    selected_device = resolve_vieneu_runtime_device(device)
    if selected_core in {"remote", "remote_api", "api", "remoteapi"}:
        return "remote"
    if selected_core == "local" and selected_device == "cuda":
        return "standard"
    return "standard" if selected_mode == "standard" else "turbo"


def _resolve_engine_mode(mode: object) -> str:
    resolved_mode = normalize_vieneu_mode(mode)
    if resolved_mode == "turbo" and prefer_gpu_enabled():
        return "turbo_gpu"
    return resolved_mode


def normalize_vieneu_device(value: object) -> str:
    normalized = str(value or DEFAULT_VIENEU_DEVICE).strip().lower().replace("-", "_")
    aliases = {
        "auto": "auto",
        "default": "auto",
        "prefer_gpu": "auto",
        "gpu": "cuda",
        "cuda": "cuda",
        "cuda:0": "cuda",
        "cpu": "cpu",
    }
    device = aliases.get(normalized)
    if device:
        return device
    raise TtsError(f"VieNeu runtime device is invalid: {value!r}. Supported: auto, cuda, cpu")


def resolve_vieneu_runtime_device(value: object) -> str:
    normalized = normalize_vieneu_device(value)
    if normalized == "auto":
        return "cuda" if prefer_gpu_enabled() else "cpu"
    return normalized


def _is_vieneu_lmdeploy_available() -> bool:
    return importlib.util.find_spec("lmdeploy") is not None


def normalize_vieneu_backend(value: object) -> str:
    normalized = str(value or "auto").strip().lower().replace("-", "_")
    if normalized in {"auto", "native", "lmdeploy"}:
        return normalized
    if normalized in {"default", "prefer_native"}:
        return "auto"
    return "auto"


def resolve_vieneu_runtime_backend(
    mode: object,
    model_name: object,
    device: object | None = None,
    backend: object | None = None,
) -> str:
    requested_backend = normalize_vieneu_backend(backend)
    resolved_mode = normalize_vieneu_mode(mode)
    resolved_device = resolve_vieneu_runtime_device(device)
    clean_model = str(model_name or "").strip().lower()
    supports_lmdeploy = resolved_mode == "standard" and resolved_device == "cuda"
    if "gguf" in clean_model or "turbo" in clean_model:
        supports_lmdeploy = False
    if requested_backend == "native":
        return "native"
    if requested_backend == "lmdeploy":
        return "lmdeploy" if supports_lmdeploy and _is_vieneu_lmdeploy_available() else "native"
    if not supports_lmdeploy:
        return "native"
    return "lmdeploy" if _is_vieneu_lmdeploy_available() else "native"


def _apply_vieneu_backend_kwargs(factory: Any, kwargs: dict[str, Any], backend: str) -> None:
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        signature = None
    if signature is None:
        return
    for key in ("backend", "engine", "backend_type", "runtime_backend"):
        if key in signature.parameters:
            kwargs[key] = backend
            return


def _import_vieneu_factory() -> Any:
    try:
        from vieneu import Vieneu  # type: ignore
    except Exception as exc:
        raise TtsDependencyError(
            "VieNeu TTS core cần package 'vieneu'. Hãy cài: pip install vieneu"
        ) from exc
    return Vieneu


def _normalize_engine_cache_inputs(
    *,
    mode: object,
    api_base: object,
    model_name: object,
    device: object = DEFAULT_VIENEU_DEVICE,
    backend: object | None = None,
    allow_network: bool = False,
) -> tuple[str, str, str, str, str]:
    resolved_mode = _resolve_engine_mode(mode)
    clean_model = resolve_vieneu_model_for_runtime(model_name, resolved_mode, allow_network=allow_network)
    clean_device = resolve_vieneu_runtime_device(device)
    clean_backend = normalize_vieneu_backend(backend)
    clean_model_path = Path(str(clean_model or "").strip())
    if (
        resolved_mode == "turbo_gpu"
        and str(clean_model_path)
        and clean_model_path.exists()
        and clean_model_path.is_file()
        and clean_model_path.suffix.lower() == ".gguf"
    ):
        resolved_mode = "turbo"
    clean_api_base = str(api_base or "").strip()

    if resolved_mode != "remote":
        clean_api_base = ""
    elif not clean_api_base:
        clean_api_base = DEFAULT_VIENEU_API_BASE

    return resolved_mode, clean_api_base, clean_model, clean_device, clean_backend


def _get_engine(
    *,
    mode: str = DEFAULT_VIENEU_MODE,
    api_base: str = DEFAULT_VIENEU_API_BASE,
    model_name: str = DEFAULT_VIENEU_MODEL_NAME,
    device: str = DEFAULT_VIENEU_DEVICE,
    backend: str = "auto",
    allow_network: bool = False,
) -> Any:
    resolved_mode, clean_api_base, clean_model, clean_device, clean_backend = _normalize_engine_cache_inputs(
        mode=mode,
        api_base=api_base,
        model_name=model_name,
        device=device,
        backend=backend,
        allow_network=allow_network,
    )
    backend = resolve_vieneu_runtime_backend(resolved_mode, clean_model, clean_device, clean_backend)
    cache_key = (resolved_mode, clean_api_base, clean_model, clean_device, backend, bool(allow_network))

    cached = _ENGINE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with _ENGINE_LOCK:
        cached = _ENGINE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        Vieneu = _import_vieneu_factory()
        kwargs: dict[str, Any] = {}

        bootstrap_vieneu_runtime(allow_network=allow_network)
        _apply_vieneu_backend_kwargs(Vieneu, kwargs, backend)

        if resolved_mode == "standard" and not allow_network:
            missing = _ensure_vieneu_standard_dependency_snapshots()
            if missing:
                raise FileNotFoundError(
                    "VieNeu standard local/offline còn thiếu dependency local: "
                    + "; ".join(missing)
                    + ". App đã mirror dependency vào HF cache khi tìm thấy local snapshot; "
                    "nếu vẫn thiếu, hãy dùng Adopt cached codec / Adopt cached distilhubert "
                    "hoặc copy snapshot local đúng thư mục."
                )

        if resolved_mode == "standard" and not allow_network:
            _patch_vieneu_standard_offline_dependencies()

        _patch_transformers_meta_to_empty()

        if resolved_mode == "remote":
            kwargs["api_base"] = clean_api_base
            if clean_model:
                kwargs["model_name"] = clean_model
            engine = Vieneu(mode=resolved_mode, **kwargs)
        else:
            backbone_repo = clean_model
            runtime_device = "cuda" if clean_device == "cuda" else "cpu"
            clean_model_path = Path(str(clean_model or "").strip())
            if str(clean_model_path):
                try:
                    resolved_model_path = clean_model_path.resolve()
                except Exception:
                    resolved_model_path = clean_model_path
                if resolved_mode in {"turbo", "turbo_gpu", "fast", "xpu"}:
                    if resolved_model_path.is_dir():
                        gguf_candidates = sorted(
                            [p for p in resolved_model_path.iterdir() if p.is_file() and p.suffix.lower() == ".gguf"],
                            key=lambda p: p.name.lower(),
                        )
                        if gguf_candidates:
                            backbone_repo = str(gguf_candidates[0].resolve())
                    elif resolved_model_path.is_file() and resolved_model_path.suffix.lower() == ".gguf":
                        backbone_repo = str(resolved_model_path)
            if clean_model:
                kwargs["backbone_repo"] = backbone_repo
            if resolved_mode == "standard":
                kwargs["backbone_device"] = runtime_device
                kwargs["codec_device"] = runtime_device
            else:
                kwargs["device"] = runtime_device
            engine = Vieneu(mode=resolved_mode, **kwargs)
    _ENGINE_CACHE[cache_key] = engine
    return engine


def get_vieneu_engine(
    *,
    mode: str = DEFAULT_VIENEU_MODE,
    api_base: str = DEFAULT_VIENEU_API_BASE,
    model_name: str = DEFAULT_VIENEU_MODEL_NAME,
    device: str = DEFAULT_VIENEU_DEVICE,
    backend: str = "auto",
    allow_network: bool = False,
) -> Any:
    return _get_engine(
        mode=mode,
        api_base=api_base,
        model_name=model_name,
        device=device,
        backend=backend,
        allow_network=allow_network,
    )


@lru_cache(maxsize=16)
def _list_vieneu_preset_voices_cached(
    *,
    mode: str = DEFAULT_VIENEU_MODE,
    api_base: str = DEFAULT_VIENEU_API_BASE,
    model_name: str = DEFAULT_VIENEU_MODEL_NAME,
    device: str = DEFAULT_VIENEU_DEVICE,
    backend: str = "auto",
    allow_network: bool = False,
) -> tuple[tuple[str, str], ...]:
    resolved_mode, clean_api_base, clean_model, clean_device, clean_backend = _normalize_engine_cache_inputs(
        mode=mode,
        api_base=api_base,
        model_name=model_name,
        device=device,
        backend=backend,
        allow_network=allow_network,
    )
    engine = _get_engine(
        mode=resolved_mode,
        api_base=clean_api_base,
        model_name=clean_model,
        device=clean_device,
        backend=clean_backend,
        allow_network=allow_network,
    )
    voices = tuple(
        (str(label or voice_id), str(voice_id))
        for label, voice_id in engine.list_preset_voices()
    )
    return voices


def warmup_vieneu_engine(
    *,
    mode: str = DEFAULT_VIENEU_MODE,
    api_base: str = DEFAULT_VIENEU_API_BASE,
    model_name: str = DEFAULT_VIENEU_MODEL_NAME,
    device: str = DEFAULT_VIENEU_DEVICE,
    backend: str = "auto",
    allow_network: bool = False,
) -> Any:
    return _get_engine(
        mode=mode,
        api_base=api_base,
        model_name=model_name,
        device=device,
        backend=backend,
        allow_network=allow_network,
    )


def clear_vieneu_runtime_caches() -> None:
    with _ENGINE_LOCK:
        _ENGINE_CACHE.clear()
    _list_vieneu_preset_voices_cached.cache_clear()


def _static_vieneu_sample_voices(
    mode: object = DEFAULT_VIENEU_MODE,
    model_name: object = "",
) -> tuple[tuple[str, str], ...]:
    resolved_mode = normalize_vieneu_mode(mode)
    clean_model = str(model_name or "").strip().lower()
    if resolved_mode == "remote":
        if "turbo" in clean_model or "gguf" in clean_model:
            resolved_mode = "turbo"
        else:
            resolved_mode = "standard"
    if resolved_mode == "standard":
        return (
            ("Vĩnh (Nam - Miền Nam)", "Vinh"),
            ("Bình (Nam - Miền Bắc)", "Binh"),
            ("Tuyên (Nam - Miền Bắc)", "Tuyen"),
            ("Đoan (Nữ - Miền Nam)", "Doan"),
            ("Ly (Nữ - Miền Bắc)", "Ly"),
            ("Ngọc (Nữ - Miền Bắc)", "Ngoc"),
        )
    return (
        ("Bích Ngọc (Nữ - Miền Bắc)", "Bích Ngọc"),
        ("Phạm Tuyên (Nam - Miền Bắc)", "Phạm Tuyên"),
        ("Thục Đoan (Nữ - Miền Nam)", "Thục Đoan"),
        ("Xuân Vĩnh (Nam - Miền Nam)", "Xuân Vĩnh"),
    )


def list_vieneu_preset_voices(
    *,
    mode: str = DEFAULT_VIENEU_MODE,
    api_base: str = DEFAULT_VIENEU_API_BASE,
    model_name: str = DEFAULT_VIENEU_MODEL_NAME,
    device: str = DEFAULT_VIENEU_DEVICE,
    backend: str = "auto",
    allow_network: bool = False,
) -> tuple[tuple[str, str], ...]:
    try:
        voices = _list_vieneu_preset_voices_cached(
            mode=mode,
            api_base=api_base,
            model_name=model_name,
            device=device,
            backend=backend,
            allow_network=allow_network,
        )
        return voices or _static_vieneu_sample_voices(mode=mode, model_name=model_name)
    except Exception:
        return _static_vieneu_sample_voices(mode=mode, model_name=model_name)


def _resolve_voice_id(seg: Segment, voice_map_vi: dict[str, str], voice_map_en: dict[str, str]) -> str:
    lang = str(getattr(seg, "lang", "vi") or "vi").strip().lower()
    role = str(getattr(seg, "voice", "narrator") or "narrator").strip().lower()
    mapping = voice_map_en if lang == "en" else voice_map_vi
    return str(mapping.get(role) or mapping.get("narrator") or "").strip()


def _strip_accents(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _normalize_voice_token(value: object) -> str:
    text = _strip_accents(value).replace("đ", "d").replace("Đ", "D")
    return " ".join(text.strip().lower().split())


_LEGACY_VIENEU_VOICE_HINTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "doan": (("doan",), ("nu", "mien", "nam"), ("female", "south")),
    "thuc doan": (("doan",), ("nu", "mien", "nam"), ("female", "south")),
    "ly": (("ly",), ("nu", "mien", "bac"), ("female", "north")),
    "ngoc": (("ngoc",), ("nu", "mien", "bac"), ("female", "north")),
    "bich ngoc": (("ngoc",), ("nu", "mien", "bac"), ("female", "north")),
    "vinh": (("vinh",), ("nam", "mien", "nam"), ("male", "south")),
    "xuan vinh": (("vinh",), ("nam", "mien", "nam"), ("male", "south")),
    "binh": (("binh",), ("nam", "mien", "bac"), ("male", "north")),
    "tuyen": (("tuyen",), ("nam", "mien", "bac"), ("male", "north")),
    "pham tuyen": (("tuyen",), ("nam", "mien", "bac"), ("male", "north")),
}


def migrate_vieneu_legacy_voice_id(
    voice_id: object,
    available_choices: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> str:
    raw = str(voice_id or "").strip()
    if not raw:
        return ""
    normalized = _normalize_voice_token(raw)
    if not normalized:
        return raw

    entries: list[tuple[str, str, str, str, set[str]]] = []
    for label, preset_id in tuple(available_choices or ()):
        clean_id = str(preset_id or "").strip()
        clean_label = str(label or clean_id).strip()
        if not clean_id:
            continue
        norm_id = _normalize_voice_token(clean_id)
        norm_label = _normalize_voice_token(clean_label)
        tokens = set((norm_id + " " + norm_label).split())
        entries.append((clean_id, clean_label, norm_id, norm_label, tokens))

    if not entries:
        return raw

    for clean_id, _clean_label, norm_id, norm_label, _tokens in entries:
        if normalized in {
            norm_id,
            norm_label,
            _normalize_voice_token(norm_label.split("(", 1)[0].strip()),
        }:
            return clean_id

    hint_groups = _LEGACY_VIENEU_VOICE_HINTS.get(normalized)
    if not hint_groups:
        return raw

    ranked: list[tuple[int, str]] = []
    for clean_id, _clean_label, norm_id, norm_label, tokens in entries:
        score = 0
        if normalized in tokens:
            score += 100
        for idx, group in enumerate(hint_groups):
            group_tokens = {tok for tok in (_normalize_voice_token(item) for item in group) if tok}
            if not group_tokens:
                continue
            if group_tokens.issubset(tokens):
                score += 30 - idx * 5
            elif any(tok in tokens for tok in group_tokens):
                score += 8 - idx
        if score > 0:
            ranked.append((score, clean_id))

    if ranked:
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return ranked[0][1]

    return raw


def _resolve_preset_voice(engine: Any, voice_id: str) -> Any | None:
    raw = str(voice_id or "").strip()
    if not raw:
        return None
    try:
        return engine.get_preset_voice(raw)
    except Exception:
        pass

    available_choices = tuple(engine.list_preset_voices() or ())
    normalized = _normalize_voice_token(raw)
    for label, preset_id in available_choices:
        clean_id = str(preset_id or "").strip()
        clean_label = str(label or clean_id).strip()
        if not clean_id:
            continue
        candidates = {
            _normalize_voice_token(clean_id),
            _normalize_voice_token(clean_label),
            _normalize_voice_token(clean_label.split("(", 1)[0].strip()),
        }
        if normalized in candidates:
            return engine.get_preset_voice(clean_id)

    migrated_voice_id = migrate_vieneu_legacy_voice_id(raw, available_choices)
    migrated_clean = str(migrated_voice_id or "").strip()
    if migrated_clean and migrated_clean != raw:
        _LOG.warning(
            "VieNeu legacy voice preset %r đã được migrate sang %r theo voice list hiện tại.",
            raw,
            migrated_clean,
        )
        return engine.get_preset_voice(migrated_clean)

    available_ids = [
        str(preset_id or "").strip()
        for _label, preset_id in available_choices
        if str(preset_id or "").strip()
    ]
    raise TtsError(
        f"Không tìm thấy preset voice của VieNeu TTS core: {voice_id!r}. "
        f"Các preset hiện có: {', '.join(available_ids) if available_ids else '(trống)'}"
    )


def resolve_vieneu_segment_voice(
    engine: Any,
    seg: Segment,
    voice_map_vi: dict[str, str],
    voice_map_en: dict[str, str],
) -> tuple[str, Any | None]:
    voice_id = _resolve_voice_id(seg, voice_map_vi, voice_map_en)
    voice = _resolve_preset_voice(engine, voice_id) if voice_id else None
    return voice_id, voice


def _normalize_vieneu_segment_rate(seg: Segment) -> str:
    raw_rate = normalize_rate_value(getattr(seg, "rate", "") or "", fallback="0%")
    return raw_rate


def _apply_vieneu_rate_hint(voice: Any, *, rate: str) -> Any:
    if voice is None:
        return None

    rate_factor = rate_str_to_factor(rate)
    if isinstance(voice, dict):
        updated = dict(voice)
        for key, value in (
            ("rate", rate),
            ("speed", rate_factor),
            ("speaking_rate", rate_factor),
            ("rate_factor", rate_factor),
        ):
            if key in updated:
                updated[key] = value
        return updated

    for attr, value in (
        ("rate", rate),
        ("speed", rate_factor),
        ("speaking_rate", rate_factor),
        ("rate_factor", rate_factor),
    ):
        if hasattr(voice, attr):
            try:
                setattr(voice, attr, value)
            except Exception:
                continue
    return voice


def _build_vieneu_infer_kwargs(*, engine: Any, seg: Segment, voice: Any, temperature: float, max_chars: int) -> dict[str, Any]:
    rate = _normalize_vieneu_segment_rate(seg)
    rate_factor = rate_str_to_factor(rate)
    kwargs: dict[str, Any] = {
        "text": str(getattr(seg, "text", "") or "").strip(),
        "voice": _apply_vieneu_rate_hint(voice, rate=rate),
        "temperature": temperature,
        "max_chars": max_chars,
    }

    infer = getattr(engine, "infer", None)
    try:
        signature = inspect.signature(infer) if callable(infer) else None
    except (TypeError, ValueError):
        signature = None
    if signature is None:
        return kwargs

    params = signature.parameters
    if "rate" in params:
        kwargs["rate"] = rate
    elif "speed" in params:
        kwargs["speed"] = rate_factor
    elif "speaking_rate" in params:
        kwargs["speaking_rate"] = rate_factor
    elif "rate_factor" in params:
        kwargs["rate_factor"] = rate_factor

    return {key: value for key, value in kwargs.items() if value is not None}


def synthesize_segment_with_vieneu(
    seg: Segment,
    out_wav: Path,
    voice_map_vi: dict[str, str],
    voice_map_en: dict[str, str],
    *,
    auto_en_lines: bool = False,
    vieneu_mode: str = DEFAULT_VIENEU_MODE,
    vieneu_api_base: str = DEFAULT_VIENEU_API_BASE,
    vieneu_model_name: str = DEFAULT_VIENEU_MODEL_NAME,
    vieneu_device: str = DEFAULT_VIENEU_DEVICE,
    backend: str = "auto",
    vieneu_temperature: float | None = None,
    vieneu_max_chars_chunk: int | None = None,
    vieneu_use_batch: bool | None = None,
    vieneu_max_batch_size_run: int | None = None,
) -> None:
    del auto_en_lines, vieneu_use_batch, vieneu_max_batch_size_run
    engine = get_vieneu_engine(
        mode=vieneu_mode,
        api_base=vieneu_api_base,
        model_name=vieneu_model_name,
        device=vieneu_device,
        backend=backend,
    )
    synthesize_segment_with_vieneu_using_engine(
        engine,
        seg,
        out_wav,
        voice_map_vi,
        voice_map_en,
        vieneu_mode=vieneu_mode,
        vieneu_model_name=vieneu_model_name,
        vieneu_temperature=vieneu_temperature,
        vieneu_max_chars_chunk=vieneu_max_chars_chunk,
    )


def synthesize_segment_with_vieneu_using_engine(
    engine: Any,
    seg: Segment,
    out_wav: Path,
    voice_map_vi: dict[str, str],
    voice_map_en: dict[str, str],
    *,
    vieneu_mode: str = DEFAULT_VIENEU_MODE,
    vieneu_model_name: str = DEFAULT_VIENEU_MODEL_NAME,
    backend: str = "auto",
    vieneu_temperature: float | None = None,
    vieneu_max_chars_chunk: int | None = None,
) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    text = str(getattr(seg, "text", "") or "").strip()
    if not text:
        raise TtsError("VieNeu TTS core không thể render segment rỗng")
    voice_id = _resolve_voice_id(seg, voice_map_vi, voice_map_en)
    voice = _resolve_preset_voice(engine, voice_id) if voice_id else None
    max_chars = max(1, int(vieneu_max_chars_chunk if vieneu_max_chars_chunk is not None else 240))
    temperature = float(vieneu_temperature if vieneu_temperature is not None else 0.7)

    try:
        infer_kwargs = _build_vieneu_infer_kwargs(
            engine=engine,
            seg=seg,
            voice=voice,
            temperature=temperature,
            max_chars=max_chars,
        )
        audio = engine.infer(**infer_kwargs)
        engine.save(audio, out_wav)
    except Exception as exc:
        raise TtsError(
            f"VieNeu TTS core render failed. mode={normalize_vieneu_mode(vieneu_mode)!r}, "
            f"voice={voice_id!r}, model={vieneu_model_name!r}, backend={normalize_vieneu_backend(backend)!r}. Last error: {exc}"
        ) from exc


async def synthesize_segment_with_vieneu_async(
    seg: Segment,
    out_wav: Path,
    voice_map_vi: dict[str, str],
    voice_map_en: dict[str, str],
    *,
    auto_en_lines: bool = False,
    vieneu_mode: str = DEFAULT_VIENEU_MODE,
    vieneu_api_base: str = DEFAULT_VIENEU_API_BASE,
    vieneu_model_name: str = DEFAULT_VIENEU_MODEL_NAME,
    vieneu_device: str = DEFAULT_VIENEU_DEVICE,
    backend: str = "auto",
    vieneu_temperature: float | None = None,
    vieneu_max_chars_chunk: int | None = None,
    vieneu_use_batch: bool | None = None,
    vieneu_max_batch_size_run: int | None = None,
) -> None:
    await asyncio.to_thread(
        synthesize_segment_with_vieneu,
        seg,
        out_wav,
        voice_map_vi,
        voice_map_en,
        auto_en_lines=auto_en_lines,
        vieneu_mode=vieneu_mode,
        vieneu_api_base=vieneu_api_base,
        vieneu_model_name=vieneu_model_name,
        vieneu_device=vieneu_device,
        backend=backend,
        vieneu_temperature=vieneu_temperature,
        vieneu_max_chars_chunk=vieneu_max_chars_chunk,
        vieneu_use_batch=vieneu_use_batch,
        vieneu_max_batch_size_run=vieneu_max_batch_size_run,
    )
