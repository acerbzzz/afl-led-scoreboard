"""Fetch the official result attached to a final bout, independently of display rotation."""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from urllib.request import urlopen


def method_label(result):
    if isinstance(result, str):
        return result.strip()
    if not isinstance(result, dict):
        return ""
    return str(result.get("displayName") or result.get("shortDisplayName") or result.get("name") or result.get("description") or method_label(result.get("method")) or method_label(result.get("type")) or "").strip()


def card_methods(event):
    url = "https://site.web.api.espn.com/apis/common/v3/sports/mma/ufc/fightcenter/" + event
    with urlopen(url, timeout=5) as response:
        cards = json.load(response).get("cards") or {}
    methods = {}
    for card in cards.values():
        for fight in card.get("competitions", []):
            status = fight.get("status") or {}
            method = method_label(status.get("result")) or method_label(fight.get("method")) or method_label(fight.get("result"))
            if method:
                methods[str(fight.get("id"))] = method
    return methods


class ResultFeed:
    def __init__(self):
        self.worker = ThreadPoolExecutor(max_workers=2)
        self.pending = {}
        self.labels = {}
        self.retry = {}
        self.cards = {}
        self.card_retry = {}

    @staticmethod
    def lookup(key):
        event, bout = key
        url = ("https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/"
               "events/{}/competitions/{}/status").format(event, bout)
        with urlopen(url, timeout=5) as response:
            return method_label(json.load(response).get("result"))

    def update(self, card):
        for fight in card:
            key = fight.key
            if fight.state != "post" or not all(part.isdigit() for part in key) or len(key) != 2:
                continue
            if fight.method:
                continue
            event = key[0]
            future = self.cards.get(event)
            if future and future.done():
                try:
                    for bout, label in future.result().items():
                        self.labels[(event, bout)] = label
                except (OSError, ValueError, AttributeError) as exc:
                    logging.debug("Card lookup failed: %s", exc)
                del self.cards[event]
                self.card_retry[event] = monotonic() + 90
            if key not in self.labels and event not in self.cards and monotonic() >= self.card_retry.get(event, 0):
                self.cards[event] = self.worker.submit(card_methods, event)
            if key in self.pending and self.pending[key].done():
                try:
                    label = self.pending[key].result()
                    if label:
                        self.labels[key] = label
                except (ValueError, OSError) as exc:
                    logging.debug("Result lookup failed: %s", exc)
                del self.pending[key]
                self.retry[key] = monotonic() + 60
            fight.method = self.labels.get(key, "")
            if not fight.method and key not in self.pending and monotonic() >= self.retry.get(key, 0):
                self.pending[key] = self.worker.submit(self.lookup, key)
