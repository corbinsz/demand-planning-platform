"""Client brief: stockout risk, reorder recommendations, dead stock.

The same payload feeds the on-screen report, the PDF, and a read-only
share link. It never includes tokens or raw order lines.
"""

from __future__ import annotations

from app.database import async_session
from app.models.models import Workspace
from app.services.analytics import dead_stock_report
from app.services.forecasting import SKUForecast, generate_all_forecasts
from app.services.reorder import urgency
from app.timeutil import utcnow_naive


def _pdf_safe(value) -> str:
    text = "" if value is None else str(value)
    return text.encode("latin-1", "replace").decode("latin-1")


def _forecast_row(row: SKUForecast) -> dict:
    return {
        "sku": row.sku,
        "title": row.title,
        "current_stock": row.current_stock,
        "days_of_stock_remaining": row.days_of_stock_remaining,
        "lead_time_days": row.lead_time_days,
        "forecast_30d": row.forecast_30d,
        "confidence_low_30": row.confidence_low_30,
        "confidence_high_30": row.confidence_high_30,
        "suggested_reorder_qty": row.suggested_reorder_qty,
        "reorder_point": row.reorder_point,
        "model": row.model,
        "urgency": urgency(row.days_of_stock_remaining, row.lead_time_days),
    }


async def build_brief(workspace_id: int) -> dict:
    async with async_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        name = workspace.name if workspace else "Workspace"
        is_demo = bool(workspace.is_demo) if workspace else False

    forecasts, report = await generate_all_forecasts(workspace_id)
    dead = await dead_stock_report(workspace_id)

    risks = [
        row for row in forecasts
        if row.days_of_stock_remaining is not None and row.days_of_stock_remaining <= row.lead_time_days
    ]
    risks.sort(key=lambda row: (row.days_of_stock_remaining if row.days_of_stock_remaining is not None else 10**6, row.sku))
    reorders = [row for row in forecasts if row.below_reorder_point and row.suggested_reorder_qty > 0]
    reorders.sort(key=lambda row: (row.days_of_stock_remaining if row.days_of_stock_remaining is not None else 10**6, row.sku))

    dead_value = round(sum(item.inventory_value for item in dead), 2)
    return {
        "workspace_name": name,
        "is_demo": is_demo,
        "generated_at": utcnow_naive().isoformat(timespec="minutes") + "Z",
        "summary": {
            "sku_count": len(forecasts),
            "stockout_risk_count": len(risks),
            "reorder_count": len(reorders),
            "reorder_units": int(sum(row.suggested_reorder_qty for row in reorders)),
            "dead_stock_count": len(dead),
            "dead_stock_value": dead_value,
        },
        "model_report": report,
        "stockout_risks": [_forecast_row(row) for row in risks[:25]],
        "reorders": [_forecast_row(row) for row in reorders[:25]],
        "dead_stock": [
            {
                "sku": item.sku,
                "title": item.title,
                "current_stock": item.current_stock,
                "inventory_value": item.inventory_value,
                "days_since_last_sale": item.days_since_last_sale,
                "recommendation": item.recommendation,
            }
            for item in dead[:25]
        ],
    }


def render_brief_pdf(brief: dict) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="Letter")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.set_fill_color(18, 11, 70)
    pdf.rect(0, 0, 216, 28, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, _pdf_safe("Inventory Intel  |  Client brief"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    pdf.cell(0, 6, _pdf_safe(brief.get("workspace_name") or ""), new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(40, 40, 60)
    pdf.set_xy(12, 34)
    pdf.set_font("Helvetica", "", 9)
    stamp = brief.get("generated_at") or ""
    note = "Sample data for a fictional brand. Not a customer." if brief.get("is_demo") else "Confidential. Prepared for this workspace only."
    pdf.multi_cell(0, 5, _pdf_safe(f"Generated {stamp}. {note}"))

    summary = brief.get("summary") or {}
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    cards = [
        ("Stockout risk", str(summary.get("stockout_risk_count", 0))),
        ("Reorder lines", str(summary.get("reorder_count", 0))),
        ("Units to buy", f"{summary.get('reorder_units', 0):,}"),
        ("Dead stock at cost", f"${summary.get('dead_stock_value', 0):,.0f}"),
    ]
    pdf.set_font("Helvetica", "", 9)
    for label, _value in cards:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(90, 90, 110)
        pdf.cell(46, 5, _pdf_safe(label), new_x="RIGHT")
    pdf.ln(5)
    for _, value in cards:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(18, 11, 70)
        pdf.cell(46, 7, _pdf_safe(value), new_x="RIGHT")
    pdf.ln(10)
    pdf.set_text_color(40, 40, 60)

    def section(title: str, rows: list[dict], columns: list[tuple[str, str, int]]):
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(18, 11, 70)
        pdf.cell(0, 8, _pdf_safe(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(90, 90, 110)
        for _key, label, width in columns:
            pdf.cell(width, 6, _pdf_safe(label), border=0)
        pdf.ln(6)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(40, 40, 60)
        if not rows:
            pdf.cell(0, 6, "None right now.", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            return
        for row in rows[:15]:
            for key, _, width in columns:
                pdf.cell(width, 6, _pdf_safe(row.get(key, ""))[:42])
            pdf.ln(6)
        pdf.ln(2)

    section(
        "Stockout risk  (will run out inside supplier lead time)",
        brief.get("stockout_risks") or [],
        [("sku", "SKU", 42), ("days_of_stock_remaining", "Days left", 24), ("current_stock", "On hand", 24), ("forecast_30d", "30d forecast", 28), ("model", "Model", 32)],
    )
    section(
        "Reorder recommendations",
        brief.get("reorders") or [],
        [("sku", "SKU", 42), ("suggested_reorder_qty", "Buy", 22), ("current_stock", "On hand", 24), ("reorder_point", "Reorder at", 28), ("urgency", "Urgency", 28)],
    )
    section(
        "Dead stock  (valued at cost, not retail)",
        brief.get("dead_stock") or [],
        [("sku", "SKU", 42), ("current_stock", "Units", 22), ("inventory_value", "Value $", 28), ("days_since_last_sale", "Days quiet", 28), ("recommendation", "Action", 50)],
    )

    model = brief.get("model_report") or {}
    if model.get("baseline_ets_mase") is not None:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(90, 90, 110)
        pdf.multi_cell(
            0,
            4,
            _pdf_safe(
                "Forecast note: models were scored with a rolling-origin backtest. "
                f"Always using Holt-Winters scored MASE {model.get('baseline_ets_mase')}. "
                f"The selected mix scored MASE {model.get('selected_mase')} "
                f"(catalog winner: {model.get('global_winner')}). "
                "Lower is better. 1.0 matches repeating last week. "
                "Ranges on the live screen are an 80% band from backtest residuals."
            ),
        )

    out = pdf.output()
    return bytes(out)
