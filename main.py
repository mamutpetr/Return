import os
import json
import base64
import logging
import asyncio
import csv
from datetime import datetime

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# Допоміжна функція транслітерації (для латиниці в PDF)
def translit(text):
    cyr = "АБВГДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯабвгдеєжзиіїйклмнопрстуфхцчшщьюя"
    lat = ["A","B","V","H","D","E","Ye","Zh","Z","Y","I","Yi","Y","K","L","M","N","O","P","R","S","T","U","F","Kh","Ts","Ch","Sh","Shch","'","Yu","Ya",
           "a","b","v","h","d","e","ye","zh","z","y","i","yi","y","k","l","m","n","o","p","r","s","t","u","f","kh","ts","ch","sh","shch","'","yu","ya"]
    trans = str.maketrans(cyr, "".join(lat[:len(cyr)])) # спрощено
    # Для стабільності просто використовуємо англійську назву, яку дасть ШІ
    return text

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = f"invoice_{update.message.chat_id}.jpg"
    await file.download_to_drive(file_path)

    await update.message.reply_text("📸 Фотка отримав! Обробляю 22 позиції...")

    try:
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": (
                                "Зчитай табличну частину накладної (всі позиції). "
                                "Розбий на категорії. НАЗВИ ТОВАРІВ ТА КАТЕГОРІЙ ПИШИ ЛАТИНИЦЕЮ (ТРАНСЛІТОМ). "
                                "Для кожної категорії порахуй суми та додай поле 'total_text' — сума прописом англійською. "
                                "JSON Структура: "
                                "{\"invoices\": [{\"category\": \"name\", \"total_text\": \"sum in words\", \"items\": [{\"product\": \"name\", \"quantity\": 1, \"price\": 10.5}]}]}"
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
        )

        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)
        invoices = data.get("invoices", [])

        pdf_path = f"return_invoices_{update.message.chat_id}.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        elements = []
        
        style_normal = ParagraphStyle('Normal', fontName='Helvetica', fontSize=9, leading=11)
        style_bold_center = ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=11, leading=14, alignment=1)
        style_table_header = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1)
        style_table_cell = ParagraphStyle('TC', fontName='Helvetica', fontSize=8, leading=10)
        style_table_cell_right = ParagraphStyle('TCR', fontName='Helvetica', fontSize=8, leading=10, alignment=2)

        for inv in invoices:
            category = inv.get("category", "Group")
            items = inv.get("items", [])
            
            elements.append(Paragraph(f"<b>Return Invoice: {category}</b>", style_bold_center))
            elements.append(Spacer(1, 15))
            
            table_data = [["No.", "Product", "Unit", "Qty", "Price w/VAT", "Total w/VAT"]]
            sum_bez_pdv = 0.0
            
            for idx, item in enumerate(items, 1):
                p_name = item.get("product", "Item")
                qty = float(item.get("quantity", 0))
                price = float(item.get("price", 0))
                total = qty * price
                sum_bez_pdv += (total / 1.2)
                
                table_data.append([str(idx), p_name, "pcs", f"{qty:.3f}", f"{price:.2f}", f"{total:.2f}"])

            t = Table(table_data, colWidths=[20, 200, 30, 60, 90, 90])
            t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
            elements.append(t)
            elements.append(Spacer(1, 20))

        doc.build(elements)
        await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladni.pdf")

    except Exception as e:
        await update.message.reply_text(f"💥 Помилка: {str(e)}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        if os.path.exists(pdf_path): os.remove(pdf_path)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application.run_polling()
