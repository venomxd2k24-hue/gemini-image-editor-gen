import os
import io
from typing import Optional

from fastapi import FastAPI, Request
from pydantic import BaseModel
from telegram import Update
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

# Endpoint webhook (init Application baru tiap request, cocok serverless)
@app.post("/webhook")
async def webhook(request: Request):
    try:
        webhook_data = await request.json()
        
        # Buat & init Application baru tiap request (stateless)
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        await application.initialize()
        
        # Tambah handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('generate', generate_image))
        application.add_handler(CommandHandler('edit', edit_image))
        application.add_handler(MessageHandler(filters.PHOTO, edit_image))
        
        # Proses update
        update = Update.de_json(webhook_data, application.bot)
        await application.process_update(update)
        
        # Shutdown optional, tapi bagus buat clean up
        await application.shutdown()
        
        return {"message": "ok"}
    except Exception as e:
        print(f"Webhook error: {str(e)}")  # Log error
        return {"message": "error"}  # Tapi return 200 biar Telegram nggak retry

# Root untuk test deploy
@app.get("/")
async def index():
    return {"message": "Bot deployed successfully!"}
