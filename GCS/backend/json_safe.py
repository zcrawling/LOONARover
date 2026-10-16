"""Keep unavailable telemetry numeric values valid on JSON API boundaries."""
import json
import math


def finite_values(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_values(item) for item in value]
    return value


def dumps(value):
    return json.dumps(finite_values(value), ensure_ascii=False, allow_nan=False)
