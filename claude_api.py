from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import os
import shutil
from uuid import uuid4
from dotenv import load_dotenv
import fitz  # PyMuPDF
import json
import anthropic
from base64 import b64encode
from PIL import Image, ImageEnhance

# Load environment variables
load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

# Initialize Claude client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Initialize FastAPI app
app = FastAPI()
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# Supported image formats
SUPPORTED_IMAGE_FORMATS = {"jpg", "jpeg", "png", "gif", "bmp", "webp"}


def encode_image_to_base64(image_path: str) -> tuple[str, str]:
    """Convert image to base64 and determine media type."""
    try:
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
        ext = image_path.lower().split(".")[-1]
        media_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
        base64_data = b64encode(image_data).decode("utf-8")
        return base64_data, media_type
    except Exception as e:
        raise ValueError(f"Failed to encode image: {str(e)}")


def optimize_image(image_path: str, max_size: tuple[int, int] = (1024, 1024)) -> str:
    """Optimize image size to reduce token usage."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            optimized_path = image_path.replace(".", "_optimized.")
            img.save(optimized_path, "JPEG", quality=85, optimize=True)
            return optimized_path
    except Exception as e:
        print(f"Image optimization failed: {e}")
        return image_path


def extract_pdf_text(file_path: str) -> str:
    """Extract text from a PDF file."""
    try:
        with fitz.open(file_path) as doc:
            text = "\n".join(page.get_text() for page in doc)
            return text[:8000]  # Truncate to prevent token overload
    except Exception as e:
        raise ValueError(f"PDF text extraction failed: {str(e)}")


def process_pdf(file_path: str) -> dict:
    """Process PDF file using Claude."""
    try:
        text = extract_pdf_text(file_path)
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            temperature=0.2,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract invoice data from the following text and return it in JSON with the keys:\n"
                        "- invoice_number\n"
                        "- issue_date\n"
                        "- customer_name\n"
                        "- customer_address\n"
                        "- items (array of objects with description, quantity, unit_price)\n"
                        "- total\n\n"
                        f"Invoice text:\n{text}"
                    ),
                }
            ],
        )
        content = response.content[0].text.strip()
        return parse_response(content)
    except anthropic.APIStatusError as e:
        return {"error": f"Anthropic API error: {str(e)}"}
    except Exception as e:
        return {"error": f"PDF processing error: {str(e)}"}


def process_image(file_path: str) -> list[str] | dict:
    """Process image file for barcode detection."""
    try:
        optimized_path = optimize_image(file_path)
        base64_image, media_type = encode_image_to_base64(optimized_path)
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            temperature=0.2,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extract all barcode numbers from this image and return them in a JSON array format. "
                                'Example: ["12345678", "87654321"]. If no barcodes are found, return an empty array.'
                            ),
                        },
                    ],
                }
            ],
        )
        content = response.content[0].text.strip()
        return parse_response(content)
    except anthropic.APIStatusError as e:
        return {"error": f"Anthropic API error: {str(e)}"}
    except Exception as e:
        return {"error": f"Image processing error: {str(e)}"}


def parse_response(content: str) -> dict | list:
    """Parse Claude response and extract JSON content."""
    try:
        content = content.strip()
        if content.startswith("```json"):
            content = content.replace("```json
        elif content.startswith("```"):
            content = content.replace("```", "").strip()
        return json.loads(content)
    except json.JSONDecodeError:
        return {"raw_response": content}


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Invoice Data Extraction API is running"}


@app.get("/supported-formats")
async def get_supported_formats():
    """Return supported file formats."""
    return {
        "supported_formats": {
            "documents": ["pdf"],
            "images": list(SUPPORTED_IMAGE_FORMATS),
        }
    }


@app.post("/extract-data-claude")
async def extract_data_claude(file: UploadFile = File(...)):
    """Extract data from uploaded PDF or image file."""
    file_ext = file.filename.lower().split(".")[-1]
    filename = f"{uuid4().hex}_{file.filename}"
    file_path = TEMP_DIR / filename
    optimized_path = None

    try:
        # Save uploaded file
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Process file based on type
        if file_ext == "pdf":
            data = process_pdf(file_path)
        elif file_ext in SUPPORTED_IMAGE_FORMATS:
            data = process_image(file_path)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Supported formats: PDF, {', '.join(SUPPORTED_IMAGE_FORMATS).upper()}",
            )

        return JSONResponse(
            content={
                "status": "success",
                "file_type": file_ext,
                "data": data,
            }
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")
    finally:
        # Cleanup temporary files
        for temp_file in [file_path, optimized_path]:
            if temp_file and Path(temp_file).exists():
                Path(temp_file).unlink()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)