# app/routers/schedule.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User

router = APIRouter(
    prefix="",
    tags=["Agendamento"]
)


@router.post("/schedule-post", response_model=schemas.ScheduleResponse, status_code=status.HTTP_201_CREATED)
def schedule_post(
    data: schemas.ScheduleCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        now = datetime.now()
        hours, minutes = map(int, data.target_time_str.split(":"))
        scheduled_datetime = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de horário inválido. Utilize o padrão HH:MM."
        )

    db_schedule = models.Schedule(
        user_id=user.id,
        niche=data.niche,
        scheduled_time=scheduled_datetime,
        status="pending"
    )

    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)

    return db_schedule