import os
import sqlite3
import datetime
import logging
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_states = {}
temp_data = {}

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
        conn.commit()

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

def add_months(dt, months):
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, [31,
                       29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                       31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month-1])
    return datetime.date(year, month, day)

def data_str_para_iso(data_str):
    dia, mes, ano = map(int, data_str.split("/"))
    dt = datetime.date(ano, mes, dia)
    return dt.isoformat()

def data_iso_para_str(data_iso):
    dt = datetime.date.fromisoformat(data_iso)
    return dt.strftime("%d/%m/%Y")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Bem-vindo ao *Gerenciador de Despesas*!",
        reply_markup=teclado_principal(),
        parse_mode="Markdown"
    )
    user_states.pop(update.message.from_user.id, None)
    temp_data.pop(update.message.from_user.id, None)

async def relatorio_mensal(update: Update):
    hoje = datetime.date.today()
    await relatorio_por_mes(update, hoje.month, hoje.year)

async def relatorio_por_mes(update: Update, mes: int, ano: int):
    mes_str, ano_str = f"{mes:02d}", str(ano)
    with get_db() as conn:
        contas = conn.execute(
            "SELECT descricao, valor, vencimento, status FROM contas "
            "WHERE strftime('%m', vencimento) = ? AND strftime('%Y', vencimento) = ?",
            (mes_str, ano_str)
        ).fetchall()

    if not contas:
        await update.message.reply_text(f"📊 Nenhuma conta encontrada para {mes_str}/{ano_str}.")
        return

    texto = f"📅 *Contas de {mes_str}/{ano_str}:*\n\n"
    total_pagas = total_pendentes = 0
    for desc, val, venc, status in contas:
        emoji = "✅" if status == "paga" else "⏳"
        texto += f"{emoji} *{desc}* - R${val:.2f} - Venc: `{data_iso_para_str(venc)}`\n"
        if status == "paga":
            total_pagas += val
        else:
            total_pendentes += val
    texto += f"\n💰 *Total pago:* R${total_pagas:.2f}\n⌛ *Pendente:* R${total_pendentes:.2f}"

    await update.message.reply_text(texto, parse_mode="Markdown")

def renovar_conta(conn, conta):
    tipo = conta["tipo"]
    if tipo in ("mensal", "semanal"):
        parcelas_restantes = conta["parcelas_restantes"]
        if parcelas_restantes and parcelas_restantes > 1:
            vencimento_atual = datetime.date.fromisoformat(conta["vencimento"])
            if tipo == "mensal":
                novo_venc = add_months(vencimento_atual, 1)
            else:
                novo_venc = vencimento_atual + datetime.timedelta(weeks=1)

            conn.execute("""
                INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                VALUES (?, ?, ?, 'pendente', ?, ?)
            """, (
                conta["descricao"],
                conta["valor"],
                novo_venc.isoformat(),
                tipo,
                parcelas_restantes - 1
            ))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data
    logger.info(f"Callback recebido: {data} do usuário {uid}")

    try:
        with get_db() as conn:
            if data.startswith("remover_"):
                idc = int(data.split("_")[1])
                cursor = conn.execute("DELETE FROM contas WHERE id = ?", (idc,))
                if cursor.rowcount == 0:
                    await query.edit_message_text("⚠️ Conta não encontrada ou já removida.")
                else:
                    await query.edit_message_text("🗑️ Conta removida com sucesso!")
                conn.commit()

            elif data.startswith("atualizar_"):
                idc = int(data.split("_")[1])
                temp_data[uid] = {"id": idc}
                user_states[uid] = "update_valor"
                await query.edit_message_text("Digite o *novo valor* da conta:", parse_mode="Markdown")

            elif data.startswith("pagar_"):
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
                renovar_conta(conn, conta)
                conn.commit()
                await query.edit_message_text("✅ Conta marcada como paga e renovada se aplicável!")

            else:
                await query.edit_message_text("❌ Ação não reconhecida.")

    except Exception as e:
        logger.error(f"Erro no button_handler: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ocorreu um erro: {e}")

