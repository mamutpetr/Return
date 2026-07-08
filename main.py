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
    
    # Підключаємо шрифт
    pdf.add_font('DejaVu', '', 'DejaVuSerif.ttf')
    pdf.set_font('DejaVu', '', 9)
    
    # --- ШАПКА 1С ---
    pdf.cell(35, 5, 'Одержувач:', border=0)
    pdf.cell(0, 5, 'ТОВ "МЕРЕЖА-СЕРВІС ЛЬВІВ", тел. 0800201800', ln=1)
    
    pdf.cell(35, 5, 'Постачальник:', border=0)
    pdf.multi_cell(0, 5, 'ПП "ТРОЯНДА-ЗАХІД", ЄДРПОУ 30275535, тел. 0322395800\nР/р UA873052990000026002021002174 в АТ КБ "ПРИВАТБАНК"\nІПН 302755313052, свідоцтво 17957486\nЛьвівська обл., м. Львів, вул. Повстанська, буд. 3А, кв. 8')
    
    pdf.cell(35, 5, 'Платник:', border=0)
    pdf.cell(0, 5, 'той самий', ln=1)
    
    pdf.cell(35, 5, 'Замовлення:', border=0)
    pdf.cell(0, 5, 'Без замовлення', ln=1)
    
    pdf.cell(35, 5, 'Умова продажу:', border=0)
    pdf.cell(0, 5, 'Безготівковий розрахунок', ln=1)
    
    pdf.ln(8)
    
    # --- ЗАГОЛОВОК ---
    pdf.set_font('DejaVu', '', 14)
    invoice_num = data.get("invoice_num", "________")
    pdf.cell(0, 6, f'Накладна на повернення № {invoice_num}', align='C', ln=1)
    pdf.set_font('DejaVu', '', 11)
    date = data.get("date", "________________")
    pdf.cell(0, 6, f'від {date}', align='C', ln=1)
    pdf.ln(6)
    
    # --- ТАБЛИЦЯ ---
    pdf.set_font('DejaVu', '', 9)
    col_widths = [10, 85, 15, 20, 30, 30]
    headers = ['№', 'Товар', 'Од.', 'Кількість', 'Ціна без ПДВ', 'Сума без ПДВ']
    
    # Малюємо заголовки колонок
    for i in range(len(headers)):
        pdf.cell(col_widths[i], 8, headers[i], border=1, align='C')
    pdf.ln()
    
    # Малюємо товари
    for idx, it in enumerate(data.get('items', []), 1):
        pdf.cell(col_widths[0], 8, str(idx), border=1, align='C')
        
        name = str(it.get('name', 'Товар'))
        if len(name) > 42:
            name = name[:39] + "..."
            
        pdf.cell(col_widths[1], 8, name, border=1)
        pdf.cell(col_widths[2], 8, str(it.get('unit', 'шт')), border=1, align='C')
        
        qty = float(it.get('qty', 0))
        price = float(it.get('price_no_vat', 0))
        if price == 0 and 'price' in it: # Запобіжник, якщо ШІ віддасть старий формат
            price = float(it.get('price', 0))
            
        sum_no_vat = qty * price
        
        # Формат 1С: кількість 3 знаки (1.000), ціна 6 знаків (87.900000)
        pdf.cell(col_widths[3], 8, f"{qty:.3f}", border=1, align='C')
        pdf.cell(col_widths[4], 8, f"{price:.6f}", border=1, align='C')
        pdf.cell(col_widths[5], 8, f"{sum_no_vat:.2f}", border=1, align='R')
        pdf.ln()
        
    pdf.ln(4)
    
    # --- БЛОК ПІДСУМКІВ (ТАБЛИЧКА З РАМКАМИ ЗНИЗУ СПРАВА) ---
    total_no_vat = float(data.get('total_no_vat', 0))
    vat = float(data.get('vat', 0))
    total_with_vat = float(data.get('total_with_vat', 0))
    
    pdf.set_font('DejaVu', '', 10)
    
    # Сумарна ширина таблиці = 190. Робимо відступ так, щоб табличка підсумків прилягала до правого краю
    label_x = 10 + 190 - 30 - 45
    
    # Разом без ПДВ
    pdf.set_x(label_x)
    pdf.cell(45, 8, 'Разом без ПДВ:', align='R')
    pdf.cell(30, 8, f'{total_no_vat:.2f}', border=1, align='R', ln=1)
    
    # ПДВ
    pdf.set_x(label_x)
    pdf.cell(45, 8, 'ПДВ:', align='R')
    pdf.cell(30, 8, f'{vat:.2f}', border=1, align='R', ln=1)
    
    # Всього з ПДВ
    pdf.set_x(label_x)
    pdf.cell(45, 8, 'Всього з ПДВ:', align='R')
    pdf.cell(30, 8, f'{total_with_vat:.2f}', border=1, align='R', ln=1)
    
    pdf.ln(8)
    
    # --- ФУТЕР ---
    total_text = data.get('total_text', '____________________')
    pdf.set_font('DejaVu', '', 9)
    pdf.cell(0, 6, 'Всього на суму:', ln=1)
    pdf.cell(0, 6, f'Сума прописом: {total_text}', ln=1)
    pdf.cell(0, 6, f'ПДВ: {vat:.2f} грн.', ln=1)
    
    pdf.ln(10)
    pdf.cell(95, 6, 'Отримав(ла) _______________________', align='L')
    pdf.cell(95, 6, 'Видав(ла) _______________________', align='R', ln=1)
    
    pdf.output(output_path)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Аналізую накладну на повернення...")
    file_id = update.message.document.file_id if update.message.document else update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    file_path = "invoice_raw.jpg"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as image:
            b64 = base64.b64encode(image.read()).decode('utf-8')
        
        prompt = """Аналізуй накладну. Поверни JSON: {"is_readable": bool, "invoice_num": str, "date": str, "items": [{"name": str, "unit": str, "qty": float, "price_no_vat": float}], "total_no_vat": float, "vat": float, "total_with_vat": float, "total_text": str}. Якщо нечитабельно, is_readable: false."""
        
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        )
        data = json.loads(response.choices[0].message.content)
        
        if not data.get("is_readable", True):
            await update.message.reply_text("🛑 Не вдалося розібрати. Введи загальну суму 'Всього з ПДВ' вручну:")
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
        total = float(update.message.text.replace(',', '.'))
        data['total_with_vat'] = total
        data['total_no_vat'] = total / 1.2
        data['vat'] = total - data['total_no_vat']
    except ValueError:
        await update.message.reply_text("Будь ласка, введи коректне число (наприклад, 100.50):")
        return ASKING_FOR_TOTAL
    return await process_pdf(update, context, data)

async def process_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict):
    pdf_path = "Nakladna.pdf"
    
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
