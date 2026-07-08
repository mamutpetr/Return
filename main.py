import os
import json
import asyncio
import base64
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, ConversationHandler, CommandHandler
from openai import OpenAI
from xhtml2pdf import pisa

# Налаштування
logging.basicConfig(level=logging.INFO)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASKING_FOR_TOTAL = 1

def generate_pdf(html_content, output_path):
    with open(output_path, "w+b") as result_file:
        # Використовуємо простий підхід для xhtml2pdf
        pisa.CreatePDF(html_content, dest=result_file, encoding='utf-8')

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Аналізую накладну...")
    file_id = update.message.document.file_id if update.message.document else update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    file_path = "invoice_raw.jpg"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as image:
            b64 = base64.b64encode(image.read()).decode('utf-8')
        
        prompt = """Аналізуй накладну. Поверни JSON: {"is_readable": bool, "invoice_num": str, "date": str, "items": [{"name": str, "unit": str, "qty": float, "price": float}], "total_with_vat": float}. Якщо нечитабельно, is_readable: false."""
        
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        )
        data = json.loads(response.choices[0].message.content)
        
        if not data.get("is_readable", True):
            await update.message.reply_text("🛑 Не вдалося розібрати. Введи суму вручну:")
            context.user_data['temp_data'] = data
            return ASKING_FOR_TOTAL
            
        return await process_pdf(update, context, data)
    except Exception as e:
        await update.message.reply_text(f"Помилка: {str(e)}")
        return ConversationHandler.END
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def receive_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('temp_data')
    data['total_with_vat'] = float(update.message.text.replace(',', '.'))
    return await process_pdf(update, context, data)

async def process_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict):
    with open("template.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    rows = ""
    for idx, it in enumerate(data.get('items', []), 1):
        rows += f"<tr><td>{idx}</td><td>{it.get('name', 'Товар')}</td><td>{it.get('qty', 0)}</td><td>{it.get('price', 0)}</td><td>{it.get('qty', 0)*it.get('price', 0):.2f}</td></tr>"
    
    html = html.replace("{{items_rows}}", rows).replace("{{invoice_num}}", data.get("invoice_num", "-"))
    html = html.replace("{{date}}", data.get("date", "-")).replace("{{total_with_vat}}", f"{data.get('total_with_vat', 0):.2f}")
    
    pdf_path = "Nakladna.pdf"
    generate_pdf(html, pdf_path)
    await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladna.pdf")
    if os.path.exists(pdf_path): os.remove(pdf_path)
    return ConversationHandler.END

if __name__ == '__main__':
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo)],
        states={ASKING_FOR_TOTAL: [MessageHandler(filters.TEXT, receive_hint)]},
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)]
    )
    app.add_handler(conv_handler)
    app.run_polling()
