from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import os
import json
import fitz  # PyMuPDF
from dotenv import load_dotenv
from openai import OpenAI
from uuid import uuid4
import shutil
import mimetypes
from base64 import b64encode
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode

# Initialize environment and dependencies
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=OPENAI_API_KEY)
app = FastAPI()
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)


def preprocess_image(image_path: str) -> Image.Image:
    """Preprocess image for barcode detection."""
    try:
        image = Image.open(image_path).convert("L")  # Grayscale
        image = image.resize((image.width * 2, image.height * 2))  # Upscale
        image = ImageEnhance.Contrast(image).enhance(2.0)  # Boost contrast
        image = ImageEnhance.Sharpness(image).enhance(2.0)  # Sharpen
        image = image.point(lambda x: 255 if x > 128 else 0)  # type: ignore # Binarize
        return image
    except Exception as e:
        raise ValueError(f"Image preprocessing failed: {str(e)}")


def detect_barcodes_pyzbar(image_path: str) -> list[str]:
    """Detect barcodes using pyzbar."""
    try:
        image = preprocess_image(image_path)
        decoded_objects = decode(image)
        return [obj.data.decode("utf-8") for obj in decoded_objects]
    except Exception:
        return []


def extract_pdf_text(file_path: str) -> str:
    """Extract text from a PDF file."""
    try:
        with fitz.open(file_path) as doc:
            text = "\n".join(page.get_text("text") for page in doc)  # type: ignore
            return text[:6000]  # Truncate to prevent token overload
    except Exception as e:
        raise ValueError(f"PDF text extraction failed: {str(e)}")


def process_pdf(file_path: str) -> dict:
    """Process PDF file using GPT-4o."""
    try:
        text = extract_pdf_text(file_path)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Please provide clean JSON format for the invoice including:\n"
                        "- invoice number\n"
                        "- issue date\n"
                        "- total\n"
                        "- customer name and address\n\n"
                        f"Document:\n{text}"
                    ),
                }
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        content = response.choices[0].message.content
        if not content:
            return {"error": "No response content"}
        return json.loads(content)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON response: {str(e)}"}
    except Exception as e:
        return {"error": f"PDF processing error: {str(e)}"}


def process_image(file_path: str, mime_type: str) -> list[str] | dict:
    """Process image file for barcode detection."""
    # Try pyzbar first for barcode detection
    barcodes = detect_barcodes_pyzbar(file_path)
    if barcodes:
        return barcodes

    # Fallback to GPT-4o for barcode detection
    try:
        with open(file_path, "rb") as image_file:
            image_bytes = image_file.read()
            base64_image = b64encode(image_bytes).decode("utf-8")
            image_data_url = f"data:{mime_type};base64,{base64_image}"

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                        {
                            "type": "text",
                            "text": (
                                "Extract all barcode numbers from this image and return them in a JSON array format. "
                                'If you can see barcodes, return them as an array of strings. If no barcodes are visible, return an empty array. '
                                'Example: ["12345678", "87654321"]'
                            ),
                        },
                    ],
                }
            ],
            max_tokens=500,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        if not content:
            return {"error": "No response content"}

        content = content.strip()
        # Extract JSON array from response
        start, end = content.find("["), content.rfind("]") + 1
        if start != -1 and end:
            return json.loads(content[start:end])
        return {"error": "Invalid response format"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON response: {str(e)}"}
    except Exception as e:
        return {"error": f"Image processing error: {str(e)}"}


@app.get("/")
async def root():
    return {"message": "GPT API is running"}


@app.post("/extract-data-gpt")
async def extract_data(file: UploadFile = File(...)):
    """Extract data from uploaded PDF or image file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    file_ext = file.filename.lower().split(".")[-1]
    filename = f"{uuid4().hex}_{file.filename}"
    file_path = TEMP_DIR / filename

    try:
        # Save uploaded file
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Process file based on type
        if file_ext == "pdf":
            data = process_pdf(str(file_path))
        elif file_ext in ["jpg", "jpeg", "png"]:
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type or not mime_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="Invalid image type")
            data = process_image(str(file_path), mime_type)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        return JSONResponse(content={"status": "success", "data": data})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if file_path.exists():
            file_path.unlink()