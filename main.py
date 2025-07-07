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
    conn = get_db()
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
    conn.close()

# Utilitários
def add_months(orig_date, months):
    year = orig_date.year + (orig_date.month + months - 1) // 12
    month = (orig_date.month + months - 1) % 12 + 1
    day = min(orig_date.day, 28)  # evita problemas com fevereiro
    return datetime.date(year, month, day)

def parse_date_br(date_str):
    return datetime.datetime.strptime(date_str, "%d/%m/%Y").date()

def format_date_br(date):
    return date.strftime("%d/%m/%Y")

def month_year_key(date):
    return date.strftime("%Y-%m")

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
        [KeyboardButton("🗕️ Relatório por Mês")],
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
        parse_mode="MarkdownV2"
    )
    user_states.pop(update.message.from_user.id, None)
    temp_data.pop(update.message.from_user.id, None)

# Função auxiliar para listar contas pendentes com botões inline para ações
def listar_contas_pendentes():
    conn = get_db()
    cursor = conn.execute("SELECT * FROM contas WHERE status = 'pendente' ORDER BY vencimento")
    contas = cursor.fetchall()
    conn.close()
    return contas

def formatar_conta_texto(conta):
    venc = datetime.date.fromisoformat(conta["vencimento"])
    return f"#{conta['id']} - {conta['descricao']}\nValor: R$ {conta['valor']:.2f}\nVencimento: {format_date_br(venc)}\nTipo: {conta['tipo']}\nStatus: {conta['status']}"

