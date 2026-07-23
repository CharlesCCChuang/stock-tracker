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

# 13 個類股標籤＝大類（同一支股票可掛多個標籤）；子分類為標籤內的細分
GROUPS = [
    {"name": "AI/ML", "subs": [
        {"name": "AI晶片", "tickers": ["NVDA", "AMD", "AVGO", "QCOM", "MRVL"]},
        {"name": "伺服器與算力雲", "tickers": ["SMCI", "DELL", "NBIS", "CRWV", "APLD", "ANET"]},
        {"name": "AI軟體與平台", "tickers": ["GOOGL", "GOOG", "META", "PLTR", "CRWD", "NOW", "CRM"]},
    ]},
    {"name": "光通訊", "subs": [
        {"name": "光通訊晶片與IP", "tickers": ["AVGO", "MRVL", "CRDO", "RMBS"]},
        {"name": "光模組與設備", "tickers": ["AAOI", "CIEN"]},
        {"name": "材料基板", "tickers": ["AXTI"]},
    ]},
    {"name": "加密/金融", "subs": [
        {"name": "加密貨幣", "tickers": ["COIN", "MSTR", "HOOD"]},
        {"name": "私募與另類資產", "tickers": ["BX", "ARES", "DXYZ"]},
    ]},
    {"name": "半導體", "subs": [
        {"name": "運算晶片", "tickers": ["NVDA", "AMD", "INTC"]},
        {"name": "網通與連接晶片", "tickers": ["AVGO", "QCOM", "MRVL", "CRDO", "RMBS"]},
        {"name": "功率與車用", "tickers": ["ON"]},
        {"name": "代工、設備與材料", "tickers": ["TSM", "ASML", "AXTI"]},
        {"name": "記憶體", "tickers": ["MU"]},
        {"name": "EDA", "tickers": ["CDNS", "SNPS"]},
    ]},
    {"name": "國防", "subs": [
        {"name": "軍工與國防IT", "tickers": ["NOC", "CACI"]},
    ]},
    {"name": "基因編輯", "subs": [
        {"name": "基因編輯", "tickers": ["CRSP", "EDIT", "NTLA", "BEAM"]},
        {"name": "細胞治療", "tickers": ["ALLO"]},
    ]},
    {"name": "太空", "subs": [
        {"name": "發射與衛星", "tickers": ["RKLB", "ASTS"]},
        {"name": "感測", "tickers": ["AEVA"]},
    ]},
    {"name": "核能", "subs": [
        {"name": "反應爐與SMR", "tickers": ["OKLO", "SMR"]},
        {"name": "鈾與核燃料", "tickers": ["CCJ", "LEU"]},
        {"name": "綜合電力", "tickers": ["BEPC"]},
    ]},
    {"name": "機器人", "subs": [
        {"name": "自駕與實體AI", "tickers": ["TSLA"]},
        {"name": "配送機器人", "tickers": ["SERV"]},
        {"name": "感測", "tickers": ["AEVA"]},
    ]},
    {"name": "生技/製藥", "subs": [
        {"name": "減重與代謝", "tickers": ["LLY", "NVO", "VKTX", "RYTM"]},
        {"name": "基因編輯與細胞治療", "tickers": ["CRSP", "EDIT", "NTLA", "BEAM", "ALLO"]},
        {"name": "免疫與其他製藥", "tickers": ["IBRX", "VRTX", "ARQT"]},
    ]},
    {"name": "網路安全", "subs": [
        {"name": "資安", "tickers": ["PANW", "CRWD", "ZS"]},
    ]},
    {"name": "能源/電力", "subs": [
        {"name": "電力設備與散熱", "tickers": ["VRT", "ETN", "FIX"]},
        {"name": "發電與電網工程", "tickers": ["GEV", "PWR", "BEPC"]},
        {"name": "水資源", "tickers": ["XYL", "PNR"]},
        {"name": "稀土材料", "tickers": ["MP"]},
        {"name": "電動車", "tickers": ["TSLA"]},
    ]},
    {"name": "雲端/SaaS", "subs": [
        {"name": "企業SaaS", "tickers": ["NOW", "CRM", "ORCL", "HUBS", "DDOG", "PLTR"]},
        {"name": "消費網路與平台", "tickers": ["GOOGL", "GOOG", "META", "AAPL", "NFLX", "BABA"]},
        {"name": "雲端基礎設施", "tickers": ["ANET", "NBIS", "CRWV"]},
    ]},
]

