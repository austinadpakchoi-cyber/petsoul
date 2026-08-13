"""地图相关端点：输入提示与逆地理编码。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_amap_client, get_google_client
from ..schemas import MapSearchTip, ReverseGeocodeResult

router = APIRouter()


@router.get("/api/v1/amap/input_tips", response_model=list[MapSearchTip])
def amap_input_tips(
    keywords: str,
    city: str | None = None,
    limit: int = 10,
    amap_client=Depends(get_amap_client),
) -> list[MapSearchTip]:
    return amap_client.input_tips(keywords=keywords, city=city, limit=max(1, min(20, limit)))


@router.get("/api/v1/amap/reverse_geocode", response_model=ReverseGeocodeResult | None)
def amap_reverse_geocode(lat: float, lng: float, amap_client=Depends(get_amap_client)) -> ReverseGeocodeResult | None:
    return amap_client.reverse_geocode(lat=lat, lng=lng)


@router.get("/api/v1/google/reverse_geocode", response_model=ReverseGeocodeResult | None)
def google_reverse_geocode(
    lat: float,
    lng: float,
    google_client=Depends(get_google_client),
) -> ReverseGeocodeResult | None:
    return google_client.reverse_geocode(lat=lat, lng=lng)
