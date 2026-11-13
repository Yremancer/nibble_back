from src.auth.exceptions import (
    AuthenticationError,
    EmailAlreadyRegisteredError,
    InvalidCityError,
)
from src.auth.repository import AuthRepository
from src.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from src.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.models.user import User, UserRole
from src.settings import settings


class AuthService:
    def __init__(self, repo: AuthRepository):
        self._repo = repo

    async def register(self, data: RegisterRequest) -> User:
        email = str(data.email).lower()
        if await self._repo.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError
        if not await self._repo.city_exists(data.city_id):
            raise InvalidCityError
        return await self._repo.add(
            User(
                email=email,
                password_hash=await hash_password(data.password.get_secret_value()),
                display_name=data.display_name,
                city_id=data.city_id,
                role=UserRole.USER,
            )
        )

    async def login(self, data: LoginRequest) -> TokenResponse:
        user = await self._repo.get_by_email(str(data.email).lower())
        hashed = user.password_hash if user is not None else None
        valid = await verify_password(data.password.get_secret_value(), hashed)
        if user is None or not valid:
            raise AuthenticationError
        return TokenResponse(
            access_token=create_access_token(user.id),
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def current_user(self, token: str) -> User:
        user = await self._repo.get_by_id(decode_access_token(token))
        if user is None:
            raise AuthenticationError
        return user
