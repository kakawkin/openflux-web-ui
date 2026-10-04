#!/usr/bin/env python3
import uvicorn
import os

if __name__ == "__main__":
    host = os.environ.get("OPENFLUX_HOST", "127.0.0.1")
    port = int(os.environ.get("OPENFLUX_PORT", "8000"))
    print(f"Starting OpenFlux Web UI on http://{host}:{port} ...")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
