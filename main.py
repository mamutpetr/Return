import os
import json
import base64
import logging
import asyncio
import pandas as pd  # <-- Додана бібліотека для Екселю
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import OpenAI
from reportlab.lib.pagesizes import letter
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

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = "invoice.jpg"
    await file.download_to_drive(file_path)

    await update.message.reply_text("📸 Фотка залетіла! Аналізую та формую PDF + Excel...")

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
                                "Зчитай табличну частину цієї накладної. "
                                "Твоє головне завдання: РОЗБИЙ всі товари на логічні групи (категорії), "
                                "щоб згенерувати кілька дрібних накладних на повернення (наприклад: Vegetables, Meat, Dough, Ice Cream тощо). "
                                "ВАЖЛИВО: Всі українські назви товарів і категорій переведи в ТРАНСЛІТ! "
                                "Поверни результат суворо у форматі JSON. Структура: "
                                "{\"invoices\": [{\"category\": \"назва групи\", \"items\": [{\"product\": \"nazva\", \"quantity\": 1, \"price\": 10.5, \"total\": 10.5}]}]}"
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

        if not invoices:
            await update.message.reply_text("❌ ШІ не зміг витягнути товари. Спробуй інше фото.")
            return

        await update.message.reply_text(f"✅ Готово! Знайдено категорій: {len(invoices)}. Відправляю файли...")

        # --- ГЕНЕРАЦІЯ PDF ---
        pdf_path = "return_invoices.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle', parent=styles['Heading1'], fontSize=16, leading=20, spaceAfter=15, textColor=colors.darkblue
        )
        cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=10, leading=12)

        # Список для збору даних у Excel
        excel_data = []

        for inv in invoices:
            category_name = inv.get("category", "Other")
            items = inv.get("items", [])
            
            elements.append(Paragraph(f"Return Invoice: {category_name.upper()}", title_style))
            
            table_data = [["No.", "Product (Translit)", "Qty", "Price", "Total"]]
            
            for idx, item in enumerate(items, 1):
                prod_name = str(item.get("product", "Unknown"))
                qty = item.get("quantity", 0)
                price = item.get("price", 0)
                total = item.get("total", 0)
                
                # Додаємо в PDF
                table_data.append([
                    str(idx),
                    Paragraph(prod_name, cell_style),
                    str(qty),
                    str(price),
                    str(total)
                ])
                
                # Додаємо в Excel
                excel_data.append({
                    "Category": category_name.upper(),
                    "Product": prod_name,
                    "Quantity": qty,
                    "Price": price,
                    "Total": total
                })

            t = Table(table_data, colWidths=[30, 250, 60, 70, 80])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#4a86e8")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('ALIGN', (2,0), (-1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,0), 8),
                ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f3f6fc")),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            
            elements.append(t)
            elements.append(Spacer(1, 30))

        doc.build(elements)

        # --- ГЕНЕРАЦІЯ EXCEL ---
        excel_path = "return_invoices.xlsx"
        df = pd.DataFrame(excel_data)
        df.to_excel(excel_path, index=False)

        # Відправка файлів користувачу
        await update.message.reply_document(
            document=open(pdf_path, 'rb'), 
            filename="split_invoices.pdf",
            caption="📄 Ось твоя PDF-ка для швидкого перегляду."
        )
        await update.message.reply_document(
            document=open(excel_path, 'rb'), 
            filename="1C_import.xlsx",
            caption="📊 А ось готовий EXCEL-файл! Бухгалтерія буде задоволена."
        )

    except Exception as e:
        logging.error(f"Помилка: {e}")
        await update.message.reply_text(f"💥 Щось пішло не так: {str(e)}")
        
    finally:
        # Чистимо сервери від тимчасових файлів
        for f in [file_path, pdf_path, excel_path]:
            if os.path.exists(f):
                os.remove(f)

if __name__ == '__main__':
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        print("ПОМИЛКА: Перевір Environment Variables!")
        exit(1)
        
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот успішно запущений і чекає на фотки...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application.run_polling()
