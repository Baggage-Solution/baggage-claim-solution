"""
backend/api/routes/qr.py

QR code generation endpoint — T-018.

Generates a QR code PNG that deep-links to the React simulator with
airport and terminal context pre-filled as URL query parameters.

The passenger scans the QR code placed at the baggage carousel and is
taken directly to:
    http://<host>/simulator?airport=T3&terminal=B&auto=1

The simulator reads those params and auto-starts the claim flow with
airport context already embedded in the session, so A1 can greet the
passenger with their exact location.

Routes:
    GET /qr/generate          — Returns QR PNG bytes (download)
    GET /qr/generate?airport=T3&terminal=B&format=json
                              — Returns JSON with base64 PNG + metadata
    GET /qr/poster            — Returns a printable A4 PDF poster
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

router = APIRouter(tags=["QR Entry"])
logger = logging.getLogger(__name__)


def _build_simulator_url(host: str, airport: str, terminal: str) -> str:
    """Build the deep-link URL that the QR code will encode.

    Args:
        host: The base URL of the simulator (e.g. http://localhost:5173).
        airport: Airport code or name (e.g. T3, BOM, DXB).
        terminal: Terminal identifier (e.g. A, B, 2).

    Returns:
        Full URL with query params for simulator auto-start.
    """
    return f"{host}/simulator?airport={airport}&terminal={terminal}&auto=1"


def _generate_qr_image(url: str, box_size: int = 10, border: int = 4) -> bytes:
    """Generate a QR code PNG for the given URL.

    Args:
        url: The URL to encode in the QR code.
        box_size: Pixel size of each QR module box.
        border: Number of quiet-zone boxes around the QR code.

    Returns:
        Raw PNG bytes of the generated QR code.
    """
    import qrcode  # type: ignore
    from qrcode.constants import ERROR_CORRECT_H  # type: ignore

    qr = qrcode.QRCode(
        version=None,  # auto-size
        error_correction=ERROR_CORRECT_H,  # 30% error correction — good for print
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _generate_poster_pdf(
    qr_png_bytes: bytes, airport: str, terminal: str, url: str
) -> bytes:
    """Generate a printable A4 PDF poster embedding the QR code.

    Layout:
      - ABC Airline logo text header
      - "Baggage Damaged?" headline
      - Instruction text
      - QR code image centred
      - URL printed below QR for fallback
      - Footer with airport + terminal context

    Args:
        qr_png_bytes: PNG bytes of the generated QR code.
        airport: Airport / terminal label for footer.
        terminal: Terminal letter/number for footer.
        url: The URL encoded in the QR — printed as fallback text.

    Returns:
        Raw PDF bytes of the A4 poster.
    """
    from PIL import Image  # type: ignore
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
    from reportlab.lib.units import cm  # type: ignore
    from reportlab.platypus import Image as RLImage  # type: ignore
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    width, height = A4
    usable_width = width - 4 * cm

    # ── Styles ────────────────────────────────────────────────────────────────
    from reportlab.lib.enums import TA_CENTER  # type: ignore
    from reportlab.lib.styles import ParagraphStyle  # type: ignore

    header_style = ParagraphStyle(
        "Header",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#666666"),
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    headline_style = ParagraphStyle(
        "Headline",
        parent=styles["Normal"],
        fontSize=28,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1a1a1a"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    subline_style = ParagraphStyle(
        "Subline",
        parent=styles["Normal"],
        fontSize=14,
        textColor=colors.HexColor("#333333"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    instruction_style = ParagraphStyle(
        "Instruction",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#555555"),
        alignment=TA_CENTER,
        spaceAfter=4,
        leading=16,
    )
    url_style = ParagraphStyle(
        "URL",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1a73e8"),
        alignment=TA_CENTER,
    )

    # ── QR image ──────────────────────────────────────────────────────────────
    qr_img_buf = io.BytesIO(qr_png_bytes)
    qr_size = 9 * cm  # centre-square QR — large for easy scanning from ~60cm

    # ── Story ─────────────────────────────────────────────────────────────────
    story = [
        Paragraph("ABC AIRLINE", header_style),
        Spacer(1, 0.3 * cm),
        Paragraph("Baggage Damaged?", headline_style),
        Paragraph("File your claim instantly — no queues, no forms.", subline_style),
        Spacer(1, 0.5 * cm),
        Paragraph(
            "1. Scan the QR code with your phone camera<br/>"
            "2. Take photos of the damage and your bag tag<br/>"
            "3. Receive your claim decision in under 2 minutes",
            instruction_style,
        ),
        Spacer(1, 0.6 * cm),
        RLImage(qr_img_buf, width=qr_size, height=qr_size),
        Spacer(1, 0.4 * cm),
        Paragraph(f"Or visit: {url}", url_style),
        Spacer(1, 0.5 * cm),
        Paragraph(f"✈  {airport}  ·  Terminal {terminal}", footer_style),
    ]

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/qr/generate")
async def generate_qr(
    airport: str = Query(
        default="T3", description="Airport code or name, e.g. T3, BOM"
    ),
    terminal: str = Query(default="B", description="Terminal identifier, e.g. A, B, 2"),
    host: str = Query(
        default="http://localhost:5173",
        description="Base URL of the simulator — change to ngrok URL for mobile testing",
    ),
    format: str = Query(
        default="png",
        description="Response format: 'png' (binary download) or 'json' (base64 + metadata)",
    ),
) -> Response:
    """Generate a QR code deep-linking to the simulator with airport context.

    The QR encodes:
        {host}/simulator?airport={airport}&terminal={terminal}&auto=1

    Args:
        airport: Airport / zone identifier embedded in the QR URL.
        terminal: Terminal letter or number embedded in the QR URL.
        host: Base URL of the React simulator. Defaults to localhost for dev.
        format: 'png' returns raw image bytes; 'json' returns base64 + metadata.

    Returns:
        PNG image bytes (Content-Type: image/png) or JSON with base64 payload.
    """
    url = _build_simulator_url(host, airport, terminal)
    png_bytes = _generate_qr_image(url)

    logger.info(
        "qr_generated",
        extra={"airport": airport, "terminal": terminal, "url": url, "format": format},
    )

    if format == "json":
        return JSONResponse(
            content={
                "url": url,
                "airport": airport,
                "terminal": terminal,
                "qr_base64": base64.b64encode(png_bytes).decode("utf-8"),
                "content_type": "image/png",
            }
        )

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="qr_{airport}_{terminal}.png"'
        },
    )


@router.get("/qr/poster")
async def generate_poster(
    airport: str = Query(
        default="T3", description="Airport code shown on the poster footer"
    ),
    terminal: str = Query(
        default="B", description="Terminal identifier on the poster footer"
    ),
    host: str = Query(
        default="http://localhost:5173",
        description="Base URL of the simulator encoded in the QR",
    ),
) -> Response:
    """Generate a printable A4 PDF poster with QR code and claim instructions.

    Generates a full A4 poster suitable for printing and placing at the
    baggage carousel. Contains:
    - ABC Airline header
    - 'Baggage Damaged?' headline
    - 3-step instructions for passengers
    - Large QR code for easy scanning from ~60cm distance
    - Fallback URL in small print
    - Airport + terminal footer

    Args:
        airport: Airport / zone for the poster footer label.
        terminal: Terminal letter/number for the poster footer label.
        host: Base URL of the simulator — change to public URL for deployment.

    Returns:
        PDF bytes as attachment download.
    """
    url = _build_simulator_url(host, airport, terminal)
    png_bytes = _generate_qr_image(url, box_size=12, border=4)

    try:
        pdf_bytes = _generate_poster_pdf(png_bytes, airport, terminal, url)
    except ImportError:
        logger.warning(
            "reportlab_not_installed — returning QR PNG instead of PDF poster"
        )
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="qr_poster_{airport}_{terminal}.png"'
            },
        )

    logger.info(
        "qr_poster_generated",
        extra={"airport": airport, "terminal": terminal, "url": url},
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="qr_poster_{airport}_{terminal}.pdf"'
        },
    )
