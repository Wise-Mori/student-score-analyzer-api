from io import BytesIO
import os
from urllib.parse import quote

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


app = FastAPI(
    title="Student Score Analyzer API",
    description="Calculate student averages and classify students from an Excel file",
    version="1.0.0",
    swagger_ui_parameters={
        "docExpansion": "none",
        "defaultModelsExpandDepth": -1,
        "displayRequestDuration": True,
    },
    docs_url=None,
    redoc_url=None,
)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    for path_data in openapi_schema.get("paths", {}).values():
        for operation in path_data.values():
            responses = operation.get("responses", {})
            responses.pop("422", None)
            if "200" in responses:
                responses["200"] = {
                    "description": responses["200"].get("description", "Successful Response")
                }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

NAME_COLUMN = "نام دانشجو"
SUBJECTS = ["ریاضی", "فیزیک", "آمار", "شیمی", "هندسه"]
REQUIRED_COLUMNS = [NAME_COLUMN, *SUBJECTS]
GAPGPT_BASE_URL = "https://api.gapgpt.app/v1"
DEFAULT_GAPGPT_MODEL = "gpt-5.6-luna"
AI_SYSTEM_PROMPT = "تو یک ایجنت تحلیل آموزشی هستی و باید پاسخ فارسی، خلاصه و کاربردی بدهی."


def classify_student(average: float) -> str:
    """بالاتر از ۱۷: هوشمند، ۱۴ تا ۱۷: متوسط، پایین‌تر از ۱۴: ضعیف."""
    if average > 17:
        return "دانشجوی قوی (معدل الف)"
    if average >= 14:
        return "دانشجوی متوسط (عادی)"
    return "دانشجوی ضعیف"


def analyze_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    data.columns = [str(column).strip() for column in data.columns]

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail=f"ستون‌های زیر در فایل وجود ندارند: {', '.join(missing_columns)}",
        )

    result = data[REQUIRED_COLUMNS].copy()

    if result.empty:
        raise HTTPException(status_code=400, detail="فایل Excel هیچ دانشجویی ندارد.")

    if result[NAME_COLUMN].isna().any() or result[NAME_COLUMN].astype(str).str.strip().eq("").any():
        raise HTTPException(status_code=400, detail="نام دانشجو نمی‌تواند خالی باشد.")

    for subject in SUBJECTS:
        result[subject] = pd.to_numeric(result[subject], errors="coerce")

    invalid_cells = result[SUBJECTS].isna() | ~result[SUBJECTS].apply(
        lambda column: column.between(0, 20)
    )
    if invalid_cells.any().any():
        positions = []
        for row_index, column in zip(*invalid_cells.to_numpy().nonzero()):
            positions.append(f"ردیف {row_index + 2}، ستون {SUBJECTS[column]}")
        raise HTTPException(
            status_code=400,
            detail="نمرات باید عددی و بین ۰ تا ۲۰ باشند. موارد نامعتبر: "
            + "؛ ".join(positions[:10]),
        )

    result["معدل"] = result[SUBJECTS].mean(axis=1).round(2)
    result["سطح"] = result["معدل"].apply(classify_student)
    result = result.sort_values("معدل", ascending=False).reset_index(drop=True)
    result.insert(0, "رتبه", range(1, len(result) + 1))
    return result


def get_gapgpt_client() -> OpenAI:
    api_key = os.getenv("GAPGPT_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="متغیر محیطی GAPGPT_API_KEY تنظیم نشده است.",
        )
    return OpenAI(api_key=api_key, base_url=GAPGPT_BASE_URL)


def build_ai_prompt(result: pd.DataFrame) -> str:
    records = result.to_dict(orient="records")
    return f"""
داده زیر شامل نمرات دانشجویان، معدل، رتبه و سطح آنهاست.

قوانین سطح‌بندی:
- معدل بالاتر از 17: دانشجوی قوی (معدل الف)
- معدل 14 تا 17: دانشجوی متوسط (عادی)
- معدل پایین‌تر از 14: دانشجوی ضعیف

لطفاً خروجی را فارسی، خلاصه و کاربردی بده:
1. یک جمع‌بندی کلی از وضعیت کلاس
2. بهترین دانشجوها و دلیل
3. دانشجوهای نیازمند توجه بیشتر
4. پیشنهاد آموزشی برای بهبود وضعیت

داده:
{records}
""".strip()


