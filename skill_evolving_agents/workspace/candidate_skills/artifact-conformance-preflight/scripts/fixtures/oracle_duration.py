"""Task-derived independent oracle for the independent_recompute fixture.

This second implementation derives duration from distance and speed with
different intermediate operations from the producer, which stored the rounded
duration directly. It reads only record fields and hard-codes no answers.
"""


def recompute(record):
    distance_km = float(record["distance_km"])
    speed_kmh = float(record["speed_kmh"])
    if speed_kmh <= 0:
        raise ValueError("speed_kmh must be positive")
    return distance_km / speed_kmh * 60.0
