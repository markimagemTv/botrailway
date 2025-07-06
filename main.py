import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Eu estou funcionando no Railway 😎")

# Inicialização
if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    
    if not TOKEN:
        print("⚠️ BOT_TOKEN não encontrado. Configure como variável de ambiente.")
        exit()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    print("✅ Bot iniciado...")
    app.run_polling()
