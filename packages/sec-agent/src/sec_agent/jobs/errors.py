"""Errors a job handler raises to steer the retry policy."""


class PermanentJobError(Exception):
    """The job can never succeed (bad payload, unknown CIK): fail it without retrying."""
