import os
import json
import base64
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import OpenAI
from xhtml2pdf import pisa

logging.basicConfig(level=logging.INFO)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def generate_pdf(html_content, output_path):
    with open(output_path, "w+b") as result_file:
        pisa.CreatePDF(html_content, dest=result_file)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Читаю фото та натягую на HTML-шаблон...")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = "invoice_raw.jpg"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as image:
            b64 = base64.b64encode(image.read()).decode('utf-8')
        
        prompt_text = """
        Analyze the invoice photo. Extract ALL items into a SINGLE list.
        Transliterate all product names to Latin (English letters).
        Calculate the total sum with VAT and provide it in words (transliterated Ukrainian, e.g., "Dvi tysyachi...").
        Output JSON strictly in this structure:
        {
          "invoice_num": "VN-0009255",
          "date": "30 Kvitnya 2026 r.",
          "items": [
             {"id": 1, "name": "Sumish Ovocheva Rud Vesnyana", "unit": "sht", "qty": 1.0, "price_with_vat": 67.02}
          ],
          "total_text": "Dvi tysyachi p'yatsot shistdesyat dvi hrn. 72 kop."
        }
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt_text}, 
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}]
        )
        
        data = json.loads(response.choices[0].message.content)
        items = data.get("items", [])
        
        # Читаємо шаблон з файлу
        with open("template.html", "r", encoding="utf-8") as f:
            html_template = f.read()

        # Формуємо рядки таблиці
        items_html = ""
        total_sum_no_vat = 0.0

        for idx, it in enumerate(items, 1):
            qty = float(it.get('qty', 0))
            price_with_vat = float(it.get('price_with_vat', 0))
            
            # Математика 1С
            price_no_vat = price_with_vat / 1.2
            sum_no_vat = qty * price_no_vat
            total_sum_no_vat += sum_no_vat
            
            items_html += f'''
            <tr>
                <td style="text-align: center;">{idx}</td>
                <td>{it.get('name', '')}</td>
                <td style="text-align: center;">{it.get('unit', 'sht')}</td>
                <td style="text-align: right;">{qty:.3f}</td>
                <td style="text-align: right;">{price_no_vat:.6f}</td>
                <td style="text-align: right;">{sum_no_vat:.2f}</td>
            </tr>
            '''
        
        total_vat = total_sum_no_vat * 0.20
        total_with_vat = total_sum_no_vat + total_vat

        # Підставляємо зчитані дані та математику в HTML
        html_content = html_template.replace("{{invoice_num}}", data.get("invoice_num", "VN-0000000"))
        html_content = html_content.replace("{{date}}", data.get("date", "30 Kvitnya 2026 r."))
        html_content = html_content.replace("{{items_rows}}", items_html)
        html_content = html_content.replace("{{total_no_vat}}", f"{total_sum_no_vat:.2f}")
        html_content = html_content.replace("{{vat}}", f"{total_vat:.2f}")
        html_content = html_content.replace("{{total_with_vat}}", f"{total_with_vat:.2f}")
        html_content = html_content.replace("{{total_text}}", data.get("total_text", ""))

        # Генеруємо PDF
        pdf_path = "Nakladna.pdf"
        generate_pdf(html_content, pdf_path)
        
        await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladna_1C_Single.pdf")

    except Exception as e:
        await update.message.reply_text(f"Помилка: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        if os.path.exists(pdf_path): os.remove(pdf_path)

if __name__ == '__main__':
    # Фікс петлі подій для Render
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот запущено на базі HTML-шаблону.")
    app.run_polling()
