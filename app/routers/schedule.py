# app/routers/schedule.py
from datetime import datetime, timedelta
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


def parse_schedule_time(target_time_str: str | None, scheduled_datetime: datetime | None) -> datetime:
    if scheduled_datetime:
        return scheduled_datetime

    if not target_time_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe 'target_time_str' (HH:MM) ou 'scheduled_datetime' (ISO 8601)."
        )

    try:
        now = datetime.now()
        hours, minutes = map(int, target_time_str.split(":"))
        candidate = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        # Se o horário já passou hoje, agenda para o dia seguinte automaticamente
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de horário inválido. Utilize o padrão HH:MM."
        )


@router.get("/", response_model=list[schemas.ScheduleResponse])
def list_schedules(
    status_filter: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna todos os agendamentos do usuário logado de forma dinâmica.
    """
    query = db.query(models.Schedule).filter(models.Schedule.user_id == user.id)
    if status_filter:
        query = query.filter(models.Schedule.status == status_filter)
    
    return query.order_by(models.Schedule.scheduled_time.asc()).all()


@router.post("/schedule-post", response_model=schemas.ScheduleResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=schemas.ScheduleResponse, status_code=status.HTTP_201_CREATED)
def schedule_post(
    data: schemas.ScheduleCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    scheduled_datetime = parse_schedule_time(data.target_time_str, data.scheduled_datetime)

    db_schedule = models.Schedule(
        user_id=user.id,
        title=data.title or f"Post sobre {data.niche}",
        niche=data.niche,
        scheduled_time=scheduled_datetime,
        status="pending"
    )

    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)

    return db_schedule


@router.patch("/{schedule_id}", response_model=schemas.ScheduleResponse)
def update_schedule(
    schedule_id: int,
    data: schemas.ScheduleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    item = db.query(models.Schedule).filter(
        models.Schedule.id == schedule_id,
        models.Schedule.user_id == user.id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")

    if data.niche is not None:
        item.niche = data.niche
    if data.title is not None:
        item.title = data.title
    if data.status is not None:
        item.status = data.status
    if data.target_time_str or data.scheduled_datetime:
        item.scheduled_time = parse_schedule_time(data.target_time_str, data.scheduled_datetime)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
def delete_schedule(
    schedule_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    item = db.query(models.Schedule).filter(
        models.Schedule.id == schedule_id,
        models.Schedule.user_id == user.id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")

    db.delete(item)
    db.commit()
    return {"message": "Agendamento excluído com sucesso."}