
from importlib import import_module


_PROFILE_FIELDS = ("_inference_profile", "_yolo_profile", "_tensor_rt_profile")
_TRANSFORM_FIELDS = ("image_transform", "yolo_transform", "tensor_rt_transform")


def _report(kind):
    return import_module("pipeworks.embedded.yolo_report")


def inherited_profile(item):
    return next(
        (getattr(item, name) for name in _PROFILE_FIELDS if getattr(item, name, None) is not None),
        None,
    )


def bind_profile(profile, kind):
    if profile is not None:
        stats = _report(kind).store()
        profile.kind = kind
        profile.stats = stats if stats.enabled(kind) else None
    return profile


def begin_preprocess(preferred_kind):
    report = _report(preferred_kind)
    stats = report.store()
    with stats.lock:
        active = tuple(kind for kind, count in stats.active.items() if count > 0 and kind != "*")
    for kind in dict.fromkeys((preferred_kind, *active)):
        if stats.enabled(kind):
            return report.Profile(kind, stats)
    return None


def pop_profile(item):
    profile = inherited_profile(item)
    for name in _PROFILE_FIELDS:
        vars(item).pop(name, None)
    return profile


def image_transform(item):
    return next(
        (getattr(item, name) for name in _TRANSFORM_FIELDS if getattr(item, name, None) is not None),
        None,
    )


def clear_model_context(item):
    for name in ("model_input", "model_output", "model_id", *_TRANSFORM_FIELDS, *_PROFILE_FIELDS):
        vars(item).pop(name, None)