# Handler de mensagens
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text

    # Iniciar fluxo de adicionar conta
    if text == "➕ Adicionar Conta":
        user_states[uid] = "add_desc"
        await update.message.reply_text("📝 Digite a descrição da conta:")

    # Marcar conta como paga: mostrar lista e pedir para escolher
    elif text == "✅ Marcar Conta como Paga":
        contas = listar_contas_pendentes()
        if not contas:
            await update.message.reply_text("🎉 Nenhuma conta pendente para pagar.", reply_markup=teclado_principal())
            return

        buttons = [
            [InlineKeyboardButton(f"{c['descricao']} - R$ {c['valor']:.2f}", callback_data=f"pagar_{c['id']}")]
            for c in contas
        ]
        await update.message.reply_text(
            "Selecione a conta que deseja marcar como paga:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        user_states.pop(uid, None)
        temp_data.pop(uid, None)

    # Relatório mensal: mostra total e contas do mês atual
    elif text == "📊 Relatório Mensal":
        hoje = datetime.date.today()
        chave_mes = hoje.strftime("%Y-%m")
        conn = get_db()
        cursor = conn.execute("""
            SELECT status, SUM(valor) as total FROM contas
            WHERE substr(vencimento,1,7) = ?
            GROUP BY status
        """, (chave_mes,))
        resultados = cursor.fetchall()
        conn.close()

        total_pagos = sum(r["total"] for r in resultados if r["status"] == "paga") or 0
        total_pendentes = sum(r["total"] for r in resultados if r["status"] == "pendente") or 0
        texto = f"📅 *Relatório do mês {hoje.strftime('%m/%Y')}*\n\n" \
                f"✅ Total Pago: R$ {total_pagos:.2f}\n" \
                f"⏳ Total Pendente: R$ {total_pendentes:.2f}"
        await update.message.reply_text(texto, parse_mode="MarkdownV2", reply_markup=teclado_principal())
        user_states.pop(uid, None)
        temp_data.pop(uid, None)

    # Relatório por mês: pede mês e ano
    elif text == "🗕️ Relatório por Mês":
        user_states[uid] = "rel_mes_ano"
        await update.message.reply_text("Digite o mês e ano no formato mm/aaaa (ex: 07/2025):")

    elif user_states.get(uid) == "rel_mes_ano":
        try:
            mes_ano = datetime.datetime.strptime(text, "%m/%Y")
            chave_mes = mes_ano.strftime("%Y-%m")
            conn = get_db()
            cursor = conn.execute("""
                SELECT status, SUM(valor) as total FROM contas
                WHERE substr(vencimento,1,7) = ?
                GROUP BY status
            """, (chave_mes,))
            resultados = cursor.fetchall()
            conn.close()

            total_pagos = sum(r["total"] for r in resultados if r["status"] == "paga") or 0
            total_pendentes = sum(r["total"] for r in resultados if r["status"] == "pendente") or 0
            texto = f"📅 *Relatório do mês {text}*\n\n" \
                    f"✅ Total Pago: R$ {total_pagos:.2f}\n" \
                    f"⏳ Total Pendente: R$ {total_pendentes:.2f}"
            await update.message.reply_text(texto, parse_mode="MarkdownV2", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)
        except ValueError:
            await update.message.reply_text("❌ Formato inválido. Use mm/aaaa. Tente novamente:")

    # Atualizar conta: listar contas e escolher
    elif text == "📝 Atualizar Conta":
        conn = get_db()
        cursor = conn.execute("SELECT * FROM contas ORDER BY vencimento")
        contas = cursor.fetchall()
        conn.close()
        if not contas:
            await update.message.reply_text("❌ Não há contas cadastradas para atualizar.", reply_markup=teclado_principal())
            return

        buttons = [
            [InlineKeyboardButton(f"{c['descricao']} - R$ {c['valor']:.2f}", callback_data=f"atualizar_{c['id']}")]
            for c in contas
        ]
        await update.message.reply_text("Selecione a conta que deseja atualizar:", reply_markup=InlineKeyboardMarkup(buttons))
        user_states.pop(uid, None)
        temp_data.pop(uid, None)

    # Remover conta: listar contas e escolher
    elif text == "❌ Remover Conta":
        conn = get_db()
        cursor = conn.execute("SELECT * FROM contas ORDER BY vencimento")
        contas = cursor.fetchall()
        conn.close()
        if not contas:
            await update.message.reply_text("❌ Não há contas cadastradas para remover.", reply_markup=teclado_principal())
            return

        buttons = [
            [InlineKeyboardButton(f"{c['descricao']} - R$ {c['valor']:.2f}", callback_data=f"remover_{c['id']}")]
            for c in contas
        ]
        await update.message.reply_text("Selecione a conta que deseja remover:", reply_markup=InlineKeyboardMarkup(buttons))
        user_states.pop(uid, None)
        temp_data.pop(uid, None)

    # Fluxo de adicionar conta (continua como antes)
    elif user_states.get(uid) == "add_desc":
        temp_data[uid] = {"descricao": text}
        user_states[uid] = "add_valor"
        await update.message.reply_text("💰 Digite o valor da conta (ex: 123.45):")

    elif user_states.get(uid) == "add_valor":
        try:
            valor = float(text.replace(",", "."))
            temp_data[uid]["valor"] = valor
            user_states[uid] = "add_venc"
            await update.message.reply_text("📅 Digite a data de vencimento (dd/mm/aaaa):")
        except ValueError:
            await update.message.reply_text("❌ Valor inválido. Tente novamente.")

    elif user_states.get(uid) == "add_venc":
        try:
            venc = parse_date_br(text)
            temp_data[uid]["vencimento"] = venc.isoformat()
            user_states[uid] = "add_tipo"
            await update.message.reply_text("📌 Escolha o tipo da conta:", reply_markup=teclado_tipo_conta())
        except ValueError:
            await update.message.reply_text("❌ Data inválida. Use o formato dd/mm/aaaa.")

    elif user_states.get(uid) == "add_tipo":
        tipo = text
        parcelas = 1
        if "Parcelada" in tipo:
            parcelas = 3  # poderia perguntar quantidade real

        data = temp_data.get(uid, {})
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                VALUES (?, ?, ?, 'pendente', ?, ?)
            """, (
                data["descricao"],
                data["valor"],
                data["vencimento"],
                tipo,
                parcelas
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Erro ao inserir no DB: {e}")
            await update.message.reply_text("❌ Erro ao adicionar conta. Tente novamente.")
            user_states.pop(uid, None)
            temp_data.pop(uid, None)
            return

        await update.message.reply_text("✅ Conta adicionada com sucesso!", reply_markup=teclado_principal())
        user_states.pop(uid, None)
        temp_data.pop(uid, None)

    # Fluxo atualização: digitar novo valor para campo selecionado
    elif user_states.get(uid, "").startswith("upd_"):
        # Exemplo: "upd_valor_5" onde 5 é id da conta
        state = user_states[uid]
        parts = state.split("_")
        campo = parts[1]
        idc = int(parts[2])

        conn = get_db()
        cursor = conn.execute("SELECT * FROM contas WHERE id = ?", (idc,))
        conta = cursor.fetchone()
        if not conta:
            await update.message.reply_text("❌ Conta não encontrada.", reply_markup=teclado_principal())
            user_states.pop(uid, None)
            temp_data.pop(uid, None)
            conn.close()
            return

        if campo == "descricao":
            # Atualiza descrição
            try:
                conn.execute("UPDATE contas SET descricao = ? WHERE id = ?", (text, idc))
                conn.commit()
                await update.message.reply_text("✅ Descrição atualizada com sucesso!", reply_markup=teclado_principal())
            except Exception as e:
                logger.error(f"Erro ao atualizar descricao: {e}")
                await update.message.reply_text("❌ Erro ao atualizar descrição.")
        elif campo == "valor":
            try:
                valor = float(text.replace(",", "."))
                conn.execute("UPDATE contas SET valor = ? WHERE id = ?", (valor, idc))
                conn.commit()
                await update.message.reply_text("✅ Valor atualizado com sucesso!", reply_markup=teclado_principal())
            except ValueError:
                await update.message.reply_text("❌ Valor inválido. Operação cancelada.", reply_markup=teclado_principal())
            except Exception as e:
                logger.error(f"Erro ao atualizar valor: {e}")
                await update.message.reply_text("❌ Erro ao atualizar valor.")
        elif campo == "vencimento":
            try:
                venc = parse_date_br(text)
                conn.execute("UPDATE contas SET vencimento = ? WHERE id = ?", (venc.isoformat(), idc))
                conn.commit()
                await update.message.reply_text("✅ Vencimento atualizado com sucesso!", reply_markup=teclado_principal())
            except ValueError:
                await update.message.reply_text("❌ Data inválida. Operação cancelada.", reply_markup=teclado_principal())
            except Exception as e:
                logger.error(f"Erro ao atualizar vencimento: {e}")
                await update.message.reply_text("❌ Erro ao atualizar vencimento.")
        else:
            await update.message.reply_text("❌ Campo desconhecido.", reply_markup=teclado_principal())
        user_states.pop(uid, None)
        temp_data.pop(uid, None)
        conn.close()

    else:
        await update.message.reply_text(
            "🤖 Comando não reconhecido. Use o menu abaixo.",
            reply_markup=teclado_principal()
        )

# CallbackQuery para botões inline
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data

    await query.answer()

    # Marcar conta como paga
    if data.startswith("pagar_"):
        id_conta = int(data.split("_")[1])
        conn = get_db()
        cursor = conn.execute("SELECT * FROM contas WHERE id = ?", (id_conta,))
        conta = cursor.fetchone()
        if not conta:
            await query.edit_message_text("❌ Conta não encontrada.")
            conn.close()
            return
        if conta["status"] == "paga":
            await query.edit_message_text("✅ Conta já está marcada como paga.")
            conn.close()
            return

        # Se conta parcelada, descontar uma parcela e gerar próxima parcela
        if conta["tipo"] == "Parcelada" and conta["parcelas_restantes"] > 1:
            parcelas_restantes = conta["parcelas_restantes"] - 1
            venc_atual = datetime.date.fromisoformat(conta["vencimento"])
            prox_venc = add_months(venc_atual, 1)

            conn.execute("""
                UPDATE contas SET parcelas_restantes = ? WHERE id = ?
            """, (parcelas_restantes, id_conta))
            # Cria nova parcela
            conn.execute("""
                INSERT INTO contas (descricao, valor, vencimento, status, tipo, parcelas_restantes)
                VALUES (?, ?, ?, 'pendente', ?, ?)
            """, (
                conta["descricao"],
                conta["valor"],
                prox_venc.isoformat(),
                conta["tipo"],
                parcelas_restantes
            ))
            conn.commit()
            conn.close()
            await query.edit_message_text("✅ Parcela paga. Próxima parcela criada.")
            return
        else:
            # Marca como paga normalmente
            conn.execute("UPDATE contas SET status = 'paga' WHERE id = ?", (id_conta,))
            conn.commit()
            conn.close()
            await query.edit_message_text("✅ Conta marcada como paga.")
            return

    # Atualizar conta - escolher campo para atualizar
    if data.startswith("atualizar_"):
        id_conta = int(data.split("_")[1])
        conn = get_db()
        cursor = conn.execute("SELECT * FROM contas WHERE id = ?", (id_conta,))
        conta = cursor.fetchone()
        conn.close()
        if not conta:
            await query.edit_message_text("❌ Conta não encontrada.")
            return

        buttons = [
            [InlineKeyboardButton("Descrição", callback_data=f"upd_desc_{id_conta}")],
            [InlineKeyboardButton("Valor", callback_data=f"upd_valor_{id_conta}")],
            [InlineKeyboardButton("Vencimento", callback_data=f"upd_vencimento_{id_conta}")]
        ]
        await query.edit_message_text(
            f"Escolha o campo para atualizar na conta:\n\n{formatar_conta_texto(conta)}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # Atualizar campos: iniciar estado para receber o novo dado
    if data.startswith("upd_"):
        partes = data.split("_")
        campo = partes[1]
        id_conta = int(partes[2])
        campo_nome = {"desc": "descrição", "valor": "valor", "vencimento": "vencimento"}.get(campo, campo)
        user_states[uid] = f"upd_{campo}_{id_conta}"
        await query.edit_message_text(f"Digite o novo valor para {campo_nome} da conta #{id_conta}:")
        return

    # Remover conta
    if data.startswith("remover_"):
        id_conta = int(data.split("_")[1])
        conn = get_db()
        cursor = conn.execute("SELECT * FROM contas WHERE id = ?", (id_conta,))
        conta = cursor.fetchone()
        if not conta:
            await query.edit_message_text("❌ Conta não encontrada.")
            conn.close()
            return
        conn.execute("DELETE FROM contas WHERE id = ?", (id_conta,))
        conn.commit()
        conn.close()
        await query.edit_message_text(f"❌ Conta '{conta['descricao']}' removida com sucesso.")
        return

# Rodar o bot
async def main():
    init_db()
    TOKEN = os.getenv("TOKEN_TELEGRAM")
    if not TOKEN:
        print("⚠️ Defina a variável de ambiente TOKEN_TELEGRAM com o token do bot.")
        return
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    print("Bot iniciado...")
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
