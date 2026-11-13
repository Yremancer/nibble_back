from src.auth.exceptions import AuthenticationError
from src.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from src.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.settings import settings
from src.user.models import User
from src.user.service import UserService


class AuthService:
    def __init__(self, users: UserService):
        self._users = users

    async def register(self, data: RegisterRequest) -> User:
        return await self._users.create(
            email=str(data.email),
            password_hash=await hash_password(data.password.get_secret_value()),
            display_name=data.display_name,
            city_id=data.city_id,
        )

    async def login(self, data: LoginRequest) -> TokenResponse:
        user = await self._users.get_by_email(str(data.email))
        hashed = user.password_hash if user is not None else None
        valid = await verify_password(data.password.get_secret_value(), hashed)
        if user is None or not valid:
            raise AuthenticationError
        return TokenResponse(
            access_token=create_access_token(user.id),
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def current_user(self, token: str) -> User:
        user = await self._users.get_by_id(decode_access_token(token))
        if user is None:
            raise AuthenticationError
        return user
