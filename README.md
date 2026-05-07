# 🧾 Invoice Data Extractor API (FastAPI + OpenAI Grok)

This project is a simple and powerful REST API built with **FastAPI** that extracts invoice data from **PDF** or **image files** using the **OpenAI Grok (X.AI) Vision model**.

---

## 🚀 Features

- ✅ Upload PDF or image files (`.pdf`, `.jpg`, `.jpeg`, `.png`)
- ✅ Extracts structured invoice data using Grok
- ✅ Returns clean JSON format
- ✅ Handles PDF text and base64-encoded image processing
- ✅ Automatically deletes uploaded temp files

---

## 📦 Tech Stack

- Python 3.10+
- [FastAPI](https://fastapi.tiangolo.com/)
- [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/en/latest/)
- [OpenAI (X.AI) SDK](https://platform.x.ai/)
- Base64 for image encoding
- UUID for secure file naming

---

## 📄 Extracted Fields

The API uses Grok to extract:
- Invoice Number
- Issue Date
- Total Amount
- Customer Name
- Customer Address

---

## 📁 Folder Structure

project-root/
│
├── temp/ # Temporary folder for uploaded files
├── main.py # Main FastAPI app
├── .env # Environment variables (API key)
└── README.md # This file

## Activate a virtual environment
In cmd, run below code:
```
venv\Scripts\activate
```

## Run the app
```
uvicorn gpt_api:app --reload
uvicorn grok_api:app --reload
uvicorn claude_api:app --reload
```

## API Endpoint
```
Endpoint: POST /extract-data-gpt
Endpoint: POST /extract-data-grok
Endpoint: POST /extract-data-claude
```

---

## API Usage
```
Request:

Form-data with a file upload (file key)
Key = file
Value = invoice.png or pdf

Accepts PDF or image

Response:
{
  "status": "success",
  "data": {
    "invoice_number": "INV-123456",
    "issue_date": "2024-06-01",
    "total": "RM 3,000.00",
    "customer": {
      "name": "ABC Transport Sdn Bhd",
      "address": "No.1, Jalan ABC, 43000 Kajang"
    }
  }
}
````


## 👨‍💻 Developed by
Muhamad Fakhrul Najmi bin Abd Aziz
Backend Developer