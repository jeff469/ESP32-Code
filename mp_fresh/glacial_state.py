import os

try:
    import ujson as json
except Exception:
    import json

import config


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _ensure_dir(path):
    if not _exists(path):
        os.mkdir(path)


def ensure_state_file():
    parts = config.STATE_PATH.rsplit("/", 1)
    if len(parts) == 2:
        dir_path = parts[0]
        _ensure_dir(dir_path)
    if not _exists(config.STATE_PATH):
        data = {"bin_counts": {}, "trial_counter": 1}
        save_state(data)


def load_state():
    ensure_state_file()
    with open(config.STATE_PATH, "r") as fp:
        content = fp.read()
        if not content:
            return {"bin_counts": {}, "trial_counter": 1}
        return json.loads(content)


def save_state(state):
    with open(config.STATE_PATH, "w") as fp:
        fp.write(json.dumps(state))


def next_trial_number(state):
    num = state.get("trial_counter", 1)
    state["trial_counter"] = num + 1
    save_state(state)
    return num


def get_bin_count(state, bin_id):
    current = state.get("bin_counts", {}).get(bin_id, 0)
    if current < 0:
        current = 0
    return current


def bump_bin_count(state, bin_id, reset_at):
    counts = state.get("bin_counts", {})
    current = counts.get(bin_id, 0)
    # Clamp any previously persisted values that exceeded the reset threshold
    if current > reset_at:
        current = 0
    use_value = current
    current += 1
    if current > reset_at:
        current = 0
    counts[bin_id] = current
    state["bin_counts"] = counts
    save_state(state)
    return use_value
