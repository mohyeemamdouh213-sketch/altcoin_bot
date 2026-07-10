"""
بوت كشف الدايفرجنس الإيجابي (Bullish MACD Divergence) - منصة Gate.io
=======================================================================
الفكرة:
  1) يجيب كل أزواج USDT على Gate.io
  2) يفلترهم بحجم تداول مجمّع (كل المنصات) >= MIN_TOTAL_VOLUME_USD (عبر CoinMarketCap)
  3) لكل عملة عدّت الفلتر، يفحص فريم اليومي (1d) و4 ساعات (4h)
  4) يكشف الدايفرجنس الإيجابي الشرائي بنوعيه بين السعر وMACD (لأول ما يتكوّن - detection مبكر):
       - Regular Bullish (عادي): إشارة انعكاس - السعر قاع أدنى / MACD قاع أعلى
       - Hidden Bullish (خفي): إشارة استمرار الاتجاه الصاعد - السعر قاع أعلى / MACD قاع أدنى
  5) يتأكد بمؤشرات قوة شرائية إضافية (RSI, Volume Spike, OBV)
  6) يبعت تنبيه (Console + تيليجرام اختياري) - مفيش تنفيذ صفقات فعلي

المتطلبات: pip install -r requirements.txt

الإعدادات هنا بتتقرا من Environment Variables (لو موجودة) وإلا بتاخد القيم الافتراضية تحت.
ده عشان يبقى سهل نشغّله على Railway من غير ما نحط أي بيانات حساسة (زي توكن تيليجرام) جوه الكود.
"""

import os
import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd
import requests
import ccxt


def env(name: str, default, cast=str):
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    if cast is bool:
        return val.strip().lower() in ("1", "true", "yes", "on")
    return cast(val)


# ======================= الإعدادات (عدّل هنا أو عن طريق Environment Variables) =======================

EXCHANGE_ID = env("EXCHANGE_ID", "gate")            # اسم المنصة في ccxt
# لو سبته فاضي، البوت هيفحص كل أزواج التداول على المنصة (كل الـ quotes).
# لو حابب تحصره في quotes معينة (مثلاً USDT,USDC) اكتبهم مفصولين بفاصلة.
ALLOWED_QUOTE_CURRENCIES = [q.strip().upper() for q in env("ALLOWED_QUOTE_CURRENCIES", "").split(",") if q.strip()]
TIMEFRAMES = env("TIMEFRAMES", "1d,4h").split(",")   # الفريمات المطلوب فحصها
CANDLES_LIMIT = env("CANDLES_LIMIT", 150, int)       # عدد الشموع اللي هيتم تحليلها كل مرة

MIN_TOTAL_VOLUME_USD = env("MIN_TOTAL_VOLUME_USD", 4_000_000, float)  # أقل حجم تداول مجمّع (كل المنصات) بالدولار
GATE_MIN_VOLUME_USD = env("GATE_MIN_VOLUME_USD", 200_000, float)      # فلتر أولي سريع على حجم Gate.io نفسه
CMC_API_KEY = env("7eeaf1fd132e416ab49279ee21cc6ce0")  # مفتاح CoinMarketCap API - مطلوب لفلتر الحجم الإجمالي (كل المنصات)

# إعدادات كشف القيعان (Pivots) - كل ما قلّلت RIGHT_BARS كل ما الاكتشاف أسرع (أقل تأكيد)
PIVOT_LEFT_BARS = env("PIVOT_LEFT_BARS", 3, int)
PIVOT_RIGHT_BARS = env("PIVOT_RIGHT_BARS", 2, int)
MAX_PIVOT_LOOKBACK = env("MAX_PIVOT_LOOKBACK", 80, int)     # أقصى عدد شمعات نرجع لها بحثاً عن قاعين للمقارنة
MIN_BARS_BETWEEN_PIVOTS = env("MIN_BARS_BETWEEN_PIVOTS", 4, int)  # أقل مسافة بين القاعين

# أنواع الدايفرجنس المطلوب البحث عنها (شرائي بس - regular و/أو hidden)
DETECT_REGULAR_BULLISH = env("DETECT_REGULAR_BULLISH", True, bool)
DETECT_HIDDEN_BULLISH = env("DETECT_HIDDEN_BULLISH", True, bool)

