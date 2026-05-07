from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import os
import fitz #PyMuPDF
from dotenv import load_dotenv
from openai import OpenAI
from uuid import uuid4
import shutil
from pathlib import Path
from base64 import b64encode
import mimetypes
from pyzbar.pyzbar import decode
from PIL import Image, ImageEnhance

# load env variables
load_dotenv()
XAI_API_KEY = os.getenv("XAI_API_KEY")


# setup api
app = FastAPI()
TEMP_DIR ="temp"
os.makedirs(TEMP_DIR, exist_ok=True)

client = OpenAI(
    api_key = XAI_API_KEY,
    base_url= "https://api.x.ai/v1",
    timeout=15.0,  # 15 second timeout
)


def detect_barcodes_pyzbar(image_path):
    """Detect barcodes using pyzbar library"""
    try:
        # Open and preprocess image
        image = Image.open(image_path)
        image = image.convert("L")  # Grayscale
        image = image.resize((image.width * 2, image.height * 2))  # Upscale
        image = ImageEnhance.Contrast(image).enhance(2.0)  # Boost contrast
        image = ImageEnhance.Sharpness(image).enhance(2.0)  # Sharpen
        image = image.point(lambda x: 255 if x > 128 else 0)  # type: ignore # Binarize
        
        # Decode barcodes
        decoded_objects = decode(image)
        
        if decoded_objects:
            barcodes = [obj.data.decode('utf-8') for obj in decoded_objects]
            return barcodes
        else:
            return []
            
    except Exception as e:
        return []


@app.post("/extract-data-grok")
async def extract_data(file: UploadFile = File(...)):
    filename = f"{uuid4().hex}_{file.filename}"
    file_ext = filename.lower().split(".")[-1]
    file_path = os.path.join(TEMP_DIR, filename)
    data = None  # Initialize data variable

    try:
        # save uploaded file in temp folder
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # extract from pdf
        if file_ext == "pdf":
            with fitz.open(file_path) as doc:
                text = "" 
                
                for page in doc:
                    text += page.get_text("text") + "\n"  # type: ignore
                text = text[:6000]  # set grok limit
            
            # send to grok (text)
            response = client.chat.completions.create(
                model = "grok-4-0709",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Please give me clean JSON format for the invoice including:\n"
                            "- invoice number\n"
                            "- issue date\n"  
                            "- total\n"
                            "- customer name and address\n\n"
                            f"Document:\n{text}"
                        ),
                    }
                ],
                max_tokens = 2000,
                temperature = 0.2,
            )
            
            # Parse response for PDF processing
            import json
            try:
                print(f"Full Grok PDF response: {response}")  # Debug print
                content = response.choices[0].message.content
                print(f"Grok PDF content: {content}")  # Debug print
                if content:
                    content = content.strip()
                    
                    if content.startswith('{') and content.endswith('}'):
                        data = json.loads(content)
                    elif '{' in content and '}' in content:
                        start = content.find('{')
                        end = content.rfind('}') + 1
                        json_str = content[start:end]
                        data = json.loads(json_str)
                    else:
                        data = content
                else:
                    data = "No response content"
                    
            except json.JSONDecodeError as e:
                print(f"Grok PDF JSON Error: {e}")  # Debug print
                data = "Invalid JSON response"
            except Exception as e:
                print(f"Grok PDF parsing error: {e}")  # Debug print
                data = f"Error parsing response: {str(e)}"
        
        # extract from image
        elif file_ext in ["jpg", "jpeg", "png"]:
            mime_type, _ = mimetypes.guess_type(file_path)

            if not mime_type or not mime_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="Invalid image type")

            # Try pyzbar first (faster and more reliable for barcodes)
            pyzbar_barcodes = detect_barcodes_pyzbar(file_path)
            
            if pyzbar_barcodes:
                # If pyzbar found barcodes, return them directly
                data = pyzbar_barcodes
            else:
                # Fallback to Grok if pyzbar didn't find anything
                with open(file_path, "rb") as image_file:
                    image_bytes = image_file.read()
                    base64_image = b64encode(image_bytes).decode("utf-8")
                    image_data_url = f"data:{mime_type};base64,{base64_image}"

                response = client.chat.completions.create(
                    model="grok-4-0709",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": image_data_url,
                                        "detail": "high"
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": "Extract barcode numbers from this image. Return as JSON array: [\"12345678\"] or [] if none found."
                                }
                            ]
                        }
                    ],
                    max_tokens=1000,
                    temperature=0.1,
                )
                
                # Parse Grok response
                import json
                try:
                    print(f"Full Grok response: {response}")  # Debug print
                    content = response.choices[0].message.content
                    print(f"Grok content: {content}")  # Debug print
                    
                    if content:
                        content = content.strip()
                        
                        if content.startswith('[') and content.endswith(']'):
                            data = json.loads(content)
                        elif '[' in content and ']' in content:
                            start = content.find('[')
                            end = content.rfind(']') + 1
                            json_str = content[start:end]
                            data = json.loads(json_str)
                        else:
                            data = content
                    else:
                        data = "No response content"
                        
                except json.JSONDecodeError as e:
                    print(f"Grok JSON Error: {e}")  # Debug print
                    data = "Invalid JSON response"
                except Exception as e:
                    print(f"Grok parsing error: {e}")  # Debug print
                    data = f"Error parsing response: {str(e)}"

        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        if data is None:
            data = "No data extracted"

        return JSONResponse(content={"status": "success", "data": data})
        
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)