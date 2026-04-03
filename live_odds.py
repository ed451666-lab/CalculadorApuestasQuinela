from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from datetime import datetime
from itertools import combinations
from typing import Any

import requests
import websocket


TELETRAK_BASE_URL = "https://apuestas.teletrak.cl"
TELETRAK_WS_URL = "wss://apuestas.teletrak.cl/api/falcon/ws/websocket"
LIVE_LANGUAGE_TAG = "es-PR"
DEFAULT_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    ),
    "accept-language": "es-CL,es;q=0.9,en;q=0.8",
    "x-requested-with": "XMLHttpRequest",
    "x-g440-tenant": "chile",
    "x-g440-language": LIVE_LANGUAGE_TAG,
    "x-g440-platform": "web",
    "referer": f"{TELETRAK_BASE_URL}/",
    "origin": TELETRAK_BASE_URL,
}
TRACK_ALIASES = {
    "chs": ("club hipico de santiago",),
    "hch": ("hipodromo chile",),
    "vsc": ("valparaiso sporting", "valparaiso sporting club"),
    "chc": ("club hipico de concepcion",),
}
UNAVAILABLE_MESSAGE = "Probables Quinela aún no disponibles en Teletrak"


def normalize_track_code(track_code: str) -> str:
    return (track_code or "").strip().lower()


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)

    text = str(value).strip().replace(" ", "")
    if not text or text.lower() in {"-", "--", "null", "none"}:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None

    try:
        return round(float(match.group(0)), 2)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def normalize_combo_key(first: Any, second: Any) -> str | None:
    a = parse_int(first)
    b = parse_int(second)
    if a is None or b is None or a == b:
        return None
    low, high = sorted((a, b))
    return f"{low}-{high}"


def build_quinela_box_combinations(selected_numbers: list[Any]) -> list[tuple[int, int]]:
    cleaned: list[int] = []
    seen: set[int] = set()
    for value in selected_numbers or []:
        number = parse_int(value)
        if number is None or number <= 0 or number in seen:
            continue
        seen.add(number)
        cleaned.append(number)
    return list(combinations(cleaned, 2))


def filter_selected_probables(probables: dict[str, float], selected_numbers: list[Any] | None) -> dict[str, float]:
    if not selected_numbers:
        return dict(sorted(probables.items(), key=lambda item: tuple(int(part) for part in item[0].split("-"))))
    valid_keys = {
        normalize_combo_key(first, second)
        for first, second in build_quinela_box_combinations(selected_numbers)
    }
    filtered = {
        key: value
        for key, value in probables.items()
        if key in valid_keys
    }
    return dict(sorted(filtered.items(), key=lambda item: tuple(int(part) for part in item[0].split("-"))))


def _walk_dicts(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            found.append(node)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(payload)
    return found


def _parse_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else None


def _extract_combo_from_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"(\d+)\D+(\d+)", text)
    if not match:
        return None
    return normalize_combo_key(match.group(1), match.group(2))


def _is_quinella_label(value: Any) -> bool:
    normalized = normalize_text(value)
    return any(token in normalized for token in ("quinela", "quinella", "qui"))


def parse_cross_runner_odds(payload: dict[str, Any]) -> dict[str, float]:
    probables: dict[str, float] = {}

    for node in _walk_dicts(payload):
        cross_runner_odds = node.get("crossRunnerOdds")
        markets = cross_runner_odds if isinstance(cross_runner_odds, list) else None
        if not markets and {"betType", "payouts"}.issubset(node.keys()):
            markets = [node]
        if not markets:
            continue

        for market in markets:
            bet_type = market.get("betType", {}) if isinstance(market, dict) else {}
            labels = [
                bet_type.get("logicalId"),
                bet_type.get("code"),
                bet_type.get("name"),
                market.get("logicalId"),
                market.get("code"),
                market.get("name"),
            ]
            if not any(_is_quinella_label(label) for label in labels):
                continue

            payouts = market.get("payouts", [])
            if not isinstance(payouts, list):
                continue

            for row in payouts:
                row_number = parse_int(row.get("programNumber") or row.get("bettingInterest") or row.get("number"))
                if row_number is None:
                    continue

                payout_values = row.get("payout")
                if isinstance(payout_values, list):
                    for index, payout in enumerate(payout_values, start=1):
                        combo_key = normalize_combo_key(row_number, index)
                        dividend = parse_float(payout)
                        if combo_key and dividend is not None and dividend > 0:
                            probables[combo_key] = dividend
                    continue

                combo_key = normalize_combo_key(
                    row.get("runnerNumberA") or row.get("firstRunner") or row_number,
                    row.get("runnerNumberB") or row.get("secondRunner"),
                )
                dividend = parse_float(row.get("value") or row.get("payout") or row.get("probable"))
                if combo_key and dividend is not None and dividend > 0:
                    probables[combo_key] = dividend

    return dict(sorted(probables.items(), key=lambda item: tuple(int(part) for part in item[0].split("-"))))


