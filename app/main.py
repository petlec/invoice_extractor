from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pytesseract import image_to_string
from pdf2image import convert_from_path
import pytesseract
import pdfplumber
import re
import os
import openai
import json
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
from babel.numbers import format_currency

# Načtení API klíče z .env
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

# Cesta k šablonám
templates = Jinja2Templates(directory="app/templates")

# --- JINJA FILTRY ---
def format_cz_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except:
        return value

def format_czk(value):
    try:
        num = float(value.replace(",", ".").replace(" ", ""))
        return format_currency(round(num, 2), 'CZK', locale='cs_CZ')
    except:
        return value

templates.env.filters["format_cz_date"] = format_cz_date
templates.env.filters["format_czk"] = format_czk

# Inicializace FastAPI
app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Nastavení cesty k Tesseract OCR
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

def extract_text_from_pdf(file_path: str) -> str:
    text = ""

    # Nejprve zkusíme pdfplumber (textová PDF)
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    # Pokud text téměř chybí → použij OCR
    if len(text.strip()) < 100:
        print("⚠️ OCR aktivováno...")
        images = convert_from_path(file_path)
        text = ""
        for image in images:
            text += pytesseract.image_to_string(image, lang="ces+eng") + "\n"

    text = text.replace('\n', ' ').replace('\r', ' ')
    text = re.sub(r'\s+', ' ', text)

    return text

def extract_by_regex(full_text: str) -> dict:
    extracted = {
        "variabilni_symbol": None,
        "datum_vystaveni": None,
        "datum_splatnosti": None,
        "duzp": None,
        "castka_s_dph": None,
        "zaklad_dph": None,
        "vyse_dph": None,
        "dodavatel": {
            "nazev": None,
            "adresa": None,
            "ico": None,
            "dic": None
        }
    }

    return extracted

def extract_invoice_data(file_path: str) -> dict:
    full_text = extract_text_from_pdf(file_path)

    prompt = f"""
    Z následujícího textu faktury prosím najdi tyto informace a vrať je jako JSON:

    - variabilni_symbol (číslo, např. 20250457)
    - datum_vystaveni (ve formátu RRRR-MM-DD)
    - datum_splatnosti (RRRR-MM-DD)
    - duzp (datum uskutečnění zdanitelného plnění)
    - castka_s_dph (celková částka k úhradě, s DPH)
    - zaklad_dph (částka bez DPH)
    - vyse_dph (částka DPH)
    - dodavatel:
        - nazev
        - adresa
        - ico
        - dic

    Text faktury:
    ----------------------
    {full_text}

    Hledej pouze informace o DODAVATELI (ne odběrateli). Pokud text faktury obsahuje více firem, vyber tu, která fakturuje.
    Vrať odpověď výhradně jako dobře formátovaný JSON bez vysvětlení, komentářů nebo textu navíc.
    """

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        result_text = response.choices[0].message.content.strip()
        print("📦 OpenAI odpověď:\n", result_text)
        if result_text.startswith("```json"):
            result_text = result_text.removeprefix("```json").removesuffix("```")
        return json.loads(result_text)

    except Exception as e:
        print(f"⚠️ AI extrakce selhala: {e}")
        return extract_by_regex(full_text)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload", response_class=HTMLResponse)
async def upload_invoice(request: Request, file: UploadFile = File(...)):
    file_path = f"temp_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())

    extracted_data = extract_invoice_data(file_path)
    os.remove(file_path)

    return templates.TemplateResponse("index.html", {"request": request, "extracted": extracted_data})
