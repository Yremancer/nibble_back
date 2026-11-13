from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    original_name: str
    content_type: str
    size: int
    created_at: datetime