def _walk_probable_nodes(payload: Any) -> dict[str, float]:
    probables: dict[str, float] = {}
    for node in _walk_dicts(payload):
        combo = None
        for key in ("combination", "name", "label", "descripcion", "description"):
            combo = _extract_combo_from_text(node.get(key))
            if combo:
                break
        if not combo:
            combo = normalize_combo_key(node.get("firstRunner"), node.get("secondRunner"))
        if not combo:
            continue
        dividend = None
        for key in ("value", "probable", "payout", "amount", "dividend"):
            dividend = parse_float(node.get(key))
            if dividend is not None:
                break
        if dividend is not None and dividend > 0:
            probables[combo] = dividend
    return dict(sorted(probables.items(), key=lambda item: tuple(int(part) for part in item[0].split("-"))))


def candidate_endpoints(race_id: int | None = None, race_card_id: int | None = None) -> list[str]:
    endpoints: list[str] = []
    if race_id is not None:
        endpoints.extend(
            [
                f"{TELETRAK_BASE_URL}/api/falcon/v2/race/{race_id}/probables",
                f"{TELETRAK_BASE_URL}/api/falcon/v2/race/{race_id}/will-pays",
                f"{TELETRAK_BASE_URL}/api/falcon/v1/race/{race_id}/probables",
                f"{TELETRAK_BASE_URL}/api/falcon/v1/race/{race_id}/will-pays",
                f"{TELETRAK_BASE_URL}/api/falcon/v1/results/raceCard/{race_id}",
            ]
        )
    if race_card_id is not None:
        endpoints.extend(
            [
                f"{TELETRAK_BASE_URL}/api/falcon/v2/raceCard/{race_card_id}/probables",
                f"{TELETRAK_BASE_URL}/api/falcon/v1/raceCard/{race_card_id}/probables",
            ]
        )
    return endpoints


def request_json(url: str, timeout: int = 10) -> Any:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _build_stomp_frame(command: str, headers: dict[str, Any] | None = None, body: str = "") -> str:
    header_lines = []
    for key, value in (headers or {}).items():
        header_lines.append(f"{key}:{value}")
    return f"{command}\n" + "\n".join(header_lines) + f"\n\n{body}\x00"


