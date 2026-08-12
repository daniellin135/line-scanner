from fastapi import FastAPI

from api.routes import router as ev_bets_router

app = FastAPI(
    title="EV Betting Engine API",
    description="Backend for tracking SharpAPI odds and calculating Expected Value",
    version="1.0.0"
)

app.include_router(ev_bets_router)

@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "online", "message": "The EV Betting Engine is running."}
