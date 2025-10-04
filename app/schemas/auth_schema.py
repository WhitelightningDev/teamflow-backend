from pydantic import BaseModel, EmailStr


class UserIn(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    company_name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr


class AuthResponse(BaseModel):
    user: UserOut
    token: str
