from pydantic import BaseModel, field_validator

class VisitorRegister(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_max_length(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 characters or fewer")
        return v

class FarmerRegister(BaseModel):
    name: str
    email: str
    password: str
    farm_name: str

    @field_validator("password")
    @classmethod
    def password_max_length(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 characters or fewer")
        return v

class RegistrationResponse(BaseModel):
    detail: str
    email: str

class EmailVerification(BaseModel):
    token: str

class UserMe(BaseModel):
    id: int
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str

class LoginResponse(BaseModel):
    detail: str

class TokenData(BaseModel):
    email: str | None = None