# Invoice Extractor (CZ faktury)

Tato webová aplikace umožňuje nahrát PDF fakturu a automaticky z ní vytěžit klíčové údaje jako:
- variabilní symbol
- datumy (vystavení, splatnost, DUZP)
- částky (celkem, bez DPH, DPH)
- údaje o dodavateli

## Využívá
- FastAPI (backend)
- Jinja2 (HTML šablony)
- pytesseract (OCR fallback)
- OpenAI GPT-4o (AI vytěžování)
- Render.com (nasazení zdarma)

## Spuštění lokálně
```bash
git clone https://github.com/tvoje-jmeno/invoice-extractor.git
cd invoice-extractor
pip install -r requirements.txt
uvicorn app.main:app --reload