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

user_states = {}
temp_data = {}

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
                parcelas_restantes INTEGER,
                vencimento_pago TEXT
            )
        ''')

def teclado_principal():
    buttons = [
        [KeyboardButton("\U0001F680 Iniciar")],
        [KeyboardButton("\u2795 Adicionar Conta")],
        [KeyboardButton("\u2705 Marcar Conta como Paga")],
        [KeyboardButton("\U0001F4CA Relatório Mensal")],
        [KeyboardButton("\U0001F4C5 Relatório por Mês")],
        [KeyboardButton("\U0001F4DD Atualizar Conta")],
        [KeyboardButton("\u274C Remover Conta")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def teclado_tipo_conta():
    tipos = [["Simples", "Parcelada"], ["Repetir Semanal", "Repetir Mensal"]]
    return ReplyKeyboardMarkup(tipos, resize_keyboard=True, one_time_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001F44B Olá! Bem-vindo ao *Gerenciador de Despesas*!",
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
        contas = conn.execute("""
            SELECT descricao, valor,
                CASE WHEN status = 'paga' AND vencimento_pago IS NOT NULL THEN vencimento_pago ELSE vencimento END as data_referencia,
                status
            FROM contas
            WHERE 
                (
                    (status = 'paga' AND strftime('%m', vencimento_pago) = ? AND strftime('%Y', vencimento_pago) = ?)
                    OR
                    (status != 'paga' AND strftime('%m', vencimento) = ? AND strftime('%Y', vencimento) = ?)
                )
        """, (mes_str, ano_str, mes_str, ano_str)).fetchall()

    if not contas:
        await update.message.reply_text(f"\U0001F4CA Nenhuma conta encontrada para {mes_str}/{ano_str}.")
        return

    texto = f"\U0001F4C5 *Contas de {mes_str}/{ano_str}:*\n\n"
    total_pagas = total_pendentes = 0
    for desc, val, venc, status in contas:
        venc_fmt = datetime.datetime.strptime(venc, "%Y-%m-%d").strftime("%d/%m/%Y")
        emoji = "\u2705" if status == "paga" else "\u23F3"
        texto += f"{emoji} *{desc}* - R${val:.2f} - Venc: `{venc_fmt}`\n"
        if status == "paga":
            total_pagas += val
        else:
            total_pendentes += val
    texto += f"\n\U0001F4B0 *Total pago:* R${total_pagas:.2f}\n\u231B *Pendente:* R${total_pendentes:.2f}"

    await update.message.reply_text(texto, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    with get_db() as conn:
        if data.startswith("remover_"):
            idc = int(data.split("_")[1])
            conn.execute("DELETE FROM contas WHERE id = ?", (idc,))
            await query.edit_message_text("\U0001F5D1 Conta removida com sucesso!")

        elif data.startswith("atualizar_"):
            idc = int(data.split("_")[1])
            temp_data[uid] = {"id": idc}
            user_states[uid] = "update_valor"
            await query.edit_message_text("Digite o *novo valor* da conta:", parse_mode="Markdown")

        elif data.startswith("pagar_"):
            idc = int(data.split("_")[1])
            conta = conn.execute("SELECT descricao, valor, vencimento, status, tipo FROM contas WHERE id = ?", (idc,)).fetchone()
            if conta is None:
                await query.edit_message_text("Conta não encontrada.")
                return
            descricao, valor, vencimento, status, tipo = conta
            hoje = datetime.date.today().isoformat()
            conn.execute("UPDATE contas SET status = 'paga', vencimento_pago = ? WHERE id = ?", (hoje, idc))

            temp_data[uid] = {
                "id": idc,
                "descricao": descricao,
                "valor": valor,
                "vencimento": vencimento,
                "tipo": tipo,
            }
            user_states[uid] = "confirmar_repetir"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Sim", callback_data="repetir_sim")],
                [InlineKeyboardButton("Não", callback_data="repetir_nao")]
            ])
            await query.edit_message_text(
                "Conta marcada como paga!\nDeseja repetir essa conta para o próximo mês com o mesmo dia de vencimento?",
                reply_markup=keyboard
            )

        elif data == "repetir_sim":
            if uid not in temp_data:
                await query.edit_message_text("Erro: dados da conta não encontrados.")
                return
            conta = temp_data[uid]
            vencimento_atual = datetime.datetime.strptime(conta["vencimento"], "%Y-%m-%d").date()

            ano = vencimento_atual.year + (vencimento_atual.month // 12)
            mes = vencimento_atual.month % 12 + 1
            dia = vencimento_atual.day

            try:
                proximo_vencimento = datetime.date(ano, mes, dia)
            except ValueError:
                import calendar
                ultimo_dia = calendar.monthrange(ano, mes)[1]
                proximo_vencimento = datetime.date(ano, mes, ultimo_dia)

            conn.execute("""
                INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                VALUES (?, ?, ?, 'pendente', ?, NULL)
            """, (conta["descricao"], conta["valor"], proximo_vencimento.isoformat(), conta["tipo"]))

            await query.edit_message_text(
                "Conta repetida para o próximo mês com vencimento em {}.".format(proximo_vencimento.strftime("%d/%m/%Y"))
            )

            user_states.pop(uid, None)
            temp_data.pop(uid, None)

        elif data == "repetir_nao":
            await query.edit_message_text("Ok, não será criada uma nova conta.")
            user_states.pop(uid, None)
            temp_data.pop(uid, None)

async def salvar_contas_repetidas(uid, update):
    tipo = temp_data[uid]["tipo"]
    parcelas = temp_data[uid]["parcelas"]
    data = datetime.datetime.fromisoformat(temp_data[uid]["vencimento"])

    with get_db() as conn:
        for i in range(parcelas):
            if tipo == "semanal":
                venc = data + datetime.timedelta(weeks=i)
            else:  # mensal
                ano = data.year + ((data.month - 1 + i) // 12)
                mes = (data.month - 1 + i) % 12 + 1
                dia = data.day
                try:
                    venc = datetime.date(ano, mes, dia)
                except ValueError:
                    import calendar
                    ultimo_dia = calendar.monthrange(ano, mes)[1]
                    venc = datetime.date(ano, mes, ultimo_dia)
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
    await update.message.reply_text("\U0001F4BE Contas salvas com sucesso!", reply_markup=teclado_principal())
    user_states.pop(uid, None)
    temp_data.pop(uid, None)

async def gerar_inline(update, sql, prefixo):
    with get_db() as conn:
        contas = conn.execute(sql).fetchall()
    if not contas:
        await update.message.reply_text("Nenhuma conta encontrada.")
        return
    if "vencimento" in sql:
        keyboard = [[
            InlineKeyboardButton(
                f"{desc} - Venc: {datetime.datetime.strptime(venc, '%Y-%m-%d').strftime('%d/%m/%Y')}",
                callback_data=f"{prefixo}{idc}"
            )
        ] for idc, desc, venc in contas]
    else:
        keyboard = [[InlineKeyboardButton(desc, callback_data=f"{prefixo}{idc}")] for idc, desc in contas]
    await update.message.reply_text("Selecione uma opção:", reply_markup=InlineKeyboardMarkup(keyboard))

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    texto = update.message.text.strip()
    estado = user_states.get(uid)

    if texto == "\U0001F680 Iniciar":
        await start(update, context)
    elif texto == "\u2795 Adicionar Conta":
        user_states[uid] = "descricao"
        temp_data[uid] = {}
        await update.message.reply_text("Digite a descrição da conta:")
    elif texto == "\u2705 Marcar Conta como Paga":
        await gerar_inline(update, "SELECT id, descricao, vencimento FROM contas WHERE status = 'pendente'", "pagar_")
    elif texto == "\U0001F4CA Relatório Mensal":
        await relatorio_mensal(update)
    elif texto == "\U0001F4C5 Relatório por Mês":
        user_states[uid] = "relatorio_mes"
        await update.message.reply_text("Digite o mês e o ano (mm/aaaa):")
    elif texto == "\u274C Remover Conta":
        await gerar_inline(update, "SELECT id, descricao FROM contas", "remover_")
    elif texto == "\U0001F4DD Atualizar Conta":
        await gerar_inline(update, "SELECT id, descricao FROM contas", "atualizar_")

    elif estado == "relatorio_mes":
        try:
            mes, ano = map(int, texto.split("/"))
            await relatorio_por_mes(update, mes, ano)
        except:
            await update.message.reply_text("\u274C Formato inválido. Use mm/aaaa.")
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
            await update.message.reply_text("\u274C Valor inválido.")

    elif estado == "vencimento":
        try:
            data = datetime.datetime.strptime(texto, "%d/%m/%Y").date()
            temp_data[uid]["vencimento"] = data.isoformat()
            user_states[uid] = "tipo"
            await update.message.reply_text("Selecione o tipo da conta:", reply_markup=teclado_tipo_conta())
        except:
            await update.message.reply_text("\u274C Data inválida.")

    elif estado == "tipo":
        tipo = texto.lower()
        if tipo not in ("simples", "parcelada", "repetir semanal", "repetir mensal"):
            await update.message.reply_text("\u274C Tipo inválido. Escolha um dos botões.")
            return
        temp_data[uid]["tipo"] = tipo
        if tipo == "parcelada":
            user_states[uid] = "parcelas"
            await update.message.reply_text("Quantas parcelas?")
        elif tipo in ("repetir semanal", "repetir mensal"):
            user_states[uid] = "parcelas"
            await update.message.reply_text("Quantas vezes deseja repetir?")
        else:
            # simples: salvar direto
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                    VALUES (?, ?, ?, 'pendente', ?, NULL)
                """, (temp_data[uid]["descricao"], temp_data[uid]["valor"], temp_data[uid]["vencimento"], tipo))
            await update.message.reply_text("\U0001F4BE Conta adicionada!", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)

    elif estado == "parcelas":
        try:
            parcelas = int(texto)
            if parcelas < 1:
                raise ValueError
            temp_data[uid]["parcelas"] = parcelas
            await salvar_contas_repetidas(uid, update)
        except:
            await update.message.reply_text("\u274C Número inválido.")

    elif estado == "update_valor":
        try:
            valor = float(texto.replace(",", "."))
            idc = temp_data[uid]["id"]
            with get_db() as conn:
                conn.execute("UPDATE contas SET valor = ? WHERE id = ?", (valor, idc))
            await update.message.reply_text("\U0001F4DD Valor atualizado!", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)
        except:
            await update.message.reply_text("\u274C Valor inválido.")

    else:
        await update.message.reply_text("Comando não reconhecido. Use os botões do teclado.")

async def main():
    init_db()
    token = os.getenv("TELEGRAM_TOKEN")
    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    application.add_handler(CallbackQueryHandler(button_handler))

    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
