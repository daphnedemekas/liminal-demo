"""Auth routes: register, login, user profile."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import UserProfile, OnboardingState, Project, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    name: str


class LoginRequest(BaseModel):
    name: str


class UserResponse(BaseModel):
    id: str
    name: str
    user_type: str
    onboarding_complete: bool
    discovery_complete: bool
    default_involvement: str
    explanation_preference: str
    model_summary: str

    class Config:
        from_attributes = True


@router.post("/register", response_model=UserResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(UserProfile).filter_by(name=req.name).first()
    if existing:
        raise HTTPException(400, "Name already taken")
    user = UserProfile(name=req.name)
    db.add(user)
    db.flush()
    db.add(OnboardingState(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=UserResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserProfile).filter_by(name=req.name).first()
    if not user:
        user = UserProfile(name=req.name)
        db.add(user)
        db.flush()
        db.add(OnboardingState(user_id=user.id))
        db.commit()
        db.refresh(user)

    # Ensure home project exists
    _ensure_home_project(user.id, db)

    return user


def _ensure_home_project(user_id: str, db: Session):
    """Create the home chat project if it doesn't exist."""
    home = db.query(Project).filter_by(user_id=user_id, domain="home").first()
    if not home:
        home = Project(
            user_id=user_id,
            name="Home",
            domain="home",
            description="Your general-purpose chat. Ask anything, explore ideas, or start new projects.",
            suggested_by_system=True,
        )
        db.add(home)
        db.commit()


@router.get("/user/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(UserProfile).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user
