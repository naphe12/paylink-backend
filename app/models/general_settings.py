# app/models/general_settings.py
from sqlalchemy import Column, Numeric, Text, TIMESTAMP, ForeignKey,Integer,String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class GeneralSettings(Base):
    __tablename__ = "general_settings"
    __table_args__ = {"schema": "paylink"}
    id = Column(Integer, primary_key=True)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())	
    currency = Column(String(3), nullable=False, default="EUR")    
    charge = Column(Numeric(12,2), nullable=False)
    decimal_after_point= Column(Integer, nullable=False, default=2) 
    email_notification =Column(Integer, nullable=False, default=1) 
    sms_notification = Column(Integer, nullable=False, default=1)   
    updated_at =Column(TIMESTAMP(timezone=True))
    fix_charge =Column(Numeric(12,2), nullable=False, default= 0.09)
    coefficient= Column(Numeric(12,2), nullable=False, default= 1.0250)
    fixValue = Column("fixvalue", Integer, nullable=False, default=120)
    smstransfert_fees = Column("smstransfert_fees", Numeric(12, 2), nullable=False, default=1.5000)
    bonus = Column(Integer, nullable=False, default=0)
    smsPhone = Column(String(50), nullable=False, default="")
    account = Column(String(50), nullable=False, default="")
    account_name = Column(String(50), nullable=False, default="")
