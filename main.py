import os
import json
import base64
import logging
import asyncio
import csv
import urllib.request
from datetime import datetime

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# --- АВТОЗАВАНТАЖЕННЯ ШРИФТУ З КИРИЛИЦЕЮ ---
font_path = "DejaVuSans.ttf"
if not os.path.exists(font_path):
    print("Завантажую шрифт для кирилиці...")
    urllib.request.urlretrieve("https://github.com/matomo-org/travis-scripts/raw/master/fonts/DejaVuSans.ttf", font_path)
pdfmetrics.registerFont(TTFont('DejaVu', font_path))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = f"invoice_{update.message.chat_id}.jpg"
    await file.download_to_drive(file_path)

    await update.message.reply_text("📸 Фотку отримав! Розпізнаю оригінальні назви та верстаю накладні як в 1С...")

    try:
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Оновлений промпт: зберігаємо УКРАЇНСЬКУ мову
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
                                "РОЗБИЙ всі товари на логічні групи (категорії), щоб згенерувати кілька накладних (наприклад: Овочі заморожені, Напівфабрикати, Випічка тощо). "
                                "ВАЖЛИВО: Зберігай оригінальні УКРАЇНСЬКІ назви товарів, ніякого трансліту! "
                                "Поверни результат у JSON. Структура: "
                                "{\"invoices\": [{\"category\": \"назва групи\", \"items\": [{\"product\": \"назва\", \"quantity\": 1, \"price\": 10.5, \"total\": 10.5}]}]}"
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
            await update.message.reply_text("❌ Не вдалося розпізнати товари.")
            return

        # --- ГЕНЕРАЦІЯ PDF (ЯК В 1С) ---
        pdf_path = f"return_invoices_{update.message.chat_id}.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        
        # Стилі з нашим шрифтом
        style_normal = ParagraphStyle('Normal_Cyr', fontName='DejaVu', fontSize=9, leading=11)
        style_bold = ParagraphStyle('Bold_Cyr', fontName='DejaVu', fontSize=11, leading=14, alignment=1) # Center
        style_table = ParagraphStyle('Table_Cyr', fontName='DejaVu', fontSize=8, leading=10)

        excel_data = []
        current_date = datetime.now().strftime("%d %B %Y р.")

        for idx_inv, inv in enumerate(invoices, 1):
            category_name = inv.get("category", f"Група {idx_inv}")
            items = inv.get("items", [])
            
            # 1. ШАПКА ЯК НА ФОТО
            header_data = [
                [Paragraph("<b>Одержувач</b>", style_normal), Paragraph('Товариство з обмеженою відповідальністю "МЕРЕЖА-СЕРВІС ЛЬВІВ"<br/>тел. 0800201800', style_normal)],
                [Paragraph("<b>Постачальник</b>", style_normal), Paragraph('ПРИВАТНЕ ПІДПРИЄМСТВО "ТРОЯНДА-ЗАХІД"<br/>ЄДРПОУ 30275535, тел. 0322395800<br/>Р/р UA873052990000026002021002174 в АТ КБ "ПРИВАТБАНК"<br/>ІПН 302755313052, номер свідоцтва 17957486<br/>Адреса Львівська обл., м. Львів, вул. Повстанська, буд. 3А, кв. 8', style_normal)],
                [Paragraph("<b>Платник</b>", style_normal), Paragraph('той самий', style_normal)],
                [Paragraph("<b>Замовлення</b>", style_normal), Paragraph('Без замовлення', style_normal)],
                [Paragraph("<b>Умова продажу:</b>", style_normal), Paragraph('Безготівковий розрахунок', style_normal)]
            ]
            
            t_header = Table(header_data, colWidths=[100, 400])
            t_header.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ]))
            elements.append(t_header)
            elements.append(Spacer(1, 15))

            # 2. ЗАГОЛОВОК ДОКУМЕНТА
            doc_number = f"ВН-{datetime.now().strftime('%y%m')}{idx_inv:03d}"
            elements.append(Paragraph(f"<b>Накладна на повернення № {doc_number}</b>", style_bold))
            elements.append(Paragraph(f"<b>від {current_date}</b>", style_bold))
            elements.append(Spacer(1, 15))
            
            # 3. ТАБЛИЦЯ ТОВАРІВ
            table_data = [[
                Paragraph("<b>№</b>", style_table), 
                Paragraph("<b>Товар</b>", style_table), 
                Paragraph("<b>Од.</b>", style_table), 
                Paragraph("<b>Кількість</b>", style_table), 
                Paragraph("<b>Ціна без ПДВ</b>", style_table), 
                Paragraph("<b>Сума без ПДВ</b>", style_table)
            ]]
            
            total_sum_bez_pdv = 0.0

            for idx, item in enumerate(items, 1):
                prod_name = str(item.get("product", "Невідомо"))
                qty = float(item.get("quantity", 0))
                price = float(item.get("price", 0))
                total = qty * price
                total_sum_bez_pdv += total
                
                table_data.append([
                    str(idx),
                    Paragraph(prod_name, style_table),
                    "шт",
                    f"{qty:.3f}",
                    f"{price:.6f}",
                    f"{total:.2f}"
                ])
                
                excel_data.append({
                    "Категорія": category_name,
                    "Товар": prod_name,
                    "Кількість": qty,
                    "Ціна": price,
                    "Сума": total
                })

            # Підсумки під таблицею
            pdv = total_sum_bez_pdv * 0.20
            total_with_pdv = total_sum_bez_pdv + pdv

            # Додаємо порожні клітинки для вирівнювання підсумків
            table_data.append(["", "", "", "", Paragraph("<b>Разом без ПДВ:</b>", style_table), f"{total_sum_bez_pdv:.2f}"])
            table_data.append(["", "", "", "", Paragraph("<b>ПДВ:</b>", style_table), f"{pdv:.2f}"])
            table_data.append(["", "", "", "", Paragraph("<b>Всього з ПДВ:</b>", style_table), f"{total_with_pdv:.2f}"])

            t_items = Table(table_data, colWidths=[20, 250, 30, 60, 80, 80])
            t_items.setStyle(TableStyle([
                ('GRID', (0,0), (-1, -4), 0.5, colors.black), # Сітка тільки для товарів
                ('BOX', (4,-3), (-1,-1), 0.5, colors.black),  # Рамка для підсумків
                ('GRID', (4,-3), (-1,-1), 0.5, colors.black),
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('ALIGN', (0,0), (-1,0), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (2,1), (4,-4), 'RIGHT'),
            ]))
            
            elements.append(t_items)
            elements.append(Spacer(1, 20))
            
            # 4. ПІДПИСИ
            elements.append(Paragraph(f"Всього на суму: <br/><b>Генерована сума прописом (ШІ)</b>", style_normal))
            elements.append(Paragraph(f"ПДВ: {pdv:.2f} грн.", style_normal))
            elements.append(Spacer(1, 20))
            
            signatures = [[Paragraph("Отримав(ла) _______________________", style_normal), Paragraph("Видав(ла) _______________________", style_normal)]]
            t_signs = Table(signatures, colWidths=[270, 270])
            elements.append(t_signs)
            
            # Розрив сторінки для наступної накладної
            elements.append(Spacer(1, 50))

        doc.build(elements)

        # --- ГЕНЕРАЦІЯ CSV ---
        csv_path = f"return_invoices_{update.message.chat_id}.csv"
        with open(csv_path, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=["Категорія", "Товар", "Кількість", "Ціна", "Сума"])
            writer.writeheader()
            writer.writerows(excel_data)

        # Відправка
        await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladni_1C.pdf")
        await update.message.reply_document(document=open(csv_path, 'rb'), filename="Data_1C.csv")

    except Exception as e:
        logging.error(f"Помилка: {e}")
        await update.message.reply_text(f"💥 Помилка: {str(e)}")
        
    finally:
        for f in [file_path, pdf_path, csv_path]:
            if os.path.exists(f):
                os.remove(f)

if __name__ == '__main__':
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        print("ПОМИЛКА: Перевір Environment Variables!")
        exit(1)
        
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот запущений! Шрифт підключено.")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application.run_polling()
