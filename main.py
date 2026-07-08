import os
import json
import asyncio
import pdfkit
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ConversationHandler, CommandHandler
from openai import OpenAI
import base64

client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))
ASKING_FOR_TOTAL = 1

async def handle_photo(update, context):
    await update.message.reply_text("⏳ Аналізую накладну...")
    file_id = update.message.document.file_id if update.message.document else update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    file_path = "invoice_raw.jpg"
    await file.download_to_drive(file_path)
    
    data = {}
    try:
        with open(file_path, "rb") as image:
            b64 = base64.b64encode(image.read()).decode('utf-8')
        
        prompt = """Аналізуй накладну. Витягни дані. 
        Відповідь JSON: {"is_readable": bool, "invoice_num": str, "date": str, "items": [{"name": str, "unit": str, "qty": float, "price": float}], "total_no_vat": float, "vat": float, "total_with_vat": float, "total_text": str}.
        Якщо нечитабельно, is_readable: false."""
        
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        )
        data = json.loads(response.choices[0].message.content)
        
        if not data.get("is_readable", True):
            await update.message.reply_text("🛑 Не вдалося розібрати накладну. Введи суму 'Всього до сплати' вручну:")
            context.user_data['temp_data'] = data
            return ASKING_FOR_TOTAL
        
        return await process_pdf(update, context, data)
    except Exception as e:
        await update.message.reply_text(f"Помилка обробки: {str(e)}")
        return ConversationHandler.END
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def receive_hint(update, context):
    data = context.user_data.get('temp_data')
    data['total_with_vat'] = float(update.message.text.replace(',', '.'))
    return await process_pdf(update, context, data)

async def process_pdf(update, context, data):
    with open("template.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    rows = ""
    for idx, it in enumerate(data.get('items', []), 1):
        rows += f"<tr><td>{idx}</td><td>{it.get('name', '')}</td><td>{it.get('unit', '')}</td><td>{it.get('qty', 0)}</td><td>{it.get('price', 0)}</td><td>{it.get('qty', 0)*it.get('price', 0)}</td></tr>"
    
    html = html.replace("{{items_rows}}", rows).replace("{{invoice_num}}", data.get("invoice_num", "-"))
    html = html.replace("{{total_with_vat}}", f"{data.get('total_with_vat', 0):.2f}")
    
    pdf_path = "Nakladna.pdf"
    pdfkit.from_string(html, pdf_path)
    
    await update.message.reply_document(document=open(pdf_path, 'rb'), filename="Nakladna.pdf")
    if os.path.exists(pdf_path): os.remove(pdf_path)
    return ConversationHandler.END

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo)],
        states={ASKING_FOR_TOTAL: [MessageHandler(filters.TEXT, receive_hint)]},
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)]
    )
    
    app.add_handler(conv_handler)
    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.updater.start_polling())
    loop.run_until_complete(app.start())
    loop.run_forever()