async def salvar_contas_repetidas(uid, update):
    tipo = temp_data[uid]["tipo"]
    parcelas = temp_data[uid]["parcelas"]
    data_venc = datetime.date.fromisoformat(temp_data[uid]["vencimento"])

    with get_db() as conn:
        for i in range(parcelas):
            if tipo == "semanal":
                venc = data_venc + datetime.timedelta(weeks=i)
            else:
                venc = add_months(data_venc, i)

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
        conn.commit()

    await update.message.reply_text("💾 Contas salvas com sucesso!", reply_markup=teclado_principal())
    user_states.pop(uid, None)
    temp_data.pop(uid, None)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    texto = update.message.text.strip()
    estado = user_states.get(uid)

    if texto == "🚀 Iniciar":
        await start(update, context)
        return
    elif texto == "➕ Adicionar Conta":
        user_states[uid] = "descricao"
        temp_data[uid] = {}
        await update.message.reply_text("Digite a descrição da conta:")
        return
    elif texto == "✅ Marcar Conta como Paga":
        await gerar_inline(update, "SELECT id, descricao, valor FROM contas WHERE status = 'pendente'", "pagar_")
        return
    elif texto == "📊 Relatório Mensal":
        await relatorio_mensal(update)
        return
    elif texto == "📅 Relatório por Mês":
        user_states[uid] = "relatorio_mes"
        await update.message.reply_text("Digite o mês e o ano (mm/aaaa):")
        return
    elif texto == "❌ Remover Conta":
        await gerar_inline(update, "SELECT id, descricao, valor FROM contas", "remover_")
        return
    elif texto == "📝 Atualizar Conta":
        await gerar_inline(update, "SELECT id, descricao, valor FROM contas", "atualizar_")
        return

    if estado == "relatorio_mes":
        try:
            mes, ano = map(int, texto.split("/"))
            await relatorio_por_mes(update, mes, ano)
        except:
            await update.message.reply_text("❌ Formato inválido. Use mm/aaaa.")
        user_states.pop(uid, None)
        return

    elif estado == "descricao":
        temp_data[uid]["descricao"] = texto
        user_states[uid] = "valor"
        await update.message.reply_text("Digite o valor (ex: 1234,56):")
        return

    elif estado == "valor":
        try:
            temp_data[uid]["valor"] = float(texto.replace(",", "."))
            user_states[uid] = "vencimento"
            await update.message.reply_text("Digite a data de vencimento (dd/mm/aaaa):")
        except:
            await update.message.reply_text("❌ Valor inválido. Digite novamente.")
        return

    elif estado == "vencimento":
        try:
            iso = data_str_para_iso(texto)
            temp_data[uid]["vencimento"] = iso
            user_states[uid] = "tipo"
            await update.message.reply_text(
                "Selecione o tipo da conta:", reply_markup=teclado_tipo_conta()
            )
        except Exception:
            await update.message.reply_text("❌ Data inválida. Use dd/mm/aaaa.")
        return

    elif estado == "tipo":
        if texto.lower() not in ("simples", "parcelada", "repetir semanal", "repetir mensal"):
            await update.message.reply_text("❌ Tipo inválido. Tente novamente.")
            return
        tipo_map = {
            "simples": "simples",
            "parcelada": "parcelada",
            "repetir semanal": "semanal",
            "repetir mensal": "mensal"
        }
        temp_data[uid]["tipo"] = tipo_map[texto.lower()]
        if tipo_map[texto.lower()] == "simples":
            await salvar_simples(uid, update)
        else:
            user_states[uid] = "parcelas"
            await update.message.reply_text("Digite o número de parcelas:")
        return

    elif estado == "parcelas":
        try:
            parcelas = int(texto)
            if parcelas < 1:
                raise ValueError()
            temp_data[uid]["parcelas"] = parcelas
            await salvar_contas_repetidas(uid, update)
        except:
            await update.message.reply_text("❌ Número inválido. Digite um número inteiro maior que 0.")
        user_states.pop(uid, None)
        return

    elif estado == "update_valor":
        try:
            valor = float(texto.replace(",", "."))
            idc = temp_data[uid]["id"]
            with get_db() as conn:
                conn.execute("UPDATE contas SET valor = ? WHERE id = ?", (valor, idc))
                conn.commit()
            await update.message.reply_text("✅ Valor atualizado com sucesso!", reply_markup=teclado_principal())
        except Exception as e:
            await update.message.reply_text(f"❌ Erro ao atualizar valor: {e}")
        user_states.pop(uid, None)
        temp_data.pop(uid, None)
        return

    else:
        await update.message.reply_text("❓ Comando não reconhecido. Use os botões abaixo.", reply_markup=teclado_principal())

async def salvar_simples(uid, update):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
            VALUES (?, ?, ?, 'pendente', ?, 1)
        """, (
            temp_data[uid]["descricao"],
            temp_data[uid]["valor"],
            temp_data[uid]["vencimento"],
            temp_data[uid]["tipo"]
        ))
        conn.commit()
    await update.message.reply_text("💾 Conta simples salva com sucesso!", reply_markup=teclado_principal())
    user_states.pop(uid, None)
    temp_data.pop(uid, None)

async def gerar_inline(update: Update, query_sql, prefix):
    with get_db() as conn:
        contas = conn.execute(query_sql).fetchall()
    if not contas:
        await update.message.reply_text("⚠️ Nenhuma conta encontrada.")
        return

    buttons = []
    for c in contas:
        buttons.append([InlineKeyboardButton(f"{c['descricao']} - R${c['valor']:.2f}", callback_data=f"{prefix}{c['id']}")])

    await update.message.reply_text(
        "Escolha uma conta:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

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
