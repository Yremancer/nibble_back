from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Response, UploadFile, status
from src.auth.deps import CurrentUserDep
from src.storage.deps import FileServiceDep
from src.storage.policy import CATEGORIES
from src.storage.schemas import FileSchema

router = APIRouter(prefix="/files", tags=["Файлы"])


@router.post("/{category}", status_code=status.HTTP_201_CREATED)
async def upload_file(
    category: Literal["image", "video"],
    user: CurrentUserDep,
    service: FileServiceDep,
    file: Annotated[UploadFile, File()],
) -> FileSchema:
    return await service.upload(
        await file.read(CATEGORIES[category].max_bytes + 1),
        filename=file.filename or "unnamed",
        category=category,
        uploaded_by=user.id,
    )


@router.get("/{key:path}/url")
async def get_file_url(key: str, service: FileServiceDep) -> dict[str, str]:
    return {"url": await service.link(key)}


@router.get("/{key:path}")
async def download_file(key: str, service: FileServiceDep) -> Response:
    data, record = await service.download(key)
    return Response(
        content=data,
        media_type=record.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(record.original_name, safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    key: str, user: CurrentUserDep, service: FileServiceDep
) -> None:
    await service.delete(key, user)
