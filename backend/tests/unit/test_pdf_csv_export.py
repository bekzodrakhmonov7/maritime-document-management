import os
import subprocess
import tempfile

import pytest
from fastapi.responses import StreamingResponse

from app.models.report import FleetSummary, MissingDocRow, VesselComplianceRow
from app.services.report_service import export_csv, export_pdf


class TestExportCSV:
    def test_csv_has_correct_headers_and_utf8(self):
        rows = [
            MissingDocRow(
                seafarer_id=1,
                first_name="José",
                last_name="García",
                rank="Captain",
                vessel_name="M/V Tëst",
                doc_type_id=2,
                type_name="Passport",
            )
        ]
        response = export_csv(rows)
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/csv"

        # Read the response body
        body = b""
        async def _read():
            nonlocal body
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

        import asyncio
        asyncio.run(_read())

        content = body.decode("utf-8")
        lines = content.strip().split("\r\n")
        assert len(lines) == 2
        assert lines[0] == "seafarer_id,first_name,last_name,rank,vessel_name,doc_type_id,type_name"
        assert "José" in lines[1]
        assert "Tëst" in lines[1]


class TestExportPDF:
    def test_pdf_starts_with_pdf_header(self):
        summary = FleetSummary(
            vessels=[
                VesselComplianceRow(
                    vessel_id=1,
                    vessel_name="Test Vessel",
                    valid_count=5,
                    expiring_soon_count=2,
                    expired_count=1,
                    missing_count=3,
                )
            ],
            total_valid=5,
            total_expiring_soon=2,
            total_expired=1,
            total_missing=3,
        )
        pdf_bytes = export_pdf(summary)
        assert pdf_bytes.startswith(b"%PDF")

    def test_pdf_contains_expected_text(self):
        summary = FleetSummary(
            vessels=[
                VesselComplianceRow(
                    vessel_id=1,
                    vessel_name="Ocean Explorer",
                    valid_count=10,
                    expiring_soon_count=0,
                    expired_count=0,
                    missing_count=0,
                )
            ],
            total_valid=10,
            total_expiring_soon=0,
            total_expired=0,
            total_missing=0,
        )
        pdf_bytes = export_pdf(summary)

        # Write to temp file and use pdftotext to extract text
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            temp_path = f.name

        try:
            result = subprocess.run(
                ["pdftotext", temp_path, "-"],
                capture_output=True,
                text=True,
                check=True,
            )
            text = result.stdout
            assert "Fleet Compliance Summary" in text
            assert "Ocean Explorer" in text
            assert "Total" in text
        finally:
            os.unlink(temp_path)
