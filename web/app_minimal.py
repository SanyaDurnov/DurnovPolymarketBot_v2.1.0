"""
Minimal Web UI для Polymarket Bot V2 (FastAPI) - без шаблонов.
"""

import logging
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(
    title="Polymarket Bot V2 - Minimal",
    description="Minimal trading bot для Polymarket",
    version="2.0.0",
)

@app.get("/")
async def root():
    """Главная страница."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Polymarket Bot V2 - Minimal</title>
    </head>
    <body>
        <h1>🤖 Polymarket Bot V2 - Minimal Test</h1>
        <p>Web server is working!</p>
        <p><a href="/api/status">Check API Status</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/status")
async def get_status():
    """Простой статус."""
    return {"status": "Web server is running", "mode": "minimal"}