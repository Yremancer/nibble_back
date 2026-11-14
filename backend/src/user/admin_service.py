from src.auth.security import hash_password
from src.exceptions import ForbiddenError
from src.storage.images import ImageService
from src.user.admin_schemas import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserPage,
    AdminUserQuery,
)
from src.user.exceptions import UserNotFoundError
from src.user.models import User, UserRole
from src.user.repository import UserRepository
from src.user.service import UserService


class AdminUserService:
    def __init__(
        self, repo: UserRepository, users: UserService, images: ImageService
    ) -> None:
        self.repo = repo
        self.users = users
        self.images = images

    async def list_users(self, query: AdminUserQuery) -> AdminUserPage:
        rows = await self.repo.admin_list(
            query.role.value if query.role else None, query.q or None, query.cursor, query.limit
        )
        page = rows[: query.limit]
        items = await self.images.apply(
            [AdminUserOut.model_validate(u) for u in page], "avatar_url"
        )
        return AdminUserPage(
            items=items,
            next_cursor=page[-1].id if len(rows) > query.limit else None,
        )

    async def get_user(self, user_id: int) -> AdminUserOut:
        return await self._out(await self._require(user_id))

    async def create(self, data: AdminUserCreate) -> AdminUserOut:
        user = await self.users.create(
            email=str(data.email),
            password_hash=await hash_password(data.password.get_secret_value()),
            display_name=data.display_name,
            city_id=data.city_id,
            role=data.role,
        )
        return await self._out(user)

    async def set_role(self, user_id: int, role: UserRole, actor: User) -> AdminUserOut:
        if user_id == actor.id:
            raise ForbiddenError("You cannot change your own role")
        user = await self._require(user_id)
        user = await self.repo.update(user, {"role": role.value})
        return await self._out(user)

    async def _require(self, user_id: int) -> User:
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(id=user_id)
        return user

    async def _out(self, user: User) -> AdminUserOut:
        return await self.images.apply_one(AdminUserOut.model_validate(user), "avatar_url")
