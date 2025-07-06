import os
import sqlite3
import datetime
import calendar
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
import re

# Estados e dados temporários por usuário
user_states = {}
temp_data = {}

# Função para adicionar meses corretamente (evita problemas com dias finais de mês)
def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)

# Banco de dados
def get_db():
    return sqlite3.connect("despesas.db")

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

# Escape para MarkdownV2 (segura a mensagem para envio com parse_mode=MarkdownV2)
def escape_markdown(text):
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

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

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Bem-vindo ao *Gerenciador de Despesas*! Use /help para ver comandos.",
        reply_markup=teclado_principal(),
        parse_mode="MarkdownV2"
    )
    user_states.pop(update.message.from_user.id, None)
    temp_data.pop(update.message.from_user.id, None)

# Comando /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "*Comandos e opções disponíveis:*\n\n"
        "🚀 Iniciar - Reinicia o bot\n"
        "➕ Adicionar Conta - Cadastra nova conta\n"
        "✅ Marcar Conta como Paga - Marca conta pendente como paga e renova se parcelada/repetida\n"
        "📊 Relatório Mensal - Mostra relatório do mês atual\n"
        "📅 Relatório por Mês - Mostra relatório para mês/ano específico\n"
        "📝 Atualizar Conta - Atualiza valor da conta\n"
        "❌ Remover Conta - Remove uma conta cadastrada\n"
    )
    await update.message.reply_text(texto, parse_mode="MarkdownV2")

# Relatório mensal automático
async def relatorio_mensal(update: Update):
    hoje = datetime.date.today()
    await relatorio_por_mes(update, hoje.month, hoje.year)

# Relatório por mês/ano (com melhorias)
async def relatorio_por_mes(update: Update, mes: int, ano: int):
    mes_str, ano_str = f"{mes:02d}", str(ano)
    with get_db() as conn:
        contas = conn.execute(
            "SELECT id, descricao, valor, vencimento, status, tipo, parcelas_restantes FROM contas "
            "WHERE strftime('%m', vencimento) = ? AND strftime('%Y', vencimento) = ?",
            (mes_str, ano_str)
        ).fetchall()

    if not contas:
        await update.message.reply_text(f"📊 Nenhuma conta encontrada para {mes_str}/{ano_str}.")
        return

    texto = f"📅 *Contas de {mes_str}/{ano_str}:*\n\n"
    total_pagas = total_pendentes = 0
    for idc, desc, val, venc, status, tipo, parcelas_restantes in contas:
        emoji = "✅" if status == "paga" else "⏳"
        parcelas_txt = ""
        if parcelas_restantes is not None:
            parcelas_txt = f" (parcelas restantes: {parcelas_restantes})"
        texto += f"{emoji} *{escape_markdown(desc)}* - R$`{val:.2f}` - Venc: `{venc}` - Tipo: `{tipo}`{parcelas_txt}\n"
        if status == "paga":
            total_pagas += val
        else:
            total_pendentes += val
    texto += f"\n💰 *Total pago:* R$`{total_pagas:.2f}`\n⌛ *Pendente:* R$`{total_pendentes:.2f}`"

    await update.message.reply_text(texto, parse_mode="MarkdownV2")

# Função para renovar conta para próximo mês se for parcelada ou mensal repetida
def renovar_conta(conn, conta):
    """
    conta: (id, descricao, valor, vencimento, status, tipo, parcelas_restantes)
    """
    idc, descricao, valor, vencimento, status, tipo, parcelas_restantes = conta
    if status != "paga":
        return  # só renova se paga

    # Se tipo parcelada com parcelas_restantes > 1, cria próxima parcela diminuindo 1 parcela
    if tipo == "parcelada" and parcelas_restantes and parcelas_restantes > 1:
        data_venc = datetime.date.fromisoformat(vencimento)
        proximo_venc = add_months(data_venc, 1)
        conn.execute("""
            INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
            VALUES (?, ?, ?, 'pendente', ?, ?)
        """, (descricao, valor, proximo_venc.isoformat(), tipo, parcelas_restantes - 1))
        return

    # Se tipo mensal repetida (tipo == "mensal"), cria nova conta igual no próximo mês
    if tipo == "mensal":
        data_venc = datetime.date.fromisoformat(vencimento)
        proximo_venc = add_months(data_venc, 1)
        conn.execute("""
            INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
            VALUES (?, ?, ?, 'pendente', ?, NULL)
        """, (descricao, valor, proximo_venc.isoformat(), tipo))
        return

# Handler dos botões inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    with get_db() as conn:
        if data.startswith("remover_"):
            idc = int(data.split("_")[1])
            conn.execute("DELETE FROM contas WHERE id = ?", (idc,))
            await query.edit_message_text("🗑️ Conta removida com sucesso!")

        elif data.startswith("atualizar_"):
            idc = int(data.split("_")[1])
            temp_data[uid] = {"id": idc}
            user_states[uid] = "update_valor"
            await query.edit_message_text("Digite o *novo valor* da conta:", parse_mode="MarkdownV2")

        elif data.startswith("pagar_"):
            idc = int(data.split("_")[1])
            # Atualiza status para paga
            conn.execute("UPDATE contas SET status = 'paga' WHERE id = ?", (idc,))
            # Busca conta para renovação
            conta = conn.execute("SELECT * FROM contas WHERE id = ?", (idc,)).fetchone()
            renovar_conta(conn, conta)
            await query.edit_message_text("✅ Conta marcada como paga e renovada se aplicável!")

