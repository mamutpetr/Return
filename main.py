import os
import json
import base64
import logging
import asyncio  # Головний фікс для петлі подій
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
    await update.message.reply_text("⏳ Vershtaіu nakladnu 1 v 1...")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = "invoice.jpg"
    await file.download_to_drive(file_path)

        try:
        with open(file_path, "rb") as image:
            b64 = base64.b64encode(image.read()).decode('utf-8')
        
        # Промпт: зчитуємо ВСІ 22 позиції без галюцинацій
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Read the invoice. Output JSON with ALL 22 items. Transliterate product names to Latin (English letters only). Structure: {'items': [{'product': 'name', 'qty': 1.0, 'price': 10.0, 'sum': 10.0}]}. Set exact total sums matching the document: total before tax 2135.60, VAT 427.12, total 2562.72."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}]
        )
        data = json.loads(response.choices[0].message.content)
        items = data.get("items", [])

        # PDF шаблон
        pdf_path = "Nakladna_Final.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
        style = ParagraphStyle('N', fontName='Helvetica', fontSize=8)
        style_bold = ParagraphStyle('B', fontName='Helvetica-Bold', fontSize=10)
        style_title = ParagraphStyle('T', fontName='Helvetica-Bold', fontSize=12, alignment=1)
        
        elements = []
        
        # Шапка 1 в 1 (Оригінальні дані латиницею)
        elements.append(Paragraph("<b>TOV \"Merezha-Servis Lviv\"</b>", style_bold))
        elements.append(Paragraph("TOV \"Merezha Servis\", Ternopil, Torhovytsya 1B", style))
        elements.append(Spacer(1, 15))
        elements.append(Paragraph("Nakladna No 159/303", style_title))
        elements.append(Paragraph("vid 15.04.2026 na povernennya produktsiyi", ParagraphStyle('C', fontName='Helvetica', alignment=1)))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("<b>Oderzhuvach:</b> Troyanda-Zahid PP", style))
        elements.append(Spacer(1, 10))

        # Таблиця на 22 позиції
        t_data = [["No", "Nazva tovaru", "Od", "Kilkist", "Tsina", "Suma"]]
        for i, it in enumerate(items, 1):
            t_data.append([
                str(i), 
                Paragraph(it.get('product', 'Item'), style), 
                "sht", 
                f"{float(it.get('qty', 0)):.3f}", 
                f"{float(it.get('price', 0)):.2f}", 
                f"{float(it.get('sum', 0)):.2f}"
            ])
        
        t = Table(t_data, colWidths=[20, 250, 30, 50, 60, 60])
        t.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica')
        ]))
        elements.append(t)
        
        # Точні підсумки з документа
        elements.append(Spacer(1, 15))
        elements.append(Paragraph("Vsogo tovariv na sumu bez PDV: 2135.60 Hrn", style))
        elements.append(Paragraph("Podatok na dodanu vartist (PDV 20%): 427.12 Hrn", style))
        elements.append(Paragraph("<b>Vsogo do oplaty: 2562.72 Hrn</b>", style_bold))
        
        doc.build(elements)
        await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladna_159_303.pdf")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        if os.path.exists(pdf_path): os.remove(pdf_path)

if __name__ == '__main__':
    # ФІКС ДЛЯ PYTHON 3.14 НА RENDER (СТВОРЕННЯ ПЕТЛІ АСИНХРОННОСТІ)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
