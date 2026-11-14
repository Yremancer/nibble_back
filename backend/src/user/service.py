from src.exceptions import ForbiddenError
from src.user.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCityError,
    UserNotFoundError,
)
from src.storage.images import ImageService
from src.user.models import User, UserRole
from src.user.repository import UserRepository
from src.user.schemas import UserUpdate


class UserService:
    def __init__(self, repo: UserRepository, images: ImageService):
        self._repo = repo
        self._images = images

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._repo.get_by_id(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._repo.get_by_email(email.lower())

    async def list_users(self) -> list[User]:
        return await self._repo.list_all()

    async def get_user(self, user_id: int, actor: User) -> User:
        if actor.id != user_id and actor.role != UserRole.ADMIN:
            raise ForbiddenError
        user = await self.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(id=user_id)
        return user

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        city_id: int,
        role: UserRole = UserRole.USER,
    ) -> User:
        email = email.lower()
        if await self.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError
        if not await self._repo.city_exists(city_id):
            raise InvalidCityError
        return await self._repo.add(
            User(
                email=email,
                password_hash=password_hash,
                display_name=display_name,
                city_id=city_id,
                role=role,
            )
        )

    async def update(self, user_id: int, data: UserUpdate, actor: User) -> User:
        user = await self.get_user(user_id, actor)
        values = data.model_dump(exclude_unset=True)
        if "role" in values and actor.role != UserRole.ADMIN:
            raise ForbiddenError
        if "role" in values and user.id == actor.id and values["role"] != user.role:
            # Иначе единственный админ мог бы случайно лишить себя прав.
            raise ForbiddenError("You cannot change your own role")
        if "email" in values:
            values["email"] = values["email"].lower()
            existing = await self.get_by_email(values["email"])
            if existing is not None and existing.id != user.id:
                raise EmailAlreadyRegisteredError
        if "city_id" in values and not await self._repo.city_exists(values["city_id"]):
            raise InvalidCityError
        old_avatar = user.avatar_url
        if "avatar_key" in values:
            key = values.pop("avatar_key")
            values["avatar_url"] = (
                await self._images.claim(key, actor, current=old_avatar) if key else None
            )
        user = await self._repo.update(user, values)
        if "avatar_url" in values and values["avatar_url"] != old_avatar:
            await self._images.release(old_avatar)
        return user

    async def delete(self, user_id: int, actor: User) -> None:
        user = await self.get_user(user_id, actor)
        avatar = user.avatar_url
        await self._repo.delete(user)
        await self._images.release(avatar)
