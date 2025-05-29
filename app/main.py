from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pytesseract import image_to_string
from pdf2image import convert_from_path
import pytesseract
from pdf2image import convert_from_path
import pdfplumber
import re
import os
import openai
import json
from openai import OpenAI


# Cesta k šablonám
templates = Jinja2Templates(directory="app/templates")

# Inicializace FastAPI
app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Nastavení cesty k Tesseract OCR
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

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
        "variabilní_symbol": None,
        "datum_vystavení": None,
        "datum_splatnosti": None,
        "datum_duzp": None,
        "částka_celkem": None,
        "částka_bez_dph": None,
        "dph": None,
        "dodavatel": None
    }

    patterns = {
        "variabilní_symbol": r"Variabilní\s*symbol[:\s]+(\d{4,})",
        "datum_vystavení": r"Datum\s+vystavení[:\s]+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})",
        "datum_splatnosti": r"Datum\s+splatnosti[:\s]+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})",
        "datum_duzp": r"(Datum\s+zdan\.?\s+plnění|DUZP)[:\s]+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})",
        "částka_celkem": r"(\d{1,3}(?:\s\d{3})*,\d{2})\s*Kč",
        "částka_bez_dph": r"21\s*%\s*(\d{1,3}(?:\s\d{3})*,\d{2})\s*Kč",
        "dph": r"21\s*%\s*\d{1,3}(?:\s\d{3})*,\d{2}\s*Kč\s*(\d{1,3}(?:\s\d{3})*,\d{2})",
        "dodavatel": r"DODAVATEL\s*(.*?)(?=\s+ODBĚRATEL|CZ\d{8,})"
    }

    for key, pattern in patterns.items():
        if match := re.search(pattern, full_text, re.IGNORECASE | re.DOTALL):
            if match.lastindex and match.lastindex >= 2:
                extracted[key] = (match.group(2) or match.group(1)).strip()
            else:
                extracted[key] = match.group(1).strip()

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
    """

    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",  # nebo "gpt-4"
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content)
    
    except Exception as e:
        print(f"⚠️ AI extrakce selhala: {e}")
        # fallback na regex extrakci
        return extract_by_regex(full_text)



# extracted_data = json.loads(response.choices[0].message["content"])
# print(json.dumps(extracted_data, indent=2, ensure_ascii=False))


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
