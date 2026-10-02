from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from obloha.core.weather import (
    OPEN_METEO,
    Forecast,
    HourWeather,
    best_window,
    cloud_factor,
    darkness_factor,
    fetch_forecast,
    moon_factor,
    night_scores,
    parse_open_meteo,
    score_word,
)

NOW = datetime(2026, 10, 1, 17, 0, tzinfo=UTC)


def _payload(cloud=10):
    times = [(NOW.replace(hour=0) + timedelta(hours=h)) for h in range(72)]
    n = len(times)
    return {
        "hourly": {
            "time": [t.strftime("%Y-%m-%dT%H:%M") for t in times],
            "cloud_cover": [cloud] * n,
            "cloud_cover_low": [cloud] * n,
            "cloud_cover_mid": [0] * n,
            "cloud_cover_high": [None] * n,
            "visibility": [24000] * n,
        }
    }


def test_parse():
    f = parse_open_meteo(_payload(), NOW)
    assert len(f.hours) == 72
    h = f.at(NOW + timedelta(minutes=25))
    assert h is not None and h.cloud == 10 and h.high == 0 and h.visibility_km == 24


@respx.mock
async def test_fetch_success_and_cache(tmp_path, prague):
    route = respx.get(OPEN_METEO).mock(return_value=httpx.Response(200, json=_payload()))
    res = await fetch_forecast(tmp_path, prague, now=NOW)
    assert res.forecast is not None and res.status == "předpověď Open-Meteo"
    assert route.called
    res2 = await fetch_forecast(tmp_path, prague, now=NOW + timedelta(minutes=10))
    assert res2.status == "předpověď z mezipaměti"
    assert route.call_count == 1


@respx.mock
async def test_fetch_error_uses_stale_cache(tmp_path, prague):
    respx.get(OPEN_METEO).mock(return_value=httpx.Response(200, json=_payload()))
    await fetch_forecast(tmp_path, prague, now=NOW)
    respx.get(OPEN_METEO).mock(return_value=httpx.Response(500))
    res = await fetch_forecast(tmp_path, prague, now=NOW + timedelta(hours=3))
    assert res.forecast is not None and res.forecast.stale
    assert "starší předpověď" in res.status


@respx.mock
async def test_fetch_timeout_without_cache(tmp_path, prague):
    respx.get(OPEN_METEO).mock(side_effect=httpx.ReadTimeout("slow"))
    res = await fetch_forecast(tmp_path, prague, now=NOW)
    assert res.forecast is None and "není k dispozici" in res.status


async def test_offline(tmp_path, prague):
    res = await fetch_forecast(tmp_path, prague, now=NOW, offline=True)
    assert res.forecast is None and "offline" in res.status


@respx.mock
async def test_offline_with_old_cache(tmp_path, prague):
    respx.get(OPEN_METEO).mock(return_value=httpx.Response(200, json=_payload()))
    await fetch_forecast(tmp_path, prague, now=NOW)
    res = await fetch_forecast(tmp_path, prague, now=NOW + timedelta(hours=5), offline=True)
    assert res.forecast is not None and "offline" in res.status
    res = await fetch_forecast(tmp_path, prague, now=NOW + timedelta(days=3), offline=True)
    assert res.forecast is None


def test_factors():
    assert darkness_factor(0) == 0 and darkness_factor(-20) == 1
    assert 0.15 < darkness_factor(-12) < 1
    assert moon_factor(1.0, -5) == 1.0
    assert moon_factor(1.0, 60) < moon_factor(0.2, 60)
    clear = HourWeather(NOW, 0, 0, 0, 0, 30)
    cloudy = HourWeather(NOW, 100, 100, 50, 50, 30)
    hazy = HourWeather(NOW, 0, 0, 0, 0, 3)
    assert cloud_factor(clear) == 1.0 and cloud_factor(cloudy) == 0.0
    assert cloud_factor(hazy) < 0.5


def test_night_scores_and_window(prague):
    forecast = parse_open_meteo(_payload(cloud=5), NOW)
    start = NOW
    scores = night_scores(start, start + timedelta(hours=14), prague, forecast, 0.7)
    assert len(scores) == 14
    assert scores[0].score < scores[3].score  # 19:00 CEST still twilight
    assert max(s.score for s in scores) > 70
    win = best_window(scores)
    assert win is not None and win[0] < win[1]
    astro = night_scores(start, start + timedelta(hours=14), prague, None, 0.7)
    assert all(s.clouds is None for s in astro)
    cloudy = parse_open_meteo(_payload(cloud=100), NOW)
    bad = night_scores(start, start + timedelta(hours=14), prague, cloudy, 0.7)
    assert max(s.score for s in bad) == 0
    assert best_window(bad) is None


@pytest.mark.parametrize(
    ("score", "word"),
    [(90, "výborné"), (60, "dobré"), (40, "průměrné"), (5, "špatné"), (0, "nelze pozorovat")],
)
def test_score_word(score, word):
    assert score_word(score) == word


def test_forecast_lookup_missing():
    assert Forecast((), NOW).at(NOW) is None
