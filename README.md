# بوت كشف الدايفرجنس الإيجابي (MACD) - Gate.io

بوت بايثون بيراقب **كل أزواج التداول على منصة Gate.io** (مش أزواج USDT بس - أي quote زي
BTC وETH وغيرهم كمان) ويبعتلك تنبيه لما يحصل **دايفرجنس إيجابي شرائي** بين السعر ومؤشر **MACD**
على فريم **اليومي (1d)** أو **4 ساعات (4h)**، بنوعين:

| النوع | الشرط | معناه |
|---|---|---|
| **عادي (Regular Bullish)** | السعر بيعمل قاع أدنى + MACD بيعمل قاع أعلى | إشارة **انعكاس** محتمل (ضعف في الهبوط) |
| **خفي (Hidden Bullish)** | السعر بيعمل قاع أعلى + MACD بيعمل قاع أدنى | إشارة **استمرار** الاتجاه الصاعد (تصحيح بس) |

الاتنين شغالين افتراضيًا مع بعض (تقدر تقفل أي واحد منهم من الإعدادات).

**شروط إضافية:**
- حجم التداول **المجمّع من كل المنصات** (عبر CoinMarketCap - مش Gate.io بس) ≥ **4,000,000 $**
- تأكيد بقوة شرائية: لازم 2 من 3 يتحققوا: RSI منخفض عند القاع، فوليوم أعلى من المتوسط، OBV بيعمل قاع أعلى

البوت بيدّي **تنبيه فقط** (Console + تيليجرام اختياري) - **مفيش تنفيذ صفقات فعلي**.

## من فين بيجيب حجم التداول الإجمالي؟
من **CoinMarketCap API** (`/v1/cryptocurrency/quotes/latest`) - الرقم ده (`volume_24h`) بيجمع حجم
التداول لنفس العملة عبر كل المنصات اللي CMC بيتابعها، مش حجم Gate.io بس.

