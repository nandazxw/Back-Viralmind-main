# app/models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    schedules = relationship("Schedule", back_populates="owner")
    chat_histories = relationship("ChatHistory", back_populates="user")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=True)
    niche = Column(String(100), nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    status = Column(String(30), default="pending")  # pending, sent, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="schedules")


class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="chat_histories")


class Trend(Base):
    __tablename__ = "trends"

    id = Column(Integer, primary_key=True, index=True)
    niche = Column(String(100), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    growth_score = Column(Integer, default=85)  # pontuação de 0 a 100 de viralidade / relevância
    suggested_hook = Column(Text, nullable=True)
    suggested_tags = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)