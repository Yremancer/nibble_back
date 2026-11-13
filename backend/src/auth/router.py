from fastapi import APIRouter, status
from src.auth.deps import AuthServiceDep, CurrentUserDep
from src.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(data: RegisterRequest, service: AuthServiceDep):
    return await service.register(data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, service: AuthServiceDep):
    return await service.login(data)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUserDep):
    return user
