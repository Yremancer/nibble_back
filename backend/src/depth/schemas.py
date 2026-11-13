from typing import Any, Literal

from pydantic import BaseModel


class DepthZoneProperties(BaseModel):
    depth_from: int
    depth_to: int | None


class DepthZone(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: DepthZoneProperties
    geometry: dict[str, Any]


class DepthZones(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    attribution: str | None
    features: list[DepthZone]
