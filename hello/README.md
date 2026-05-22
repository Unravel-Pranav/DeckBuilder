# hello (legacy application)

This directory is a **separate** FastAPI application from Auto Deck (`backend/` + `frontend/`). It includes auth, Snowflake integration, scheduling, and ML agents under `hello/ml/`.

The Vue wizard in `frontend/` does **not** call this service. Keep deployments and documentation separate unless you are explicitly working on the legacy stack.