# 單一歸類模式：多標籤股票的「最適標籤」
PRIMARY = {
    # 半導體
    "NVDA": "半導體", "AMD": "半導體", "AVGO": "半導體", "QCOM": "半導體",
    "MRVL": "半導體", "RMBS": "半導體", "INTC": "半導體", "ON": "半導體",
    "TSM": "半導體", "ASML": "半導體", "MU": "半導體", "CDNS": "半導體", "SNPS": "半導體",
    # 光通訊
    "CRDO": "光通訊", "AXTI": "光通訊", "AAOI": "光通訊", "CIEN": "光通訊",
    # AI/ML
    "SMCI": "AI/ML", "DELL": "AI/ML", "NBIS": "AI/ML", "CRWV": "AI/ML",
    "APLD": "AI/ML", "ANET": "AI/ML", "PLTR": "AI/ML", "META": "AI/ML",
    "GOOGL": "AI/ML", "GOOG": "AI/ML",
    # 雲端/SaaS
    "NOW": "雲端/SaaS", "CRM": "雲端/SaaS", "ORCL": "雲端/SaaS", "HUBS": "雲端/SaaS",
    "DDOG": "雲端/SaaS", "AAPL": "雲端/SaaS", "NFLX": "雲端/SaaS", "BABA": "雲端/SaaS",
    # 網路安全
    "PANW": "網路安全", "CRWD": "網路安全", "ZS": "網路安全",
    # 基因編輯
    "CRSP": "基因編輯", "EDIT": "基因編輯", "NTLA": "基因編輯", "BEAM": "基因編輯", "ALLO": "基因編輯",
    # 生技/製藥
    "LLY": "生技/製藥", "NVO": "生技/製藥", "VKTX": "生技/製藥", "RYTM": "生技/製藥",
    "IBRX": "生技/製藥", "VRTX": "生技/製藥", "ARQT": "生技/製藥",
    # 核能
    "OKLO": "核能", "SMR": "核能", "CCJ": "核能", "LEU": "核能",
    # 能源/電力
    "VRT": "能源/電力", "ETN": "能源/電力", "FIX": "能源/電力", "GEV": "能源/電力",
    "PWR": "能源/電力", "BEPC": "能源/電力", "XYL": "能源/電力", "PNR": "能源/電力", "MP": "能源/電力",
    # 機器人
    "TSLA": "機器人", "SERV": "機器人", "AEVA": "機器人",
    # 太空
    "RKLB": "太空", "ASTS": "太空",
    # 國防
    "NOC": "國防", "CACI": "國防",
    # 加密/金融
    "COIN": "加密/金融", "MSTR": "加密/金融", "HOOD": "加密/金融",
    "BX": "加密/金融", "ARES": "加密/金融", "DXYZ": "加密/金融",
}

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
    peak_idx = 0
    seg_low = bars[0]["low"]
    low_date = bars[0]["date"]

    for i, b in enumerate(bars[1:], start=1):
        if b["high"] >= peak:
            # 創段內新高：高點上移，段內低點重設
            peak, peak_date, peak_idx = b["high"], b["date"], i
            seg_low, low_date = b["low"], b["date"]
            continue
        mid = (peak + seg_low) / 2.0
        if seg_low < peak and b["high"] >= mid:
            # 反彈成立（盤中碰到中點就算）：本段結束，從反彈高點重新起算
            peak, peak_date, peak_idx = b["high"], b["date"], i
            seg_low, low_date = b["low"], b["date"]
            continue
        if b["low"] < seg_low:
            seg_low, low_date = b["low"], b["date"]

    last = bars[-1]
    # 回檔天數＝交易日數（高點當天算第 1 天，數到最新資料日）
    days = len(bars) - peak_idx
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
        "days": days,
    }


def main():
    # 同一支股票可能出現在多個標籤，去重後抓資料
    all_tickers = list(dict.fromkeys(
        t for g in GROUPS for s in g["subs"] for t in s["tickers"]))
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
        "primary": PRIMARY,
        "data": result,
        "failed": failed,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\ndone: {len(result)} ok, {len(failed)} failed -> data.json")


if __name__ == "__main__":
    main()
