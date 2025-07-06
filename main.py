import os
import sqlite3
import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import nest_asyncio
import asyncio

# Estados e dados temporários por usuário
user_states = {}
temp_data = {}

# Banco de dados
def init_db():
    conn = sqlite3.connect("despesas.db")
    c = conn.cursor()
    c.execute('''
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
    conn.commit()
    conn.close()

# Teclado principal
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

# Comando /start ou botão iniciar
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Bem-vindo ao Gerenciador de Despesas.",
        reply_markup=teclado_principal()
    )
    user_states.pop(update.message.from_user.id, None)
    temp_data.pop(update.message.from_user.id, None)

# Relatório por mês atual
async def relatorio_mensal(update: Update):
    hoje = datetime.date.today()
    await relatorio_por_mes(update, hoje.month, hoje.year)

# Relatório por mês específico
async def relatorio_por_mes(update: Update, mes: int, ano: int):
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    conn = sqlite3.connect("despesas.db")
    c = conn.cursor()
    c.execute("SELECT descricao, valor, vencimento, status FROM contas WHERE strftime('%m', vencimento) = ? AND strftime('%Y', vencimento) = ?", (mes_str, ano_str))
    contas = c.fetchall()
    conn.close()

    if not contas:
        await update.message.reply_text(f"📊 Nenhuma conta encontrada para {mes_str}/{ano_str}.")
        return

    texto = f"📊 Contas de {mes_str}/{ano_str}:\n\n"
    total_pagas = sum(val for _, val, _, status in contas if status == 'paga')
    total_pendentes = sum(val for _, val, _, status in contas if status != 'paga')

    for desc, val, venc, status in contas:
        emoji = "✅" if status == "paga" else "⏳"
        texto += f"{emoji} {desc} - R$ {val:.2f} - Venc: {venc}\n-----------\n"

    texto += f"\n💰 Pago: R$ {total_pagas:.2f} | ⌛ Pendente: R$ {total_pendentes:.2f}"
    await update.message.reply_text(texto)

# Botões Inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    conn = sqlite3.connect("despesas.db")
    c = conn.cursor()

    if data.startswith("remover_"):
        idc = int(data.split("_")[1])
        c.execute("DELETE FROM contas WHERE id = ?", (idc,))
        await query.edit_message_text("🗑️ Conta removida com sucesso!")

    elif data.startswith("atualizar_"):
        idc = int(data.split("_")[1])
        temp_data[uid] = {"id": idc}
        user_states[uid] = "update_valor"
        await query.edit_message_text("Digite o novo valor da conta:")

    elif data.startswith("pagar_"):
        idc = int(data.split("_")[1])
        c.execute("UPDATE contas SET status = 'paga' WHERE id = ?", (idc,))
        await query.edit_message_text("✅ Conta marcada como paga!")

    conn.commit()
    conn.close()

# Repetição mensal/semanal/parcelada
async def salvar_contas_repetidas(uid, update):
    tipo = temp_data[uid]["tipo"]
    parcelas = temp_data[uid]["parcelas"]
    data = datetime.datetime.fromisoformat(temp_data[uid]["vencimento"])
    conn = sqlite3.connect("despesas.db")
    c = conn.cursor()
    for i in range(parcelas):
        venc = data + datetime.timedelta(weeks=i) if tipo == "semanal" else data + datetime.timedelta(days=30 * i)
        c.execute("INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes) VALUES (?, ?, ?, 'pendente', ?, ?)",
                  (temp_data[uid]["descricao"], temp_data[uid]["valor"], venc.date().isoformat(), tipo, parcelas - i))
    conn.commit()
    conn.close()
    await update.message.reply_text("💾 Conta adicionada com sucesso!", reply_markup=teclado_principal())
    user_states.pop(uid, None)
    temp_data.pop(uid, None)

# Tratamento de mensagens
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    texto = update.message.text
    estado = user_states.get(uid)

    if texto == "🚀 Iniciar":
        await start(update, context)
    elif texto == "➕ Adicionar Conta":
        user_states[uid] = "descricao"
        temp_data[uid] = {}
        await update.message.reply_text("Digite a descrição da conta:")
    elif texto == "✅ Marcar Conta como Paga":
        conn = sqlite3.connect("despesas.db")
        c = conn.cursor()
        c.execute("SELECT id, descricao FROM contas WHERE status = 'pendente'")
        contas = c.fetchall()
        conn.close()
        if contas:
            keyboard = [[InlineKeyboardButton(desc, callback_data=f"pagar_{idc}")] for idc, desc in contas]
            await update.message.reply_text("Selecione a conta paga:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text("Nenhuma conta pendente.")
    elif texto == "📊 Relatório Mensal":
        await relatorio_mensal(update)
    elif texto == "📅 Relatório por Mês":
        user_states[uid] = "relatorio_mes"
        await update.message.reply_text("Digite o mês e o ano (mm/aaaa):")
    elif texto == "❌ Remover Conta":
        conn = sqlite3.connect("despesas.db")
        c = conn.cursor()
        c.execute("SELECT id, descricao FROM contas")
        contas = c.fetchall()
        conn.close()
        if contas:
            keyboard = [[InlineKeyboardButton(desc, callback_data=f"remover_{idc}")] for idc, desc in contas]
            await update.message.reply_text("Selecione a conta a remover:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text("Nenhuma conta encontrada.")
    elif texto == "📝 Atualizar Conta":
        conn = sqlite3.connect("despesas.db")
        c = conn.cursor()
        c.execute("SELECT id, descricao FROM contas")
        contas = c.fetchall()
        conn.close()
        if contas:
            keyboard = [[InlineKeyboardButton(desc, callback_data=f"atualizar_{idc}")] for idc, desc in contas]
            await update.message.reply_text("Selecione a conta a atualizar:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text("Nenhuma conta encontrada.")
    elif estado == "relatorio_mes":
        try:
            mes, ano = map(int, texto.split("/"))
            await relatorio_por_mes(update, mes, ano)
        except:
            await update.message.reply_text("❌ Formato inválido. Use mm/aaaa.")
        user_states.pop(uid, None)
    elif estado == "descricao":
        temp_data[uid]["descricao"] = texto
        user_states[uid] = "valor"
        await update.message.reply_text("Digite o valor (ex: 1234,56):")
    elif estado == "valor":
        try:
            temp_data[uid]["valor"] = float(texto.replace(",", "."))
            user_states[uid] = "vencimento"
            await update.message.reply_text("Digite o vencimento (dd/mm/aaaa):")
        except:
            await update.message.reply_text("❌ Valor inválido.")
    elif estado == "vencimento":
        try:
            data = datetime.datetime.strptime(texto, "%d/%m/%Y").date()
            temp_data[uid]["vencimento"] = data.isoformat()
            user_states[uid] = "tipo_conta"
            await update.message.reply_text("Essa conta é:", reply_markup=ReplyKeyboardMarkup(
                [["Simples", "Parcelada", "Repetir Semanal", "Repetir Mensal"]], resize_keyboard=True))
        except:
            await update.message.reply_text("❌ Data inválida.")
    elif estado == "tipo_conta":
        tipo = texto.lower()
        if tipo == "parcelada":
            user_states[uid] = "parcelas"
            temp_data[uid]["tipo"] = "parcelada"
            await update.message.reply_text("Quantas parcelas?")
        elif tipo == "repetir semanal":
            temp_data[uid]["tipo"] = "semanal"
            temp_data[uid]["parcelas"] = 52
            await salvar_contas_repetidas(uid, update)
        elif tipo == "repetir mensal":
            temp_data[uid]["tipo"] = "mensal"
            temp_data[uid]["parcelas"] = 12
            await salvar_contas_repetidas(uid, update)
        else:
            temp_data[uid]["tipo"] = "simples"
            conn = sqlite3.connect("despesas.db")
            c = conn.cursor()
            c.execute("INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes) VALUES (?, ?, ?, 'pendente', ?, NULL)",
                      (temp_data[uid]["descricao"], temp_data[uid]["valor"], temp_data[uid]["vencimento"], "simples"))
            conn.commit()
            conn.close()
            await update.message.reply_text("💾 Conta adicionada com sucesso!", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)
    elif estado == "parcelas":
        try:
            temp_data[uid]["parcelas"] = int(texto)
            await salvar_contas_repetidas(uid, update)
        except:
            await update.message.reply_text("❌ Número inválido de parcelas.")

# Execução segura no Railway
if __name__ == "__main__":
    nest_asyncio.apply()

    async def main():
        print("🔄 Inicializando...")
        init_db()
        token = os.getenv("BOT_TOKEN")
        if not token:
            print("❌ BOT_TOKEN não encontrado.")
            return
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        app.add_handler(CallbackQueryHandler(button_handler))
        print("✅ Bot rodando no Railway...")
        await app.run_polling()

    asyncio.get_event_loop().run_until_complete(main())