@app.get("/", response_class=HTMLResponse)
def home_page() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Student Score Analyzer</title>
  <style>
    :root {
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #667085;
      --line: #d9e1ec;
      --primary: #1f6feb;
      --primary-dark: #174ea6;
      --success: #168a4a;
      --danger: #b42318;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: Tahoma, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }

    .page {
      width: min(980px, calc(100% - 32px));
      margin: 36px auto;
    }

    header {
      margin-bottom: 24px;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 28px;
    }

    .subtitle {
      margin: 0;
      color: var(--muted);
      line-height: 1.8;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }

    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }

    .card h2 {
      margin: 0 0 10px;
      font-size: 18px;
    }

    .card p {
      margin: 0 0 16px;
      color: var(--muted);
      line-height: 1.8;
      font-size: 14px;
    }

    input[type="file"] {
      width: 100%;
      padding: 10px;
      border: 1px dashed #a8b3c7;
      border-radius: 8px;
      background: #fbfcfe;
      margin-bottom: 12px;
      direction: ltr;
    }

    button {
      width: 100%;
      border: 0;
      border-radius: 8px;
      padding: 12px 14px;
      background: var(--primary);
      color: white;
      cursor: pointer;
      font-weight: 700;
      font-size: 14px;
    }

    button:hover {
      background: var(--primary-dark);
    }

    button:disabled {
      opacity: 0.65;
      cursor: wait;
    }

    .result {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      min-height: 120px;
    }

    .result h2 {
      margin: 0 0 12px;
      font-size: 18px;
    }

    .message {
      margin: 0;
      color: var(--muted);
      line-height: 1.8;
      white-space: pre-wrap;
    }

    .ok {
      color: var(--success);
      font-weight: 700;
    }

    .error {
      color: var(--danger);
      font-weight: 700;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 16px;
      font-size: 14px;
    }

    th,
    td {
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: right;
      vertical-align: top;
    }

    th {
      background: #f1f5fb;
      font-weight: 700;
    }

    @media (max-width: 760px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="page">
    <header>
      <h1>تحلیل نمرات دانشجویان</h1>
      <p class="subtitle">فایل Excel را آپلود کن، معدل و سطح‌بندی را بگیر یا تحلیل هوشمند متنی بساز.</p>
    </header>

    <section class="grid">
      <div class="card">
        <h2>خروجی Excel</h2>
        <p>معدل، رتبه و سطح هر دانشجو محاسبه می‌شود و فایل نتیجه دانلود می‌شود.</p>
        <input id="excelFile" type="file" accept=".xlsx" />
        <button id="analyzeButton" type="button">تحلیل و دانلود Excel</button>
      </div>

      <div class="card">
        <h2>تحلیل هوشمند</h2>
        <p>همان فایل تحلیل می‌شود و یک جمع‌بندی آموزشی با مدل GapGPT ساخته می‌شود.</p>
        <input id="aiFile" type="file" accept=".xlsx" />
        <button id="aiButton" type="button">تحلیل با AI</button>
      </div>
    </section>

    <section class="result">
      <h2>نتیجه</h2>
      <div id="result" class="message">هنوز فایلی ارسال نشده است.</div>
    </section>
  </main>

  <script>
    const resultBox = document.getElementById("result");
    const analyzeButton = document.getElementById("analyzeButton");
    const aiButton = document.getElementById("aiButton");

    function setMessage(text, type = "") {
      resultBox.className = "message " + type;
      resultBox.textContent = text;
    }

    function selectedFile(inputId) {
      const fileInput = document.getElementById(inputId);
      if (!fileInput.files.length) {
        throw new Error("لطفاً اول یک فایل Excel با پسوند .xlsx انتخاب کن.");
      }
      return fileInput.files[0];
    }

    async function parseError(response) {
      try {
        const data = await response.json();
        return data.detail || "درخواست ناموفق بود.";
      } catch {
        return "درخواست ناموفق بود.";
      }
    }

    analyzeButton.addEventListener("click", async () => {
      try {
        const file = selectedFile("excelFile");
        const formData = new FormData();
        formData.append("file", file);

        analyzeButton.disabled = true;
        setMessage("در حال پردازش فایل...");

        const response = await fetch("/analyze", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          throw new Error(await parseError(response));
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "student-score-result.xlsx";
        link.click();
        URL.revokeObjectURL(url);
        setMessage("فایل خروجی با موفقیت ساخته و دانلود شد.", "ok");
      } catch (error) {
        setMessage(error.message, "error");
      } finally {
        analyzeButton.disabled = false;
      }
    });

    aiButton.addEventListener("click", async () => {
      try {
        const file = selectedFile("aiFile");
        const formData = new FormData();
        formData.append("file", file);

        aiButton.disabled = true;
        setMessage("در حال گرفتن تحلیل هوشمند...");

        const response = await fetch("/analyze-ai", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          throw new Error(await parseError(response));
        }

        const data = await response.json();
        const rows = data.students
          .map((student) => `
            <tr>
              <td>${student["رتبه"]}</td>
              <td>${student["نام دانشجو"]}</td>
              <td>${student["معدل"]}</td>
              <td>${student["سطح"]}</td>
            </tr>
          `)
          .join("");

        resultBox.className = "message";
        resultBox.innerHTML = `
          <p><strong>مدل:</strong> ${data.model}</p>
          <p>${data.ai_analysis}</p>
          <table>
            <thead>
              <tr>
                <th>رتبه</th>
                <th>نام دانشجو</th>
                <th>معدل</th>
                <th>سطح</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        `;
      } catch (error) {
        setMessage(error.message, "error");
      } finally {
        aiButton.disabled = false;
      }
    });
  </script>
</body>
</html>
        """
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"message": "API فعال است."}


@app.post("/analyze")
async def analyze_excel(file: UploadFile = File(...)) -> StreamingResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="فقط فایل با پسوند .xlsx قابل قبول است.")

    try:
        file_bytes = await file.read()
        source = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="فایل Excel قابل خواندن نیست.") from exc

    result = analyze_dataframe(source)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="نتایج", index=False)
        worksheet = writer.sheets["نتایج"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 4, 32)

    output.seek(0)
    output_name = "نتایج-تحلیل-نمرات.xlsx"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(output_name)}"}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.post("/analyze-ai")
async def analyze_excel_with_ai(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="فقط فایل با پسوند .xlsx قابل قبول است.")

    try:
        file_bytes = await file.read()
        source = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="فایل Excel قابل خواندن نیست.") from exc

    result = analyze_dataframe(source)
    client = get_gapgpt_client()
    model = os.getenv("GAPGPT_MODEL", DEFAULT_GAPGPT_MODEL)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": build_ai_prompt(result)},
            ],
            max_tokens=500,
            temperature=0.2,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"خطا در ارتباط با GapGPT: {exc}") from exc

    return JSONResponse(
        {
            "model": model,
            "students": result.to_dict(orient="records"),
            "ai_analysis": response.choices[0].message.content,
        }
    )
