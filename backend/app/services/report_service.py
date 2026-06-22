import csv
import io
from datetime import date

import asyncpg
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.report import FleetSummary, MissingDocRow, VesselComplianceRow


async def missing_mandatory_documents(
    conn: asyncpg.Connection,
) -> list[MissingDocRow]:
    rows = await conn.fetch(
        """
        SELECT
            s.seafarer_id,
            s.first_name,
            s.last_name,
            s.rank,
            v.vessel_name,
            dt.doc_type_id,
            dt.type_name
        FROM public.seafarer s
        JOIN public.vessel v ON v.vessel_id = s.vessel_id
        CROSS JOIN public.document_type dt
        WHERE dt.is_mandatory = true
          AND NOT EXISTS (
              SELECT 1
              FROM public.document d
              WHERE d.seafarer_id = s.seafarer_id
                AND d.doc_type_id = dt.doc_type_id
                AND d.status = 'verified'
          )
        ORDER BY v.vessel_name, s.last_name, s.first_name, dt.type_name
        """
    )
    return [MissingDocRow(**dict(r)) for r in rows]


async def fleet_compliance_summary(conn: asyncpg.Connection) -> FleetSummary:
    # Get mandatory doc type count for total_documents calculation
    mandatory_count = await conn.fetchval(
        "SELECT COUNT(*) FROM public.document_type WHERE is_mandatory = true"
    )

    rows = await conn.fetch(
        """
        WITH mandatory_requirements AS (
            SELECT s.seafarer_id, s.vessel_id, dt.doc_type_id
            FROM public.seafarer s
            CROSS JOIN public.document_type dt
            WHERE dt.is_mandatory = true
        ),
        doc_status AS (
            SELECT DISTINCT ON (mr.seafarer_id, mr.doc_type_id)
                mr.vessel_id,
                mr.seafarer_id,
                mr.doc_type_id,
                d.status
            FROM mandatory_requirements mr
            LEFT JOIN public.document d
                ON d.seafarer_id = mr.seafarer_id
                AND d.doc_type_id = mr.doc_type_id
            ORDER BY mr.seafarer_id, mr.doc_type_id,
                CASE COALESCE(d.status, '')
                    WHEN 'verified' THEN 1
                    WHEN 'expiring_soon' THEN 2
                    WHEN 'expired' THEN 3
                    ELSE 4
                END
        ),
        vessel_seafarer_counts AS (
            SELECT vessel_id, COUNT(*) AS seafarer_count
            FROM public.seafarer
            GROUP BY vessel_id
        )
        SELECT
            v.vessel_id,
            v.vessel_name,
            COALESCE(vsc.seafarer_count, 0) AS total_seafarers,
            COALESCE(vsc.seafarer_count, 0) * $1 AS total_documents,
            COUNT(*) FILTER (WHERE ds.status = 'verified') AS valid_count,
            COUNT(*) FILTER (WHERE ds.status = 'expiring_soon') AS expiring_soon_count,
            COUNT(*) FILTER (WHERE ds.status = 'expired') AS expired_count,
            COUNT(*) FILTER (WHERE ds.doc_type_id IS NOT NULL AND (ds.status IS NULL OR ds.status NOT IN ('verified', 'expiring_soon', 'expired'))) AS missing_count
        FROM public.vessel v
        LEFT JOIN vessel_seafarer_counts vsc ON vsc.vessel_id = v.vessel_id
        LEFT JOIN doc_status ds ON ds.vessel_id = v.vessel_id
        GROUP BY v.vessel_id, v.vessel_name, vsc.seafarer_count
        ORDER BY v.vessel_id
        """,
        mandatory_count,
    )

    vessels = [VesselComplianceRow(**dict(r)) for r in rows]

    total_valid = sum(v.valid_count for v in vessels)
    total_expiring_soon = sum(v.expiring_soon_count for v in vessels)
    total_expired = sum(v.expired_count for v in vessels)
    total_missing = sum(v.missing_count for v in vessels)

    return FleetSummary(
        vessels=vessels,
        total_valid=total_valid,
        total_expiring_soon=total_expiring_soon,
        total_expired=total_expired,
        total_missing=total_missing,
    )


def export_csv(rows: list[MissingDocRow]) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "seafarer_id",
        "first_name",
        "last_name",
        "rank",
        "vessel_name",
        "doc_type_id",
        "type_name",
    ])
    for row in rows:
        writer.writerow([
            row.seafarer_id,
            row.first_name,
            row.last_name,
            row.rank,
            row.vessel_name,
            row.doc_type_id,
            row.type_name,
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=missing_mandatory_documents.csv"},
    )


def export_pdf(summary: FleetSummary) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    title = Paragraph("Fleet Compliance Summary", styles["Heading1"])
    elements.append(title)
    elements.append(Spacer(1, 12))

    date_para = Paragraph(f"Report Date: {date.today().isoformat()}", styles["Normal"])
    elements.append(date_para)
    elements.append(Spacer(1, 12))

    table_data = [
        [
            "Vessel",
            "Valid",
            "Expiring Soon",
            "Expired",
            "Missing",
        ]
    ]
    for vessel in summary.vessels:
        table_data.append([
            vessel.vessel_name,
            str(vessel.valid_count),
            str(vessel.expiring_soon_count),
            str(vessel.expired_count),
            str(vessel.missing_count),
        ])

    table_data.append([
        "Total",
        str(summary.total_valid),
        str(summary.total_expiring_soon),
        str(summary.total_expired),
        str(summary.total_missing),
    ])

    table = Table(table_data, hAlign="LEFT")
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ])
    )
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
