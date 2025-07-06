import os
import sqlite3
import datetime
import calendar
import re
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

# Função para adicionar meses corretamente (lida com dias finais de mês)
def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)

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
                descricao TEXT NOT NULL,
                valor REAL NOT NULL,
                vencimento TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pendente', 'paga')),
                tipo TEXT NOT NULL CHECK(tipo IN ('simples', 'parcelada', 'semanal', 'mensal')),
                parcelas_restantes INTEGER
            )
        ''')

# Escape para MarkdownV2
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
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

def teclado_tipo_conta():
    tipos = [["Simples", "Parcelada"], ["Repetir Semanal", "Repetir Mensal"]]
    return ReplyKeyboardMarkup(tipos, resize_keyboard=True, one_time_keyboard=True)

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states.pop(user_id, None)
    temp_data.pop(user_id, None)
    await update.message.reply_text(
        "👋 Olá! Bem-vindo ao *Gerenciador de Despesas*! Use /help para ver comandos.",
        reply_markup=teclado_principal(),
        parse_mode="MarkdownV2"
    )

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

# Relatório por mês/ano (melhorado)
async def relatorio_por_mes(update: Update, mes: int, ano: int):
    mes_str = f"{mes:02d}"
    ano_str = str(ano)

    with get_db() as conn:
        contas = conn.execute(
            "SELECT * FROM contas WHERE strftime('%m', vencimento) = ? AND strftime('%Y', vencimento) = ? ORDER BY vencimento",
            (mes_str, ano_str)
        ).fetchall()

    if not contas:
        await update.message.reply_text(f"📊 Nenhuma conta encontrada para {mes_str}/{ano_str}.")
        return

    texto = f"📅 *Contas de {mes_str}/{ano_str}:*\n\n"
    total_pagas = 0.0
    total_pendentes = 0.0

    for c in contas:
        emoji = "✅" if c["status"] == "paga" else "⏳"
        parcelas_txt = ""
        if c["parcelas_restantes"] is not None:
            parcelas_txt = f" (parcelas restantes: {c['parcelas_restantes']})"
        texto += (
            f"{emoji} *{escape_markdown(c['descricao'])}* - R$`{c['valor']:.2f}` - "
            f"Venc: `{c['vencimento']}` - Tipo: `{escape_markdown(c['tipo'])}`{parcelas_txt}\n"
        )
        if c["status"] == "paga":
            total_pagas += c["valor"]
        else:
            total_pendentes += c["valor"]

    texto += (
        f"\n💰 *Total pago:* R$`{total_pagas:.2f}`\n"
        f"⌛ *Pendente:* R$`{total_pendentes:.2f}`"
    )
    await update.message.reply_text(texto, parse_mode="MarkdownV2")

# Função para renovar conta para próximo mês/semana se paga e repetida
def renovar_conta(conn, conta):
    """
    conta: sqlite3.Row
    """
    if conta["status"] != "paga":
        return  # só renova se paga

    tipo = conta["tipo"]
    parcelas_restantes = conta["parcelas_restantes"]
    descricao = conta["descricao"]
    valor = conta["valor"]
    vencimento = datetime.date.fromisoformat(conta["vencimento"])

    if tipo == "parcelada":
        if parcelas_restantes is not None and parcelas_restantes > 1:
            proximo_venc = add_months(vencimento, 1)
            conn.execute("""
                INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                VALUES (?, ?, ?, 'pendente', ?, ?)
            """, (descricao, valor, proximo_venc.isoformat(), tipo, parcelas_restantes - 1))
    elif tipo == "mensal":
        proximo_venc = add_months(vencimento, 1)
        conn.execute("""
            INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
            VALUES (?, ?, ?, 'pendente', ?, NULL)
        """, (descricao, valor, proximo_venc.isoformat(), tipo))
    elif tipo == "semanal":
        proximo_venc = vencimento + datetime.timedelta(weeks=1)
        conn.execute("""
            INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
            VALUES (?, ?, ?, 'pendente', ?, NULL)
        """, (descricao, valor, proximo_venc.isoformat(), tipo))
    # 'simples' não renova

# Handler dos botões inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    with get_db() as conn:
        if data.startswith("remover_"):
            try:
                idc = int(data.split("_")[1])
                conn.execute("DELETE FROM contas WHERE id = ?", (idc,))
                await query.edit_message_text("🗑️ Conta removida com sucesso!")
            except Exception as e:
                await query.edit_message_text(f"Erro ao remover: {e}")

        elif data.startswith("atualizar_"):
            try:
                idc = int(data.split("_")[1])
                temp_data[user_id] = {"id": idc}
                user_states[user_id] = "update_valor"
                await query.edit_message_text("Digite o *novo valor* da conta:", parse_mode="MarkdownV2")
            except Exception as e:
                await query.edit_message_text(f"Erro: {e}")

        elif data.startswith("pagar_"):
            try:
                idc = int(data.split("_")[1])
                conn.execute("UPDATE contas SET status = 'paga' WHERE id = ?", (idc,))
                conta = conn.execute("SELECT * FROM contas WHERE id = ?", (idc,)).fetchone()
                if conta:
                    renovar_conta(conn, conta)
                await query.edit_message_text("✅ Conta marcada como paga e renovada se aplicável!")
            except Exception as e:
                await query.edit_message_text(f"Erro ao marcar como paga: {e}")

# Salvar contas repetidas (parcelada, semanal ou mensal)
async def salvar_contas_repetidas(uid, update):
    tipo = temp_data[uid]["tipo"]
    parcelas = temp_data[uid].get("parcelas", 1)
    data_venc = datetime.date.fromisoformat(temp_data[uid]["vencimento"])
    descricao = temp_data[uid]["descricao"]
    valor = temp_data[uid]["valor"]

    with get_db() as conn:
        for i in range(parcelas):
            if tipo == "semanal":
                venc = data_venc + datetime.timedelta(weeks=i)
                parcelas_restantes = None
            elif tipo == "mensal":
                venc = add_months(data_venc, i)
                parcelas_restantes = None
            elif tipo == "parcelada":
                venc = add_months(data_venc, i)
                parcelas_restantes = parcelas - i
            else:
                venc = data_venc
                parcelas_restantes = None

            conn.execute("""
                INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                VALUES (?, ?, ?, 'pendente', ?, ?)
            """, (descricao, valor, venc.isoformat(), tipo, parcelas_restantes))

    await update.message.reply_text("💾 Contas salvas com sucesso!", reply_markup=teclado_principal())
    user_states.pop(uid, None)
    temp_data.pop(uid, None)

# Handler para mensagens de texto
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    texto = update.message.text.strip()
    estado = user_states.get(uid)

    # Comandos de botão do menu principal
    if texto == "🚀 Iniciar":
        await start(update, context)
        return
    elif texto == "➕ Adicionar Conta":
        user_states[uid] = "descricao"
        temp_data[uid] = {}
        await update.message.reply_text("Digite a descrição da conta:")
        return
    elif texto == "✅ Marcar Conta como Paga":
        await gerar_inline(update, "SELECT id, descricao FROM contas WHERE status = 'pendente'", "pagar_")
        return
    elif texto == "📊 Relatório Mensal":
        await relatorio_mensal(update)
        return
    elif texto == "📅 Relatório por Mês":
        user_states[uid] = "relatorio_mes"
        await update.message.reply_text("Digite o mês e o ano no formato mm/aaaa:")
        return
    elif texto == "❌ Remover Conta":
        await gerar_inline(update, "SELECT id, descricao FROM contas", "remover_")
        return
    elif texto == "📝 Atualizar Conta":
        await gerar_inline(update, "SELECT id, descricao FROM contas", "atualizar_")
        return
    elif texto.lower() == "/help":
        await help_command(update, context)
        return

    # Estados do fluxo guiado
    if estado == "relatorio_mes":
        try:
            mes, ano = map(int, texto.split("/"))
            if 1 <= mes <= 12 and ano >= 2000:
                await relatorio_por_mes(update, mes, ano)
            else:
                raise ValueError
        except:
            await update.message.reply_text("❌ Formato inválido. Use mm/aaaa e valores válidos.")
        user_states.pop(uid, None)
        return

    elif estado == "descricao":
        temp_data[uid]["descricao"] = texto
        user_states[uid] = "valor"
        await update.message.reply_text("Digite o valor (ex: 1234,56):")
        return

    elif estado == "valor":
        try:
            valor = float(texto.replace(",", "."))
            if valor <= 0:
                raise ValueError
            temp_data[uid]["valor"] = valor
            user_states[uid] = "vencimento"
            await update.message.reply_text("Digite o vencimento (dd/mm/aaaa):")
        except:
            await update.message.reply_text("❌ Valor inválido. Use número maior que zero.")
        return

    elif estado == "vencimento":
        try:
            data = datetime.datetime.strptime(texto, "%d/%m/%Y").date()
            if data < datetime.date.today() - datetime.timedelta(days=365):
                await update.message.reply_text("❌ Data muito antiga. Insira uma data válida.")
                return
            temp_data[uid]["vencimento"] = data.isoformat()
            user_states[uid] = "tipo_conta"
            await update.message.reply_text("Escolha o tipo da conta:", reply_markup=teclado_tipo_conta())
        except:
            await update.message.reply_text("❌ Data inválida. Use dd/mm/aaaa.")
        return

    elif estado == "tipo_conta":
        tipo = texto.lower()
        # Padronizando tipos recebidos
        if tipo in ["simples"]:
            temp_data[uid]["tipo"] = "simples"
            # Insere no banco
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
            await update.message.reply_text("💾 Conta simples adicionada com sucesso!", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)

        elif tipo == "parcelada":
            user_states[uid] = "parcelas"
            temp_data[uid]["tipo"] = "parcelada"
            await update.message.reply_text("Digite o número de parcelas (inteiro > 0):")
        elif tipo == "repetir semanal":
            temp_data[uid]["tipo"] = "semanal"
            temp_data[uid]["parcelas"] = 12  # Exemplo: 12 semanas padrão (3 meses)
            await salvar_contas_repetidas(uid, update)
            user_states.pop(uid, None)
        elif tipo == "repetir mensal":
            temp_data[uid]["tipo"] = "mensal"
            temp_data[uid]["parcelas"] = 12  # Exemplo: 12 meses padrão (1 ano)
            await salvar_contas_repetidas(uid, update)
            user_states.pop(uid, None)
        else:
            await update.message.reply_text("❌ Tipo inválido. Escolha uma opção válida do teclado.")
        return

    elif estado == "parcelas":
        try:
            parcelas = int(texto)
            if parcelas < 1 or parcelas > 100:
                raise ValueError
            temp_data[uid]["parcelas"] = parcelas
            await salvar_contas_repetidas(uid, update)
            user_states.pop(uid, None)
        except:
            await update.message.reply_text("❌ Número inválido. Digite um inteiro entre 1 e 100.")
        return

    elif estado == "update_valor":
        try:
            valor = float(texto.replace(",", "."))
            if valor <= 0:
                raise ValueError
            idc = temp_data[uid]["id"]
            with get_db() as conn:
                conn.execute("UPDATE contas SET valor = ? WHERE id = ?", (valor, idc))
            await update.message.reply_text("✅ Valor atualizado com sucesso!", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)
        except:
            await update.message.reply_text("❌ Valor inválido. Use número maior que zero.")
        return

# Função para gerar teclado inline para seleção de conta
async def gerar_inline(update: Update, query_sql: str, prefixo: str):
    with get_db() as conn:
        contas = conn.execute(query_sql).fetchall()
    if not contas:
        await update.message.reply_text("Nenhuma conta encontrada.")
        return

    buttons = []
    for c in contas:
        descricao = escape_markdown(c["descricao"])
        text_btn = f"{descricao} (R$ {c['valor']:.2f})"
        buttons.append([InlineKeyboardButton(text_btn, callback_data=f"{prefixo}{c['id']}")])
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Selecione uma conta:", reply_markup=reply_markup)

async def main():
    # Inicialização banco
    init_db()

    token = os.getenv("TOKEN_BOT_TELEGRAM")
    if not token:
        print("Erro: TOKEN_BOT_TELEGRAM não definido nas variáveis de ambiente.")
        return

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Usando nest_asyncio para rodar dentro do notebook, se for o caso
    nest_asyncio.apply()
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
