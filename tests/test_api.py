from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_check_receipt_no_files(client):
    response = client.post("/check-receipt")
    assert response.status_code == 422


def test_check_receipt_invalid_file(client):
    response = client.post(
        "/check-receipt",
        files={"files": ("fake.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 422
    assert "not a valid PDF" in response.json()["detail"]


def test_get_receipt_not_found(client):
    response = client.get("/receipt/nonexistent-id")
    assert response.status_code == 404


@patch("app.presentation.routes.analyze_receipts_task")
def test_check_receipt_valid_pdf(mock_task, client):
    mock_task.delay.return_value = None
    pdf_header = b"%PDF-1.4 fake content for testing"
    response = client.post(
        "/check-receipt",
        files={"files": ("receipt_test.pdf", pdf_header, "application/pdf")},
    )
    assert response.status_code == 202
    data = response.json()
    assert "analysis_id" in data
    assert data["status"] == "pending"
    mock_task.delay.assert_called_once()


@patch("app.presentation.routes.analyze_receipts_task")
def test_check_receipt_multiple_files(mock_task, client):
    mock_task.delay.return_value = None
    pdf_header = b"%PDF-1.4 fake content"
    response = client.post(
        "/check-receipt",
        files=[
            ("files", ("receipt_1.pdf", pdf_header, "application/pdf")),
            ("files", ("receipt_2.pdf", pdf_header, "application/pdf")),
        ],
    )
    assert response.status_code == 202
    mock_task.delay.assert_called_once()
    args = mock_task.delay.call_args[0]
    assert len(args[1]) == 2
