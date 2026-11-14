from fastapi import APIRouter, Depends, Response, status
from src.auth.cookies import delete_refresh_cookie, set_refresh_cookie
from src.auth.deps import (
    AuthServiceDep,
    CurrentUserDep,
    RefreshCookie,
    check_auth_origin,
)
from src.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from src.storage.deps import ImageServiceDep
from src.user.schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse
)
async def register(data: RegisterRequest, service: AuthServiceDep, images: ImageServiceDep):
    user = await service.register(data)
    return await images.apply_one(UserResponse.model_validate(user), "avatar_url")


@router.post(
    "/login", response_model=TokenResponse, dependencies=[Depends(check_auth_origin)]
)
async def login(data: LoginRequest, response: Response, service: AuthServiceDep):
    tokens = await service.login(data)
    set_refresh_cookie(response, tokens.refresh_token, tokens.expires_at)
    return tokens.token


@router.post(
    "/refresh", response_model=TokenResponse, dependencies=[Depends(check_auth_origin)]
)
async def refresh(
    response: Response, service: AuthServiceDep, refresh_token: RefreshCookie = None
):
    tokens = await service.refresh(refresh_token)
    set_refresh_cookie(response, tokens.refresh_token, tokens.expires_at)
    return tokens.token


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_auth_origin)],
)
async def logout(
    response: Response, service: AuthServiceDep, refresh_token: RefreshCookie = None
) -> None:
    await service.logout(refresh_token)
    delete_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUserDep, images: ImageServiceDep):
    return await images.apply_one(UserResponse.model_validate(user), "avatar_url")
