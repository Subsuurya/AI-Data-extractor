from locust import HttpUser, task, between
import os

# Adjust path to where your test files are stored
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_FOLDER = os.path.join(BASE_DIR, "temp")

class ChatbotUser(HttpUser):
    wait_time = between(1, 2)  # simulate delay between user requests

    @task(3)  # increase weight if PDF is more common
    def upload_pdf(self):
        file_path = os.path.join(TEMP_FOLDER, "Receipt_INV-190790.pdf")
        with open(file_path, "rb") as f:
            files = {"file": ("Receipt_INV-190790.pdf", f, "application/pdf")}
            self.client.post("/chatbot/extract-data", files=files)

    @task(1)
    def upload_image(self):
        file_path = os.path.join(TEMP_FOLDER, "invoice-1.png")
        with open(file_path, "rb") as f:
            files = {"file": ("invoice-1.png", f, "image/jpeg")}
            self.client.post("/chatbot/extract-data", files=files)
