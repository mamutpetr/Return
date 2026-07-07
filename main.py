import os
import json
import base64
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors

logging.basicConfig(level=logging.INFO)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Верстаю накладну 1 в 1...")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = "invoice.jpg"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as image:
            b64 = base64.b64encode(image.read()).decode('utf-8')
        
        # Промпт: зчитуємо ВСІ 22 позиції
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Зчитай накладну №159/303. Поверни JSON з усіма 22 позиціями. Назви товарів пиши ТРАНСЛІТОМ. Структура: {'items': [{'product': 'name', 'qty': 1.0, 'price': 10.0, 'sum': 10.0}]}. Суми: 2135.60, 427.12, 2562.72."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}]
        )
        data = json.loads(response.choices[0].message.content)
        items = data.get("items", [])

        # PDF шаблон
        pdf_path = "Nakladna_Final.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
        style = ParagraphStyle('N', fontName='Helvetica', fontSize=8)
        
        # Шапка 1 в 1
        elements = [
            Paragraph("<b>TOV \"MEREZHA-SERVIS LVIV\"</b>", style),
            Paragraph("TOV \"MEREZHA SERVIS\", Ternopil, Torhovytsya 1B", style),
            Spacer(1, 10),
            Paragraph("<b>NAKLADNA No 159/303</b>", style),
            Paragraph("vid 15.04.2026 na povernennya produktsiyi", style),
            Spacer(1, 10)
        ]

        # Таблиця
        t_data = [["No", "Nazva tovaru", "Od", "Kilkist", "Tsina", "Suma"]]
        for i, it in enumerate(items, 1):
            t_data.append([i, it['product'], "sht", f"{it['qty']:.3f}", f"{it['price']:.2f}", f"{it['sum']:.2f}"])
        
        t = Table(t_data, colWidths=[20, 250, 30, 50, 60, 60])
        t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('FONTNAME', (0,0), (-1,-1), 'Helvetica')]))
        elements.append(t)
        
        # Підсумок
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Vsogo tovariv na sumu bez PDV: 2135.60", style))
        elements.append(Paragraph("Podatok na dodanu vartist: 427.12", style))
        elements.append(Paragraph("<b>Vsogo do oplaty: 2562.72</b>", style))
        
        doc.build(elements)
        await update.message.reply_document(document=open(pdf_path, 'rb'))
    except Exception as e:
        await update.message.reply_text(f"Помилка: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        if os.path.exists(pdf_path): os.remove(pdf_path)

if __name__ == '__main__':
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
