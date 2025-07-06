import os
import json
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

JOGOS_FILE = "jogos.json"

# ADMIN_USER_ID será passado como variável de ambiente
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))


# Utilitários
def carregar_jogos():
    if not os.path.exists(JOGOS_FILE):
        return []
    try:
        with open(JOGOS_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def salvar_jogo(jogo):
    jogos = carregar_jogos()
    jogos.append(jogo)
    with open(JOGOS_FILE, "w") as f:
        json.dump(jogos, f)


# Comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎯 Bot da Mega-Sena online!\nUse /addjogo para adicionar uma aposta.")

async def addjogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Apenas o admin pode adicionar jogos.")
        return

    if len(context.args) != 6:
        await update.message.reply_text("❗ Envie 6 dezenas separadas por espaço. Ex: /addjogo 01 09 15 23 33 56")
        return

    dezenas = context.args
    if not all(dz.isdigit() and 1 <= int(dz) <= 60 for dz in dezenas):
        await update.message.reply_text("❗ Apenas números entre 1 e 60 são permitidos.")
        return

    jogo = {
        "usuario": update.effective_user.first_name,
        "dezenas": sorted([int(dz) for dz in dezenas])
    }
    salvar_jogo(jogo)
    await update.message.reply_text(f"✅ Jogo salvo: {jogo['dezenas']}")

async def meusjogos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jogos = carregar_jogos()
    if not jogos:
        await update.message.reply_text("🔍 Nenhum jogo cadastrado ainda.")
        return

    resposta = "📝 Jogos cadastrados:\n"
    for i, jogo in enumerate(jogos, 1):
        resposta += f"{i}. {jogo['dezenas']} (por {jogo['usuario']})\n"

    await update.message.reply_text(resposta)

async def resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get("https://loteriascaixa-api.herokuapp.com/api/mega-sena/latest").json()
        dezenas = res["dezenas"]
        concurso = res["concurso"]
        data = res["data"]
        resposta = f"📣 Resultado da Mega-Sena #{concurso} ({data}):\n🎯 {', '.join(dezenas)}"
        await update.message.reply_text(resposta)
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao buscar resultado: {e}")

async def conferir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get("https://loteriascaixa-api.herokuapp.com/api/mega-sena/latest").json()
        dezenas_sorteadas = [int(dz) for dz in res["dezenas"]]
        jogos = carregar_jogos()
        if not jogos:
            await update.message.reply_text("❗ Nenhum jogo para conferir.")
            return

        resposta = f"🎯 Resultado: {dezenas_sorteadas}\n\n"
        for jogo in jogos:
            acertos = set(jogo["dezenas"]) & set(dezenas_sorteadas)
            resposta += f"▶ {jogo['dezenas']} - {len(acertos)} acertos: {sorted(acertos)}\n"

        await update.message.reply_text(resposta)
    except Exception as e:
        await update.message.reply_text(f"❌ Erro na conferência: {e}")


# Inicialização
if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("❌ BOT_TOKEN não encontrado.")
        exit()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addjogo", addjogo))
    app.add_handler(CommandHandler("meusjogos", meusjogos))
    app.add_handler(CommandHandler("resultado", resultado))
    app.add_handler(CommandHandler("conferir", conferir))

    print("✅ Bot da Mega-Sena rodando...")
    app.run_polling()