# Salvar contas repetidas (semanal ou mensal ou parcelada)
async def salvar_contas_repetidas(uid, update):
    tipo = temp_data[uid]["tipo"]
    parcelas = temp_data[uid]["parcelas"]
    data = datetime.date.fromisoformat(temp_data[uid]["vencimento"])

    with get_db() as conn:
        for i in range(parcelas):
            if tipo == "semanal":
                venc = data + datetime.timedelta(weeks=i)
            elif tipo == "mensal":
                venc = add_months(data, i)
            else:  # parcelada
                venc = add_months(data, i)
            conn.execute("""
                INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                VALUES (?, ?, ?, 'pendente', ?, ?)
            """, (
                temp_data[uid]["descricao"],
                temp_data[uid]["valor"],
                venc.isoformat(),
                tipo,
                parcelas - i
            ))
    await update.message.reply_text("💾 Contas salvas com sucesso!", reply_markup=teclado_principal())
    user_states.pop(uid, None)
    temp_data.pop(uid, None)

# Handler para mensagens de texto
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    texto = update.message.text.strip()
    estado = user_states.get(uid)

    # Ações diretas por botão
    if texto == "🚀 Iniciar":
        await start(update, context)
    elif texto == "➕ Adicionar Conta":
        user_states[uid] = "descricao"
        temp_data[uid] = {}
        await update.message.reply_text("Digite a descrição da conta:")
    elif texto == "✅ Marcar Conta como Paga":
        await gerar_inline(update, "SELECT id, descricao FROM contas WHERE status = 'pendente'", "pagar_")
    elif texto == "📊 Relatório Mensal":
        await relatorio_mensal(update)
    elif texto == "📅 Relatório por Mês":
        user_states[uid] = "relatorio_mes"
        await update.message.reply_text("Digite o mês e o ano no formato mm/aaaa:")
    elif texto == "❌ Remover Conta":
        await gerar_inline(update, "SELECT id, descricao FROM contas", "remover_")
    elif texto == "📝 Atualizar Conta":
        await gerar_inline(update, "SELECT id, descricao FROM contas", "atualizar_")
    elif texto == "/help":
        await help_command(update, context)

    # Estados guiados
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
            await update.message.reply_text("Essa conta é:", reply_markup=teclado_tipo_conta())
        except:
            await update.message.reply_text("❌ Data inválida.")

    elif estado == "tipo_conta":
        tipo = texto.lower()
        if tipo == "parcelada":
            user_states[uid] = "parcelas"
            temp_data[uid]["tipo"] = "parcelada"
            await update.message.reply_text("Quantas parcelas?")
        elif tipo == "repetir semanal":
            temp_data[uid].update({"tipo": "semanal", "parcelas": 52})
            await salvar_contas_repetidas(uid, update)
        elif tipo == "repetir mensal":
            temp_data[uid].update({"tipo": "mensal", "parcelas": 12})
            await salvar_contas_repetidas(uid, update)
        elif tipo == "simples":
            temp_data[uid]["tipo"] = "simples"
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                    VALUES (?, ?, ?, 'pendente', ?, NULL)
                """, (
                    temp_data[uid]["descricao"],
                    temp_data[uid]["valor"],
                    temp_data[uid]["vencimento"],
                    "simples"
                ))
            await update.message.reply_text("💾 Conta adicionada com sucesso!", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)
        else:
            await update.message.reply_text("❌ Tipo inválido. Escolha uma opção do teclado.")

    elif estado == "parcelas":
        try:
            parcelas = int(texto)
            if parcelas < 1:
                raise ValueError
            temp_data[uid]["parcelas"] = parcelas
            await salvar_contas_repetidas(uid, update)
        except:
            await update.message.reply_text("❌ Número inválido de parcelas.")

    elif estado == "update_valor":
        try:
            novo_valor = float(texto.replace(",", "."))
            idc = temp_data[uid]["id"]
            with get_db() as conn:
                conn.execute("UPDATE contas SET valor = ? WHERE id = ?", (novo_valor, idc))
            await update.message.reply_text("✅ Valor atualizado com sucesso!", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)
        except:
            await update.message.reply_text("❌ Valor inválido.")

# Função genérica para criar botões inline a partir de consulta SQL
async def gerar_inline(update, sql, prefixo):
    with get_db() as conn:
        contas = conn.execute(sql).fetchall()
    if not contas:
        await update.message.reply_text("Nenhuma conta encontrada.")
        return
    keyboard = [[InlineKeyboardButton(desc, callback_data=f"{prefixo}{idc}")] for idc, desc in contas]
    await update.message.reply_text("Selecione uma opção:", reply_markup=InlineKeyboardMarkup(keyboard))

# Execução Railway-safe
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
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        app.add_handler(CallbackQueryHandler(button_handler))
        print("✅ Bot rodando no Railway...")
        await app.run_polling()

    asyncio.get_event_loop().run_until_complete(main())
