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

# --- АВТОЗАВАНТАЖЕННЯ ШРИФТУ З КИРИЛИЦЕЮ ДЛЯ 1С-ШАБЛОНУ ---
font_path = "DejaVuSans.ttf"
font_bold_path = "DejaVuSans-Bold.ttf"

if not os.path.exists(font_path):
    print("Завантажую шрифти для кирилиці...")
    urllib.request.urlretrieve("https://github.com/matomo-org/travis-scripts/raw/master/fonts/DejaVuSans.ttf", font_path)
    urllib.request.urlretrieve("https://github.com/matomo-org/travis-scripts/raw/master/fonts/DejaVuSans-Bold.ttf", font_bold_path)

pdfmetrics.registerFont(TTFont('DejaVu', font_path))
pdfmetrics.registerFont(TTFont('DejaVu-Bold', font_bold_path))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = f"invoice_{update.message.chat_id}.jpg"
    await file.download_to_drive(file_path)

    await update.message.reply_text("📸 Фотку отримав! Верстаю ідеальні накладні 1 в 1...")

    try:
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Промпт: розбивка + сума прописом
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
                                "Зчитай табличну частину накладної. "
                                "РОЗБИЙ товари на логічні категорії для створення окремих накладних. "
                                "Зберігай оригінальні УКРАЇНСЬКІ назви товарів. "
                                "Для кожної категорії порахуй загальну суму з ПДВ і додай поле 'total_text' — сума прописом українською мовою (наприклад: 'П'ятсот тридцять дві гривні 08 копійок'). "
                                "JSON Структура: "
                                "{\"invoices\": [{\"category\": \"назва групи\", \"total_text\": \"сума прописом\", \"items\": [{\"product\": \"назва\", \"quantity\": 1, \"price\": 10.5, \"total\": 10.5}]}]}"
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

        # --- ГЕНЕРАЦІЯ PDF (Шаблон 1 в 1) ---
        pdf_path = f"return_invoices_1c_{update.message.chat_id}.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        elements = []
        
        style_normal = ParagraphStyle('Normal', fontName='DejaVu', fontSize=9, leading=11)
        style_label = ParagraphStyle('Label', fontName='DejaVu', fontSize=9, leading=11)
        style_bold_center = ParagraphStyle('Title', fontName='DejaVu-Bold', fontSize=11, leading=14, alignment=1)
        style_table_header = ParagraphStyle('TH', fontName='DejaVu-Bold', fontSize=8, leading=10, alignment=1)
        style_table_cell = ParagraphStyle('TC', fontName='DejaVu', fontSize=8, leading=10)
        style_table_cell_right = ParagraphStyle('TCR', fontName='DejaVu', fontSize=8, leading=10, alignment=2)

        excel_data = []
        current_date = datetime.now().strftime("%d Квітня 2026 р.") # Або використовуй динамічний місяць

        for idx_inv, inv in enumerate(invoices, 1):
            category_name = inv.get("category", f"Група {idx_inv}")
            total_text = inv.get("total_text", "Сума прописом відсутня")
            items = inv.get("items", [])
            
            # 1. ШАПКА
            header_data = [
                [Paragraph("<u>Одержувач</u>", style_label), Paragraph('Товариство з обмеженою відповідальністю "МЕРЕЖА-СЕРВІС ЛЬВІВ"<br/>тел. 0800201800', style_normal)],
                [Paragraph("<u>Постачальник</u>", style_label), Paragraph('ПРИВАТНЕ ПІДПРИЄМСТВО "ТРОЯНДА-ЗАХІД"<br/>ЄДРПОУ 30275535, тел. 0322395800<br/>Р/р UA873052990000026002021002174 в АТ КБ "ПРИВАТБАНК"<br/>ІПН 302755313052, номер свідоцтва 17957486<br/>Адреса Львівська обл., м. Львів, вул. Повстанська, буд. 3А, кв. 8', style_normal)],
                [Paragraph("<u>Платник</u>", style_label), Paragraph('той самий', style_normal)],
                [Paragraph("<u>Замовлення</u>", style_label), Paragraph('Без замовлення', style_normal)],
                [Paragraph("<u>Умова продажу:</u>", style_label), Paragraph('Безготівковий розрахунок', style_normal)]
            ]
            
            t_header = Table(header_data, colWidths=[90, 425])
            t_header.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            elements.append(t_header)
            elements.append(Spacer(1, 20))

            # 2. ЗАГОЛОВОК ДОКУМЕНТА
            doc_number = f"ВН-0009{idx_inv:03d}"
            elements.append(Paragraph(f"<b>Накладна на повернення № {doc_number}</b>", style_bold_center))
            elements.append(Paragraph(f"<b>від {current_date}</b>", style_bold_center))
            elements.append(Spacer(1, 15))
            
            # 3. ТАБЛИЦЯ ТОВАРІВ
            table_data = [[
                Paragraph("<b>№</b>", style_table_header), 
                Paragraph("<b>Товар</b>", style_table_header), 
                Paragraph("<b>Од.</b>", style_table_header), 
                Paragraph("<b>Кількість</b>", style_table_header), 
                Paragraph("<b>Ціна без ПДВ</b>", style_table_header), 
                Paragraph("<b>Сума без ПДВ</b>", style_table_header)
            ]]
            
            total_sum_bez_pdv = 0.0

            for idx, item in enumerate(items, 1):
                prod_name = str(item.get("product", "Невідомо"))
                qty = float(item.get("quantity", 0))
                price = float(item.get("price", 0))
                total = qty * price
                total_sum_bez_pdv += total
                
                table_data.append([
                    Paragraph(str(idx), style_table_cell_right),
                    Paragraph(prod_name, style_table_cell),
                    Paragraph("шт", style_table_cell),
                    Paragraph(f"{qty:.3f}", style_table_cell_right),
                    Paragraph(f"{price:.6f}", style_table_cell_right),
                    Paragraph(f"{total:.2f}", style_table_cell_right)
                ])
                
                excel_data.append({
                    "Категорія": category_name,
                    "Товар": prod_name,
                    "Кількість": qty,
                    "Ціна": price,
                    "Сума": total
                })

            pdv = total_sum_bez_pdv * 0.20
            total_with_pdv = total_sum_bez_pdv + pdv

            # Підсумки
            table_data.append(["", "", "", "", Paragraph("<b>Разом без ПДВ:</b>", style_table_header), Paragraph(f"{total_sum_bez_pdv:.2f}", style_table_cell_right)])
            table_data.append(["", "", "", "", Paragraph("<b>ПДВ:</b>", style_table_header), Paragraph(f"{pdv:.2f}", style_table_cell_right)])
            table_data.append(["", "", "", "", Paragraph("<b>Всього з ПДВ:</b>", style_table_header), Paragraph(f"{total_with_pdv:.2f}", style_table_cell_right)])

            t_items = Table(table_data, colWidths=[20, 215, 30, 60, 95, 95])
            t_items.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('GRID', (0,0), (-1,-4), 0.5, colors.black),
                ('GRID', (4,-3), (-1,-1), 0.5, colors.black),
                ('BOX', (4,-3), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (2,0), (2,-4), 'CENTER'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                ('TOPPADDING', (0,0), (-1,-1), 1),
            ]))
            
            elements.append(t_items)
            elements.append(Spacer(1, 15))
            
            # 4. ПІДПИСИ
            elements.append(Paragraph("Всього на суму:", style_normal))
            elements.append(Paragraph(f"<b>{total_text.capitalize()}</b>", ParagraphStyle('B', fontName='DejaVu-Bold', fontSize=9, leading=11)))
            elements.append(Paragraph(f"ПДВ: {pdv:.2f} грн.", style_normal))
            elements.append(Spacer(1, 25))
            
            sig_data = [[Paragraph("Отримав(ла) _______________________", style_normal), Paragraph("Видав(ла) _______________________", style_normal)]]
            t_sigs = Table(sig_data, colWidths=[250, 265])
            elements.append(t_sigs)
            
            elements.append(Spacer(1, 50))

        doc.build(elements)

        # --- ГЕНЕРАЦІЯ CSV ---
        csv_path = f"return_invoices_{update.message.chat_id}.csv"
        with open(csv_path, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=["Категорія", "Товар", "Кількість", "Ціна", "Сума"])
            writer.writeheader()
            writer.writerows(excel_data)

        # Відправка
        await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladni_1C_1-in-1.pdf")
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
    
    print("Бот запущений! Ідеальний шаблон підключено.")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application.run_polling()
