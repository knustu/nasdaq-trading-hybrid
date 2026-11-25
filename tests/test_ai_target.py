import pandas as pd

from app.ai_analyzer import AIAnalyzer


def test_future_unknown_rows_are_removed_and_stop_has_priority():
    frame = pd.DataFrame(
        {
            "open": [100, 100, 100, 100, 100],
            "high": [100, 103, 100, 103, 100],
            "low": [100, 97, 100, 100, 100],
            "close": [100, 100, 100, 100, 100],
            "volume": [1, 1, 1, 1, 1],
            "rsi": [50] * 5,
        }
    )
    labeled = AIAnalyzer.make_outcome_target(
        frame,
        forward_bars=2,
        target_return=0.02,
        stop_loss_rate=0.02,
    )
    assert len(labeled) == 3
    assert labeled.iloc[0]["target"] == 0  # 같은 미래 봉에서 목표/손절 동시: 손절 우선
    assert labeled.iloc[1]["target"] == 1  # 다음 구간에서는 목표가 먼저 도달
