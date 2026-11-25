from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import xgboost as xgb
import yfinance as yf
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

from .indicators import FEATURE_COLUMNS, add_features

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelMetadata:
    strategy_type: str
    interval: str
    period: str
    forward_bars: int
    target_return: float
    stop_loss_rate: float
    live_threshold: float
    feature_columns: list[str]
    trained_at_utc: str
    training_tickers: list[str]
    model_version: int = 2


class AIAnalyzer:
    def __init__(
        self,
        model_path: str | Path,
        expected_interval: str,
        strategy_type: str,
        *,
        require_metadata: bool = True,
    ):
        self.model_path = Path(model_path)
        self.metadata_path = self.model_path.with_suffix(".meta.json")
        self.expected_interval = expected_interval
        self.strategy_type = strategy_type.upper()
        self.require_metadata = require_metadata
        self.feature_columns = list(FEATURE_COLUMNS)
        self.model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.04,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=3,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
        )
        self.metadata: ModelMetadata | None = None
        self.is_model_loaded = False
        self.load()

    def load(self) -> bool:
        if not self.model_path.exists():
            logger.warning("AI 모델 없음: %s", self.model_path)
            return False
        if self.require_metadata and not self.metadata_path.exists():
            logger.error("모델 메타데이터가 없어 안전상 로드를 거부합니다: %s", self.metadata_path)
            return False
        try:
            if self.metadata_path.exists():
                raw = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                self.metadata = ModelMetadata(**raw)
                if self.metadata.interval != self.expected_interval:
                    raise ValueError(
                        f"모델 봉 간격 {self.metadata.interval}과 요청 봉 간격 {self.expected_interval}이 다릅니다."
                    )
                if self.metadata.strategy_type.upper() != self.strategy_type:
                    raise ValueError("모델 전략 종류가 현재 전략과 다릅니다.")
                self.feature_columns = list(self.metadata.feature_columns)
            self.model.load_model(self.model_path)
            self.is_model_loaded = True
            logger.info("AI 모델 로드 성공: %s", self.model_path)
            return True
        except Exception as exc:
            logger.exception("AI 모델 로드 실패: %s", exc)
            self.is_model_loaded = False
            return False

    def predict_probability(self, df: pd.DataFrame, interval: str) -> float | None:
        if interval != self.expected_interval:
            raise ValueError(
                f"{self.strategy_type} 모델은 {self.expected_interval} 데이터만 허용합니다. 입력: {interval}"
            )
        if not self.is_model_loaded:
            return None
        features = add_features(df)
        if features.empty:
            return None
        missing = [column for column in self.feature_columns if column not in features.columns]
        if missing:
            raise ValueError(f"모델 피처 누락: {missing}")
        latest = features.iloc[[-1]][self.feature_columns]
        probability = float(self.model.predict_proba(latest)[0, 1])
        return max(0.0, min(1.0, probability))

    @staticmethod
    def make_outcome_target(
        features: pd.DataFrame,
        *,
        forward_bars: int,
        target_return: float,
        stop_loss_rate: float,
    ) -> pd.DataFrame:
        """실제 전략과 맞도록 목표가/손절가 중 먼저 도달한 결과를 라벨로 만든다.

        같은 봉에서 목표와 손절이 모두 닿으면 보수적으로 손절이 먼저 발생한 것으로 처리한다.
        미래 구간이 부족한 마지막 행은 학습 데이터에서 제거한다.
        """
        if forward_bars <= 0:
            raise ValueError("forward_bars는 1 이상이어야 합니다.")
        rows: list[tuple[int, int]] = []
        closes = features["close"].to_numpy(dtype=float)
        highs = features["high"].to_numpy(dtype=float)
        lows = features["low"].to_numpy(dtype=float)
        last_valid = len(features) - forward_bars
        for index in range(max(0, last_valid)):
            entry = closes[index]
            target = entry * (1.0 + target_return)
            stop = entry * (1.0 - stop_loss_rate)
            label = 0
            for future_index in range(index + 1, index + forward_bars + 1):
                hit_stop = lows[future_index] <= stop
                hit_target = highs[future_index] >= target
                if hit_stop:
                    label = 0
                    break
                if hit_target:
                    label = 1
                    break
            rows.append((index, label))

        if not rows:
            return pd.DataFrame()
        valid_indices = [index for index, _ in rows]
        labeled = features.iloc[valid_indices].copy()
        labeled["target"] = [label for _, label in rows]
        return labeled


    @staticmethod
    def _download_training_data(ticker: str, *, period: str, interval: str) -> pd.DataFrame:
        """Yahoo의 1분봉 요청 제한을 피하기 위해 6일 단위로 나누어 수집한다."""
        if interval != "1m":
            return yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                prepost=False,
                threads=False,
            )

        end = datetime.now(timezone.utc)
        start_limit = end - timedelta(days=28)
        chunks: list[pd.DataFrame] = []
        chunk_end = end
        while chunk_end > start_limit:
            chunk_start = max(start_limit, chunk_end - timedelta(days=6))
            part = yf.download(
                ticker,
                start=chunk_start,
                end=chunk_end,
                interval=interval,
                progress=False,
                auto_adjust=False,
                prepost=False,
                threads=False,
            )
            if part is not None and not part.empty:
                chunks.append(part)
            chunk_end = chunk_start
        if not chunks:
            return pd.DataFrame()
        combined = pd.concat(chunks).sort_index()
        return combined[~combined.index.duplicated(keep="last")]

    def train(
        self,
        *,
        tickers: Iterable[str],
        period: str,
        interval: str,
        forward_bars: int,
        target_return: float,
        stop_loss_rate: float,
        live_threshold: float,
    ) -> dict[str, float | list[list[int]]]:
        if interval != self.expected_interval:
            raise ValueError("학습 interval과 분석기 expected_interval이 다릅니다.")
        ticker_list = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
        datasets: list[pd.DataFrame] = []
        for ticker in ticker_list:
            logger.info("학습 데이터 다운로드: %s", ticker)
            try:
                raw = self._download_training_data(ticker, period=period, interval=interval)
                features = add_features(raw)
                if features.empty:
                    continue
                labeled = self.make_outcome_target(
                    features,
                    forward_bars=forward_bars,
                    target_return=target_return,
                    stop_loss_rate=stop_loss_rate,
                )
                if not labeled.empty:
                    labeled["ticker"] = ticker
                    datasets.append(labeled)
            except Exception as exc:
                logger.error("%s 학습 데이터 처리 실패: %s", ticker, exc)

        if not datasets:
            raise RuntimeError("학습 가능한 데이터가 없습니다.")

        combined = pd.concat(datasets).sort_index(kind="stable")
        combined = combined.dropna(subset=self.feature_columns + ["target"])
        split_index = int(len(combined) * 0.8)
        if split_index < 100 or len(combined) - split_index < 20:
            raise RuntimeError("학습/검증 데이터가 부족합니다.")

        train_df = combined.iloc[:split_index]
        test_df = combined.iloc[split_index:]
        if train_df["target"].nunique() < 2:
            raise RuntimeError("학습 데이터에 성공/실패 두 클래스가 모두 필요합니다.")
        X_train = train_df[self.feature_columns]
        y_train = train_df["target"].astype(int)
        X_test = test_df[self.feature_columns]
        y_test = test_df["target"].astype(int)

        positives = int(y_train.sum())
        negatives = int(len(y_train) - positives)
        scale_pos_weight = negatives / positives if positives else 1.0
        self.model.set_params(scale_pos_weight=scale_pos_weight)
        self.model.fit(X_train, y_train)

        probabilities = self.model.predict_proba(X_test)[:, 1]
        predictions = (probabilities >= live_threshold).astype(int)
        metrics: dict[str, float | list[list[int]]] = {
            "accuracy": float(accuracy_score(y_test, predictions)),
            "precision": float(precision_score(y_test, predictions, zero_division=0)),
            "recall": float(recall_score(y_test, predictions, zero_division=0)),
            "f1": float(f1_score(y_test, predictions, zero_division=0)),
            "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
        }

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save_model(self.model_path)
        metadata = ModelMetadata(
            strategy_type=self.strategy_type,
            interval=interval,
            period=period,
            forward_bars=forward_bars,
            target_return=target_return,
            stop_loss_rate=stop_loss_rate,
            live_threshold=live_threshold,
            feature_columns=self.feature_columns,
            trained_at_utc=datetime.now(timezone.utc).isoformat(),
            training_tickers=ticker_list,
        )
        self.metadata_path.write_text(
            json.dumps(asdict(metadata), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.metadata = metadata
        self.is_model_loaded = True
        logger.info("모델 저장 완료: %s", self.model_path)
        logger.info("검증 지표: %s", metrics)
        return metrics
