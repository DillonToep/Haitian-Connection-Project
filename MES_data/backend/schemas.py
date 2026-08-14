from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)

class MoldUpdateRequest(MoldCreateRequest):
    is_active: bool = True


class MoldAssignmentRequest(BaseModel):
    mold_id: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=500)
