from src.city.exceptions import CityNotFoundError
from src.city.repository import CityRepository
from src.depth.repository import DepthRepository
from src.depth.schemas import DepthZone, DepthZoneProperties, DepthZones


class DepthService:
    def __init__(self, repo: DepthRepository, cities: CityRepository) -> None:
        self.repo = repo
        self.cities = cities

    async def get_zones(self, city_id: int) -> DepthZones:
        if await self.cities.get(city_id) is None:
            raise CityNotFoundError(id=city_id)
        layers = await self.repo.list_by_city(city_id)
        return DepthZones(
            attribution=layers[0].attribution if layers else None,
            features=[
                DepthZone(
                    properties=DepthZoneProperties(
                        depth_from=layer.depth_from, depth_to=layer.depth_to
                    ),
                    geometry=layer.geometry,
                )
                for layer in layers
            ],
        )
