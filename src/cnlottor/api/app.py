from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from cnlottor.analysis_engine import AssociationRuleAnalyzer, GenericCopulaGenerator, RollingBacktester
from cnlottor.analysis_engine.service import AnalysisService
from cnlottor.core import DEFAULT_REGISTRY, SQLiteDrawStore
from cnlottor.data_engine import DataSyncService, LotteryProvider, build_default_provider
from cnlottor.model_engine import TorchModelService, TrainConfig, TorchUnavailableError


class TrainRequest(BaseModel):
    window_size: int = Field(default=12, ge=1)
    epochs: int = Field(default=3, ge=1, le=500)
    hidden_size: int = Field(default=32, ge=4, le=1024)
    learning_rate: float = Field(default=1e-3, gt=0)


def create_app(
    database: str | Path | None = None,
    artifacts_root: str | Path | None = None,
    provider: LotteryProvider | None = None,
) -> FastAPI:
    db = Path(database or os.getenv("CNLOTTOR_DATABASE", "data/cnlottor.db"))
    models = Path(artifacts_root or os.getenv("CNLOTTOR_MODELS", "artifacts/models"))
    store = SQLiteDrawStore(db)
    model_service = TorchModelService(models)
    data_provider = provider or build_default_provider()
    application = FastAPI(title="CNlottor API", version="0.4.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health")
    def health():
        return {"status": "ok", "version": "0.4.0", "database": str(db)}

    @application.get("/lotteries")
    def lotteries():
        return [
            {
                "code": spec.code,
                "name": spec.name,
                "pools": [asdict(pool) for pool in spec.pools],
            }
            for spec in DEFAULT_REGISTRY.all()
        ]

    @application.get("/status/{lottery_code}")
    def status(lottery_code: str):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        checkpoint = models / spec.code / "latest.pt"
        return {
            "lottery_code": spec.code,
            "lottery_name": spec.name,
            "draw_count": len(history),
            "latest_issue": history[-1].issue if history else None,
            "model_ready": checkpoint.exists(),
            "checkpoint": str(checkpoint),
        }

    @application.get("/draws/{lottery_code}")
    def draws(lottery_code: str, limit: int = Query(default=100, ge=1, le=5000)):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        return [
            asdict(draw)
            for draw in store.load_draws(spec.code, limit=limit, ascending=False)
        ]

    @application.post("/sync/{lottery_code}")
    def sync(
        lottery_code: str,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ):
        try:
            report = DataSyncService(store, data_provider).sync(
                lottery_code,
                start_issue=start_issue,
                end_issue=end_issue,
            )
            return {"success": True, **asdict(report)}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @application.get("/analysis/{lottery_code}")
    def analysis(lottery_code: str, strategy: str = "frequency"):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        if not history:
            raise HTTPException(status_code=404, detail="no draws stored")
        try:
            if strategy == "rules":
                result = AssociationRuleAnalyzer().analyze(spec, history)
            elif strategy == "copula":
                result = GenericCopulaGenerator().analyze(spec, history)
            else:
                result = AnalysisService().run(strategy, spec, history)
            return asdict(result)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.post("/train/{lottery_code}")
    def train(lottery_code: str, request: TrainRequest):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        try:
            report = model_service.train(
                spec,
                history,
                TrainConfig(
                    window_size=request.window_size,
                    epochs=request.epochs,
                    hidden_size=request.hidden_size,
                    learning_rate=request.learning_rate,
                ),
            )
            return asdict(report)
        except TorchUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.get("/predict/{lottery_code}")
    def predict(lottery_code: str):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        try:
            return asdict(model_service.predict(spec, history))
        except TorchUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="model checkpoint not found") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.get("/backtest/{lottery_code}")
    def backtest(lottery_code: str, window: int = Query(default=12, ge=5)):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        try:
            return asdict(RollingBacktester().run(spec, history, window=window))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return application


app = create_app()
