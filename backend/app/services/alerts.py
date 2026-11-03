"""Plain-language alerts and the weekly email body.

Alerts are computed. Nothing is sent unless the server owner sets a
webhook or SMTP settings. Until then the product still shows the email
the owner would have received.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models.models import User, Workspace
from app.services.analytics import dead_stock_report, excess_stock_report
from app.services.audit import write_audit
from app.services.forecasting import generate_all_forecasts
from app.timeutil import utcnow_naive


def build_alert_list(forecasts, excess) -> list[dict]:
    alerts = []
    for row in forecasts:
        days = row.days_of_stock_remaining
        if days is None:
            continue
        if days <= row.lead_time_days:
            alerts.append({
                "severity": "critical",
                "kind": "stockout",
                "sku": row.sku,
                "headline": f"Stockout in {days:g} days" if days > 0 else "Out of stock",
                "plain": (
                    f"{row.title} will run out before a replenishment can arrive. "
                    f"Lead time is {row.lead_time_days} days and about {int(row.current_stock)} are on hand."
                ),
            })
        elif days <= row.lead_time_days * 2:
            alerts.append({
                "severity": "warning",
                "kind": "reorder_soon",
                "sku": row.sku,
                "headline": f"Reorder soon — {days:g} days of cover",
                "plain": (
                    f"{row.title} is inside two lead times. Ordering this week avoids a stockout."
                ),
            })
    for item in excess[:8]:
        alerts.append({
            "severity": "info",
            "kind": "overstock",
            "sku": item.sku,
            "headline": f"Overstock — about {int(item.days_of_stock)} days on hand",
            "plain": (
                f"{item.title} has more than a quarter of cover. "
                f"About ${item.excess_value:,.0f} at cost is above the target."
            ),
        })
    severity = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda item: severity.get(item["severity"], 9))
    return alerts[:12]


async def today_payload(workspace_id: int) -> dict:
    forecasts, report = await generate_all_forecasts(workspace_id)
    dead = await dead_stock_report(workspace_id)
    excess = await excess_stock_report(workspace_id)
    risks = [
        row for row in forecasts
        if row.days_of_stock_remaining is not None and row.days_of_stock_remaining <= row.lead_time_days
    ]
    risks.sort(key=lambda row: row.days_of_stock_remaining if row.days_of_stock_remaining is not None else 10**9)
    buys = [row for row in forecasts if row.suggested_reorder_qty > 0 and row.below_reorder_point]
    buys.sort(key=lambda row: row.days_of_stock_remaining if row.days_of_stock_remaining is not None else 10**9)
    dead_value = round(sum(item.inventory_value for item in dead), 2)
    async with async_session() as session:
        workspace = await session.get(Workspace, workspace_id)
    name = workspace.name if workspace else "Your brand"
    if risks:
        lead = f"{len(risks)} product{'s' if len(risks) != 1 else ''} will stock out before a new order can arrive."
    elif buys:
        lead = f"Nothing is inside lead time. {len(buys)} product{'s' if len(buys) != 1 else ''} should still be reordered."
    else:
        lead = "Nothing needs an urgent reorder today."
    if dead_value > 0:
        lead += f" ${dead_value:,.0f} at cost is sitting in stock that barely sells."
    return {
        "workspace_name": name,
        "is_demo": bool(workspace and workspace.is_demo),
        "generated_at": utcnow_naive().isoformat(timespec="minutes") + "Z",
        "lead": lead,
        "stockout_risks": [_buy_row(row) for row in risks[:5]],
        "reorders": [_buy_row(row) for row in buys[:5]],
        "dead_stock": [
            {
                "sku": item.sku,
                "title": item.title,
                "current_stock": item.current_stock,
                "inventory_value": item.inventory_value,
                "days_since_last_sale": item.days_since_last_sale,
                "recommendation": item.recommendation,
                "plain": _dead_plain(item),
            }
            for item in dead[:5]
        ],
        "dead_stock_value": dead_value,
        "dead_stock_count": len(dead),
        "reorder_count": len(buys),
        "stockout_count": len(risks),
        "alerts": build_alert_list(forecasts, excess),
        "model_report": report,
    }


def _buy_row(row) -> dict:
    days = row.days_of_stock_remaining
    if days is None:
        when = "No recent sales pace to time a stockout."
    elif days <= 0:
        when = "Already out of stock."
    else:
        when = f"About {days:g} days of stock left. A new order takes {row.lead_time_days} days."
    low = int(row.confidence_low_30 or 0)
    high = int(row.confidence_high_30 or 0)
    return {
        "sku": row.sku,
        "title": row.title,
        "current_stock": row.current_stock,
        "days_of_stock_remaining": days,
        "lead_time_days": row.lead_time_days,
        "suggested_reorder_qty": row.suggested_reorder_qty,
        "forecast_30d": row.forecast_30d,
        "confidence_low_30": row.confidence_low_30,
        "confidence_high_30": row.confidence_high_30,
        "model": row.model,
        "plain": when,
        "range_plain": f"Next 30 days: about {int(row.forecast_30d)} units, likely between {low} and {high}.",
    }


def _dead_plain(item) -> str:
    quiet = "never sold" if item.days_since_last_sale is None else f"quiet for {item.days_since_last_sale} days"
    return f"{item.current_stock} on hand, {quiet}. About ${item.inventory_value:,.0f} at cost. {item.recommendation}."


def render_weekly_email(payload: dict) -> dict:
    """Subject and bodies. Plain text is the source of truth; HTML is a light wrap."""
    name = payload["workspace_name"]
    subject = f"{name}: what to do this week"
    lines = [
        payload["lead"],
        "",
        "Order these first",
    ]
    if not payload["reorders"] and not payload["stockout_risks"]:
        lines.append("No urgent buys.")
    seen = set()
    for row in list(payload["stockout_risks"]) + list(payload["reorders"]):
        if row["sku"] in seen:
            continue
        seen.add(row["sku"])
        lines.append(
            f"- {row['title']} ({row['sku']}): buy {row['suggested_reorder_qty']}. {row['plain']}"
        )
    lines.append("")
    lines.append(f"Cash in quiet stock: ${payload['dead_stock_value']:,.0f} at cost across {payload['dead_stock_count']} SKUs.")
    for row in payload["dead_stock"][:3]:
        lines.append(f"- {row['title']}: {row['plain']}")
    lines.append("")
    lines.append("This note was prepared by Inventory Intel. It is not sent unless email delivery is turned on.")
    if payload.get("is_demo"):
        lines.append("Sample data for the fictional brand Northline Athletics. Not a real customer.")
    text = "\n".join(lines)
    html_items = "".join(f"<li>{_html(line[2:])}</li>" for line in lines if line.startswith("- "))
    html = (
        f"<div style=\"font-family:Georgia,serif;color:#1c1733;max-width:560px\">"
        f"<p style=\"font-size:18px\">{_html(payload['lead'])}</p>"
        f"<ul>{html_items}</ul>"
        f"<p style=\"color:#3f4a5a;font-size:13px\">Inventory Intel · weekly summary</p></div>"
    )
    return {"subject": subject, "text": text, "html": html}


def _html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def dispatch_weekly_digest(workspace_id: int) -> dict:
    """Build the email and deliver it only when a channel is configured."""
    payload = await today_payload(workspace_id)
    email = render_weekly_email(payload)
    settings = get_settings()
    channel = "preview"
    delivered = False
    async with async_session() as session:
        owner = (await session.execute(
            select(User).where(User.workspace_id == workspace_id).limit(1)
        )).scalar_one_or_none()
        to_addr = owner.email if owner else None
        if settings.digest_webhook_url:
            channel = "webhook"
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(settings.digest_webhook_url, json={
                    "to": to_addr,
                    "subject": email["subject"],
                    "text": email["text"],
                })
            delivered = response.status_code < 400
        elif settings.smtp_host and to_addr and settings.smtp_from:
            channel = "smtp"
            _send_smtp(to_addr, email, settings)
            delivered = True
        await write_audit(
            session,
            workspace_id=workspace_id,
            actor_email="scheduler",
            action="weekly_digest",
            resource=channel,
            detail=f"delivered={delivered}; subject={email['subject'][:120]}",
        )
        await session.commit()
    return {"channel": channel, "delivered": delivered, "subject": email["subject"], "email": email}


def _send_smtp(to_addr: str, email: dict, settings) -> None:
    message = EmailMessage()
    message["Subject"] = email["subject"]
    message["From"] = settings.smtp_from
    message["To"] = to_addr
    message.set_content(email["text"])
    message.add_alternative(email["html"], subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
