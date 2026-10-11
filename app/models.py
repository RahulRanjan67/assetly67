from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
class Base(DeclarativeBase):
    pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Demo Owner")
    email: Mapped[str] = mapped_column(String(255), unique=True, default="owner@assetly.local")
    assets: Mapped[list["Asset"]] = relationship(back_populates="user")
class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    assets: Mapped[list["Asset"]] = relationship(back_populates="category")
    consumables: Mapped[list["Consumable"]] = relationship(back_populates="category")
class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    assets: Mapped[list["Asset"]] = relationship(back_populates="location")
    consumables: Mapped[list["Consumable"]] = relationship(back_populates="location")
class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    contact: Mapped[str | None] = mapped_column(String(255))
    borrowings: Mapped[list["Borrowing"]] = relationship(back_populates="person")
class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    name: Mapped[str] = mapped_column(String(160), index=True)
    condition: Mapped[str] = mapped_column(String(40), default="Good")
    status: Mapped[str] = mapped_column(String(30), default="AVAILABLE", index=True)
    description: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(500))
    qr_code: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    user: Mapped["User"] = relationship(back_populates="assets")
    category: Mapped["Category | None"] = relationship(back_populates="assets")
    location: Mapped["Location | None"] = relationship(back_populates="assets")
    specs: Mapped["AssetSpec | None"] = relationship(back_populates="asset", uselist=False, cascade="all, delete-orphan")
    purchases: Mapped[list["Purchase"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    warranties: Mapped[list["Warranty"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    maintenance: Mapped[list["Maintenance"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    borrowings: Mapped[list["Borrowing"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    history: Mapped[list["AssetStatusHistory"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    repairs: Mapped[list["Repair"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
class AssetSpec(Base):
    __tablename__ = "asset_specs"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), unique=True)
    serial_number: Mapped[str | None] = mapped_column(String(120))
    model_number: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    color: Mapped[str | None] = mapped_column(String(60))
    technical_notes: Mapped[str | None] = mapped_column(Text)
    asset: Mapped["Asset"] = relationship(back_populates="specs")
class Purchase(Base):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    purchase_date: Mapped[date] = mapped_column(Date)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    seller: Mapped[str | None] = mapped_column(String(160))
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    asset: Mapped["Asset"] = relationship(back_populates="purchases")
class Warranty(Base):
    __tablename__ = "warranties"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    provider: Mapped[str] = mapped_column(String(160))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    terms: Mapped[str | None] = mapped_column(Text)
    asset: Mapped["Asset"] = relationship(back_populates="warranties")
class Maintenance(Base):
    __tablename__ = "maintenance_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    maintenance_type: Mapped[str] = mapped_column(String(120))
    maintenance_date: Mapped[date] = mapped_column(Date)
    next_due_date: Mapped[date | None] = mapped_column(Date)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    service_provider: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    asset: Mapped["Asset"] = relationship(back_populates="maintenance")
class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    expense_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    expense_type: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    asset: Mapped["Asset"] = relationship(back_populates="expenses")
class Borrowing(Base):
    __tablename__ = "borrowings"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    borrowed_date: Mapped[date] = mapped_column(Date)
    expected_return_date: Mapped[date]
    actual_return_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    payment_type: Mapped[str] = mapped_column(String(20), default="FREE")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    payment_status: Mapped[str] = mapped_column(String(30), default="NOT_REQUIRED")
    notes: Mapped[str | None] = mapped_column(Text)
    asset: Mapped["Asset"] = relationship(back_populates="borrowings")
    person: Mapped["Person"] = relationship(back_populates="borrowings")
class AssetStatusHistory(Base):
    __tablename__ = "asset_status_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    old_status: Mapped[str] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    reason: Mapped[str | None] = mapped_column(String(255))
    asset: Mapped["Asset"] = relationship(back_populates="history")
class Repair(Base):
    __tablename__ = "repairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    reported_date: Mapped[date] = mapped_column(Date, default=date.today)
    completed_date: Mapped[date | None] = mapped_column(Date)
    issue: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    provider: Mapped[str | None] = mapped_column(String(160))
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    asset: Mapped["Asset"] = relationship(back_populates="repairs")
class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(Integer)
    storage_path: Mapped[str | None] = mapped_column(String(500))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
class Consumable(Base):
    __tablename__ = "consumables"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    name: Mapped[str] = mapped_column(String(160), index=True)
    brand: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(30), default="unit")
    reorder_level: Mapped[int] = mapped_column(default=1)
    last_bought_at: Mapped[date | None] = mapped_column(Date)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped["Category | None"] = relationship(back_populates="consumables")
    location: Mapped["Location | None"] = relationship(back_populates="consumables")
    batches: Mapped[list["ConsumableBatch"]] = relationship(back_populates="consumable", cascade="all, delete-orphan")
class ConsumableBatch(Base):
    __tablename__ = "consumable_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    consumable_id: Mapped[int] = mapped_column(ForeignKey("consumables.id"))
    purchase_date: Mapped[date] = mapped_column(Date)
    initial_quantity: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    consumable: Mapped["Consumable"] = relationship(back_populates="batches")
    movements: Mapped[list["StockMovement"]] = relationship(back_populates="batch", cascade="all, delete-orphan")
class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("consumable_batches.id"))
    movement_type: Mapped[str] = mapped_column(String(30))
    quantity_change: Mapped[int] = mapped_column(Integer)
    movement_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    batch: Mapped["ConsumableBatch"] = relationship(back_populates="movements")
class SyncLog(Base):
    __tablename__ = "sync_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    client_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="COMMITTED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
