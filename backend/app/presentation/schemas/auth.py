from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class UserDto(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool


class LoginResponse(BaseModel):
    access_token: str
    user: UserDto
