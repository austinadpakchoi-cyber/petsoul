"""待领养居民：领养前就在星球上真实生活的伙伴（稳定 pet_id、住在星球居民驿站、自己出门打工），领养后保留身份与经历。"""

from .service import SYSTEM_USER, ResidentHome, ResidentService

__all__ = ["SYSTEM_USER", "ResidentHome", "ResidentService"]
