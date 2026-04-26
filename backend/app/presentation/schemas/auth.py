from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str = Field(min_length=6)


class UserData(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool = True


class LoginResponse(BaseModel):
    access_token: str
    user: UserData


RegisterResponse = LoginResponse
