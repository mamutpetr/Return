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
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors

# Логування
logging.basicConfig(level=logging.INFO)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = f"inv_{update.message.chat_id}.jpg"
    await file.download_to_drive(file_path)

    await update.message.reply_text("⏳ Готую професійний звіт...")

    try:
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Суворий промпт: зберігати оригінальні назви та структуру
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Ти — професійний бухгалтер 1С. Твоє завдання: зчитати НАКЛАДНУ №159/303 від 15.04.2026. "
                        "Поверни JSON з УСІМА 22 позиціями. "
                        "Структура: {\"items\": [{\"product\": \"назва\", \"qty\": 1.0, \"price\": 10.0, \"sum\": 10.0}]}. "
                        "Обов'язково збережи оригінальні українські назви товарів."
                    )},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }]
        )

        data = json.loads(response.choices[0].message.content)
        items = data.get("items", [])

        # --- ГЕНЕРАЦІЯ PDF 1 В 1 ---
        pdf_path = f"Nakladna_{update.message.chat_id}.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
        elements = []
        
        # Стиль для тексту (Helvetica підтримує кирилицю в багатьох середовищах, якщо кодування коректне)
        style = ParagraphStyle('Base', fontName='Helvetica', fontSize=8)

        # Шапка 1 в 1
        header = [
            [Paragraph("<b>ТОВ «Мережа-Сервіс Львів»</b>", style), Paragraph("Пров. 30.04.2026", style)],
            [Paragraph("ТОВ \"Мережа Сервіс\", Тернопіль, Торговиця 1В", style), ""],
            [Paragraph("<br/><b>НАКЛАДНА № 159/303</b>", style), ""],
            [Paragraph("від 15.04.2026 на повернення продукції", style), ""],
            [Paragraph("Одержувач: Троянда-Захід ПП", style), ""]
        ]
        elements.append(Table(header, colWidths=[300, 200]))
        elements.append(Spacer(1, 10))

        # Таблиця товарів
        table_data = [["№", "Назва товару", "Од.", "Кількість", "Ціна", "Сума"]]
        for i, it in enumerate(items, 1):
            table_data.append([i, it['product'], "шт", f"{it['qty']:.3f}", f"{it['price']:.2f}", f"{it['sum']:.2f}"])

        t = Table(table_data, colWidths=[20, 250, 30, 50, 60, 60])
        t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('FONTNAME', (0,0), (-1,-1), 'Helvetica')]))
        elements.append(t)
        
        doc.build(elements)
        await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladna_159_303.pdf")

    except Exception as e:
        await update.message.reply_text(f"Помилка: {str(e)}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

if __name__ == '__main__':
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
