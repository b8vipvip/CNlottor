from __future__ import annotations

import os


def main() -> int:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install CNlottor with the server extra") from exc
    uvicorn.run(
        "cnlottor.api.app:app",
        host=os.getenv("CNLOTTOR_HOST", "0.0.0.0"),
        port=int(os.getenv("CNLOTTOR_PORT", "8000")),
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