**محتاج تعمل حساب CMC مجاني وتاخد API Key:**
1. سجّل في [coinmarketcap.com/api](https://coinmarketcap.com/api/) (فيه خطة مجانية - Basic Plan)
2. من الداشبورد خد الـ **API Key**
3. حطه في `CMC_API_KEY` (Environment Variable)

لو سبت `CMC_API_KEY` فاضي، البوت هيشتغل بس هيتخطى فلتر الحجم الإجمالي ويكتفي بفلتر حجم Gate.io وحده
(هيطبع تحذير في اللوج يفكّرك بده).

> ملحوظة: الخطة المجانية من CMC عندها حد شهري لعدد الطلبات (Credits) - البوت بيجمّع كل العملات في
> طلبات مجمّعة (Batch) بدل طلب لكل عملة عشان يوفّر في العدد، لكن لو عندك عدد عملات كبير جدًا وبتفحص
> كل 15 دقيقة، ممكن تحتاج تزوّد `SCAN_INTERVAL_SECONDS` أو ترقّي الخطة.

---

## التشغيل محليًا

```bash
pip install -r requirements.txt
python3 divergence_bot.py
```

---

## رفعه على GitHub وتشغيله على Railway

### 1) رفع الكود على GitHub
```bash
git init
git add .
git commit -m "Initial commit - divergence bot"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO_NAME.git
git push -u origin main
```
> **مهم:** ملف `.gitignore` مضبوط بالفعل عشان يمنع رفع `.env` بالغلط. **متحطش** التوكن بتاع تيليجرام
> أو أي بيانات حساسة مباشرة في الكود - استخدم Environment Variables زي موضح تحت.

### 2) ربط الـ Repo بـ Railway
1. ادخل [railway.app](https://railway.app) وسجّل دخول
2. **New Project** → **Deploy from GitHub repo** → اختار الـ repo بتاعك
3. Railway هيكتشف إنه مشروع بايثون تلقائيًا (بفضل `requirements.txt` و`runtime.txt`)

### 3) ضبط نوع الخدمة (Worker مش Web)
البوت مش سيرفر ويب (مفيش عنده port بيسمع عليه)، فلازم تتأكد إنه شغال كـ **Worker**:
- من إعدادات الـ Service في Railway → **Settings** → **Deploy**
- في **Start Command** حط: `python3 divergence_bot.py`
- (ملف `Procfile` المرفق فيه `worker: python3 divergence_bot.py` بيساعد Railway يفهم النوع تلقائيًا)

### ملحوظة: لو الـ Build فشل بخطأ mise / GitHub attestations
لو ظهرلك خطأ زي ده في Build Logs:
```
mise ERROR Failed to install core:python@3.11.9: No GitHub artifact attestations found
```
فده بسبب أداة `mise` اللي Railway بتستخدمها لتثبيت بايثون. **ملف `mise.toml` المرفق في المشروع
بيحل المشكلة دي تلقائيًا** (بيعطّل التحقق من الـ attestations) - تأكد بس إنه اترفع مع باقي الملفات
على GitHub وإن الـ Repo فيه. لو المشكلة استمرت بعد كده، جرّب تمسح `runtime.txt` وتسيب Railway
يختار نسخة بايثون بنفسه.

### 4) إضافة Environment Variables
من **Settings → Variables** ضيف أي متغيرات عايز تغيّرها عن الافتراضي (شوف `.env.example`
لقايمة كاملة). أهمهم لو عايز تنبيهات تيليجرام:
```
TELEGRAM_BOT_TOKEN=xxxxxxxx
TELEGRAM_CHAT_ID=xxxxxxxx
```
كل المتغيرات اختيارية - لو سبتها البوت هيشتغل بالإعدادات الافتراضية المكتوبة في الكود.

### 5) Deploy
Railway هيبني وهيشغّل البوت أوتوماتيك، وهتلاقي اللوج (نفس رسايل التنبيهات) في تبويب **Deployments → Logs**.

---

## إزاي تفعّل تنبيهات تيليجرام
1. اعمل بوت جديد عن طريق [@BotFather](https://t.me/BotFather) وخد الـ Token
2. اعرف الـ Chat ID بتاعك (فيه بوتات زي @userinfobot بتديهولك)
3. حطهم في Environment Variables على Railway (أو في `.env` محليًا)

---

## أهم الإعدادات القابلة للتعديل (Environment Variables)

| المتغير | الوظيفة | الافتراضي |
|---|---|---|
| `ALLOWED_QUOTE_CURRENCIES` | حصر الفحص في quotes معينة (فاضي = كل الأزواج) | فاضي (الكل) |
| `TIMEFRAMES` | الفريمات المطلوب فحصها | `1d,4h` |
| `MIN_TOTAL_VOLUME_USD` | أقل حجم تداول مجمّع مطلوب | `4000000` |
| `CMC_API_KEY` | مفتاح CoinMarketCap API (لازم عشان فلتر الحجم الإجمالي يشتغل) | فاضي |
| `DETECT_REGULAR_BULLISH` | تفعيل/تعطيل الدايفرجنس العادي | `true` |
| `DETECT_HIDDEN_BULLISH` | تفعيل/تعطيل الدايفرجنس الخفي | `true` |
| `PIVOT_RIGHT_BARS` | رقم أصغر = اكتشاف أبكر بس تأكيد أضعف | `2` |
| `MIN_CONFIRMATIONS` | أقل عدد تأكيدات (RSI/فوليوم/OBV) مطلوبة | `2` |
| `RSI_OVERSOLD_THRESHOLD` | حد الـ RSI اللي يعتبر "ضعف بيعي" | `45` |
| `VOLUME_SPIKE_MULTIPLIER` | نسبة الفوليوم المطلوبة فوق المتوسط | `1.2` |
| `SCAN_INTERVAL_SECONDS` | كل قد إيه يعيد فحص السوق كله | `900` (15 دقيقة) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | تنبيهات تيليجرام | فاضي (متعطّل) |

القايمة الكاملة موجودة في `.env.example`.

## ملحوظة عملية عن فحص كل الأزواج
Gate.io عندها آلاف أزواج التداول. فحص كل زوج × كل فريم (يومي + 4 ساعات) هيحتاج عدد كبير من
الطلبات لكل دورة فحص، وده ممكن ياخد وقت طويل ويصطدم بحدود المنصة (rate limit). لو حابب توازن
بين الشمولية والسرعة:
- استخدم `ALLOWED_QUOTE_CURRENCIES=USDT,USDC` مثلاً لتقليل العدد مع الاحتفاظ بمعظم السيولة الفعلية
- أو زوّد `GATE_MIN_VOLUME_USD` عشان الفلتر الأولي (بيشتغل بس على الأزواج المسعّرة بعملة مستقرة) يشيل عدد أكبر بدري
- أو زوّد `SCAN_INTERVAL_SECONDS` عشان يدّي وقت أطول لكل دورة فحص تخلص

## ملحوظة مهمة
الكود اتفحص منطقيًا (unit tests لكشف الدايفرجنس بنوعيه ولـ parsing استجابة CoinMarketCap) لكن
**معنديش اتصال إنترنت بمنصة Gate.io أو CoinMarketCap في بيئة التطوير بتاعتي**، فمهم تتابع اللوج
أول مرة على Railway وتتأكد إن الاتصال شغال والـ API Key صحيح قبل ما تسيبه يشتغل مستمر.

## أفكار إضافية ممكن تضيفها بعدين
- **تأكيد بفريم أصغر (LTF confirmation):** شمعة انعكاسية (Bullish Engulfing / Hammer) على 1h قبل التأكيد النهائي
- **دايفرجنس على RSI بالإضافة لـ MACD:** لو الاتنين بيأكدوا بعض الإشارة بتبقى أقوى
- **مستوى دعم (Support Level):** التأكد إن القاع التاني قريب من دعم تاريخي أو EMA200
- **فلتر اتجاه البيتكوين العام:** تجنب إشارات وقت البيتكوين في هبوط قوي
- **تسجيل الإشارات في قاعدة بيانات** لعمل Backtest ومعرفة نسبة نجاح الإشارات فعليًا
- **Cool-down لكل عملة:** منع تكرار نفس الإشارة كل شوية دقايق لو السوق متذبذب
