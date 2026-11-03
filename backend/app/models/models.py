"""Tables.

Every brand is a workspace. Business rows carry workspace_id so one brand
cannot read another brand's orders, stock, or tokens. Natural keys
(sku, order id, snapshot id) are unique per workspace, not globally.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.timeutil import UTCDateTime, utcnow_naive


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)

    users: Mapped[list["User"]] = relationship(back_populates="workspace")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="owner", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)

    workspace: Mapped["Workspace"] = relationship(back_populates="users")


class IntegrationCredential(Base):
    """Encrypted Shopify or ShipHero credentials for one workspace."""

    __tablename__ = "integration_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)  # shopify | shiphero
    shop_domain: Mapped[str | None] = mapped_column(String(255))
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    scopes: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(40), default="connected", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_credential_provider"),
    )


class OAuthState(Base):
    """Short-lived Shopify OAuth state, so the callback cannot be forged."""

    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    shop_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive, index=True)


class ShareLink(Base):
    __tablename__ = "share_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(200), default="Inventory brief")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    variant_id: Mapped[str | None] = mapped_column(String(100))
    shopify_id: Mapped[str | None] = mapped_column(String(100))
    shiphero_id: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(String(500))
    cost_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    parent_sku: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("workspace_id", "sku", name="uq_product_ws_sku"),
        Index("ix_products_shopify_id", "workspace_id", "shopify_id"),
        Index("ix_products_shiphero_id", "workspace_id", "shiphero_id"),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    shopify_order_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)
    total_price: Mapped[float | None] = mapped_column(Numeric(12, 2))

    line_items: Mapped[list["OrderLineItem"]] = relationship(
        back_populates="order",
        primaryjoin="and_(Order.workspace_id==foreign(OrderLineItem.workspace_id), Order.order_id==foreign(OrderLineItem.order_id))",
        foreign_keys="[OrderLineItem.workspace_id, OrderLineItem.order_id]",
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "order_id", name="uq_order_ws"),
        Index("ix_orders_ws_created", "workspace_id", "created_at"),
    )


class OrderLineItem(Base):
    __tablename__ = "order_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    line_item_id: Mapped[str] = mapped_column(String(100), nullable=False)
    order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2))

    order: Mapped["Order"] = relationship(
        back_populates="line_items",
        primaryjoin="and_(foreign(OrderLineItem.workspace_id)==Order.workspace_id, foreign(OrderLineItem.order_id)==Order.order_id)",
        foreign_keys="[OrderLineItem.workspace_id, OrderLineItem.order_id]",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "order_id"],
            ["orders.workspace_id", "orders.order_id"],
            name="fk_line_order",
            ondelete="CASCADE",
        ),
        UniqueConstraint("workspace_id", "line_item_id", name="uq_line_ws"),
        Index("ix_oli_ws_sku", "workspace_id", "sku"),
    )


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(150), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    quantity_allocated: Mapped[int] = mapped_column(Integer, default=0)
    quantity_available: Mapped[int] = mapped_column(Integer, default=0)
    warehouse: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # shopify | shiphero
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("workspace_id", "snapshot_id", name="uq_snapshot_ws"),
        Index("ix_snap_ws_sku_source", "workspace_id", "sku", "source"),
        Index("ix_snap_ws_recorded", "workspace_id", "recorded_at"),
    )


class ReorderRule(Base):
    __tablename__ = "reorder_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False)
    reorder_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=14)
    safety_stock: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("workspace_id", "sku", name="uq_reorder_ws_sku"),
    )


class PromotionalPeriod(Base):
    __tablename__ = "promotional_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    job_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # running | success | failed
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow_naive)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    records_processed: Mapped[int | None] = mapped_column(Integer)
