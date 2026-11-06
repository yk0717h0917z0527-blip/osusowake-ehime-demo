"""e-Stat の小売物価統計調査（主要品目の都市別小売価格）から松山市の野菜・果物の価格を取り込む。

キーは不要。e-Stat のファイル一覧から最新月のファイルを探し、Excel を読んで
osusowake-demo-ehime.html の PRICES ブロックを書き換え、スマホ版も作り直す。
その月に調査のない品目（季節品目）は、さかのぼって直近の月の値を使う。

使い方:  python tools/update_prices.py
必要なもの: openpyxl（pip install openpyxl）
"""
import io
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date

import openpyxl

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "osusowake-demo-ehime.html"
MOBILE = ROOT / "osusowake-ehime-smartphone.html"
CITY = "松山市"
TARGETS = ["みかん", "さつまいも", "キウイフルーツ", "柿", "さといも", "だいこん", "ほうれんそう",
           "キャベツ", "はくさい", "たまねぎ", "にんじん", "じゃがいも", "ブロッコリー", "なす", "トマト", "きゅうり"]
BASE = "https://www.e-stat.go.jp"
LIST = BASE + "/stat-search/files?toukei=00200571&tstat=000000680001&cycle=1&layout=datalist&page=1&tclass1val=0"
UA = "osusowake-demo-price-updater (python urllib)"
MAX_MONTHS = 14


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    time.sleep(1)  # 連続アクセスを避ける
    return data


def month_pages():
    """ファイル一覧から月ごとのページを新しい順に返す: [(年, 月, URL)]"""
    html = get(LIST).decode("utf-8", "ignore")
    found = {}
    for href in re.findall(r'href="([^"]*year=(\d{4})0&amp;month=\d{6}(\d{2})[^"]*)"', html):
        url, y, m = href[0].replace("&amp;", "&"), int(href[1]), int(href[2])
        found[(y, m)] = BASE + url if url.startswith("/") else url
    return [(y, m, found[(y, m)]) for (y, m) in sorted(found, reverse=True)]


def city_file_id(page_url):
    """その月のページから「主要品目の都市別小売価格」（食料を含む 1001〜）の Excel の ID を探す"""
    html = get(page_url).decode("utf-8", "ignore")
    for block in re.split(r"stat-dataset_list-item", html)[1:]:
        text = re.sub(r"<[^>]+>|\s+", " ", block)
        if "主要品目の都市別小売価格" in text and "1001" in text:
            m = re.search(r"statInfId=(\d+)&(?:amp;)?fileKind=0", block)
            if m:
                return m.group(1)
    return None


def read_prices(xlsx_bytes):
    ws = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    for i, r in enumerate(rows[:40]):
        cells = [str(c).strip() if c is not None else "" for c in r]
        if CITY in cells and "品目" in cells:
            ci, ii, ui = cells.index(CITY), cells.index("品目"), cells.index("単位") if "単位" in cells else None
            break
    else:
        raise SystemExit(f"見出し行（{CITY}・品目）が見つかりません。ファイルの形式が変わった可能性があります")
    out = {}
    for r in rows[i + 1:]:
        name = str(r[ii]).strip() if r[ii] is not None else ""
        if name in TARGETS and isinstance(r[ci], (int, float)):
            unit = str(r[ui]).strip() if ui is not None and r[ui] is not None else ""
            if unit in ("1kg", "１ｋｇ"):
                out[name] = int(r[ci])
    return out


def main():
    items, files, latest = {}, [], None
    for y, m, url in month_pages()[:MAX_MONTHS]:
        fid = city_file_id(url)
        if not fid:
            continue
        prices = read_prices(get(f"{BASE}/stat-search/file-download?statInfId={fid}&fileKind=0"))
        if not prices:
            continue
        latest = latest or f"{y}年{m}月"
        files.append(fid)
        for k, v in prices.items():
            items.setdefault(k, {"p": v, "m": f"{y}年{m}月"})
        print(f"{y}年{m}月 statInfId={fid}: {len(prices)}品目")
        if all(t in items for t in TARGETS):
            break
    if not items:
        raise SystemExit("価格を取得できませんでした")
    missing = [t for t in TARGETS if t not in items]
    if missing:
        print("見つからなかった品目:", "、".join(missing))
    data = {"city": CITY, "latest": latest, "fetched": date.today().isoformat(), "files": files,
            "source": "政府統計の総合窓口（e-Stat）小売物価統計調査（動向編）主要品目の都市別小売価格",
            "items": {t: items[t] for t in TARGETS if t in items}}
    block = "const PRICES=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"
    s = SRC.read_text(encoding="utf-8")
    new, n = re.subn(r"(/\* PRICES:BEGIN[^\n]*\*/\n).*?(\n/\* PRICES:END \*/)", lambda mm: mm.group(1) + block + mm.group(2), s, flags=re.S)
    if n != 1:
        raise SystemExit("HTML に PRICES ブロックが見つかりません")
    SRC.write_text(new, encoding="utf-8")
    subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "make_mobile.py"), str(SRC), str(MOBILE)], check=True)
    print(f"更新しました（最新 {latest}・{len(data['items'])}品目）")


if __name__ == "__main__":
    main()
