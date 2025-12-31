"""Decision helpers for selecting test mode."""

"""Decision helpers for selecting sloped vs non-sloped test."""

import aurora.config as config


class DecisionResult:
    def __init__(self, mode, depth_avg_cm):
        self.mode = mode
        self.depth_avg_cm = depth_avg_cm

    def __repr__(self):
        return "DecisionResult(mode=%s depth=%.2f)" % (self.mode, self.depth_avg_cm or -1)


def choose_mode(depths, depth_avg):
    if depth_avg is None:
        return DecisionResult("skip", None)
    mode = "sloped" if depth_avg > config.DEPTH_THRESHOLD_CM else "nonsloped"
    return DecisionResult(mode, depth_avg)
