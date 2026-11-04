"""Local API launcher: uv run --project backend python main.py (from the repository root)."""

import uvicorn


def main():
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
