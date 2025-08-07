#!/usr/bin/env python3
"""
CoinChrono — подсчет средней продолжительности удержания монет и токенов на Ethereum-адресе.
"""

import os
import sys
import time
import argparse
from datetime import datetime, timezone
import requests
from dateutil import parser as dateparser
from tabulate import tabulate

ETHERSCAN_API_URL = "https://api.etherscan.io/api"

def fetch_eth_balance_events(address, api_key):
    """Получает список ETH-транзакций (incoming) для адреса."""
    params = {
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": api_key
    }
    resp = requests.get(ETHERSCAN_API_URL, params=params)
    data = resp.json()
    if data["status"] != "1":
        print("Ошибка при запросе ETH-транзакций:", data.get("message", resp.text), file=sys.stderr)
        sys.exit(1)
    return data["result"]

def fetch_erc20_events(address, api_key):
    """Получает список всех ERC-20 Transfer-событий для адреса."""
    params = {
        "module": "account",
        "action": "tokentx",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": api_key
    }
    resp = requests.get(ETHERSCAN_API_URL, params=params)
    data = resp.json()
    if data["status"] != "1":
        print("Ошибка при запросе ERC20-событий:", data.get("message", resp.text), file=sys.stderr)
        sys.exit(1)
    return data["result"]

def compute_age(events):
    """
    По списку событий (каждое со свойством 'timeStamp' и 'value'),
    подсчитывает средневзвешенный возраст монет в днях.
    """
    now = datetime.now(timezone.utc)
    total_amount = 0.0
    total_age = 0.0  # сумма amount * age_in_days
    for ev in events:
        ts = datetime.fromtimestamp(int(ev["timeStamp"]), tz=timezone.utc)
        age_days = (now - ts).total_seconds() / 86400.0
        amount = int(ev["value"]) / (10 ** int(ev.get("tokenDecimal", 18)))
        total_amount += amount
        total_age += amount * age_days
    if total_amount == 0:
        return 0.0
    return total_age / total_amount

def main():
    p = argparse.ArgumentParser(description="CoinChrono — оценка среднего времени удержания активов")
    p.add_argument("-a", "--address", required=True, help="Ethereum-адрес для анализа")
    p.add_argument("-k", "--apikey", default=os.getenv("ETHERSCAN_API_KEY"),
                   help="Etherscan API Key (или через ETHERSCAN_API_KEY)")
    args = p.parse_args()
    if not args.apikey:
        print("API key не задан! Установите переменную окружения ETHERSCAN_API_KEY или передайте ключ через -k.", file=sys.stderr)
        sys.exit(1)

    print(f"\n[+] Анализ адреса: {args.address}\n")

    # ETH
    eth_txs = fetch_eth_balance_events(args.address, args.apikey)
    # оставить только входящие txs, где to == address
    eth_in = [tx for tx in eth_txs if tx["to"].lower() == args.address.lower()]
    eth_age = compute_age(eth_in)

    # ERC-20
    token_txs = fetch_erc20_events(args.address, args.apikey)
    # сгруппировать по токену
    by_token = {}
    for tx in token_txs:
        if tx["to"].lower() != args.address.lower():
            continue
        key = (tx["contractAddress"], tx["tokenSymbol"], tx["tokenDecimal"])
        by_token.setdefault(key, []).append(tx)

    rows = [["Asset", "Balance", "Average Hold (days)"]]
    rows.append(["ETH", f"{sum(int(tx['value']) for tx in eth_in)/(10**18):.6f}", f"{eth_age:.1f}"])

    for (addr, symbol, dec), evs in by_token.items():
        avg_age = compute_age(evs)
        balance = sum(int(tx['value']) for tx in evs) / (10**int(dec))
        rows.append([symbol, f"{balance:.6f}", f"{avg_age:.1f}"])

    print(tabulate(rows, headers="firstrow", tablefmt="github"))

if __name__ == "__main__":
    main()