def _parse_stomp_frames(raw_message: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for chunk in raw_message.split("\x00"):
        if not chunk.strip():
            continue
        parts = chunk.split("\n\n", 1)
        header_blob = parts[0]
        body = parts[1] if len(parts) > 1 else ""
        lines = [line for line in header_blob.splitlines() if line.strip()]
        if not lines:
            continue
        command = lines[0].strip()
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
        frames.append({"command": command, "headers": headers, "body": body})
    return frames


def subscribe_topic_once(destination: str, timeout: int = 8) -> dict[str, Any]:
    ws = websocket.create_connection(
        TELETRAK_WS_URL,
        timeout=timeout,
        header=[
            f"Origin: {TELETRAK_BASE_URL}",
            f"User-Agent: {DEFAULT_HEADERS['user-agent']}",
        ],
    )
    subscribed = False
    deadline = time.time() + timeout

    try:
        ws.send(
            _build_stomp_frame(
                "CONNECT",
                {
                    "accept-version": "1.2",
                    "heart-beat": "0,0",
                },
            )
        )

        while time.time() < deadline:
            raw = ws.recv()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            for frame in _parse_stomp_frames(raw):
                if frame["command"] == "CONNECTED" and not subscribed:
                    ws.send(
                        _build_stomp_frame(
                            "SUBSCRIBE",
                            {
                                "id": f"sub-{int(time.time() * 1000)}",
                                "destination": destination,
                                "ack": "auto",
                            },
                        )
                    )
                    subscribed = True
                    continue

                if frame["command"] != "MESSAGE":
                    continue

                if frame["headers"].get("destination") != destination:
                    continue

                body = frame["body"].strip()
                return json.loads(body) if body else {}

        raise TimeoutError(f"No se recibió respuesta del canal {destination}")
    finally:
        try:
            ws.send(_build_stomp_frame("DISCONNECT", {"receipt": f"close-{int(time.time())}"}))
        except Exception:
            pass
        ws.close()


def track_name_matches(track_code: str, candidate_name: Any) -> bool:
    normalized_name = normalize_text(candidate_name)
    if not normalized_name:
        return False
    aliases = TRACK_ALIASES.get(normalize_track_code(track_code), ())
    return any(alias in normalized_name for alias in aliases)


def resolve_live_race_metadata(track_code: str, race_number: int, meeting_date: str | None = None) -> dict[str, Any] | None:
    payload = subscribe_topic_once(f"/broker/v2.tracks.{LIVE_LANGUAGE_TAG}")
    track_nodes = []

    if isinstance(payload, list):
        track_nodes.extend(node for node in payload if isinstance(node, dict) and isinstance(node.get("raceCards"), list))
    if isinstance(payload, dict) and isinstance(payload.get("tracks"), list):
        track_nodes.extend(node for node in payload["tracks"] if isinstance(node, dict))
    track_nodes.extend(
        node for node in _walk_dicts(payload) if isinstance(node.get("raceCards"), list) and node not in track_nodes
    )

    for track_node in track_nodes:
        race_cards = track_node.get("raceCards", []) or []
        track_candidate_name = track_node.get("name") or track_node.get("trackName")
        if not track_candidate_name and race_cards:
            track_candidate_name = race_cards[0].get("name")

        for race_card in race_cards:
            if not track_name_matches(track_code, track_candidate_name or race_card.get("name")):
                continue
            races = race_card.get("races", []) or []
            next_race = race_card.get("nextRace") or {}
            candidates = [race for race in races if isinstance(race, dict)]
            if isinstance(next_race, dict):
                candidates.append(next_race)

            for race in candidates:
                current_race_number = parse_int(race.get("number") or race.get("raceNumber") or race.get("nro"))
                race_date = _parse_date(race.get("date") or race.get("meetingDate") or race_card.get("date"))
                if current_race_number != int(race_number):
                    continue
                if meeting_date and race_date and meeting_date != race_date:
                    continue
                return {
                    "track_id": normalize_track_code(track_code),
                    "track_name": track_node.get("name") or track_node.get("trackName"),
                    "track_teletrak_id": parse_int(track_node.get("id")),
                    "race_card_id": parse_int(race_card.get("id")),
                    "race_card_name": race_card.get("name"),
                    "meeting_date": race_date or meeting_date,
                    "race_id": parse_int(race.get("id")),
                    "race_number": current_race_number,
                    "race_status": race.get("status"),
                    "next_open_race_id": parse_int(next_race.get("id")) if isinstance(next_race, dict) else None,
                    "next_open_race_number": parse_int(next_race.get("number") or next_race.get("raceNumber")) if isinstance(next_race, dict) else None,
                    "resolution_source": "teletrak_broker_tracks",
                }
    return None


def fetch_live_runners_snapshot(race_id: int) -> dict[str, Any]:
    return subscribe_topic_once(f"/broker/v2.race.{int(race_id)}.{LIVE_LANGUAGE_TAG}.runners")


def fetch_live_quinella_probables(
    track_code: str,
    race_number: int,
    meeting_date: str | None = None,
    selected_numbers: list[Any] | None = None,
    race_id: int | None = None,
    race_card_id: int | None = None,
) -> dict[str, Any]:
    attempted_channels: list[dict[str, Any]] = []
    attempted_endpoints: list[dict[str, Any]] = []
    resolution: dict[str, Any] | None = None
    probables: dict[str, float] = {}
    source: str | None = None

    if race_id is None:
        try:
            resolution = resolve_live_race_metadata(track_code, race_number, meeting_date=meeting_date)
            if resolution:
                race_id = resolution.get("race_id")
                race_card_id = race_card_id or resolution.get("race_card_id")
                attempted_channels.append(
                    {
                        "channel": f"/broker/v2.tracks.{LIVE_LANGUAGE_TAG}",
                        "status": "ok",
                        "race_id": race_id,
                        "race_card_id": race_card_id,
                    }
                )
            else:
                attempted_channels.append(
                    {
                        "channel": f"/broker/v2.tracks.{LIVE_LANGUAGE_TAG}",
                        "status": "no_match",
                    }
                )
        except Exception as exc:
            attempted_channels.append(
                {
                    "channel": f"/broker/v2.tracks.{LIVE_LANGUAGE_TAG}",
                    "status": "error",
                    "detail": str(exc),
                }
            )

    if race_id is not None:
        try:
            snapshot = fetch_live_runners_snapshot(int(race_id))
            broker_probables = parse_cross_runner_odds(snapshot)
            if not broker_probables:
                broker_probables = _walk_probable_nodes(snapshot)
            broker_probables = filter_selected_probables(broker_probables, selected_numbers)
            attempted_channels.append(
                {
                    "channel": f"/broker/v2.race.{race_id}.{LIVE_LANGUAGE_TAG}.runners",
                    "status": "ok",
                    "matches": len(broker_probables),
                }
            )
            if broker_probables:
                probables = broker_probables
                source = "teletrak_broker"
        except Exception as exc:
            attempted_channels.append(
                {
                    "channel": f"/broker/v2.race.{race_id}.{LIVE_LANGUAGE_TAG}.runners",
                    "status": "error",
                    "detail": str(exc),
                }
            )

    if not probables:
        for url in candidate_endpoints(race_id=race_id, race_card_id=race_card_id):
            try:
                payload = request_json(url)
                rest_probables = parse_cross_runner_odds(payload if isinstance(payload, dict) else {})
                if not rest_probables:
                    rest_probables = _walk_probable_nodes(payload)
                rest_probables = filter_selected_probables(rest_probables, selected_numbers)
                attempted_endpoints.append({"endpoint": url, "status": "ok", "matches": len(rest_probables)})
                if rest_probables:
                    probables = rest_probables
                    source = "teletrak_rest"
                    break
            except Exception as exc:
                attempted_endpoints.append({"endpoint": url, "status": "error", "detail": str(exc)})

    return {
        "track_code": normalize_track_code(track_code),
        "meeting_date": meeting_date,
        "race_number": int(race_number),
        "race_id": race_id,
        "race_card_id": race_card_id,
        "resolution": resolution,
        "source": source,
        "simulated": False,
        "available": bool(probables),
        "message": None if probables else UNAVAILABLE_MESSAGE,
        "attempted_channels": attempted_channels,
        "attempted_endpoints": attempted_endpoints,
        "probables": probables,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta manual de probables Quinela en vivo desde Teletrak")
    parser.add_argument("--track", required=True, help="Hipódromo: hch, chs, vsc o chc")
    parser.add_argument("--race", required=True, type=int, help="Número de carrera")
    parser.add_argument("--date", default=None, help="Fecha de reunión YYYY-MM-DD")
    parser.add_argument("--selected", nargs="*", type=int, default=[], help="Seis números de caballo")
    args = parser.parse_args()

    result = fetch_live_quinella_probables(
        args.track,
        args.race,
        meeting_date=args.date,
        selected_numbers=args.selected,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


