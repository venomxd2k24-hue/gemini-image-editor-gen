import os
import io
from typing import Optional

from fastapi import FastAPI, Request
from pydantic import BaseModel
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from PIL import Image
import base64

# Env vars (diset di Vercel)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash-image')  # Model untuk image gen/edit

app = FastAPI()

# Buat Application global (serverless ok, init di startup)
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Model untuk validate webhook data (opsional)
class TelegramWebhook(BaseModel):
    update_id: int
    message: Optional[dict] = None
    edited_message: Optional[dict] = None

# Fungsi handler (async)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Halo! Kirim /generate <prompt> untuk buat gambar, atau /edit <prompt> + kirim gambar.')

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = ' '.join(context.args) if context.args else 'Buat gambar kucing lucu'
    try:
        response = model.generate_content([prompt], generation_config=genai.types.GenerationConfig(response_mime_type='image/png'))
        if hasattr(response.parts[0], 'inline_data') and response.parts[0].inline_data:
            img_data = response.parts[0].inline_data.data
            img = Image.open(io.BytesIO(img_data))
            bio = io.BytesIO()
            img.save(bio, 'PNG')
            bio.seek(0)
            await update.message.reply_photo(photo=bio, caption='Gambar dibuat!')
        else:
            await update.message.reply_text('Gagal generate gambar.')
    except Exception as e:
        await update.message.reply_text(f'Error: {str(e)}')

async def edit_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text('Kirim gambar dulu, lalu /edit <prompt>')
        return
    prompt = ' '.join(context.args) if context.args else 'Edit gambar ini jadi lebih cerah'
    try:
        photo = await update.message.photo[-1].get_file()
        img_bytes = await photo.download_as_bytearray()
        img_pil = Image.open(io.BytesIO(img_bytes))
        buffer = io.BytesIO()
        img_pil.save(buffer, format='JPEG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': img_base64}], generation_config=genai.types.GenerationConfig(response_mime_type='image/png'))
        if hasattr(response.parts[0], 'inline_data') and response.parts[0].inline_data:
            img_edit_data = response.parts[0].inline_data.data
            img_edit = Image.open(io.BytesIO(img_edit_data))
            bio = io.BytesIO()
            img_edit.save(bio, 'PNG')
            bio.seek(0)
            await update.message.reply_photo(photo=bio, caption='Gambar diedit!')
        else:
            await update.message.reply_text('Gagal edit gambar.')
    except Exception as e:
        await update.message.reply_text(f'Error: {str(e)}')

# Setup handlers di Application (ganti dispatcher)
def setup_handlers(app: Application):
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('generate', generate_image))
    app.add_handler(CommandHandler('edit', edit_image))
    app.add_handler(MessageHandler(filters.PHOTO, edit_image))

# Init application di startup FastAPI (jalan sekali di cold start)
@app.on_event("startup")
async def startup_event():
    await application.initialize()  # Init bot, dll.
    setup_handlers(application)     # Tambah handlers

# Endpoint webhook
@app.post("/webhook")
async def webhook(request: Request):
    try:
        webhook_data = await request.json()
        bot = application.bot  # Ambil bot dari application
        update = Update.de_json(webhook_data, bot)
        await application.process_update(update)  # Proses update (ganti dispatcher)
        return {"message": "ok"}
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        return {"message": "error"}

# Root untuk test
@app.get("/")
async def index():
    return {"message": "Bot deployed successfully!"}
