# -*- coding: utf-8 -*-
"""每日盤後抓收盤資料，依「連續下跌」定義計算各股最大跌幅與目前回檔。

連續下跌定義（使用者提供）：
- 從段內高點開始下跌，只要沒出現「反彈」就屬同一段連續下跌。
- 反彈 = 下跌途中上漲超過（段內高點 + 段內低點）/ 2 的中點（盤中碰到就算）。
- 反彈成立後該段結束歸零，之後以反彈後的新高點重新起算下一段。
- 高低點皆用影線（盤中極值），目前回檔用最新收盤價計算。
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

GROUPS = [
    {"name": "1. 半導體", "subs": [
        {"name": "運算晶片", "tickers": ["NVDA", "AMD", "INTC"]},
        {"name": "網通與連接晶片", "tickers": ["AVGO", "QCOM", "MRVL", "CRDO", "RMBS"]},
        {"name": "功率與車用", "tickers": ["ON"]},
        {"name": "代工、設備與材料", "tickers": ["TSM", "ASML", "AXTI"]},
        {"name": "記憶體", "tickers": ["MU"]},
        {"name": "EDA", "tickers": ["CDNS", "SNPS"]},
    ]},
    {"name": "2. 資料中心與AI基建", "subs": [
        {"name": "伺服器與算力雲", "tickers": ["SMCI", "DELL", "CRWV", "APLD", "NBIS"]},
        {"name": "電力與散熱", "tickers": ["VRT", "ETN", "FIX"]},
        {"name": "網通與光通訊", "tickers": ["ANET", "CIEN", "AAOI"]},
    ]},
    {"name": "3. 軟體、雲端與資安", "subs": [
        {"name": "資安", "tickers": ["PANW", "CRWD", "ZS"]},
        {"name": "企業SaaS", "tickers": ["NOW", "CRM", "ORCL", "HUBS", "DDOG"]},
        {"name": "AI數據", "tickers": ["PLTR"]},
    ]},
    {"name": "4. 科技巨頭與網路", "subs": [
        {"name": "科技巨頭", "tickers": ["GOOGL", "GOOG", "AAPL", "META", "NFLX", "BABA"]},
    ]},
    {"name": "5. 醫藥與生技", "subs": [
        {"name": "基因編輯與細胞治療", "tickers": ["CRSP", "EDIT", "NTLA", "BEAM", "ALLO", "IBRX"]},
        {"name": "減重與代謝", "tickers": ["LLY", "NVO", "VKTX", "RYTM"]},
        {"name": "其他製藥", "tickers": ["VRTX", "ARQT"]},
    ]},
    {"name": "6. 能源與電網", "subs": [
        {"name": "核能與鈾", "tickers": ["OKLO", "SMR", "CCJ", "LEU"]},
        {"name": "發電與電網工程", "tickers": ["GEV", "PWR", "BEPC"]},
    ]},
    {"name": "7. AI實體機器人", "subs": [
        {"name": "實體AI與感測", "tickers": ["TSLA", "SERV", "AEVA"]},
    ]},
    {"name": "8. 航太與國防", "subs": [
        {"name": "太空與衛星", "tickers": ["RKLB", "ASTS"]},
        {"name": "軍工與國防IT", "tickers": ["NOC", "CACI"]},
    ]},
    {"name": "9. 金融、私募與加密", "subs": [
        {"name": "加密相關", "tickers": ["COIN", "MSTR", "HOOD"]},
        {"name": "私募與另類資產", "tickers": ["BX", "ARES", "DXYZ"]},
    ]},
    {"name": "10. 工業、水資源與原物料", "subs": [
        {"name": "水資源", "tickers": ["XYL", "PNR"]},
        {"name": "稀土", "tickers": ["MP"]},
    ]},
]

def fetch_daily(symbol: str):
    """從 Yahoo Finance 抓兩年日線 OHLC，回傳 [{date, high, low, close}, ...] 由舊到新。

    盤中進行中的 K 棒欄位可能是 None，直接略過。
    """
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?range=2y&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    r = data["chart"]["result"][0]
    ts = r["timestamp"]
    q = r["indicators"]["quote"][0]

    # Yahoo 有時最後一根（最新交易日）的 close 是 None，
    # 但 meta.regularMarketPrice 已是正式收盤價 → 用它補上
    meta = r.get("meta", {})
    meta_price = meta.get("regularMarketPrice")
    meta_date = None
    if meta.get("regularMarketTime"):
        meta_date = datetime.fromtimestamp(
            meta["regularMarketTime"], timezone.utc).strftime("%Y-%m-%d")

    bars = []
    for i in range(len(ts)):
        h, lo, c = q["high"][i], q["low"][i], q["close"][i]
        date = datetime.fromtimestamp(ts[i], timezone.utc).strftime("%Y-%m-%d")
        if c is None and h is not None and lo is not None \
                and meta_price is not None and date == meta_date:
            c = meta_price
        if h is None or lo is None or c is None:
            continue
        bars.append({"date": date, "high": h, "low": lo, "close": c})
    return bars


def compute_drawdown(bars):
    """逐日狀態機：回傳 (peak, peak_date, seg_low, low_date, maxdd%, cur%)。"""
    if not bars:
        return None
    peak = bars[0]["high"]
    peak_date = bars[0]["date"]
    seg_low = bars[0]["low"]
    low_date = bars[0]["date"]

    for b in bars[1:]:
        if b["high"] >= peak:
            # 創段內新高：高點上移，段內低點重設
            peak, peak_date = b["high"], b["date"]
            seg_low, low_date = b["low"], b["date"]
            continue
        mid = (peak + seg_low) / 2.0
        if seg_low < peak and b["high"] >= mid:
            # 反彈成立（盤中碰到中點就算）：本段結束，從反彈高點重新起算
            peak, peak_date = b["high"], b["date"]
            seg_low, low_date = b["low"], b["date"]
            continue
        if b["low"] < seg_low:
            seg_low, low_date = b["low"], b["date"]

    last = bars[-1]
    maxdd = (seg_low - peak) / peak * 100.0
    cur = min((last["close"] - peak) / peak * 100.0, 0.0)
    chg = ((last["close"] - bars[-2]["close"]) / bars[-2]["close"] * 100.0
           if len(bars) >= 2 else 0.0)
    return {
        "price": round(last["close"], 2),
        "chg": round(chg, 2),
        "date": last["date"],
        "peak": round(peak, 2),
        "peak_date": peak_date,
        "low": round(seg_low, 2),
        "low_date": low_date,
        "maxdd": round(maxdd, 2),
        "cur": round(cur, 2),
    }


def main():
    all_tickers = [t for g in GROUPS for s in g["subs"] for t in s["tickers"]]
    result, failed = {}, []
    for i, sym in enumerate(all_tickers):
        for attempt in range(3):
            try:
                bars = fetch_daily(sym)
                if len(bars) < 30:
                    raise ValueError(f"only {len(bars)} bars")
                result[sym] = compute_drawdown(bars)
                print(f"[{i+1}/{len(all_tickers)}] {sym}: "
                      f"price={result[sym]['price']} maxdd={result[sym]['maxdd']}% "
                      f"cur={result[sym]['cur']}%")
                break
            except Exception as e:
                if attempt == 2:
                    failed.append(sym)
                    print(f"[{i+1}/{len(all_tickers)}] {sym}: FAILED ({e})")
                else:
                    time.sleep(2)
        time.sleep(0.4)

    # 那斯達克綜合指數（頁面左上角固定顯示）
    index_info = None
    try:
        bars = fetch_daily("^IXIC")
        last, prev = bars[-1], bars[-2]
        index_info = {
            "symbol": "IXIC",
            "price": round(last["close"], 2),
            "date": last["date"],
            "chg_pts": round(last["close"] - prev["close"], 2),
            "chg": round((last["close"] - prev["close"]) / prev["close"] * 100.0, 2),
        }
        print(f"IXIC: {index_info['price']} "
              f"{index_info['chg_pts']:+} ({index_info['chg']:+}%)")
    except Exception as e:
        print(f"IXIC: FAILED ({e})")

    out = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "index": index_info,
        "groups": GROUPS,
        "data": result,
        "failed": failed,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\ndone: {len(result)} ok, {len(failed)} failed -> data.json")


if __name__ == "__main__":
    main()
