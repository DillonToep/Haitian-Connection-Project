from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class MoldUpdateRequest(BaseModel):
    mold_code: str = Field(min_length=1, max_length=100)
    mold_name: str = Field(min_length=1, max_length=200)
    product_code: str | None = Field(default=None, max_length=100)
    cavities: int = Field(gt=0, le=10_000)
    remark: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class MoldAssignmentRequest(BaseModel):
    mold_id: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=500)