# مؤشرات القوة الشرائية (Confirmations) - محتاجين على الأقل MIN_CONFIRMATIONS منهم
RSI_PERIOD = env("RSI_PERIOD", 14, int)
RSI_OVERSOLD_THRESHOLD = env("RSI_OVERSOLD_THRESHOLD", 45, float)  # RSI عند القاع الثاني لازم يكون تحته
VOLUME_SMA_PERIOD = env("VOLUME_SMA_PERIOD", 20, int)
VOLUME_SPIKE_MULTIPLIER = env("VOLUME_SPIKE_MULTIPLIER", 1.2, float)  # فوليوم القاع2 أعلى من متوسطه بكام مرة
MIN_CONFIRMATIONS = env("MIN_CONFIRMATIONS", 2, int)  # أقل عدد تأكيدات (من أصل 3: RSI, Volume, OBV)

# تيليجرام (اختياري) - سيب فاضي لو مش عايز تنبيهات تيليجرام
TELEGRAM_BOT_TOKEN = env("8921609548:AAFCQ067csHkvnSiZikGA06dBTt9fjsb2rc")
TELEGRAM_CHAT_ID = env("6914157653")

SCAN_INTERVAL_SECONDS = env("SCAN_INTERVAL_SECONDS", 15 * 60, int)  # كل قد إيه يعيد فحص السوق

# عملات مستقرة (Stablecoins) - لو الزوج مسعّر بيها، فوليوم Gate.io بيبقى تقريبًا بالدولار مباشرة
# وممكن نستخدمه كفلتر أولي سريع. غير كده (أزواج مسعّرة بـ BTC/ETH.. الخ) بنسيب الفلترة كلها لـ CMC.
STABLE_QUOTES = {"USDT", "USDC", "USD", "DAI", "BUSD", "TUSD", "FDUSD", "USDP"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("divergence_bot")

# ============================== أدوات مساعدة (Indicators) ==============================

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_macd(df: pd.DataFrame, fast=12, slow=26, signal=9):
    macd_line = ema(df["close"], fast) - ema(df["close"], slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def compute_rsi(df: pd.DataFrame, period=14) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def compute_obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0))
    return (direction * df["volume"]).cumsum()


def find_pivot_lows(series: pd.Series, left: int = 3, right: int = 2) -> List[int]:
    """
    يرجّع indexes بتاعة القيعان (swing lows).
    right صغير = اكتشاف القاع بشمعات أقل بعد تكوّنه (أبكر لكن تأكيد أضعف).
    """
    pivots = []
    n = len(series)
    for i in range(left, n - right):
        window = series.iloc[i - left: i + right + 1]
        if series.iloc[i] == window.min() and (series.iloc[i - left:i] > series.iloc[i]).all():
            pivots.append(i)
    return pivots


# ============================== نتيجة الفحص ==============================

@dataclass
class DivergenceSignal:
    symbol: str
    timeframe: str
    divergence_type: str  # "regular" أو "hidden"
    price_pivot1: float
    price_pivot2: float
    macd_pivot1: float
    macd_pivot2: float
    bars_ago: int
    confirmations: List[str] = field(default_factory=list)
    confirmation_count: int = 0
    rsi_now: float = 0.0
    last_close: float = 0.0


# ============================== منطق الفحص الأساسي ==============================

