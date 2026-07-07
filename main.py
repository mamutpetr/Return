import os
import json
import base64
import logging
import asyncio  # <-- ДОДАНО ДЛЯ ФІКСУ EVENT LOOP
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токени з Environment Variables на Render
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Качаємо фотку найвищої якості
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = "invoice.jpg"
    await file.download_to_drive(file_path)

    await update.message.reply_text("📸 Фотка є! Починаю ШІ-магію розпізнавання...")

    try:
        # Кодуємо в Base64 для OpenAI
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Запит до GPT-4o з вимогою віддати ЧИСТИЙ JSON без маркдауну
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
                                "Зчитай табличну частину цієї накладної. "
                                "Поверни результат суворо у форматі JSON. "
                                "Структура має бути такою: "
                                "{\"items\": [{\"product\": \"назва\", \"quantity\": 1, \"price\": 10.5, \"total\": 10.5}]}"
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
        items = data.get("items", [])

        if not items:
            await update.message.reply_text("❌ ШІ не зміг витягнути товари з таблиці. Спробуй інше фото.")
            return

        await update.message.reply_text(f"✅ Розпізнано позицій: {len(items)}. Генерую PDF накладну...")

        # Генерація PDF
        pdf_path = "return_invoice.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Стилі для тексту
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            spaceAfter=20
        )
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=10,
            leading=12
        )

        # Шапка PDF
        elements.append(Paragraph("Накладна на повернення (Генерація ШІ)", title_style))
        elements.append(Spacer(1, 10))

        # Складання таблиці даних
        # Заголовки (використовуємо трансліт або латиницю, поки не підключиш кастомний шрифт з кирилицею для ReportLab)
        table_data = [["№", "Tovari (Product)", "K-st (Qty)", "Cina (Price)", "Suma (Total)"]]
        
        for idx, item in enumerate(items, 1):
            table_data.append([
                str(idx),
                Paragraph(item.get("product", "Unknown"), cell_style),
                str(item.get("quantity", 0)),
                str(item.get("price", 0)),
                str(item.get("total", 0))
            ])

        # Налаштування стилю таблиці
        t = Table(table_data, colWidths=[30, 250, 60, 70, 80])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('ALIGN', (2,1), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        
        elements.append(t)
        doc.build(elements)

        # Відправка готового файлу користувачу
        await update.message.reply_document(
            document=open(pdf_path, 'rb'), 
            filename="nakladna_povernennya.pdf",
            caption="🚀 Твій MVP-звіт готовий!"
        )

    except Exception as e:
        logging.error(f"Помилка: {e}")
        await update.message.reply_text(f"💥 Щось пішло не так: {str(e)}")
        
    finally:
        # Чистимо сміття за собою
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

if __name__ == '__main__':
    # Обов'язково перевір, що токени прописані в Render
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        print("ПОМИЛКА: Перевір Environment Variables!")
        exit(1)
        
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот успішно запущений і чекає на фотки...")
    
    # --- МАГІЯ ДЛЯ ФІКСУ ПОМИЛКИ EVENT LOOP ---
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # ------------------------------------------
    
    application.run_polling()
