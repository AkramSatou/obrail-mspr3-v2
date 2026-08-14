import csv
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://api.trello.com/1"
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "project" / "trello-board.csv"


def trello_request(method, path, params=None):
    key = os.environ.get("TRELLO_KEY")
    token = os.environ.get("TRELLO_TOKEN")
    if not key or not token:
        raise RuntimeError("Missing TRELLO_KEY or TRELLO_TOKEN")

    payload = {"key": key, "token": token}
    if params:
        payload.update(params)

    data = urlencode(payload).encode("utf-8")
    request = Request(f"{API_BASE}{path}", data=data if method != "GET" else None, method=method)
    if method == "GET":
        request.full_url = f"{API_BASE}{path}?{urlencode(payload)}"
    with urlopen(request, timeout=30) as response:
        import json

        return json.loads(response.read().decode("utf-8"))


def create_board():
    board = trello_request(
        "POST",
        "/boards/",
        {
            "name": "ObRail MSPR 3",
            "desc": "Pilotage du projet MSPR 3 : industrialisation ObRail, Docker, CI/CD, tests, monitoring et documentation.",
            "defaultLists": "false",
        },
    )

    list_names = ["Backlog", "A faire", "En cours", "Review", "Termine", "Bloque"]
    lists = {}
    for position, name in enumerate(list_names, start=1):
        lists[name] = trello_request(
            "POST",
            f"/boards/{board['id']}/lists",
            {"name": name, "pos": str(position)},
        )

    with CSV_PATH.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            list_id = lists[row["List"]]["id"]
            trello_request(
                "POST",
                "/cards",
                {
                    "idList": list_id,
                    "name": row["Card"],
                    "desc": f"{row['Description']}\n\nLabel: {row['Labels']}",
                },
            )

    return board


if __name__ == "__main__":
    try:
        created = create_board()
    except Exception as exc:
        print(f"Erreur création Trello: {exc}", file=sys.stderr)
        sys.exit(1)

    print(created["url"])

