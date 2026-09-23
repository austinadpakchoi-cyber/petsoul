"""网页宠物与专属领养模块。"""

from .media import MediaRejected, sanitize_image
from .service import AdoptionTaken, AlreadyHasCompanion, CandidateNotFound, PetProfileRecord, WebPetsService

__all__ = [
    "AdoptionTaken",
    "AlreadyHasCompanion",
    "CandidateNotFound",
    "MediaRejected",
    "PetProfileRecord",
    "WebPetsService",
    "sanitize_image",
]
