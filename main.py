import os
import json
import asyncio
import base64
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, ConversationHandler, CommandHandler
from openai import OpenAI
from fpdf import FPDF

# Налаштування логування
logging.basicConfig(level=logging.INFO)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASKING_FOR_TOTAL = 1

def create_invoice_pdf(data, output_path):
    pdf = FPDF()
    pdf.add_page()
    
    # Підключаємо шрифт намертво (DejaVuSerif.ttf має бути в корені)
    pdf.add_font('DejaVu', '', 'DejaVuSerif.ttf')
    
    # --- ШАПКА ---
    pdf.set_font('DejaVu', '', 10)
    pdf.cell(0, 5, 'Одержувач: ТОВ "МЕРЕЖА-СЕРВІС ЛЬВІВ"', ln=1)
    pdf.cell(0, 5, 'Постачальник: ПП "ТРОЯНДА-ЗАХІД"', ln=1)
    pdf.ln(10)
    
    # --- ЗАГОЛОВОК ---
    pdf.set_font('DejaVu', '', 14)
    invoice_title = f'Накладна № {data.get("invoice_num", "-")} від {data.get("date", "-")}'
    pdf.cell(0, 10, invoice_title, align='C', ln=1)
    pdf.ln(5)
    
    # --- ТАБЛИЦЯ ---
    pdf.set_font('DejaVu', '', 10)
    # Задаємо ширину колонок: № (10), Товар (80), Од (20), К-ть (20), Ціна (30), Сума (30)
    col_widths = [10, 80, 20, 20, 30, 30]
    headers = ['№', 'Товар', 'Од.', 'К-ть', 'Ціна', 'Сума']
    
    # Малюємо заголовки колонок
    for i in range(len(headers)):
        pdf.cell(col_widths[i], 8, headers[i], border=1, align='C')
    pdf.ln()
    
    # Малюємо товари
    for idx, it in enumerate(data.get('items', []), 1):
        pdf.cell(col_widths[0], 8, str(idx), border=1, align='C')
        
        # Запобіжник: якщо назва товару дуже довга, обрізаємо її, щоб не зламалась таблиця
        name = str(it.get('name', 'Товар'))
        if len(name) > 42:
            name = name[:39] + "..."
            
        pdf.cell(col_widths[1], 8, name, border=1)
        pdf.cell(col_widths[2], 8, str(it.get('unit', '-')), border=1, align='C')
        pdf.cell(col_widths[3], 8, str(it.get('qty', 0)), border=1, align='C')
        pdf.cell(col_widths[4], 8, f"{float(it.get('price', 0)):.2f}", border=1, align='C')
        pdf.cell(col_widths[5], 8, f"{float(it.get('qty', 0)) * float(it.get('price', 0)):.2f}", border=1, align='C')
        pdf.ln()
        
    pdf.ln(5)
    
    # --- ВСЬОГО ---
    pdf.set_font('DejaVu', '', 12)
    total_str = f'Всього з ПДВ: {data.get("total_with_vat", 0):.2f} грн.'
    pdf.cell(0, 10, total_str, align='R', ln=1)
    
    # Зберігаємо файл
    pdf.output(output_path)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Аналізую накладну...")
    file_id = update.message.document.file_id if update.message.document else update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    file_path = "invoice_raw.jpg"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as image:
            b64 = base64.b64encode(image.read()).decode('utf-8')
        
        prompt = """Аналізуй накладну. Поверни JSON: {"is_readable": bool, "invoice_num": str, "date": str, "items": [{"name": str, "unit": str, "qty": float, "price": float}], "total_with_vat": float}. Якщо нечитабельно, is_readable: false."""
        
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        )
        data = json.loads(response.choices[0].message.content)
        
        if not data.get("is_readable", True):
            await update.message.reply_text("🛑 Не вдалося розібрати. Введи суму вручну:")
            context.user_data['temp_data'] = data
            return ASKING_FOR_TOTAL
            
        return await process_pdf(update, context, data)
    except Exception as e:
        await update.message.reply_text(f"Помилка: {str(e)}")
        return ConversationHandler.END
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def receive_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('temp_data')
    try:
        data['total_with_vat'] = float(update.message.text.replace(',', '.'))
    except ValueError:
        await update.message.reply_text("Будь ласка, введи коректне число (наприклад, 100.50):")
        return ASKING_FOR_TOTAL
    return await process_pdf(update, context, data)

async def process_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict):
    pdf_path = "Nakladna.pdf"
    
    # Викликаємо нову генерацію через fpdf2
    create_invoice_pdf(data, pdf_path)
    
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
    
    print("Бот запущено через ручний Event Loop")
    
    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.updater.start_polling())
    loop.run_until_complete(app.start())
    
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(app.stop())
        loop.run_until_complete(app.shutdown())
