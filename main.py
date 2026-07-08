import os
import json
import asyncio
import base64
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ConversationHandler, CommandHandler
from openai import OpenAI
from xhtml2pdf import pisa

client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))
ASKING_FOR_TOTAL = 1

def generate_pdf(html_content, output_path):
    # Кодуємо в utf-8, щоб уникнути квадратів
    with open(output_path, "w+b") as result_file:
        pisa.CreatePDF(html_content.encode("utf-8"), dest=result_file, encoding='utf-8')

async def process_pdf(update, context, data):
    with open("template.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    rows = ""
    for idx, it in enumerate(data.get('items', []), 1):
        rows += f"<tr><td>{idx}</td><td>{it.get('name', 'Товар')}</td><td>{it.get('unit', '-')}</td><td>{it.get('qty', 0)}</td><td>{it.get('price', 0)}</td><td>{it.get('qty', 0)*it.get('price', 0)}</td></tr>"
    
    html = html.replace("{{items_rows}}", rows).replace("{{invoice_num}}", data.get("invoice_num", "-"))
    html = html.replace("{{date}}", data.get("date", "-")).replace("{{total_with_vat}}", f"{data.get('total_with_vat', 0):.2f}")
    
    pdf_path = "Nakladna.pdf"
    generate_pdf(html, pdf_path)
    await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladna.pdf")
    if os.path.exists(pdf_path): os.remove(pdf_path)
    return ConversationHandler.END

# ... (інші функції handle_photo та receive_hint залишаються без змін) ...

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    # ... (реєстрація хендлерів) ...
    loop.run_forever()
