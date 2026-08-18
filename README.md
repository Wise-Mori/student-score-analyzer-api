# API تحلیل نمرات دانشجویان

این پروژه یک فایل Excel می‌گیرد، معدل پنج درس را حساب می‌کند، دانشجویان را بر اساس معدل سطح‌بندی و رتبه‌بندی می‌کند و می‌تواند نتیجه را به دو شکل برگرداند:

- خروجی Excel با محاسبات دقیق
- خروجی هوشمند با تحلیل متنی از طریق GapGPT API

## قانون سطح‌بندی

- معدل بیشتر از ۱۷: `دانشجوی هوشمند (الف)`
- معدل از ۱۴ تا خود ۱۷: `دانشجوی متوسط (عادی)`
- معدل کمتر از ۱۴: `دانشجوی ضعیف`

## ۱. اجرای پروژه در VS Code

پوشه پروژه را در VS Code باز کنید. سپس از منوی `Terminal > New Terminal` یک ترمینال بسازید و دستورات زیر را اجرا کنید.

### Windows (PowerShell)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload
```

اگر PowerShell اجازه فعال‌سازی محیط مجازی نداد، یک بار این دستور را در همان ترمینال اجرا کنید:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload
```

## ۲. تنظیم GapGPT API

اگر فقط می‌خواهید معدل و سطح‌بندی Excel را بگیرید، این بخش لازم نیست.

اگر می‌خواهید endpoint هوشمند `POST /analyze-ai` کار کند، در پوشه پروژه یک فایل به نام `.env` بسازید و مقدارهای زیر را داخل آن قرار دهید:

```text
GAPGPT_API_KEY=YOUR_GAPGPT_API_KEY
GAPGPT_MODEL=gpt-5.6-luna
```

نمونه اتصال GapGPT در این پروژه با کتابخانه `openai` انجام می‌شود:

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.gapgpt.app/v1",
)

response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[{"role": "user", "content": "سلام!"}],
)
```

## ۳. تست API

پس از اجرا، این آدرس را در مرورگر باز کنید:

`http://127.0.0.1:8000/`

سپس:

1. برای خروجی Excel، فایل `sample_students.xlsx` را در کارت `خروجی Excel` انتخاب کنید.
2. روی `تحلیل و دانلود Excel` بزنید.
3. برای تحلیل هوشمند، فایل را در کارت `تحلیل هوشمند` انتخاب کنید.
4. روی `تحلیل با AI` بزنید.

## ساختار فایل ورودی

نام ستون‌ها باید دقیقاً به شکل زیر باشد:

| نام دانشجو | ریاضی | فیزیک | آمار | شیمی | هندسه |
|---|---:|---:|---:|---:|---:|
| علی احمدی | ۱۸ | ۱۷ | ۱۹ | ۱۶ | ۱۸ |

نمرات باید عددی و بین صفر تا بیست باشند. تعداد دانشجویان محدود به ۱۰ نفر نیست و می‌توانید ردیف‌های بیشتری نیز ارسال کنید.

## خروجی

خروجی شامل ستون‌های ورودی به همراه `رتبه`، `معدل` و `سطح` است و بر اساس معدل از بیشترین به کمترین مرتب می‌شود.

## آدرس‌های مهم

- صفحه اصلی برنامه: `http://127.0.0.1:8000/`
- بررسی فعال بودن API: `http://127.0.0.1:8000/health`
- مسیر پردازش فایل و خروجی Excel: `POST http://127.0.0.1:8000/analyze`
- مسیر پردازش فایل با تحلیل هوشمند GapGPT: `POST http://127.0.0.1:8000/analyze-ai`

## نکته مهم

محاسبه معدل، رتبه و سطح‌بندی همچنان با کد انجام می‌شود، چون دقیق و قابل اعتماد است. تحلیل متنی و پیشنهاد آموزشی از طریق GapGPT API تولید می‌شود.
