"""Stop-condition helpers for sloped and non-sloped tests."""

import aurora.config as config


def melt_complete(depth_avg_cm, streak):
    if depth_avg_cm is None:
        return streak, False
    if depth_avg_cm <= config.MELT_COMPLETE_CM:
        streak += 1
    else:
        streak = 0
    return streak, streak >= config.MELT_STREAK_REQUIRED


def pavement_ready(pav_avg_c, streak):
    if pav_avg_c is None:
        return streak, False
    if pav_avg_c >= 1.0:
        streak += 1
    else:
        streak = 0
    return streak, streak >= config.MELT_STREAK_REQUIRED
