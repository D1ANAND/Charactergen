import os
from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image
import requests
import boto3
from urllib.parse import quote, urlparse
from pydub import AudioSegment
from ibm_watson import TextToSpeechV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
import replicate
from pydantic import BaseModel
from pydantic import ValidationError
from pydantic import EmailStr
import uvicorn
import json
import uuid
import time
import asyncio

# Define a global semaphore to control access to the functions
mutex = asyncio.Semaphore(value=1)


load_dotenv()

s3 = boto3.client(
    's3',
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
)
s3_bucket_name="bucketforadgen"
client = OpenAI()


apikey = os.environ.get("watson_apikey")
url = os.environ.get("watson_url")
authenticator = IAMAuthenticator(apikey)
tts = TextToSpeechV1(authenticator=authenticator)
tts.set_service_url(url)

app = FastAPI()

# Enable CORS
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ModelImageRequest(BaseModel):
    mod_description: str = Form(...)

    class Config:
        # Set protected_namespaces to an empty tuple to resolve conflicts
        mod_config = {'protected_namespaces': ()}

@app.post("/model-image/")
async def generate_model_image(mod_description: str = Form(...)):
    async with mutex:
        try:
            dalle_api_prompt = f"Generate a realistic image of a model captured from a 70-200mm f/2.8E FL ED VR lens, with a shallow depth of field --ar 2:3- with the following attributes: {mod_description}"
            dalle_response = client.images.generate(
                model="dall-e-3",
                prompt=dalle_api_prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )

            image_content = BytesIO(requests.get(dalle_response.data[0].url).content)

            uploaded_url = upload_to_s3_mod(image_content, mod_description)
            return {"s3_public_url": uploaded_url}
        
        except Exception as e:
            print(f"Error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
def upload_to_s3_mod(image_content, mod_description):
    try:
        unique_identifier=str(uuid.uuid4())
        s3_bucket_name = 'bucketforadgen'

        model_description_cleaned = mod_description.replace(" ", "_")

        s3_key = f"{model_description_cleaned}_model_img_{unique_identifier}.png"

        s3.put_object(Body=image_content.getvalue(), Bucket=s3_bucket_name, Key=s3_key, ContentType='image/png')

        s3_public_url = f'https://{s3_bucket_name}.s3.amazonaws.com/{s3_key}'
        print(f"Public URL for the image: {s3_public_url}")
        return s3_public_url
    
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def upload_to_s3_ad(image, ad_product_name):
    try:
        unique_identifier=str(uuid.uuid4())
        s3_bucket_name = 'bucketforadgen'
        
        ad_product_name_cleaned = ad_product_name.replace(" ", "_")
        
        s3_key = f"{ad_product_name_cleaned}_ad_poster_{unique_identifier}.png"
        image_bytesio = BytesIO()
        image.save(image_bytesio, format='PNG')
        image_bytes = image_bytesio.getvalue()
        s3.put_object(Body=image_bytes, Bucket=s3_bucket_name, Key=s3_key, ContentType="image/png")
        s3_public_url = f'https://{s3_bucket_name}.s3.amazonaws.com/{s3_key}'
        print(f"Ad poster uploaded to S3. Public URL: {s3_public_url}")
        return s3_public_url
    
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        raise HTTPException(status_code=500, detail=str(e))



class AdPosterRequest(BaseModel):
    ad_product_name: str = Form(...)
    ad_product_description: str = Form(...)
    image_url1: str = Form(...)
    image_url2: str = Form(...)

    
    class Config:
        # Set protected_namespaces to an empty tuple to resolve conflicts
        model_config = {'protected_namespaces': ()}

@app.post("/content/")
async def generate_ad_poster(ad_product_name: str = Form(...), ad_product_description: str = Form(...),image_url1: str = Form(...), image_url2: str = Form(...)):
    async with mutex:
        try:
            removebg_url = "https://api.remove.bg/v1.0/removebg"
            headers = {"X-Api-Key": os.environ.get("REMOVEBG_API_KEY")}

            removebg_response1 = requests.post(removebg_url, headers=headers, data={'image_url': image_url1, 'size': 'auto'})

            if removebg_response1.status_code == 200:
                removebg_content1 = BytesIO(removebg_response1.content)
                image1_without_bg = Image.open(removebg_content1).convert("RGBA")

                removebg_response2 = requests.post(removebg_url, headers=headers, data={'image_url': image_url2, 'size': 'auto'})

                if removebg_response2.status_code == 200:
                    removebg_content2 = BytesIO(removebg_response2.content)
                    image2_without_bg = Image.open(removebg_content2).convert("RGBA")

                    tagline_prompt = f"Create a short catchy tagline for a product named {ad_product_name}. Description: {ad_product_description}"
                    tagline_response = client.completions.create(
                        model="text-davinci-003",
                        prompt=tagline_prompt,
                        max_tokens=50
                    )
                    tagline = tagline_response.choices[0].text.strip().replace('"', '')

                    dalle_api_prompt = f"Generate a solid background image which focuses on top and contains only tagline  should be placed at the bottom only, in which we can paste the image later on top of the generated background.  Tagline: {tagline}"
                    dalle_response = client.images.generate(
                        model="dall-e-3",
                        prompt=dalle_api_prompt,
                        size="1024x1024",
                        quality="hd",
                        n=1,
                    )

                    generated_image_content = BytesIO(requests.get(dalle_response.data[0].url).content)
                    generated_image = Image.open(generated_image_content).convert("RGBA")

                    generated_image.paste(image1_without_bg, (50, 50), mask=image1_without_bg)
                    generated_image.paste(image2_without_bg, (200, 200), mask=image2_without_bg)

                    s3_public_url = upload_to_s3_ad(generated_image, ad_product_name)
                    return {"s3_public_url": s3_public_url}

                else:
                    raise HTTPException(status_code=500, detail=f"Error removing background for the second image. Status Code: {removebg_response2.status_code}")

            else:
                raise HTTPException(status_code=500, detail=f"Error removing background for the first image. Status Code: {removebg_response1.status_code}")

        except Exception as e:
            print(f"Error generating ad poster: {e}")
            raise HTTPException(status_code=500, detail=str(e))




def url_to_uri(url):
    parsed_url = urlparse(url)
    uri = parsed_url.scheme + "://" + parsed_url.netloc + quote(parsed_url.path)

    if parsed_url.query:
        uri += quote("?" + parsed_url.query)

    if parsed_url.fragment:
        uri += quote("#" + parsed_url.fragment)

    return uri

def audiogen(product_name, product_description, model_gender):
    script = generate_script(product_name, product_description)

    try:
        s3_audio = None
        if model_gender == "female":
            with open('./generated-audio-female.mp3', 'wb') as audio_file:
                response = tts.synthesize(script, accept='audio/mp3', voice='en-US_AllisonV3Voice').get_result()
                generated_audio = response.content
                audio_file.write(generated_audio)
        elif model_gender == "male":
            with open('./generated-audio-male.mp3', 'wb') as audio_file:
                response = tts.synthesize(script, accept='audio/mp3', voice='en-US_HenryV3Voice').get_result()
                generated_audio = response.content
                if response.status_code != 200:
                    print(f"Error synthesizing audio. Status code: {response.status_code}")
                audio_file.write(generated_audio)

        audio = AudioSegment.from_mp3(f'./generated-audio-{model_gender}.mp3')
        audio.export(f'./generated-audio-{model_gender}.wav', format='wav')
        
        with open(f'./generated-audio-{model_gender}.wav', 'rb') as wav_file:
            audio_bytes = BytesIO(wav_file.read())

        s3_audio = upload_audio_to_s3_vid(audio_bytes, product_name)
    except Exception as e:
        print(f"Error generating or uploading audio: {e}")

    return s3_audio

def upload_audio_to_s3_vid(audio_bytes, product_name):
    try:

        unique_identifier=str(uuid.uuid4())
        product_name_cleaned = product_name.replace(" ", "_")
        s3_bucket_name = 'bucketforadgen'
        s3_key = f"{product_name_cleaned}_generated_audio_{unique_identifier}.mp3"
        s3.put_object(Body=audio_bytes, Bucket=s3_bucket_name, Key=s3_key, ContentType='audio/mpeg')
        audio_public_url = f'https://{s3_bucket_name}.s3.amazonaws.com/{s3_key}'
        return audio_public_url
    except Exception as e:
        print(f"Error uploading audio to S3: {e}")
        raise e

def generate_script(product_name, product_description):
    script_prompt = f"Create a short catchy advertisement script for a product named {product_name}. Description: {product_description}"
    script_response = client.completions.create(
        model="text-davinci-003",
        prompt=script_prompt,
        max_tokens=50
    )
    
    script = script_response.choices[0].text.strip().replace('"', '')
    script = [line.replace('\n', '') for line in script]
    script = ''.join(str(line) for line in script) 
    print(f"Script: {script}")
    return script



class VideoGenerationRequest(BaseModel):
    model_image: str = Form(...)
    product_name: str = Form(...)
    product_description: str = Form(...)
    model_gender: str = Form(...)

    class Config:
        # Set protected_namespaces to an empty tuple to resolve conflicts
        protected_namespaces = ()
@app.post("/generate-vid/")
async def generate_video(request: VideoGenerationRequest):
    async with mutex:
        try:
            model_image = request.model_image
            product_name = request.product_name
            product_description = request.product_description
            model_gender = request.model_gender

            print(f"Model Gender: {model_gender}")

            model_voice = audiogen(product_name, product_description, model_gender)
            model_image_encoded = url_to_uri(model_image)
            print(f"Model Image URI: {model_image_encoded}")

            output = replicate.run(
                "cjwbw/sadtalker:3aa3dac9353cc4d6bd62a8f95957bd844003b401ca4e4a9b33baa574c549d376",
                input={
                    "still": True,
                    "enhancer": "gfpgan",
                    "preprocess": "full",
                    "driven_audio": model_voice,
                    "source_image": model_image_encoded
                }
            )

            print(output)
            return JSONResponse(content={"result": output}, status_code=200)

        except Exception as e:
            print(f"Error generating video: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)




load_dotenv()


api_key = os.environ.get("LEOAI_API_KEY")
S3_BUCKET_NAME = 'bucketforadgen'


url_init_image = "https://cloud.leonardo.ai/api/rest/v1/init-image"
url_generations = "https://cloud.leonardo.ai/api/rest/v1/generations"


model_id = "e316348f-7773-490e-adcd-46757c738eb7"

region = os.environ.get("AWS_DEFAULT_REGION")


headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Bearer {api_key}"
}


def download_image(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def upload_to_s3_img(image_bytes, user_prompt):
    try:
        unique_identifier = str(uuid.uuid4())
        user_prompt_cleaned = user_prompt.replace(" ", "_")
        s3_key = f"{user_prompt_cleaned}_generated_img_{unique_identifier}.png"
        s3.put_object(Body=image_bytes, Bucket=S3_BUCKET_NAME, Key=s3_key, ContentType="image/jpg")
        s3_public_url = f'https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}'
        return s3_public_url

    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None


@app.get("/")
def read_root():
    return {"message": "Hello, welcome to the image generation API!"}



@app.post("/finetuning/")
async def generate_images(image_url: str = Form(...), user_prompt: str = Form(...)):
    async with mutex:
        try:
            # Download the image from the URL
            image_bytes = download_image(image_url)

            # Get a presigned URL for uploading an image
            payload_init_image = {"extension": "png"}
            response_init_image = requests.post(url_init_image, json=payload_init_image, headers=headers)
            response_init_image.raise_for_status()

            # Upload image via presigned URL
            fields = response_init_image.json().get('uploadInitImage', {}).get('fields', {})
            fields = json.loads(fields) if isinstance(fields, str) else fields
            url_upload_image = response_init_image.json().get('uploadInitImage', {}).get('url', '')
            image_id = response_init_image.json().get('uploadInitImage', {}).get('id', '')

            # Modified line for the files parameter
            response_upload = requests.post(url_upload_image, files={'file': ('image.png', image_bytes)}, data=fields)
            response_upload.raise_for_status()

            # Generate with an image prompt
            payload_generations = {
                "height": 832,
                "modelId": model_id,
                "prompt": user_prompt,
                "width": 640,
                "alchemy": False,
                "guidance_scale": 7,
                "imagePrompts": [image_id],
                "init_strength": 0.71,
                "num_images": 2,
                "presetStyle": "LEONARDO",
                "promptMagic": False,
                "sd_version": "v1_5",
                "scheduler": "LEONARDO",
                "photoReal": False,
                "imagePromptWeight": 0.67,
            }

            response_generate = requests.post(url_generations, json=payload_generations, headers=headers)
            response_generate.raise_for_status()

            # Get the generation of images
            generation_id = response_generate.json().get('sdGenerationJob', {}).get('generationId', '')
            url_generation_result = f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}"


            time.sleep(20)

            response_result = requests.get(url_generation_result, headers=headers)
            response_result.raise_for_status()

            # Upload the ad poster to S3 with the correct content type
            s3_public_url = upload_to_s3_img(response_result.content, user_prompt)


            # Upload generated images to S3
            generated_images = response_result.json().get("generations_by_pk", {}).get("generated_images", [])
            generated_image_urls = []
            for idx, image_info in enumerate(generated_images):
                image_url = image_info.get("url", "")
                image_bytes = download_image(image_url)
                generated_image_urls.append(upload_to_s3_img(image_bytes, f"{user_prompt}generated{idx}"))

            generations_string = [
                f"Open-Image-{idx + 1}: {image_url}"
                for idx, image_url in enumerate(generated_image_urls)
            ]

            return {"objects": generations_string}

        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

if __name__ == "__main__":
    uvicorn.run(app,port=int(os.environ.get('PORT', 8080)), host="0.0.0.0")
    
