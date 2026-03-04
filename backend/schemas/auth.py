from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    email: EmailStr | None = None
    password: str
    role: str = "user"


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None
    role: str

    model_config = {"from_attributes": True}
