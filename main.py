import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime

# Dicionário em memória para armazenar despesas por usuário
despesas = {}

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Eu estou funcionando no Railway 😎\nUse /add, /listar ou /limpar para gerenciar suas despesas.")

# Comando /add valor descrição
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Uso correto: /add valor descrição\nEx: /add 50 almoço")
        return

    try:
        valor = float(context.args[0])
        descricao = ' '.join(context.args[1:])
        data = datetime.now().strftime('%d/%m/%Y %H:%M')

        if user_id not in despesas:
            despesas[user_id] = []

        despesas[user_id].append({"valor": valor, "descricao": descricao, "data": data})
        await update.message.reply_text(f"✅ Despesa adicionada: R${valor:.2f} - {descricao}")
    except ValueError:
        await update.message.reply_text("❌ Valor inválido. Use um número. Ex: /add 25 café")

# Comando /listar
async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in despesas or not despesas[user_id]:
        await update.message.reply_text("Você ainda não registrou nenhuma despesa.")
        return

    total = 0
    mensagem = "📋 Suas despesas:\n"
    for item in despesas[user_id]:
        mensagem += f"- R${item['valor']:.2f} | {item['descricao']} ({item['data']})\n"
        total += item['valor']
    mensagem += f"\n💰 Total: R${total:.2f}"
    await update.message.reply_text(mensagem)

# Comando /limpar
async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    despesas[user_id] = []
    await update.message.reply_text("🧹 Todas as suas despesas foram apagadas.")

# Inicialização
if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")

    if not TOKEN:
        print("⚠️ BOT_TOKEN não encontrado. Configure como variável de ambiente.")
        exit()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("limpar", limpar))

    print("✅ Bot iniciado...")
    app.run_polling()
