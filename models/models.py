from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="visitor")  # visitor | farmer | admin
    phone_code = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    farm = relationship("Farm", back_populates="owner", uselist=False, cascade="all, delete-orphan")


class Farm(Base):
    __tablename__ = "farms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    capacity = Column(Integer, nullable=True)
    status = Column(String, default="pending")  # pending | active

    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    owner = relationship("User", back_populates="farm", passive_deletes=True)

    horses = relationship("Horse", back_populates="farm", cascade="all, delete-orphan")
    images = relationship("FarmImage", back_populates="farm", cascade="all, delete-orphan", order_by="FarmImage.position")


class Horse(Base):
    __tablename__ = "horses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    story = Column(Text, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    color = Column(String, nullable=True)
    gender = Column(String, nullable=True)      # colt | stallion | gelding | filly | mare
    sire = Column(String, nullable=True)         # father
    dam = Column(String, nullable=True)          # mother
    sires_sire = Column(String, nullable=True)   # paternal grandfather
    sires_dam = Column(String, nullable=True)    # paternal grandmother
    dams_sire = Column(String, nullable=True)    # maternal grandfather
    dams_dam = Column(String, nullable=True)     # maternal grandmother
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    farm = relationship("Farm", back_populates="horses")
    images = relationship("HorseImage", back_populates="horse", cascade="all, delete-orphan", order_by="HorseImage.position")
    race_records = relationship("RaceRecord", back_populates="horse", cascade="all, delete-orphan")


class RaceRecord(Base):
    __tablename__ = "race_records"

    id = Column(Integer, primary_key=True, index=True)
    race_date = Column(Date, nullable=False)
    course = Column(String, nullable=False)
    race_name = Column(String, nullable=False)
    grade = Column(String, nullable=True)
    finish_position = Column(Integer, nullable=True)
    track = Column(String, nullable=True)
    distance = Column(Integer, nullable=True)
    condition = Column(String, nullable=True)

    horse_id = Column(Integer, ForeignKey("horses.id", ondelete="CASCADE"), nullable=False)
    horse = relationship("Horse", back_populates="race_records")


class HorseImage(Base):
    __tablename__ = "horse_images"

    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String, nullable=False)
    image_public_id = Column(String, nullable=False)
    position = Column(Integer, nullable=False, default=0)

    horse_id = Column(Integer, ForeignKey("horses.id", ondelete="CASCADE"), nullable=False)
    horse = relationship("Horse", back_populates="images")


class FarmImage(Base):
    __tablename__ = "farm_images"

    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String, nullable=False)
    image_public_id = Column(String, nullable=False)
    position = Column(Integer, nullable=False, default=0)

    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    farm = relationship("Farm", back_populates="images")
