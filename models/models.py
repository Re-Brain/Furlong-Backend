from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, Date, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base
from core.availability import default_farm_availability

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

    # Visit availability schedule. NULL means "never configured" -> callers fall
    # back to default_farm_availability(). Shape matches the FarmAvailability schema.
    availability = Column(JSONB, nullable=True)

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
    # Which visit periods this horse participates in (subset of PERIOD_KEYS, canonical
    # order). NULL means "unset" -> defaults to all three; [] means not available.
    periods = Column(JSONB, nullable=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    farm = relationship("Farm", back_populates="horses")
    images = relationship("HorseImage", back_populates="horse", cascade="all, delete-orphan", order_by="HorseImage.position")
    race_records = relationship("RaceRecord", back_populates="horse", cascade="all, delete-orphan")

    @property
    def farm_availability(self) -> dict:
        """Owning farm's availability, resolved to the default when unconfigured.

        Exposed on the horse so the public read (GET /horses/{id}) can serialize it.
        """
        stored = self.farm.availability if self.farm else None
        return stored if stored is not None else default_farm_availability()


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


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    horse_id = Column(Integer, ForeignKey("horses.id", ondelete="CASCADE"), nullable=False)
    # Denormalized from the horse so the farm owner can query bookings directly.
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    visitor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    date = Column(Date, nullable=False)
    period = Column(String, nullable=False)  # morning | afternoon | evening
    # Time window resolved from the farm schedule at booking time and snapshotted
    # here, so later schedule edits never rewrite existing bookings. Column names
    # avoid the reserved word "end"; the Python attrs stay start/end.
    start = Column("start_time", String, nullable=False)  # "HH:MM"
    end = Column("end_time", String, nullable=False)      # "HH:MM"
    party_size = Column(Integer, nullable=False)
    note = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending | confirmed | declined | cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    visitor = relationship("User")
    horse = relationship("Horse")
    farm = relationship("Farm")

    @property
    def visitor_name(self):
        return self.visitor.name if self.visitor else None

    @property
    def visitor_email(self):
        return self.visitor.email if self.visitor else None

    @property
    def horse_name(self):
        return self.horse.name if self.horse else None

    @property
    def farm_name(self):
        return self.farm.name if self.farm else None
