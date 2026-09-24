"""网页宠物与专属领养模块。"""

from .media import MediaRejected, sanitize_image
from .service import AdoptionTaken, AlreadyHasCompanion, CandidateNotFound, PetProfileRecord, PhotoNotAddable, WebPetsService

__all__ = [
    "AdoptionTaken",
    "AlreadyHasCompanion",
    "CandidateNotFound",
    "MediaRejected",
    "PetProfileRecord",
    "PhotoNotAddable",
    "WebPetsService",
    "sanitize_image",
]
