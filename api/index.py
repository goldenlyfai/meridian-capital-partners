"""
Vercel Python Serverless Function — entry point for all /api/* routes.
Wraps the existing FastAPI app with Mangum (ASGI → Lambda/Vercel adapter).
"""
import sys
import os

# Make repo root importable (data/, factors/, analysis/, etc.)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api_server import app  # noqa: E402  (FastAPI app with all routes)
from mangum import Mangum

# Mangum adapts ASGI (FastAPI) to the Vercel/AWS Lambda request format
handler = Mangum(app, lifespan="off")
