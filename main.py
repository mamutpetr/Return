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

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Отримав! Сканую цифри в оригінальній якості...")
    
    # Визначаємо, як саме відправили зображення (як фото чи як файл)
    if update.message.document:
        file_id = update.message.document.file_id
    else:
        file_id = update.message.photo[-1].file_id

    file = await context.bot.get_file(file_id)
    file_path = "invoice_raw.jpg"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as image:
            b64 = base64.b64encode(image.read()).decode('utf-8')
        
        prompt_text = """
        You are a strict OCR accounting bot. Analyze the invoice photo. 
        DO NOT invent, guess, or hallucinate numbers or names. Read EXACTLY what is printed.
        For each row, extract data from these specific columns:
        - "Кількість" -> qty (e.g., 2.000)
        - "Ціна з ПДВ" -> price_with_vat (e.g., 78.24)
        - "Сума з ПДВ" -> sum_with_vat (e.g., 156.48)
        Transliterate product names to Latin.
        Extract the exact document number and date.
        Extract the exact totals from the bottom of the document (printed or handwritten):
        - Всього товарів на суму без ПДВ -> total_no_vat
        - Податок на додану вартість -> vat
        - Усього до сплати -> total_with_vat
        
        Output JSON strictly in this structure:
        {
          "invoice_num": "272/288",
          "date": "17 Kvitnya 2026 r.",
          "items": [
             {"id": 1, "name": "Krabovi palychky...", "unit": "sht", "qty": 2.0, "price_with_vat": 78.24, "sum_with_vat": 156.48}
          ],
          "total_no_vat": 1652.25,
          "vat": 330.45,
          "total_with_vat": 1982.70,
          "total_text": "Odna tysyacha shistsot visimdesyat dvi hrn. 70 kop."
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
        
        with open("template.html", "r", encoding="utf-8") as f:
            html_template = f.read()

        items_html = ""

        for idx, it in enumerate(items, 1):
            qty = float(it.get('qty', 0))
            price_with_vat = float(it.get('price_with_vat', 0))
            sum_with_vat = float(it.get('sum_with_vat', 0))
            
            price_no_vat = price_with_vat / 1.2
            sum_no_vat = sum_with_vat / 1.2
            
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
        
        total_no_vat = float(data.get("total_no_vat", 0))
        vat = float(data.get("vat", 0))
        total_with_vat = float(data.get("total_with_vat", 0))

        html_content = html_template.replace("{{invoice_num}}", data.get("invoice_num", "VN-0000000"))
        html_content = html_content.replace("{{date}}", data.get("date", "17 Kvitnya 2026 r."))
        html_content = html_content.replace("{{items_rows}}", items_html)
        html_content = html_content.replace("{{total_no_vat}}", f"{total_no_vat:.2f}")
        html_content = html_content.replace("{{vat}}", f"{vat:.2f}")
        html_content = html_content.replace("{{total_with_vat}}", f"{total_with_vat:.2f}")
        html_content = html_content.replace("{{total_text}}", data.get("total_text", ""))

        pdf_path = "Nakladna.pdf"
        generate_pdf(html_content, pdf_path)
        
        await update.message.reply_document(document=open(pdf_path, 'rb'), filename=f"Nakladna_{data.get('invoice_num', '1C').replace('/', '_')}.pdf")

    except Exception as e:
        await update.message.reply_text(f"Помилка: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        if os.path.exists(pdf_path): os.remove(pdf_path)

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    
    # ТУТ ГОЛОВНА ЗМІНА: тепер приймаємо і фото, і файли (зображення)
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_document))
    
    print("Бот запущено. Готовий приймати файли в максимальній якості.")
    app.run_polling()
