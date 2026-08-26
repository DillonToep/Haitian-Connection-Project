from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class MoldParameterInput(BaseModel):
    parameter_id: str = Field(min_length=1, max_length=50)
    value: str | None = Field(default=None, max_length=200)
    tolerance_mode: str = Field(default="percent", pattern="^(percent|flat)$")
    tolerance_percent: float | None = Field(default=None, ge=0, le=1000)
    tolerance_flat: float | None = Field(default=None, ge=0)


class MoldParametersUpdateRequest(BaseModel):
    parameters: list[MoldParameterInput]

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
    max_output: int | None = Field(default=None, gt=0, le=10_000_000)


class MoldAssignmentRequest(BaseModel):
    mold_id: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=500)

class MoldExtendedInfoRequest(BaseModel):
    fields: dict[str, str | float | int | bool | None] = {}


class MachineTypeCreateRequest(BaseModel):
    machine_type: str = Field(min_length=1, max_length=150)