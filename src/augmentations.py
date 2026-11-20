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


SURGERY_DISTRIBUTIONS = ("truncnormal", "gamma", "lognormal")


def sample_surgery_duration(instance, distribution="truncnormal", cv=0.25, seed=None):
    """Return a copy of `instance` with each patient's surgery duration resampled.

    Each new duration is drawn from `distribution`, parametrised so that its mean
    is the patient's current surgery duration and its standard deviation is
    `cv` * mean (so longer surgeries vary more in absolute terms):
    - "truncnormal": normal(mean, cv * mean) truncated to positive values (by
      rejection). Truncation raises the mean slightly, but only noticeably for
      large `cv` (the cut is 1 / cv standard deviations below the mean).
    - "gamma": shape 1 / cv**2, scale mean * cv**2 (mean and sd exact).
    - "lognormal": sigma**2 = ln(1 + cv**2), mu = ln(mean) - sigma**2 / 2
      (mean and sd exact; right-skewed with a heavier tail than the gamma).

    Samples are rounded to the nearest minute and floored at 1 minute. The input
    instance is not modified. Pass `seed` for reproducible samples.
    """
    if distribution not in SURGERY_DISTRIBUTIONS:
        raise ValueError(f"distribution must be one of {SURGERY_DISTRIBUTIONS}, got {distribution!r}")
    rng = random.Random(seed)
    augmented = copy.deepcopy(instance)

    for patient in augmented["patients"]:
        mean = patient["surgery_duration"]
        sample = _sample_positive(rng, distribution, mean, cv)
        patient["surgery_duration"] = max(1, round(sample))

    return augmented


def _sample_positive(rng, distribution, mean, cv):
    """One draw from `distribution` with the given mean and coefficient of variation."""
    if distribution == "truncnormal":
        while (x := rng.gauss(mean, cv * mean)) <= 0:
            pass
        return x
    if distribution == "gamma":
        return rng.gammavariate(1 / cv**2, mean * cv**2)
    sigma2 = math.log(1 + cv**2)  # lognormal
    return rng.lognormvariate(math.log(mean) - sigma2 / 2, math.sqrt(sigma2))
