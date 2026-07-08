import os
import json
import asyncio
import pdfkit
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ConversationHandler, CommandHandler
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))
ASKING_FOR_TOTAL = 1

async def handle_photo(update, context):
    await update.message.reply_text("⏳ Аналізую...")
    # ... логіка OpenAI та завантаження фото (без змін) ...
    
    # Генерація PDF через pdfkit
    pdf_path = "Nakladna.pdf"
    pdfkit.from_string(html_content, pdf_path) # html_content готовий з шаблону
    
    await update.message.reply_document(document=open(pdf_path, 'rb'))
    # ... видалення файлів ...

if __name__ == '__main__':
    # ... (стандартний запуск з Loop) ...
