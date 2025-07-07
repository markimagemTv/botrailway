import os
import sqlite3
import datetime
import nest_asyncio
import asyncio
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# Configurar log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Banco de dados

def get_db():
    conn = sqlite3.connect("despesas.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS contas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                descricao TEXT,
                valor REAL,
                vencimento TEXT,
                status TEXT,
                tipo TEXT,
                parcelas_restantes INTEGER
            )
        ''')

# Utilitários
def add_months(orig_date, months):
    year = orig_date.year + (orig_date.month + months - 1) // 12
    month = (orig_date.month + months - 1) % 12 + 1
    day = min(orig_date.day, 28)  # evita problemas com fevereiro
    return datetime.date(year, month, day)

# Estados e dados temporários
user_states = {}
temp_data = {}

# Teclados
def teclado_principal():
    buttons = [
        [KeyboardButton("🚀 Iniciar")],
        [KeyboardButton("➕ Adicionar Conta")],
        [KeyboardButton("✅ Marcar Conta como Paga")],
        [KeyboardButton("📊 Relatório Mensal")],
        [KeyboardButton("📅 Relatório por Mês")],
        [KeyboardButton("📝 Atualizar Conta")],
        [KeyboardButton("❌ Remover Conta")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def teclado_tipo_conta():
    tipos = [["Simples", "Parcelada"], ["Repetir Semanal", "Repetir Mensal"]]
    return ReplyKeyboardMarkup(tipos, resize_keyboard=True, one_time_keyboard=True)

# Comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Bem-vindo ao *Gerenciador de Despesas*!",
        reply_markup=teclado_principal(),
        parse_mode="Markdown"
    )
    user_states.pop(update.message.from_user.id, None)
    temp_data.pop(update.message.from_user.id, None)

# Handler de mensagens
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... mantido igual, conforme já trabalhado anteriormente ...
    pass

# Handler de botões inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    with get_db() as conn:
        if data.startswith("pagar_"):
            idc = int(data.split("_")[1])
            cursor = conn.execute("SELECT * FROM contas WHERE id = ?", (idc,))
            conta = cursor.fetchone()
            if not conta:
                await query.edit_message_text("⚠️ Conta não encontrada.")
                return

            if conta["status"] == "paga":
                await query.edit_message_text("⚠️ Esta conta já está marcada como paga.")
                return

            conn.execute("UPDATE contas SET status = 'paga' WHERE id = ?", (idc,))
            conn.commit()
            temp_data[uid] = {"conta": dict(conta)}

            await query.edit_message_text(
                "✅ Conta marcada como paga!\n\nDeseja repetir essa conta para o próximo mês?",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔁 Sim", callback_data="repetir_sim"),
                        InlineKeyboardButton("❌ Não", callback_data="repetir_nao")
                    ]
                ])
            )

        elif data == "repetir_sim":
            conta = temp_data.get(uid, {}).get("conta")
            if not conta:
                await query.edit_message_text("❌ Erro ao repetir conta.")
                return

            venc_atual = datetime.date.fromisoformat(conta["vencimento"])
            novo_venc = add_months(venc_atual, 1)

            conn.execute("""
                INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                VALUES (?, ?, ?, 'pendente', ?, ?)
            """, (
                conta["descricao"],
                conta["valor"],
                novo_venc.isoformat(),
                conta["tipo"],
                conta["parcelas_restantes"] or 1
            ))
            conn.commit()
            await query.edit_message_text("🔁 Conta repetida para o próximo mês com sucesso!")
            temp_data.pop(uid, None)

        elif data == "repetir_nao":
            await query.edit_message_text("✅ Conta paga. Nenhuma repetição foi criada.")
            temp_data.pop(uid, None)

# Execução principal

def main():
    init_db()
    nest_asyncio.apply()  # Railway e Jupyter friendly

    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("Variável BOT_TOKEN não encontrada!")

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot iniciado!")
    application.run_polling()

if __name__ == "__main__":
    main()