def analyze_dataframe(df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[DivergenceSignal]:
    if len(df) < 40:
        return None

    df = df.copy()
    macd_line, signal_line, hist = compute_macd(df)
    df["macd"] = macd_line
    df["rsi"] = compute_rsi(df, RSI_PERIOD)
    df["obv"] = compute_obv(df)
    df["vol_sma"] = df["volume"].rolling(VOLUME_SMA_PERIOD).mean()

    # نقصر البحث على آخر MAX_PIVOT_LOOKBACK شمعة عشان الديفرجنس يكون "حديث"
    recent = df.tail(MAX_PIVOT_LOOKBACK).reset_index(drop=True)
    pivots = find_pivot_lows(recent["close"], PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS)
    if len(pivots) < 2:
        return None

    i1, i2 = pivots[-2], pivots[-1]
    if (i2 - i1) < MIN_BARS_BETWEEN_PIVOTS:
        return None

    price1, price2 = recent["close"].iloc[i1], recent["close"].iloc[i2]
    macd1, macd2 = recent["macd"].iloc[i1], recent["macd"].iloc[i2]

    price_lower_low = price2 < price1
    price_higher_low = price2 > price1
    macd_higher_low = macd2 > macd1
    macd_lower_low = macd2 < macd1

    divergence_type = None
    # Regular Bullish: انعكاس - السعر بيعمل قاع أدنى بينما MACD بيعمل قاع أعلى (ضعف في الزخم الهابط)
    if DETECT_REGULAR_BULLISH and price_lower_low and macd_higher_low:
        divergence_type = "regular"
    # Hidden Bullish: استمرار الاتجاه الصاعد - السعر بيعمل قاع أعلى بينما MACD بيعمل قاع أدنى (تصحيح بس مش انعكاس)
    elif DETECT_HIDDEN_BULLISH and price_higher_low and macd_lower_low:
        divergence_type = "hidden"

    if divergence_type is None:
        return None

    bars_ago = len(recent) - 1 - i2  # قد إيه القاع الثاني قريب من آخر شمعة (0 = آخر شمعة)

    # ------------- التأكيدات (قوة شرائية) -------------
    confirmations = []
    rsi_now = recent["rsi"].iloc[i2]
    if rsi_now < RSI_OVERSOLD_THRESHOLD:
        confirmations.append(f"RSI منخفض عند القاع ({rsi_now:.1f})")

    vol2 = recent["volume"].iloc[i2]
    vol_sma2 = recent["vol_sma"].iloc[i2]
    if pd.notna(vol_sma2) and vol_sma2 > 0 and vol2 > vol_sma2 * VOLUME_SPIKE_MULTIPLIER:
        confirmations.append(f"فوليوم أعلى من المتوسط بـ {vol2/vol_sma2:.1f}x")

    obv1, obv2 = recent["obv"].iloc[i1], recent["obv"].iloc[i2]
    if obv2 > obv1:
        confirmations.append("OBV بيعمل قاع أعلى (تراكم شرائي)")

    if len(confirmations) < MIN_CONFIRMATIONS:
        return None

    return DivergenceSignal(
        symbol=symbol,
        timeframe=timeframe,
        divergence_type=divergence_type,
        price_pivot1=price1,
        price_pivot2=price2,
        macd_pivot1=macd1,
        macd_pivot2=macd2,
        bars_ago=bars_ago,
        confirmations=confirmations,
        confirmation_count=len(confirmations),
        rsi_now=rsi_now,
        last_close=df["close"].iloc[-1],
    )


# ============================== جلب البيانات ==============================

def get_high_volume_symbols(exchange: ccxt.Exchange) -> List[str]:
    """
    يرجّع قايمة كل أزواج التداول على Gate.io (بكل الـ quotes، إلا لو حددت ALLOWED_QUOTE_CURRENCIES)
    اللي حجم تداولها المجمّع (كل المنصات عبر CoinMarketCap) >= MIN_TOTAL_VOLUME_USD.
    بيستخدم فلتر أولي سريع بحجم Gate.io نفسه (للأزواج المسعّرة بعملة مستقرة فقط) عشان يقلل عدد طلبات CMC.
    """
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()

    candidates = []
    for symbol, market in markets.items():
        if not market.get("active", True) or market.get("spot") is False:
            continue
        quote = market.get("quote")
        if ALLOWED_QUOTE_CURRENCIES and quote not in ALLOWED_QUOTE_CURRENCIES:
            continue

        ticker = tickers.get(symbol, {})
        if quote in STABLE_QUOTES:
            # الفوليوم هنا تقريبًا بالدولار مباشرة، ممكن نفلتر بيه بسرعة
            quote_vol = ticker.get("quoteVolume") or 0
            if quote_vol < GATE_MIN_VOLUME_USD:
                continue
        # لأزواج زي BTC/ETH.. مش هنقدر نقدّر الدولار محليًا بدقة، فبنسيب القرار النهائي لـ CMC

        candidates.append((symbol, market["base"]))

    log.info(f"مرشحين أوليين من كل أزواج Gate.io: {len(candidates)}")

    if not CMC_API_KEY:
        log.warning(
            "CMC_API_KEY غير موجود - هيتم تخطي فلتر الحجم الإجمالي (كل المنصات) "
            "والاكتفاء بفلتر حجم Gate.io فقط. ضيف CMC_API_KEY في الـ Environment Variables."
        )
        return [symbol for symbol, _ in candidates]

    bases = [base for _, base in candidates]
    volumes = get_cmc_total_volumes(bases)

    approved = []
    for symbol, base in candidates:
        total_vol = volumes.get(base.upper())
        if total_vol is not None and total_vol >= MIN_TOTAL_VOLUME_USD:
            approved.append(symbol)

    log.info(f"عملات عدّت فلتر الحجم الكلي (>= {MIN_TOTAL_VOLUME_USD:,}$): {len(approved)}")
    return approved


CMC_BATCH_SIZE = 100  # حد أقصى للعملات في الطلب الواحد لـ CoinMarketCap


def get_cmc_total_volumes(base_symbols: List[str]) -> dict:
    """
    يجيب حجم التداول المجمّع (24h) بالدولار لمجموعة عملات من CoinMarketCap دفعة واحدة
    (بيجمع الحجم من كل المنصات اللي CMC بيتابعها، مش منصة واحدة بس).
    بيرجع dict: {SYMBOL: volume_24h_usd}
    """
    volumes = {}
    unique_symbols = sorted(set(s.upper() for s in base_symbols))

    for i in range(0, len(unique_symbols), CMC_BATCH_SIZE):
        batch = unique_symbols[i:i + CMC_BATCH_SIZE]
        try:
            resp = requests.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers={"X-CMC_PRO_API_KEY": CMC_API_KEY, "Accept": "application/json"},
                params={"symbol": ",".join(batch), "convert": "USD"},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            for sym, entry in data.items():
                # CMC ممكن ترجع list لو أكتر من عملة بنفس الـ symbol (بتاخد أعلى واحدة بالماركت كاب)
                item = entry[0] if isinstance(entry, list) else entry
                vol = item.get("quote", {}).get("USD", {}).get("volume_24h")
                if vol is not None:
                    volumes[sym.upper()] = vol
        except Exception as e:
            log.warning(f"تعذر جلب أحجام دفعة من CoinMarketCap: {e}")
        time.sleep(1)  # احترام حدود CMC (rate limit)

    return volumes


def fetch_ohlcv_df(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
    try:
        raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not raw:
            return None
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        log.warning(f"تعذر جلب بيانات {symbol} ({timeframe}): {e}")
        return None


# ============================== التنبيهات ==============================

DIVERGENCE_LABELS = {
    "regular": "دايفرجنس عادي (Regular Bullish) - إشارة انعكاس محتمل",
    "hidden": "دايفرجنس خفي (Hidden Bullish) - إشارة استمرار الاتجاه الصاعد",
}


def format_signal_message(sig: DivergenceSignal) -> str:
    lines = [
        f"🟢 إشارة شراء محتملة - {DIVERGENCE_LABELS.get(sig.divergence_type, sig.divergence_type)}",
        f"العملة: {sig.symbol}",
        f"الفريم: {sig.timeframe}",
        f"آخر سعر: {sig.last_close:.6g}",
        f"القاع 1 -> القاع 2 (سعر): {sig.price_pivot1:.6g} -> {sig.price_pivot2:.6g}",
        f"القاع 1 -> القاع 2 (MACD): {sig.macd_pivot1:.4f} -> {sig.macd_pivot2:.4f}",
        f"القاع التاني حصل من: {sig.bars_ago} شمعة",
        f"RSI الحالي: {sig.rsi_now:.1f}",
        f"التأكيدات ({sig.confirmation_count}): " + "، ".join(sig.confirmations),
    ]
    return "\n".join(lines)


def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        log.warning(f"فشل إرسال تنبيه تيليجرام: {e}")


def send_alert(sig: DivergenceSignal):
    message = format_signal_message(sig)
    log.info("\n" + "=" * 50 + "\n" + message + "\n" + "=" * 50)
    send_telegram_alert(message)


# ============================== الحلقة الرئيسية ==============================

def run_once(exchange: ccxt.Exchange, symbols: List[str]):
    for symbol in symbols:
        for tf in TIMEFRAMES:
            df = fetch_ohlcv_df(exchange, symbol, tf, CANDLES_LIMIT)
            if df is None:
                continue
            signal = analyze_dataframe(df, symbol, tf)
            if signal:
                send_alert(signal)
            time.sleep(exchange.rateLimit / 1000)  # احترام حدود المنصة


def main():
    exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})

    log.info("جاري تجهيز قايمة العملات (فلتر الحجم)...")
    symbols = get_high_volume_symbols(exchange)
    last_symbol_refresh = time.time()

    while True:
        try:
            log.info(f"بدء فحص {len(symbols)} عملة على {TIMEFRAMES}...")
            run_once(exchange, symbols)

            # تحديث قايمة العملات كل ساعة (الفوليوم بيتغير)
            if time.time() - last_symbol_refresh > 3600:
                symbols = get_high_volume_symbols(exchange)
                last_symbol_refresh = time.time()

        except Exception as e:
            log.error(f"خطأ غير متوقع أثناء الفحص: {e}")

        log.info(f"نوم {SCAN_INTERVAL_SECONDS // 60} دقيقة لحد الفحص الجاي...")
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
