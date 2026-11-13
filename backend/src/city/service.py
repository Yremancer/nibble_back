from src.city.models import City
from src.city.repository import CityRepository


class CityService:
    def __init__(self, repo: CityRepository) -> None:
        self.repo = repo

    async def list_cities(self) -> list[City]:
        return await self.repo.list_all()
