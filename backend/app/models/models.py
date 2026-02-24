from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    String,
    Integer,
    Numeric,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    variant_id: Mapped[str | None] = mapped_column(String(100))
    shopify_id: Mapped[str | None] = mapped_column(String(100))
    shiphero_id: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(String(500))
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    parent_sku: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    order_line_items: Mapped[list["OrderLineItem"]] = relationship(
        back_populates="product", primaryjoin="Product.sku == foreign(OrderLineItem.sku)"
    )
    inventory_snapshots: Mapped[list["InventorySnapshot"]] = relationship(
        back_populates="product",
        primaryjoin="Product.sku == foreign(InventorySnapshot.sku)",
    )
    reorder_rule: Mapped["ReorderRule | None"] = relationship(
        back_populates="product",
        primaryjoin="Product.sku == foreign(ReorderRule.sku)",
        uselist=False,
    )

    __table_args__ = (
        Index("ix_products_sku", "sku"),
        Index("ix_products_shopify_id", "shopify_id"),
        Index("ix_products_shiphero_id", "shiphero_id"),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    shopify_order_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    line_items: Mapped[list["OrderLineItem"]] = relationship(back_populates="order")

    __table_args__ = (Index("ix_orders_shopify_order_id", "shopify_order_id"),)


class OrderLineItem(Base):
    __tablename__ = "order_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_item_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    order_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("orders.order_id"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    order: Mapped["Order"] = relationship(back_populates="line_items")
    product: Mapped["Product | None"] = relationship(
        back_populates="order_line_items",
        primaryjoin="foreign(OrderLineItem.sku) == Product.sku",
    )

    __table_args__ = (
        Index("ix_order_line_items_sku", "sku"),
        Index("ix_order_line_items_order_id", "order_id"),
    )


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    quantity_allocated: Mapped[int] = mapped_column(Integer, default=0)
    quantity_available: Mapped[int] = mapped_column(Integer, default=0)
    warehouse: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # shopify | shiphero
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    product: Mapped["Product | None"] = relationship(
        back_populates="inventory_snapshots",
        primaryjoin="foreign(InventorySnapshot.sku) == Product.sku",
    )

    __table_args__ = (
        Index("ix_inventory_snapshots_sku", "sku"),
        Index("ix_inventory_snapshots_source", "source"),
        Index("ix_inventory_snapshots_recorded_at", "recorded_at"),
    )


class ReorderRule(Base):
    __tablename__ = "reorder_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False)
    reorder_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=14)
    safety_stock: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped["Product | None"] = relationship(
        back_populates="reorder_rule",
        primaryjoin="foreign(ReorderRule.sku) == Product.sku",
    )

    __table_args__ = (Index("ix_reorder_rules_sku", "sku"),)


class PromotionalPeriod(Base):
    __tablename__ = "promotional_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # running | success | failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    records_processed: Mapped[int | None] = mapped_column(Integer)
