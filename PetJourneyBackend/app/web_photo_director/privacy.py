"""Explicit photo-purpose projection. Raw DNA, owner notes and free-form traits are rejected."""
from collections.abc import Mapping

from .catalog import DNA_FIELDS
from .contracts import PhotoDNA, PhotoDirectorError


def validate_dna(dna: PhotoDNA) -> None:
    if dna.purpose != "photo_generation" or type(dna.version) is not int or dna.version < 0:
        raise PhotoDirectorError("dna_purpose_or_version")
    for field, allowed in DNA_FIELDS.items():
        values = getattr(dna, field)
        if len(values) > 4 or len(set(values)) != len(values) or any(value not in allowed for value in values):
            raise PhotoDirectorError("dna_value_not_allowed")


def project_photo_dna(raw: Mapping[str, object], *, allowed_fields: frozenset[str], version: int, projection_id: str) -> PhotoDNA:
    """The caller must project purpose-authorized data before this boundary, not pass raw notes.

    Reject unknown keys (rather than silently strip them) and reject non-vocabulary values.
    The returned object owns tuples, so later mutation of caller dictionaries cannot leak in.
    """
    if not isinstance(raw, Mapping) or not set(raw) <= set(DNA_FIELDS) or not set(allowed_fields) <= set(DNA_FIELDS):
        raise PhotoDirectorError("dna_field_not_allowed")
    if not set(raw) <= set(allowed_fields):
        raise PhotoDirectorError("dna_field_not_authorized")
    values = {}
    for field, value in raw.items():
        if not isinstance(value, (tuple, list)) or any(type(item) is not str for item in value):
            raise PhotoDirectorError("dna_value_not_allowed")
        values[field] = tuple(value)
    result = PhotoDNA(version=version, projection_id=projection_id, **values)
    validate_dna(result)
    return result


def dna_codes(dna: PhotoDNA) -> tuple[str, ...]:
    validate_dna(dna)
    return tuple(f"{field}:{value}" for field in DNA_FIELDS for value in getattr(dna, field))
