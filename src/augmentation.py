"""Augment IHTC instances with randomness."""

import copy
import math
import random


def sample_length_of_stay(instance, cv=0.25, seed=None):
    """Return a copy of `instance` with each patient's length of stay resampled.

    Each patient's new length of stay is drawn from a normal distribution with
    mean equal to their current length of stay and standard deviation
    `cv` * mean (so `cv` is the coefficient of variation: longer stays vary more
    in absolute terms). The sample is rounded up to whole days, since a patient
    there for part of a day still needs the bed that day, and floored at 1 day.

    The per-shift lists `workload_produced` and `skill_level_required` must keep
    one entry per shift of the stay, so they are resized to match:
    - shorter stay: the lists are truncated;
    - longer stay: the last day's values are repeated for each extra day.

    Occupants (already in hospital) are left unchanged. The input instance is
    not modified. Pass `seed` for reproducible samples.
    """
    rng = random.Random(seed)
    shifts_per_day = len(instance["shift_types"])
    augmented = copy.deepcopy(instance)

    for patient in augmented["patients"]:
        mean = patient["length_of_stay"]
        new_los = max(1, math.ceil(rng.gauss(mean, cv * mean)))
        for key in ("workload_produced", "skill_level_required"):
            patient[key] = _resize_per_shift(patient[key], new_los, shifts_per_day)
        patient["length_of_stay"] = new_los

    return augmented


def _resize_per_shift(values, new_los, shifts_per_day):
    """Truncate `values` to `new_los` days, or extend it by repeating its last day."""
    target = new_los * shifts_per_day
    if target <= len(values):
        return values[:target]
    last_day = values[-shifts_per_day:]
    extra_days = (target - len(values)) // shifts_per_day
    return values + last_day * extra_days
