import os
import re
import time
from datetime import datetime

import hashids as hashids
from bs4 import BeautifulSoup
import requests as requests
import openai
from dotenv import load_dotenv
from pydub import AudioSegment
from gcloud import storage
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()
openai.api_key = os.getenv("OPENAI_KEY")


def createHash(text):
    salt = 'bellbone'
    hash_generator = hashids.Hashids(salt=salt)

    text_bytes = text.encode('utf-8')

    hash_value = hash_generator.encode(int.from_bytes(text_bytes, byteorder='big'))

    return hash_value[:25]


def createPostcontentName():
    prompt = f"Придумай необычную тему для поста"

    print(prompt)
    messages = [{"role": "system", "content": "Ты автор блога про здоровый образ жизни"},
                {"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,

    )
    theme = response.choices[0].message.content
    print(theme)
    return theme


def createAudio(name, content_text):
    name = ''.join(e for e in name if e.isalnum())
    # Формирование запроса
    url = "https://aimyvoice.com/api/v1/synthesize"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "api-key": os.getenv("AIMYVOICE_KEY")
    }

    # Разбиваем текст на части, используя пунктуацию в качестве разделителя
    chunks = re.split('[.!?]', content_text)
    audio_files = []
    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if len(chunk) == 0:
            continue
        if len(chunk) > 200:
            # Если часть текста слишком большая, разбиваем ее еще раз
            sub_chunks = re.findall('.{1,200}(?:\\s+|$)', chunk)
            for j, sub_chunk in enumerate(sub_chunks):
                payload = {
                    "text": sub_chunk
                }
                print(f"Preparing chunk {i}.{j}")
                try:
                    response = requests.post(url, headers=headers, data=payload)
                    response.raise_for_status()
                except requests.exceptions.HTTPError as errh:
                    print("HTTP Error")
                    print(errh.args[0])
                if response.status_code == 200:
                    audio_file = f"{name}_{i}_{j}.wav"
                    with open(audio_file, "wb") as result:
                        result.write(response.content)
                    audio_files.append(audio_file)
        else:
            payload = {
                "text": chunk
            }
            print(f"Preparing chunk {i}")
            try:
                response = requests.post(url, headers=headers, data=payload)
                response.raise_for_status()
            except requests.exceptions.HTTPError as errh:
                print("HTTP Error")
                print(errh.args[0])
            if response.status_code == 200:
                audio_file = f"{name}_{i}.wav"
                with open(audio_file, "wb") as result:
                    result.write(response.content)
                audio_files.append(audio_file)

    # Объединяем все аудиофайлы в один
    sound = None
    for audio_file in audio_files:
        if sound is None:
            sound = AudioSegment.from_wav(audio_file)
        else:
            sound += AudioSegment.from_wav(audio_file)
    # Сохраняем объединенный аудиофайл
    if sound is not None:
        f_name = createHash(name)
        sound.export(f"{f_name}.wav", format="wav")
        print("Ready")
        # Удаляем временные файлы
        for audio_file in audio_files:
            os.remove(audio_file)
        return f'{f_name}.wav'


def loadDataToGoogle(filename):
    credentials_dict = {
        'type': 'service_account',
        'client_id': os.getenv("USER_ID"),
        'client_email': os.getenv("USER_EMAIL"),
        'private_key_id': os.getenv("PRIVATE_KEY_ID"),
        'private_key': os.getenv("PRIVATE_KEY"),
    }
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        credentials_dict
    )
    client = storage.Client(credentials=credentials, project='myproject')
    bucket = client.get_bucket('bellboneaudio')
    blob = bucket.blob(filename)
    blob.upload_from_filename(filename)
    os.remove(filename)
    return blob.public_url


def generateImage(prompt):
    # Generate an image
    response = openai.Image.create(
        prompt=prompt,
        model="image-alpha-001",
        size="1024x1024",
        response_format="url"
    )

    # Print the URL of the generated image
    return response["data"][0]["url"]


def generateImagePrompt(text):
    prompt = f'Напиши prompt для DALL-E на английском, чтобы он сгенерировал картинку по описанию: {text}'

    print(prompt)
    messages = [{"role": "system", "content": "Ты генератор prompt для DALL-E"},
                {"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,

    )
    content = response.choices[0].message.content

    print(content)
    return content


def addImages(content):
    soup = BeautifulSoup(content, 'html.parser')
    images = soup.find_all('img')

    for img in images:
        img['src'] = generateImage(generateImagePrompt(str(img['alt'])))
        time.sleep(21)
    return str(soup)


def createPostcontentText(theme):
    prompt = f"Напиши текст для блога на тему {theme}. При написании текста используй html-разметку. Добавь картинки, но в поле src поставь $"

    print(prompt)
    messages = [{"role": "system", "content": "Ты автор блога про здоровый образ жизни"},
                {"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,

    )
    content = response.choices[0].message.content

    print(content)
    return content


theme = createPostcontentName()
time.sleep(21)
th_without = str(theme).replace('"', '').replace('«', '').replace('»', '')

text_with_tags = str(createPostcontentText(theme)).replace('\n', '')
time.sleep(21)
cleantext = BeautifulSoup(text_with_tags, "lxml").text
file_name = createAudio(th_without, cleantext)
audio_url = loadDataToGoogle(file_name)
text_with_tags = addImages(text_with_tags)

post_text = f"""<figure>
    <figcaption>Статья в аудиоформате</figcaption>
    <audio
        controls
        src="{audio_url}">
    </audio>
</figure>""" + text_with_tags

data = {
    'from_cron_task': '1',
    "postTitle": th_without,
    "postTags": "Здоровое питание,ЗОЖ,СтатьяОтНейросети",
    "postContent": post_text,
    "postDescription": f'Статья от нейросети на тему: "{th_without}"',
    "postAuthor": "HealthAI"
}
r = requests.post('http://127.0.0.1:5000/createpost', data=data)
