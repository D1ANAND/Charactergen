import os
from io import BytesIO
import uuid
import time
from fastapi import FastAPI, HTTPException, Depends,Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import boto3
import requests
import uvicorn

app = FastAPI()

load_dotenv()

api_key = os.environ.get("LEOAI_API_KEY")
S3_BUCKET_NAME = 'bucketforadgen'
model_id = "e316348f-7773-490e-adcd-46757c738eb7"

s3 = boto3.client(
    's3',
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
)
region = os.environ.get("AWS_DEFAULT_REGION")

headers = {
    'accept': 'application/json',
    'authorization': f"Bearer {api_key}",
    'content-type': 'application/json',
}

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/generate-character/")
async def generate_images(user_prompt:str = Form(...)):
    try:
    
        engineered_prompt = f"Generate a realistic image of a model captured with a Nikon D850 and a Nikon AF-S NIKKOR 70-200mm f/2.8E FL ED VR lens, lit with high-key lighting to create a soft and ethereal feel, with a shallow depth of field --ar 2:3- with the following attributes: {user_prompt}"
        
        payloads = {
            "height": 832,
            "modelId": model_id,
            "prompt": engineered_prompt,
            "width": 640,
            "alchemy": False,
            "num_images": 1,
            "presetStyle": "LEONARDO",
            "promptMagic": False,
            "sd_version": "v1_5",
            "scheduler": "LEONARDO",
            "photoReal": False,
        }

        response_generate = requests.post('https://cloud.leonardo.ai/api/rest/v1/generations', headers=headers, json=payloads, timeout=20)
        response_generate.raise_for_status()

        time.sleep(20)

        response_result = requests.get('https://cloud.leonardo.ai/api/rest/v1/generations/', timeout=20)
        response_result.raise_for_status()

        image_bytes = BytesIO(requests.get(response_result).content)
        s3_public_url = upload_to_s3(image_bytes, user_prompt)

        return {"S3-public-url": s3_public_url}
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))


def upload_to_s3(image_bytes, user_prompt):
    try:
        unique_identifier = str(uuid.uuid4())
        user_prompt_cleaned = user_prompt.replace(" ", "_")
        s3_key = f"{user_prompt_cleaned}_generated_img_{unique_identifier}"

        s3.put_object(Body=image_bytes, Bucket=S3_BUCKET_NAME, Key=s3_key, ContentType="image/jpg")

        s3_public_url = f'https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}'
        return s3_public_url
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
