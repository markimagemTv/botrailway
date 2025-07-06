#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import time
import uuid
import sys
import io
import signal
import requests
import subprocess
from datetime import datetime

# Importações locais (serão resolvidas após a definição do logger)
# Essas importações serão tratadas mais adiante no código
git_manager = None
catalog_manager = None

# Configuração inicial de logging básico para permitir logs antes da configuração completa
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('bot')

try:
    from dotenv import load_dotenv
    logger.info("Módulo dotenv importado com sucesso")
except ImportError:
    # Fallback simples para caso dotenv não esteja disponível
    def load_dotenv():
        logger.info("dotenv não está disponível, ignorando arquivo .env")
        pass
    logger.warning("Módulo dotenv não encontrado. Variáveis de ambiente devem ser definidas manualmente.")

# Configuração para compatibilidade de codificação em diferentes sistemas
try:
    if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        logger.info("Configuração de codificação UTF-8 aplicada aos streams de saída")
except Exception as e:
    logger.warning(f"Não foi possível configurar encoding UTF-8 para saída: {e}")
    logger.warning("Caracteres especiais podem não ser exibidos corretamente")

# Carregar variáveis de ambiente do arquivo .env se existir
load_dotenv()

try:
    import mercadopago
    from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                        ReplyKeyboardMarkup, Update)
    from telegram.ext import (CallbackContext, CallbackQueryHandler,
                            CommandHandler, ConversationHandler, Filters,
                            MessageHandler, Updater)
except ImportError as e:
    print(f"Erro ao importar dependências: {e}")
    print("Por favor, instale as dependências com: pip install -r requirements_render.txt")
    sys.exit(1)

# Configuração de logging já foi feita no início do arquivo
# Esta linha está sendo mantida apenas para compatibilidade com versões antigas do Python
# que possam ignorar a configuração inicial

# Tokens e configuração
TOKEN = os.getenv("TELEGRAM_TOKEN")
MERCADO_PAGO_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Configurações GitHub removidas

# Verificação de variáveis de ambiente obrigatórias
if not TOKEN:
    logger.error("TELEGRAM_TOKEN não definido. Configure a variável de ambiente ou o arquivo .env")
    sys.exit(1)
if not MERCADO_PAGO_TOKEN:
    logger.warning("MERCADO_PAGO_TOKEN não definido. O processamento de pagamentos não funcionará.")
if not ADMIN_ID:
    logger.warning("ADMIN_ID não definido. Funcionalidades de administrador não estarão disponíveis.")

# Catálogo de produtos
PRODUCT_CATALOG = {
    "ATIVAR APP": [
        {"name": "➕​ ASSIST+ R$ 65", "price": 65.00, "fields": ["MAC"]},
        {"name": "📱 NINJA PLAYER R$65", "price": 65.00, "fields": ["MAC", "CHAVE OTP"]},
        {"name": "📺 MEGA IPTV R$ 75", "price": 75.00, "fields": ["MAC"]},
        {"name": "🧠 SMART ONE R$60", "price": 70.00, "fields": ["MAC"]},
        {"name": "🎮 IBO PRO PLAYER R$50", "price": 50.00, "fields": ["MAC"]},
        {"name": "📡 IBO TV OFICIAL R$50", "price": 50.00, "fields": ["MAC"]},
        {"name": "🧩 DUPLECAST R$60", "price": 60.00, "fields": ["MAC", "CHAVE OTP"]},
        {"name": "🌐 BAY TV R$60", "price": 60.00, "fields": ["MAC"]},
        {"name": "🟣​ QUICK PLAYER R$65", "price": 65.00, "fields": ["MAC"]},
        {"name": "▶️​ TIVI PLAYER R$65", "price": 65.00, "fields": ["MAC"]},
        {"name": "🔥 SUPER PLAY R$50", "price": 50.00, "fields": ["MAC"]},
        {"name": "☁️ CLOUDDY R$65", "price": 65.00, "fields": ["E-mail", "Senha do app"]},
    ],
    "COMPRAR CRÉDITOS": [
        {"name": "🎯 X SERVER PLAY (13,50und)", "price": 13.50, "discount": True},
        {"name": "⚡ FAST PLAYER (13,50und)", "price": 13.50, "discount": True},
        {"name": "👑 GOLD PLAY (13,50und)", "price": 13.50, "discount": True},
        {"name": "📺 EI TV (13,50und)", "price": 13.50, "discount": True},
        {"name": "🛰️ Z TECH (13,50und)", "price": 13.50, "discount": True},
        {"name": "🧠 GENIAL PLAY (13,50und)", "price": 13.50, "discount": True},
        {"name": "🚀 UPPER PLAY (15,00und)", "price": 150.00, "discount": False},
    ],
    "🔥 PROMOÇÕES": [
        {"name": "📺 PACOTE 30 CRÉDITOS EI TV", "price": 300.00, "discount": False},
    ]
}

# Desconto para produtos de crédito
DISCOUNT_PERCENTAGE = 0.95  # 5% de desconto
DISCOUNT_THRESHOLD = 20  # Aplicar apenas para 20 créditos ou mais

# Importar módulos locais após a inicialização do logger
try:
    import git_manager
    import catalog_manager
    logger.info("Módulos de gerenciamento de Git e catálogo importados com sucesso")
except ImportError as e:
    logger.warning(f"Não foi possível importar módulos de Git/catálogo/GitHub: {e}")
    # Definir funções dummy para não quebrar o código
    class DummyManager:
        @staticmethod
        def commit_catalog_changes(*args, **kwargs):
            logger.warning("Operação Git ignorada - módulo não disponível")
            return False
            
        @staticmethod
        def is_git_repo(*args, **kwargs):
            return False
            
        @staticmethod
        def setup_git_identity(*args, **kwargs):
            return False
            
        @staticmethod
        def save_catalog_to_git(*args, **kwargs):
            logger.warning("Operação Git (save_catalog_to_git) ignorada - módulo não disponível")
            return False
            
        @staticmethod
        def export_catalog_to_json(*args, **kwargs):
            logger.warning("Operação (export_catalog_to_json) ignorada - módulo não disponível")
            return False
    
    if git_manager is None:
        git_manager = DummyManager()
    
    if catalog_manager is None:
        catalog_manager = DummyManager()

# Inicializar cliente Mercado Pago
mp = mercadopago.SDK(MERCADO_PAGO_TOKEN)

# Configurar identidade Git para commits automáticos se estiver em um repositório Git
try:
    if git_manager.is_git_repo():
        git_manager.setup_git_identity(
            name="Bot Telegram Automático", 
            email="bot@exemplo.com"
        )
        logger.info("Identidade Git configurada para commits automáticos")
except Exception as e:
    logger.warning(f"Não foi possível configurar identidade Git: {e}")

# Teclado principal
MAIN_KEYBOARD = ReplyKeyboardMarkup([
    ['🛍️ Produtos', '🛒 Ver Carrinho'],
    ['📋 Meus Pedidos', '❓ Ajuda']
], resize_keyboard=True)

# Teclado para administrador
ADMIN_KEYBOARD = ReplyKeyboardMarkup([
    ['🛍️ Produtos', '🛒 Ver Carrinho'],
    ['📋 Meus Pedidos', '🛠️ Admin'],
    ['❓ Ajuda']
], resize_keyboard=True)

# Estados de conversa para registro
NOME, TELEFONE = range(2)

# Estados para autenticação de administrador
ADMIN_AUTH = 100

# Estados para conversa de admin de produtos
CATEGORY_SELECTION = 1
PRODUCT_ACTION = 2
ADD_PRODUCT_NAME = 3
ADD_PRODUCT_PRICE = 4
ADD_PRODUCT_FIELDS = 5
CONFIRM_DELETE = 6
EDIT_PRODUCT_FIELD = 7
EDIT_PRODUCT_VALUE = 8

# Dados temporários para admin
product_temp_data = {}

# CLASSES DE MODELO

class User:
    def __init__(self, id, nome, telefone):
        self.id = id
        self.nome = nome
        self.telefone = telefone
        
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'telefone': self.telefone
        }

class CartItem:
    def __init__(self, name, price, details=None):
        self.name = name
        self.price = price
        self.details = details or {}
        
    def to_dict(self):
        return {
            'name': self.name,
            'price': self.price,
            'details': self.details
        }
        
    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data['name'],
            price=data['price'],
            details=data.get('details', {})
        )

class Order:
    def __init__(self, id, user_id, items, status="pendente", payment_id=None):
        self.id = id
        self.user_id = user_id
        self.items = [CartItem.from_dict(item) if isinstance(item, dict) else item for item in items]
        self.status = status
        self.payment_id = payment_id
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'items': [item.to_dict() for item in self.items],
            'status': self.status,
            'payment_id': self.payment_id,
            'created_at': self.created_at
        }
        
    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data['id'],
            user_id=data['user_id'],
            items=data['items'],
            status=data.get('status', 'pendente'),
            payment_id=data.get('payment_id')
        )

class DataStore:
    """Handle in-memory data persistence for users, carts, and orders with file backup"""
    
    def __init__(self):
        self.users = {}  # user_id -> User
        self.carts = {}  # user_id -> [CartItem]
        self.orders = {}  # order_id -> Order
        self.users_file = os.path.join("data", "users.json")
        self.orders_file = os.path.join("data", "orders.json")
        self.carts_file = os.path.join("data", "carts.json")
        
        # Garantir que o diretório de dados existe
        os.makedirs("data", exist_ok=True)
        
        # Carregar dados salvos anteriormente, se existirem
        self._load_data()
    
    def _load_data(self):
        """Carrega dados dos arquivos JSON"""
        try:
            # Carregar usuários
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    users_data = json.load(f)
                    for user_id, user_data in users_data.items():
                        self.users[int(user_id)] = User(
                            int(user_id),
                            user_data['nome'],
                            user_data['telefone']
                        )
                logger.info(f"Carregados {len(self.users)} usuários do arquivo")
            
            # Carregar carrinhos
            if os.path.exists(self.carts_file):
                with open(self.carts_file, 'r', encoding='utf-8') as f:
                    carts_data = json.load(f)
                    for user_id, cart_items in carts_data.items():
                        self.carts[int(user_id)] = [CartItem.from_dict(item) for item in cart_items]
                logger.info(f"Carregados {len(self.carts)} carrinhos do arquivo")
            
            # Carregar pedidos
            if os.path.exists(self.orders_file):
                with open(self.orders_file, 'r', encoding='utf-8') as f:
                    orders_data = json.load(f)
                    for order_id, order_data in orders_data.items():
                        self.orders[order_id] = Order.from_dict(order_data)
                logger.info(f"Carregados {len(self.orders)} pedidos do arquivo")
        
        except Exception as e:
            logger.error(f"Erro ao carregar dados: {e}")
    
    def _save_data(self):
        """Salva todos os dados em arquivos JSON"""
        try:
            # Salvar usuários
            users_data = {}
            for user_id, user in self.users.items():
                users_data[str(user_id)] = user.to_dict()
            
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(users_data, f, ensure_ascii=False, indent=2)
            
            # Salvar carrinhos
            carts_data = {}
            for user_id, cart_items in self.carts.items():
                carts_data[str(user_id)] = [item.to_dict() for item in cart_items]
            
            with open(self.carts_file, 'w', encoding='utf-8') as f:
                json.dump(carts_data, f, ensure_ascii=False, indent=2)
            
            # Salvar pedidos
            orders_data = {}
            for order_id, order in self.orders.items():
                orders_data[order_id] = order.to_dict()
            
            with open(self.orders_file, 'w', encoding='utf-8') as f:
                json.dump(orders_data, f, ensure_ascii=False, indent=2)
            
            logger.info("Dados salvos em arquivos com sucesso")
            
        except Exception as e:
            logger.error(f"Erro ao salvar dados: {e}")
        
    def save_user(self, user_id, name, phone):
        """Save user information"""
        self.users[user_id] = User(user_id, name, phone)
        # Salvar imediatamente
        self._save_data()
        return self.users[user_id]
        
    def get_user(self, user_id):
        """Get user by ID"""
        return self.users.get(user_id)
        
    def add_to_cart(self, user_id, item):
        """Add item to user's cart"""
        if user_id not in self.carts:
            self.carts[user_id] = []
            
        # Convert dict to CartItem if needed
        if isinstance(item, dict):
            item = CartItem.from_dict(item)
            
        self.carts[user_id].append(item)
        # Salvar imediatamente
        self._save_data()
        return self.carts[user_id]
        
    def get_cart(self, user_id):
        """Get user's cart"""
        return self.carts.get(user_id, [])
        
    def clear_cart(self, user_id):
        """Clear user's cart"""
        self.carts[user_id] = []
        # Salvar imediatamente
        self._save_data()
        
    def create_order(self, user_id, cart_items, payment_id=None):
        """Create a new order"""
        order_id = str(uuid.uuid4().hex[:8])  # Generate unique order ID
        order = Order(order_id, user_id, cart_items, payment_id=payment_id)
        self.orders[order_id] = order
        # Salvar imediatamente
        self._save_data()
        return order
        
    def get_order(self, order_id):
        """Get order by ID"""
        return self.orders.get(order_id)
        
    def update_order_status(self, order_id, status, payment_id=None):
        """Update order status and optionally payment_id"""
        order = self.get_order(order_id)
        if order:
            order.status = status
            if payment_id:
                order.payment_id = payment_id
            # Salvar imediatamente
            self._save_data()
            return order
        return None
        
    def get_user_orders(self, user_id):
        """Get all orders for a user"""
        return [order for order in self.orders.values() if order.user_id == user_id]

# Inicializar armazenamento de dados
db = DataStore()

# FUNÇÕES UTILITÁRIAS

def save_catalog_to_git():
    """Salva o catálogo de produtos localmente
    
    Esta função exporta o catálogo atual para um arquivo JSON.
    A integração com Git foi removida por simplicidade.
    
    Returns:
        bool: True se o catálogo foi salvo com sucesso, False caso contrário
    """
    try:
        # Criar diretório se não existir
        os.makedirs('data', exist_ok=True)
        # Salvar catálogo em JSON
        with open('data/catalog.json', 'w', encoding='utf-8') as f:
            json.dump(PRODUCT_CATALOG, f, ensure_ascii=False, indent=4)
        logger.info("Catálogo salvo com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar catálogo: {e}")
        return False

def get_cart_total(cart_items):
    """Calculate total price of items in cart"""
    return sum(item.price for item in cart_items)

def apply_discount(product_price, quantity, has_discount=False):
    """Apply discount for credit purchases if applicable"""
    if has_discount and quantity >= DISCOUNT_THRESHOLD:
        # Aplicar desconto (5% = 0.95 do preço)
        return product_price * quantity * DISCOUNT_PERCENTAGE
    return product_price * quantity

def format_cart_message(cart_items):
    """Format cart items for display"""
    if not cart_items:
        return "Seu carrinho está vazio."
        
    message = ""
    total = 0
    
    for i, item in enumerate(cart_items, 1):
        try:
            # Garantir que item é um objeto CartItem válido
            if isinstance(item, dict):
                try:
                    item = CartItem.from_dict(item)
                except Exception as e:
                    logger.error(f"Erro ao converter item do carrinho: {e}")
                    continue
                    
            price = item.price
            details = ""
            
            if item.details:
                if 'credits' in item.details:
                    credits = item.details['credits']
                    
                    if 'original_price' in item.details:
                        original_price = item.details['original_price']
                        regular_total = original_price * credits
                        
                        # Check if discount was applied
                        if price < regular_total:
                            discount_text = " (c/ 5% desconto)"
                        else:
                            discount_text = ""
                        
                        details = f" - {credits} créditos{discount_text}"
                
                # Add any fields if present
                if 'fields' in item.details:
                    fields = item.details['fields']
                    if fields:
                        fields_text = ", ".join(f"{k}: {v}" for k, v in fields.items())
                        details += f"\n   ↳ {fields_text}"
            
            message += f"{i}. {item.name} - R${price:.2f}{details}\n"
            total += price
            
        except Exception as e:
            logger.error(f"Erro ao formatar item do carrinho: {e}")
            # Tenta formatar item com informações mínimas para não quebrar todo o carrinho
            try:
                message += f"{i}. Item (erro ao carregar detalhes)\n"
            except:
                pass
    
    message += f"\n*Total:* R${total:.2f}"
    return message

def create_categories_keyboard():
    """Create inline keyboard for product categories"""
    keyboard = []
    for category in PRODUCT_CATALOG.keys():
        keyboard.append([InlineKeyboardButton(category, callback_data=f"category_{category}")])
    return InlineKeyboardMarkup(keyboard)

def create_products_keyboard(products):
    """Create inline keyboard for products"""
    keyboard = []
    for i, product in enumerate(products):
        keyboard.append([
            InlineKeyboardButton(
                f"{product['name']} - R${product['price']:.2f}", 
                callback_data=f"product_{i}"
            )
        ])
    keyboard.append([InlineKeyboardButton("◀️ Voltar às Categorias", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(keyboard)

def create_credits_keyboard():
    """Create keyboard for credit quantities"""
    keyboard = [
        [InlineKeyboardButton("10 créditos", callback_data="qty_10"),
         InlineKeyboardButton("20 créditos (5% off)", callback_data="qty_20")],
        [InlineKeyboardButton("30 créditos (5% off)", callback_data="qty_30"),
         InlineKeyboardButton("50 créditos (5% off)", callback_data="qty_50")],
        [InlineKeyboardButton("◀️ Voltar aos Produtos", callback_data="back_to_products")]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_order_details(order, include_items=True):
    """Format order details for display"""
    try:
        total = sum(item.price for item in order.items)
        
        message = (
            f"🧾 *Pedido #{order.id}*\n"
            f"📅 Data: {order.created_at}\n"
            f"🔄 Status: {order.status.upper()}\n\n"
        )
        
        if include_items:
            message += "*Itens do pedido:*\n"
            for i, item in enumerate(order.items, 1):
                try:
                    # Garantir que item é um objeto CartItem válido
                    if isinstance(item, dict):
                        try:
                            item = CartItem.from_dict(item)
                        except Exception as e:
                            logger.error(f"Erro ao converter item do pedido: {e}")
                            # Usar representação simplificada
                            message += f"{i}. Item (erro ao carregar detalhes)\n"
                            continue

                    details = ""
                    if item.details:
                        if 'credits' in item.details:
                            details = f" - {item.details['credits']} créditos"
                        
                        # Add any fields if present
                        if 'fields' in item.details and item.details['fields']:
                            fields_text = ", ".join(f"{k}: {v}" for k, v in item.details['fields'].items())
                            details += f"\n   ↳ {fields_text}"
                    
                    message += f"{i}. {item.name} - R${item.price:.2f}{details}\n"
                except Exception as e:
                    logger.error(f"Erro ao formatar item do pedido: {e}")
                    # Tenta formatar item com informações mínimas para não quebrar todo o pedido
                    message += f"{i}. Item (erro ao carregar detalhes)\n"
            
            message += f"\n*Total:* R${total:.2f}"
        
        else:
            message += f"*Itens:* {len(order.items)} produtos\n"
            message += f"*Total:* R${total:.2f}"
        
        return message
    except Exception as e:
        logger.error(f"Erro ao formatar detalhes do pedido: {e}")
        # Retorna mensagem de erro como fallback
        return "❌ Não foi possível formatar os detalhes do pedido. Por favor, tente novamente."

def log_error(error, context=None):
    """Log errors with context"""
    error_message = f"ERROR - {context + ': ' if context else ''}{error}"
    logger.error(error_message)
    return error_message

# HANDLERS DE REGISTRO

def start(update: Update, context: CallbackContext):
    """Start command handler - entry point for new users"""
    user_id = update.effective_user.id
    
    # Check if user is already registered
    # Debug log
    logger.info(f"Iniciando fluxo de registro para usuário {user_id}")
    
    # Verifica se usuário já está registrado
    user = db.get_user(user_id)
    if user:
        logger.info(f"Usuário {user_id} já registrado como {user.nome}")
        update.message.reply_text(
            f"Olá, {user.nome}! O que você gostaria de fazer hoje?",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END
    
    # Verificar se há dados na sessão atual que podem ser usados para registrar o usuário
    if 'name' in context.user_data and 'phone' in context.user_data:
        logger.info(f"Dados de registro encontrados na sessão: {context.user_data['name']}, {context.user_data['phone']}")
        # Registrar usuário com dados da sessão
        user = db.save_user(
            user_id,
            context.user_data['name'],
            context.user_data['phone']
        )
        logger.info(f"Usuário {user_id} registrado automaticamente com dados da sessão")
        update.message.reply_text(
            f"Bem-vindo de volta, {user.nome}! Você já está registrado.",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END
    
    # User is not registered, start registration flow
    update.message.reply_text(
        "👋 *Bem-vindo à nossa loja!*\n\n"
        "Para começar, precisamos de algumas informações básicas.\n\n"
        "Por favor, digite seu nome completo:",
        parse_mode="Markdown"
    )
    
    return NOME

def handle_name(update: Update, context: CallbackContext):
    """Handle user name input"""
    user_name = update.message.text.strip()
    
    if not user_name or len(user_name) < 3:
        update.message.reply_text("Por favor, digite seu nome completo válido (mínimo 3 caracteres):")
        return NOME
    
    # Store name in user_data
    context.user_data['name'] = user_name
    
    # Ask for phone number with a custom keyboard
    contact_keyboard = KeyboardButton(text="📱 Compartilhar Telefone", request_contact=True)
    
    update.message.reply_text(
        "Agora, por favor, compartilhe seu número de telefone. "
        "Você pode usar o botão abaixo ou digitar manualmente no formato: 11999999999",
        reply_markup=ReplyKeyboardMarkup([[contact_keyboard]], one_time_keyboard=True)
    )
    
    return TELEFONE

def handle_phone(update: Update, context: CallbackContext):
    """Handle user phone input and complete registration"""
    if update.message.contact:
        # User shared contact
        phone = update.message.contact.phone_number
    else:
        # User typed phone manually
        phone = update.message.text.strip()
        
        # Basic validation
        phone = ''.join(c for c in phone if c.isdigit())
        if not phone or len(phone) < 10:
            update.message.reply_text("Por favor, digite um número de telefone válido com DDD:")
            return TELEFONE
    
    # Complete registration
    user_name = context.user_data.get('name')
    user_id = update.effective_user.id
    
    # Debug log
    logger.info(f"Registrando usuário {user_id} com nome={user_name}, telefone={phone}")
    
    # Store phone in user_data para persistência entre restarts
    context.user_data['phone'] = phone
    
    # Verificar se usuário já existe
    existing_user = db.get_user(user_id)
    if existing_user:
        logger.info(f"Usuário {user_id} já existe, atualizando informações")
    
    # Save user info
    user = db.save_user(user_id, user_name, phone)
    
    # Verificar registro
    if user:
        logger.info(f"Usuário {user_id} registrado com sucesso como {user.nome}, {user.telefone}")
    else:
        logger.error(f"Falha ao registrar usuário {user_id}")
    
    update.message.reply_text(
        f"✅ *Registro concluído com sucesso!*\n\n"
        f"Obrigado, {user_name}. Agora você pode navegar pelos nossos produtos e fazer pedidos.",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD
    )
    
    # End conversation
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    """Cancel conversation handler"""
    update.message.reply_text(
        "Registro cancelado. Você pode reiniciar o processo quando quiser usando /start.",
        reply_markup=MAIN_KEYBOARD
    )
    return ConversationHandler.END

# HANDLERS DE PRODUTOS

def menu_inicial(update: Update, context: CallbackContext):
    """Display initial product categories menu"""
    try:
        # Check if user is registered
        user_id = update.effective_user.id
        
        # Não limpar todos os dados para preservar dados de registro
        # Remover apenas dados temporários de produtos
        keys_to_remove = [k for k in context.user_data.keys() 
                          if k not in ['name', 'phone'] and not isinstance(k, int)]
        for key in keys_to_remove:
            context.user_data.pop(key, None)
            
        logger.info(f"Menu inicial para usuário {user_id}, dados preservados na sessão: {context.user_data}")
        user = db.get_user(user_id)
        
        if not user:
            update.message.reply_text(
                "Você precisa se registrar primeiro. Por favor, use o comando /start."
            )
            return
        
        # Show categories using inline buttons
        keyboard = create_categories_keyboard()
        
        update.message.reply_text(
            "🛍️ *Categorias de Produtos*\n\n"
            "Escolha uma categoria para ver os produtos disponíveis:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error showing menu for user {user_id}")
        
        update.message.reply_text(
            "❌ Ocorreu um erro ao exibir o menu. Por favor, tente novamente.",
            reply_markup=MAIN_KEYBOARD
        )

def show_category(update: Update, context: CallbackContext):
    """Show products in selected category"""
    try:
        query = update.callback_query
        query.answer()
        
        category = query.data.replace("category_", "")
        context.user_data['selected_category'] = category
        
        # Get products for this category
        products = PRODUCT_CATALOG.get(category, [])
        keyboard = create_products_keyboard(products)
        
        query.edit_message_text(
            f"📦 *Produtos na categoria {category}*\n\n"
            f"Escolha um produto para ver detalhes:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error showing products for user {user_id}")
        
        # Tratamento de erro seguro
        try:
            if update.callback_query:
                update.callback_query.edit_message_text(
                    "❌ Ocorreu um erro ao exibir os produtos. Por favor, tente novamente."
                )
            elif update.message:
                update.message.reply_text(
                    "❌ Ocorreu um erro ao exibir os produtos. Por favor, tente novamente.",
                    reply_markup=MAIN_KEYBOARD
                )
        except Exception:
            # Último recurso se nada funcionar
            pass

def select_product(update: Update, context: CallbackContext):
    """Handle product selection"""
    try:
        query = update.callback_query
        query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data == "back_to_categories":
            # Show categories menu again
            keyboard = create_categories_keyboard()
            
            query.edit_message_text(
                "🛍️ *Categorias de Produtos*\n\n"
                "Escolha uma categoria para ver os produtos disponíveis:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
        
        # Get product index from callback data
        try:
            product_index = int(data.replace("product_", ""))
        except ValueError:
            # Tratamento de callback_data inválido
            logger.error(f"Callback data inválido: {data}")
            query.edit_message_text(
                "❌ Erro ao processar a seleção. Por favor, tente novamente usando o menu principal.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Voltar ao Menu", callback_data="back_to_categories")
                ]])
            )
            return
        
        # Get category and product
        category = context.user_data.get('selected_category')
        if not category:
            logger.warning(f"Categoria não encontrada no user_data para usuário {user_id}")
            query.edit_message_text(
                "❌ Erro: Sessão expirada ou categoria não encontrada. Por favor, selecione uma categoria novamente.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Ver Categorias", callback_data="back_to_categories")
                ]])
            )
            return
            
        if category not in PRODUCT_CATALOG:
            logger.warning(f"Categoria inválida '{category}' para usuário {user_id}")
            query.edit_message_text(
                "❌ Erro: Categoria não disponível. Por favor, selecione uma categoria válida.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Ver Categorias", callback_data="back_to_categories")
                ]])
            )
            return
            
        products = PRODUCT_CATALOG.get(category, [])
        
        if not products:
            logger.warning(f"Categoria '{category}' sem produtos para usuário {user_id}")
            query.edit_message_text(
                "❌ Esta categoria não possui produtos no momento. Por favor, escolha outra categoria.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Ver Categorias", callback_data="back_to_categories")
                ]])
            )
            return
        
        if product_index >= len(products) or product_index < 0:
            logger.warning(f"Índice de produto inválido {product_index} para usuário {user_id}")
            query.edit_message_text(
                "❌ Erro: Produto não encontrado. Por favor, selecione um produto válido.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Ver Produtos", callback_data=f"category_{category}")
                ]])
            )
            return
            
        product = products[product_index]
        context.user_data['selected_product'] = product
        context.user_data['selected_product_index'] = product_index
        
        # Different handling based on product type
        if 'fields' in product:  # App product
            # Format message
            message = (
                f"📱 *{product['name']}*\n\n"
                f"💰 Preço: R${product['price']:.2f}\n\n"
                f"Para adicionar ao carrinho, forneça as seguintes informações:"
            )
            
            for field in product['fields']:
                message += f"\n- {field}"
                
            keyboard = [
                [InlineKeyboardButton("◀️ Voltar", callback_data="back_to_products")]
            ]
            
            query.edit_message_text(
                message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Set up for collecting fields
            context.user_data['collecting_fields'] = True
            context.user_data['fields_collected'] = {}
            context.user_data['required_fields'] = product['fields']
            context.user_data['current_field_index'] = 0
            
            # Ask for the first field
            context.bot.send_message(
                chat_id=query.from_user.id,
                text=f"Por favor, forneça o *{product['fields'][0]}* do seu dispositivo:",
                parse_mode="Markdown"
            )
            
        elif 'discount' in product and product['discount'] == True:  # Credit product com desconto
            # Show credit quantities
            message = (
                f"💰 *{product['name']}*\n\n"
                f"Preço unitário: R${product['price']:.2f}\n\n"
                f"Selecione a quantidade de créditos desejada:"
            )
            
            keyboard = create_credits_keyboard()
            
            query.edit_message_text(
                message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
        elif 'discount' in product and product['discount'] == False:  # Produto de preço fixo (sem desconto)
            # Format message with add to cart option
            message = (
                f"🛍️ *{product['name']}*\n\n"
                f"💰 Preço: R${product['price']:.2f}\n\n"
                f"Este é um produto de preço fixo, sem seleção de quantidade.\n"
                f"Deseja adicionar este produto ao carrinho?"
            )
            
            keyboard = [
                [InlineKeyboardButton("🛒 Adicionar ao Carrinho", callback_data="add_to_cart_fixed")],
                [InlineKeyboardButton("◀️ Voltar", callback_data="back_to_products")]
            ]
            
            query.edit_message_text(
                message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        else:  # Regular product with no special handling
            # Format message with add to cart option
            message = (
                f"🛍️ *{product['name']}*\n\n"
                f"💰 Preço: R${product['price']:.2f}\n\n"
                f"Deseja adicionar este produto ao carrinho?"
            )
            
            keyboard = [
                [InlineKeyboardButton("🛒 Adicionar ao Carrinho", callback_data="add_to_cart")],
                [InlineKeyboardButton("◀️ Voltar", callback_data="back_to_products")]
            ]
            
            query.edit_message_text(
                message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error selecting product for user {user_id}")
        
        # Tratamento de erro seguro
        try:
            if update.callback_query:
                update.callback_query.edit_message_text(
                    "❌ Ocorreu um erro ao selecionar o produto. Por favor, tente novamente."
                )
            elif update.message:
                update.message.reply_text(
                    "❌ Ocorreu um erro ao selecionar o produto. Por favor, tente novamente.",
                    reply_markup=MAIN_KEYBOARD
                )
        except Exception:
            # Último recurso se nada funcionar
            pass

def handle_quantity(update: Update, context: CallbackContext):
    """Handle credit quantity selection"""
    try:
        query = update.callback_query
        query.answer()
        
        data = query.data
        
        if data == "back_to_products":
            # Show products in the previously selected category
            category = context.user_data.get('selected_category')
            if not category:
                query.edit_message_text("❌ Erro: Categoria não encontrada. Por favor, comece novamente.")
                return
                
            products = PRODUCT_CATALOG.get(category, [])
            keyboard = create_products_keyboard(products)
            
            query.edit_message_text(
                f"📦 *Produtos na categoria {category}*\n\n"
                f"Escolha um produto para ver detalhes:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
        
        # Get quantity from callback data
        quantity = int(data.replace("qty_", ""))
        product = context.user_data.get('selected_product')
        
        if not product:
            query.edit_message_text("❌ Erro: Produto não encontrado. Por favor, comece novamente.")
            return
        
        # Calculate price with possible discount
        base_price = product['price']
        has_discount = product.get('discount', False)
        total_price = apply_discount(base_price, quantity, has_discount)
        
        # Create a cart item
        cart_item = CartItem(
            name=product['name'],
            price=total_price,
            details={
                "credits": quantity,
                "discount": has_discount,
                "original_price": base_price
            }
        )
        
        # Add to cart
        db.add_to_cart(query.from_user.id, cart_item.to_dict())
        
        # Format message with discount info if applicable
        message = f"✅ *Produto adicionado ao carrinho!*\n\n"
        message += f"🛍️ {product['name']}\n"
        message += f"📊 Quantidade: {quantity} créditos\n"
        
        if has_discount and quantity >= DISCOUNT_THRESHOLD:
            regular_price = base_price * quantity
            saved_amount = regular_price - total_price
            message += f"💰 Preço regular: R${regular_price:.2f}\n"
            message += f"🏷️ Preço com desconto: R${total_price:.2f}\n"
            message += f"💵 Economia: R${saved_amount:.2f} (5% de desconto)\n"
        else:
            message += f"💰 Preço total: R${total_price:.2f}\n"
        
        keyboard = [
            [InlineKeyboardButton("🛒 Ver Carrinho", callback_data="view_cart")],
            [InlineKeyboardButton("🛍️ Continuar Comprando", callback_data="back_to_categories")]
        ]
        
        query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error handling quantity for user {user_id}")
        
        # Tratamento de erro seguro
        try:
            if update.callback_query:
                update.callback_query.edit_message_text(
                    "❌ Ocorreu um erro ao selecionar a quantidade. Por favor, tente novamente."
                )
            elif update.message:
                update.message.reply_text(
                    "❌ Ocorreu um erro ao selecionar a quantidade. Por favor, tente novamente.",
                    reply_markup=MAIN_KEYBOARD
                )
        except Exception:
            # Último recurso se nada funcionar
            pass

def collect_product_fields(update: Update, context: CallbackContext):
    """Collect required fields for app products"""
    user_id = update.effective_user.id
    
    # Check if we're collecting fields
    if not context.user_data.get('collecting_fields', False):
        update.message.reply_text(
            "Por favor, selecione um produto primeiro.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    field_value = update.message.text.strip()
    
    # Get current field being collected
    required_fields = context.user_data.get('required_fields', [])
    current_index = context.user_data.get('current_field_index', 0)
    
    if current_index >= len(required_fields):
        # Something went wrong - reset
        update.message.reply_text(
            "❌ Ocorreu um erro ao coletar as informações. Por favor, selecione o produto novamente.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    current_field = required_fields[current_index]
    
    # Store the field value
    fields_collected = context.user_data.get('fields_collected', {})
    fields_collected[current_field] = field_value
    context.user_data['fields_collected'] = fields_collected
    
    # Move to next field or complete if all collected
    current_index += 1
    context.user_data['current_field_index'] = current_index
    
    if current_index < len(required_fields):
        # Ask for the next field
        update.message.reply_text(
            f"Por favor, forneça o *{required_fields[current_index]}* do seu dispositivo:",
            parse_mode="Markdown"
        )
    else:
        # All fields collected, add to cart
        product = context.user_data.get('selected_product')
        
        if not product:
            update.message.reply_text(
                "❌ Erro: Produto não encontrado. Por favor, comece novamente.",
                reply_markup=MAIN_KEYBOARD
            )
            return
        
        # Create a cart item with collected fields
        cart_item = CartItem(
            name=product['name'],
            price=product['price'],
            details={"fields": fields_collected}
        )
        
        # Add to cart
        db.add_to_cart(user_id, cart_item.to_dict())
        
        # Reset collection state
        context.user_data['collecting_fields'] = False
        
        # Send confirmation
        message = (
            f"✅ *Produto adicionado ao carrinho!*\n\n"
            f"🛍️ {product['name']}\n"
            f"💰 Preço: R${product['price']:.2f}\n\n"
            f"📋 Informações fornecidas:\n"
        )
        
        for field, value in fields_collected.items():
            message += f"- {field}: {value}\n"
        
        keyboard = [
            [InlineKeyboardButton("🛒 Ver Carrinho", callback_data="view_cart")],
            [InlineKeyboardButton("🛍️ Continuar Comprando", callback_data="back_to_categories")]
        ]
        
        update.message.reply_text(
            message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def continue_shopping(update: Update, context: CallbackContext):
    """Handle continue shopping action"""
    try:
        query = update.callback_query
        if not query:
            # Caso não seja um callback, pode ser uma mensagem direta
            if update.message:
                update.message.reply_text(
                    "Por favor, use os botões fornecidos para navegar pelo menu.",
                    reply_markup=MAIN_KEYBOARD
                )
            return
            
        query.answer()
        
        action = query.data
        
        if action == "back_to_categories":
            # Show categories menu
            keyboard = create_categories_keyboard()
            
            query.edit_message_text(
                "🛍️ *Categorias de Produtos*\n\n"
                "Escolha uma categoria para ver os produtos disponíveis:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        elif action == "back_to_products":
            # Show products in the previously selected category
            category = context.user_data.get('selected_category')
            if not category:
                query.edit_message_text(
                    "❌ Erro: Categoria não encontrada. Por favor, comece novamente."
                )
                return
                
            products = PRODUCT_CATALOG.get(category, [])
            keyboard = create_products_keyboard(products)
            
            query.edit_message_text(
                f"📦 *Produtos na categoria {category}*\n\n"
                f"Escolha um produto para ver detalhes:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error continuing shopping for user {user_id}")
        
        # Tratamento de erro seguro
        try:
            if update.callback_query:
                update.callback_query.edit_message_text(
                    "❌ Ocorreu um erro ao navegar. Por favor, tente novamente."
                )
            elif update.message:
                update.message.reply_text(
                    "❌ Ocorreu um erro ao navegar. Por favor, tente novamente.",
                    reply_markup=MAIN_KEYBOARD
                )
        except Exception:
            # Último recurso se nada funcionar
            pass

# HANDLERS DE CARRINHO

def view_cart(update: Update, context: CallbackContext):
    """Show user's shopping cart (triggered by message)"""
    try:
        user_id = update.effective_user.id
        
        # Get cart
        cart_items = db.get_cart(user_id)
        
        if not cart_items:
            update.message.reply_text(
                "🛒 Seu carrinho está vazio.\n\n"
                "Use o botão '🛍️ Produtos' para navegar e adicionar produtos.",
                reply_markup=MAIN_KEYBOARD
            )
            return
        
        # Format cart message
        message = "🛒 *Seu Carrinho*\n\n"
        message += format_cart_message(cart_items)
        
        # Create checkout keyboard
        keyboard = [
            [InlineKeyboardButton("💰 Finalizar Compra", callback_data="checkout")],
            [InlineKeyboardButton("🗑️ Limpar Carrinho", callback_data="clear_cart")],
            [InlineKeyboardButton("🛍️ Continuar Comprando", callback_data="back_to_categories")]
        ]
        
        update.message.reply_text(
            message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error viewing cart for user {user_id}")
        
        update.message.reply_text(
            "❌ Ocorreu um erro ao exibir seu carrinho. Por favor, tente novamente.",
            reply_markup=MAIN_KEYBOARD
        )

def view_cart_callback(update: Update, context: CallbackContext):
    """Show user's shopping cart (triggered by callback button)"""
    try:
        query = update.callback_query
        query.answer()
        
        user_id = query.from_user.id
        
        # Get cart
        cart_items = db.get_cart(user_id)
        
        if not cart_items:
            query.edit_message_text(
                "🛒 Seu carrinho está vazio.\n\n"
                "Use o botão '🛍️ Produtos' para navegar e adicionar produtos."
            )
            return
        
        # Format cart message
        message = "🛒 *Seu Carrinho*\n\n"
        message += format_cart_message(cart_items)
        
        # Create checkout keyboard
        keyboard = [
            [InlineKeyboardButton("💰 Finalizar Compra", callback_data="checkout")],
            [InlineKeyboardButton("🗑️ Limpar Carrinho", callback_data="clear_cart")],
            [InlineKeyboardButton("🛍️ Continuar Comprando", callback_data="back_to_categories")]
        ]
        
        query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error viewing cart (callback) for user {user_id}")
        
        try:
            update.callback_query.edit_message_text(
                "❌ Ocorreu um erro ao exibir seu carrinho. Por favor, tente novamente."
            )
        except:
            pass

def checkout(update: Update, context: CallbackContext):
    """Process checkout and payment"""
    try:
        logger.info("Iniciando processo de checkout")
        query = update.callback_query
        query.answer()
        
        user_id = query.from_user.id
        logger.info(f"Processando checkout para usuário {user_id}")
        
        # Verificar se o usuário está registrado
        user = db.get_user(user_id)
        if not user:
            logger.warning(f"Usuário {user_id} não está registrado")
            if 'name' in context.user_data and 'phone' in context.user_data:
                logger.info(f"Criando usuário com dados da sessão: {context.user_data['name']}, {context.user_data['phone']}")
                try:
                    user = db.save_user(user_id, context.user_data['name'], context.user_data['phone'])
                    logger.info(f"Usuário criado com sucesso: {user.nome}")
                except Exception as reg_error:
                    logger.error(f"Erro ao salvar usuário: {reg_error}")
            
            if not user:
                query.edit_message_text(
                    "❌ Você precisa estar registrado para finalizar a compra.\n"
                    "Por favor, use o comando /start para se registrar."
                )
                return
        else:
            logger.info(f"Usuário {user_id} encontrado: {user.nome}")
        
        # Verificar carrinho
        cart_items = db.get_cart(user_id)
        if not cart_items:
            logger.warning(f"Carrinho vazio para usuário {user_id}")
            query.edit_message_text(
                "❌ Seu carrinho está vazio. Adicione produtos antes de finalizar a compra."
            )
            return
        
        logger.info(f"Carrinho do usuário {user_id} contém {len(cart_items)} itens")
        
        # Verificar se todos os itens têm os campos necessários preenchidos
        incomplete_items = []
        for item in cart_items:
            product_name = item.name
            logger.info(f"Verificando campos do produto: {product_name}")
            
            for category, products in PRODUCT_CATALOG.items():
                for product in products:
                    if product['name'] == product_name and 'fields' in product:
                        required_fields = product['fields']
                        
                        # Verificar se todos os campos obrigatórios estão preenchidos
                        if not item.details.get('fields'):
                            logger.warning(f"Produto {product_name} não tem 'fields' definido")
                            incomplete_items.append(product_name)
                            break
                            
                        item_fields = item.details['fields']
                        logger.info(f"Campos preenchidos: {item_fields}")
                        for field in required_fields:
                            if field not in item_fields:
                                logger.warning(f"Campo {field} faltando para {product_name}")
                                incomplete_items.append(product_name)
                                break
        
        if incomplete_items:
            product_list = "\n".join([f"- {name}" for name in incomplete_items])
            logger.warning(f"Produtos incompletos: {incomplete_items}")
            query.edit_message_text(
                f"❌ Os seguintes produtos precisam de informações adicionais:\n\n"
                f"{product_list}\n\n"
                f"Por favor, remova-os do carrinho ou forneça as informações necessárias."
            )
            return
        
        # Tudo ok, prosseguir para pagamento
        logger.info("Iniciando processamento de pagamento")
        query.edit_message_text(
            "💳 Preparando sua forma de pagamento... Por favor, aguarde."
        )
        
        # Processar pagamento diretamente
        try:
            logger.info("Chamando função process_payment")
            return process_payment(update, context)
        except Exception as payment_error:
            logger.error(f"Erro ao processar pagamento: {payment_error}", exc_info=True)
            query.edit_message_text(
                "❌ Ocorreu um erro ao processar o pagamento. Por favor, tente novamente mais tarde."
            )
    except Exception as e:
        logger.error(f"Erro durante checkout: {e}", exc_info=True)
        try:
            update.callback_query.edit_message_text(
                "❌ Ocorreu um erro ao finalizar a compra. Por favor, tente novamente."
            )
        except Exception:
            pass

def clear_cart(update: Update, context: CallbackContext):
    """Clear user's shopping cart"""
    try:
        query = update.callback_query
        if not query:
            # Caso não seja um callback, pode ser uma mensagem direta
            if update.message:
                update.message.reply_text(
                    "Por favor, use os botões fornecidos para gerenciar seu carrinho.",
                    reply_markup=MAIN_KEYBOARD
                )
            return
            
        query.answer()
        
        user_id = query.from_user.id
        
        # Clear cart
        db.clear_cart(user_id)
        
        query.edit_message_text(
            "🗑️ Seu carrinho foi esvaziado com sucesso!\n\n"
            "Use o botão '🛍️ Produtos' para navegar e adicionar produtos."
        )
        
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error clearing cart for user {user_id}")
        
        # Tratamento de erro seguro
        try:
            if update.callback_query:
                update.callback_query.edit_message_text(
                    "❌ Ocorreu um erro ao limpar seu carrinho. Por favor, tente novamente."
                )
            elif update.message:
                update.message.reply_text(
                    "❌ Ocorreu um erro ao limpar seu carrinho. Por favor, tente novamente.",
                    reply_markup=MAIN_KEYBOARD
                )
        except Exception:
            # Último recurso se nada funcionar
            pass

# HANDLERS DE PAGAMENTO

def process_payment(update: Update, context: CallbackContext):
    """Process payment using Mercado Pago"""
    try:
        query = update.callback_query
        query.answer()
        
        user_id = query.from_user.id
        
        # Verificar se o token do MercadoPago está configurado
        if not MERCADO_PAGO_TOKEN:
            logger.error("Token do MercadoPago não configurado")
            query.edit_message_text(
                "❌ Nosso sistema de pagamentos está temporariamente indisponível.\n"
                "Por favor, tente novamente mais tarde ou entre em contato com o suporte."
            )
            return
        
        # Debug log para verificação
        logger.info(f"Processando pagamento para user_id={user_id}, verificando registro")
        
        try:
            # Check if user is registered
            user = db.get_user(user_id)
            
            # Log para debug
            if user:
                logger.info(f"Usuário {user_id} encontrado no banco de dados: {user.nome}, {user.telefone}")
            else:
                logger.info(f"Usuário {user_id} não encontrado no banco de dados, verificando context.user_data")
                logger.info(f"Context user_data: {context.user_data}")
            
            # Tentar registrar o usuário automaticamente se tiver os dados na sessão
            if not user and 'name' in context.user_data and 'phone' in context.user_data:
                logger.info(f"Registrando usuário {user_id} com dados da sessão atual: {context.user_data['name']}, {context.user_data['phone']}")
                try:
                    user = db.save_user(
                        user_id,
                        context.user_data['name'],
                        context.user_data['phone']
                    )
                    logger.info(f"Usuário registrado com sucesso: {user.nome}, {user.telefone}")
                except Exception as reg_error:
                    logger.error(f"Erro ao registrar usuário com dados da sessão: {reg_error}")
                
            # Se mesmo assim o usuário não estiver registrado
            if not user:
                logger.warning(f"Usuário {user_id} não está registrado e não tem dados de registro na sessão")
                query.edit_message_text(
                    "❌ Você precisa estar registrado para finalizar a compra.\n"
                    "Por favor, use o comando /start para se registrar."
                )
                return
            
            # Get cart
            cart_items = db.get_cart(user_id)
            
            if not cart_items:
                logger.warning(f"Carrinho vazio para o usuário {user_id}")
                query.edit_message_text(
                    "❌ Seu carrinho está vazio. Adicione produtos antes de finalizar a compra."
                )
                return
            
            logger.info(f"Carrinho recuperado para o usuário {user_id}: {len(cart_items)} itens")
            
            # Criar pedido com tratamento de erros
            try:
                order = db.create_order(user_id, cart_items)
                logger.info(f"Pedido {order.id} criado com sucesso para o usuário {user_id}")
            except Exception as order_error:
                logger.error(f"Erro ao criar pedido: {order_error}")
                query.edit_message_text(
                    "❌ Ocorreu um erro ao criar seu pedido. Por favor, tente novamente."
                )
                return
            
            # Create Mercado Pago payment
            total_amount = sum(item.price for item in cart_items)
            logger.info(f"Valor total do pedido: R$ {total_amount:.2f}")
            
            # Format product description
            if len(cart_items) == 1:
                description = f"Pedido #{order.id} - {cart_items[0].name}"
            else:
                description = f"Pedido #{order.id} - Múltiplos itens"
            
            # Create payment data for PIX
            payment_data = {
                "transaction_amount": float(total_amount),
                "description": description,
                "payment_method_id": "pix",
                "payer": {
                    "email": f"cliente_{user_id}@exemplo.com",
                    "first_name": user.nome,
                    "last_name": "Cliente",
                    "identification": {
                        "type": "CPF",
                        "number": "19119119100"
                    }
                },
                "external_reference": order.id
            }
            
            logger.info(f"Enviando dados de pagamento para o MercadoPago: {payment_data}")
            
            # Fazer a requisição com tratamento de erros específico
            try:
                payment_response = mp.payment().create(payment_data)
                logger.info(f"Resposta do MercadoPago: status {payment_response.get('status')}")
            except Exception as mp_error:
                logger.error(f"Erro na comunicação com MercadoPago: {mp_error}")
                query.edit_message_text(
                    "❌ Não foi possível conectar ao serviço de pagamento. Por favor, tente novamente mais tarde."
                )
                return
            
            if payment_response.get("status") == 201:
                try:
                    payment = payment_response.get("response", {})
                    payment_id = payment.get("id")
                    
                    if not payment_id:
                        raise ValueError("Payment ID não encontrado na resposta")
                    
                    # Update order with payment ID
                    db.update_order_status(order.id, "pendente", payment_id)
                    
                    # Get PIX data from response
                    try:
                        pix_data = payment.get("point_of_interaction", {}).get("transaction_data", {})
                        # qr_code_base64 = pix_data.get("qr_code_base64", "")
                        pix_copy_paste = pix_data.get("qr_code", "")
                        
                        if not pix_copy_paste:
                            logger.warning("Código PIX não encontrado na resposta")
                            pix_copy_paste = "Erro ao gerar código PIX. Entre em contato com o suporte."
                    except Exception as pix_error:
                        logger.error(f"Erro ao extrair dados PIX: {pix_error}")
                        pix_copy_paste = "Erro ao gerar código PIX. Entre em contato com o suporte."
                    
                    # Send payment message with PIX details
                    message = (
                        f"🧾 *Resumo do Pedido #{order.id}*\n\n"
                        f"{format_cart_message(cart_items)}\n\n"
                        f"*PAGAMENTO VIA PIX*\n"
                        f"Copie o código abaixo para pagar via PIX:\n\n"
                        f"`{pix_copy_paste}`\n\n"
                        f"Abra seu aplicativo bancário, escolha a opção PIX > Copia e Cola, e cole o código acima.\n\n"
                        f"Após realizar o pagamento, clique no botão 'Verificar Pagamento' para confirmar."
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton("🔍 Verificar Pagamento", callback_data=f"check_payment_{order.id}")]
                    ]
                    
                    # First, edit the current message
                    query.edit_message_text(
                        message,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    
                    # Clear cart after generating payment
                    db.clear_cart(user_id)
                    
                    logger.info(f"Pagamento PIX criado com sucesso para o pedido {order.id}, usuário {user_id}")
                    
                    # Notificar admin (em thread separada para não bloquear o fluxo)
                    try:
                        if ADMIN_ID:
                            context.dispatcher.run_async(
                                notify_admin_new_order,
                                context=context,
                                order=order,
                                user=user
                            )
                    except Exception as admin_error:
                        logger.error(f"Erro ao notificar admin: {admin_error}")
                    
                except Exception as process_error:
                    logger.error(f"Erro ao processar resposta do pagamento: {process_error}")
                    query.edit_message_text(
                        "❌ Ocorreu um erro ao finalizar o pagamento. Por favor, contate o suporte com o código do pedido."
                    )
            else:
                error_message = "Erro desconhecido"
                if "response" in payment_response and "message" in payment_response["response"]:
                    error_message = payment_response["response"]["message"]
                
                logger.error(f"Erro ao criar pagamento PIX: {error_message}")
                query.edit_message_text(
                    f"❌ Ocorreu um erro ao processar o pagamento PIX: {error_message}\n"
                    f"Por favor, tente novamente mais tarde."
                )
        except Exception as data_error:
            logger.error(f"Erro ao recuperar dados para pagamento: {data_error}")
            query.edit_message_text(
                "❌ Ocorreu um erro ao processar suas informações. Por favor, tente novamente."
            )
            
    except Exception as e:
        # Obter user_id da maneira mais segura possível
        try:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
        except:
            user_id = "Unknown"
            
        log_error(e, f"Erro crítico no processamento de pagamento para usuário {user_id}")
        logger.error(f"Detalhes completos do erro: {str(e)}", exc_info=True)
        
        # Último recurso para notificar o usuário
        try:
            if update.callback_query:
                update.callback_query.edit_message_text(
                    "❌ Ocorreu um erro ao processar o pagamento. Por favor, tente novamente mais tarde."
                )
        except Exception as notify_error:
            logger.error(f"Erro adicional ao notificar usuário: {notify_error}")

def check_payment_status(update: Update, context: CallbackContext):
    """Check payment status for a specific order"""
    try:
        query = update.callback_query
        if not query:
            # Caso não seja um callback, pode ser uma mensagem direta
            if update.message:
                update.message.reply_text(
                    "Por favor, use os botões fornecidos para verificar o status do pagamento."
                )
            return
            
        query.answer()
        
        data = query.data
        order_id = data.split("_")[2]
        
        user_id = update.effective_user.id
        
        # Verificação adicional para garantir que o usuário está registrado
        user = db.get_user(user_id)
        
        # Se o usuário não estiver registrado, mas já tiver dados disponíveis na conversa atual,
        # podemos registrá-lo sem reiniciar o fluxo completo de registro
        if not user and 'name' in context.user_data and 'phone' in context.user_data:
            logger.info(f"Registrando usuário {user_id} com dados da sessão atual durante verificação de pagamento")
            logger.info(f"Dados na sessão: nome={context.user_data['name']}, telefone={context.user_data['phone']}")
            user = db.save_user(
                user_id,
                context.user_data['name'],
                context.user_data['phone']
            )
            logger.info(f"Usuário registrado durante verificação de pagamento: {user.nome}, {user.telefone}")
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error starting payment check for user {user_id}")
        
        # Tratamento de erro seguro
        try:
            if update.callback_query:
                update.callback_query.edit_message_text(
                    "❌ Ocorreu um erro ao verificar o pagamento. Por favor, tente novamente."
                )
            elif update.message:
                update.message.reply_text(
                    "❌ Ocorreu um erro ao verificar o pagamento. Por favor, tente novamente."
                )
        except Exception:
            # Último recurso se nada funcionar
            pass
        return
    
    try:
        # Get order
        order = db.get_order(order_id)
        if not order:
            query.edit_message_text(
                "❌ Pedido não encontrado. Por favor, tente novamente."
            )
            return
        
        # Verify this is the user's order
        if order.user_id != user_id:
            query.edit_message_text(
                "❌ Você não tem permissão para verificar este pedido."
            )
            return
        
        # Get user info (needed for admin notification)
        user = db.get_user(user_id)
        if not user:
            query.edit_message_text(
                "❌ Informações do usuário não encontradas. Por favor, tente novamente."
            )
            return
        
        # Query Mercado Pago for payment status
        payment_status = None  # Initialize payment_status variable
        
        if not order.payment_id:
            # Check by external reference (order ID)
            search_params = {"external_reference": order_id}
            payment_result = mp.payment().search(search_params)
            
            if payment_result["status"] == 200:
                payments = payment_result["response"]["results"]
                
                if payments:
                    # Get latest payment
                    payment = payments[0]
                    payment_id = payment["id"]
                    payment_status = payment["status"]
                    
                    # Update order with payment ID
                    order.payment_id = payment_id
                    # This persists the payment ID to the order
                    db.update_order_status(order_id, order.status)
                    
                else:
                    # No payment found
                    query.edit_message_text(
                        "💰 *Status do Pagamento*\n\n"
                        "Ainda não identificamos seu pagamento.\n"
                        "Se você já pagou, aguarde alguns instantes e verifique novamente.\n\n"
                        "Se precisar pagar novamente, use o botão abaixo:",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔍 Verificar Novamente", callback_data=f"check_payment_{order_id}")]
                        ])
                    )
                    return
                    
        else:
            # We already have payment ID, check its status
            payment_id = order.payment_id
            payment_result = mp.payment().get(payment_id)
            
            if payment_result["status"] == 200:
                payment = payment_result["response"]
                payment_status = payment["status"]
            else:
                # Error getting payment info
                query.edit_message_text(
                    "❌ Não foi possível verificar o status do pagamento. Por favor, tente novamente mais tarde."
                )
                return
        
        # Make sure payment_status is defined before proceeding
        if payment_status is None:
            query.edit_message_text(
                "❌ Não foi possível determinar o status do pagamento. Por favor, tente novamente mais tarde."
            )
            return
            
        # Process payment status
        if payment_status == "approved":
            # If order wasn't marked as paid yet
            if order.status != "pago":
                # Update order status
                db.update_order_status(order_id, "pago")
                
                # Send admin notification about new paid order
                notify_admin_new_order(context, order, user)
            
            # Inform user
            query.edit_message_text(
                "✅ *Pagamento Aprovado!*\n\n"
                "Seu pagamento foi confirmado e seu pedido está sendo processado.\n"
                "Você receberá uma notificação quando seu pedido for entregue.\n\n"
                "Obrigado por comprar conosco!",
                parse_mode="Markdown"
            )
            
        elif payment_status == "pending" or payment_status == "in_process":
            query.edit_message_text(
                "⏳ *Pagamento Pendente*\n\n"
                "Seu pagamento está sendo processado.\n"
                "Por favor, verifique novamente em alguns instantes.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Verificar Novamente", callback_data=f"check_payment_{order_id}")]
                ])
            )
            
        elif payment_status == "rejected" or payment_status == "cancelled":
            query.edit_message_text(
                "❌ *Pagamento Rejeitado*\n\n"
                "Infelizmente seu pagamento foi rejeitado ou cancelado.\n"
                "Por favor, tente novamente ou use outro método de pagamento.",
                parse_mode="Markdown"
            )
            
        else:
            query.edit_message_text(
                f"ℹ️ *Status do Pagamento: {payment_status}*\n\n"
                "Por favor, verifique novamente em alguns instantes ou entre em contato com o suporte.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Verificar Novamente", callback_data=f"check_payment_{order_id}")]
                ])
            )
        
    except Exception as e:
        log_error(e, f"Error checking payment status for order {order_id}")
        query.edit_message_text(
            "❌ Ocorreu um erro ao verificar o status do pagamento. Por favor, tente novamente mais tarde.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Tentar Novamente", callback_data=f"check_payment_{order_id}")]
            ])
        )

# HANDLERS DE PEDIDOS

def list_orders(update: Update, context: CallbackContext):
    """List all user orders"""
    try:
        user_id = update.effective_user.id
        
        # Get orders
        orders = db.get_user_orders(user_id)
        
        if not orders:
            update.message.reply_text(
                "📋 *Meus Pedidos*\n\n"
                "Você ainda não fez nenhum pedido.",
                parse_mode="Markdown",
                reply_markup=MAIN_KEYBOARD
            )
            return
        
        # Sort orders by creation date (newest first)
        orders.sort(key=lambda x: x.created_at, reverse=True)
        
        # Format orders list
        message = "📋 *Seus Pedidos*\n\n"
        
        for order in orders:
            status_emoji = "✅" if order.status == "pago" else "⏳" if order.status == "pendente" else "❌"
            total = sum(item.price for item in order.items)
            
            message += (
                f"{status_emoji} *Pedido #{order.id}*\n"
                f"📅 Data: {order.created_at}\n"
                f"💰 Total: R${total:.2f}\n"
                f"🔄 Status: {order.status.upper()}\n"
                f"👉 [Ver Detalhes](callback_data=order_details_{order.id})\n\n"
            )
        
        # Create keyboard with order details buttons
        keyboard = []
        for order in orders:
            status_text = "✅ " if order.status == "pago" else "⏳ " if order.status == "pendente" else "❌ "
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_text}Pedido #{order.id} ({order.created_at[:10]})",
                    callback_data=f"order_details_{order.id}"
                )
            ])
        
        update.message.reply_text(
            "📋 *Seus Pedidos*\n\n"
            "Selecione um pedido para ver detalhes:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error listing orders for user {user_id}")
        
        update.message.reply_text(
            "❌ Ocorreu um erro ao listar seus pedidos. Por favor, tente novamente.",
            reply_markup=MAIN_KEYBOARD
        )

def order_details(update: Update, context: CallbackContext):
    """Show details for a specific order"""
    try:
        query = update.callback_query
        query.answer()
        
        data = query.data
        order_id = data.split("_")[2]
        
        user_id = query.from_user.id
        
        # Get order
        order = db.get_order(order_id)
        
        if not order:
            query.edit_message_text(
                "❌ Pedido não encontrado. Por favor, tente novamente."
            )
            return
        
        # Verify this is the user's order
        if order.user_id != user_id:
            query.edit_message_text(
                "❌ Você não tem permissão para visualizar este pedido."
            )
            return
        
        # Format order details
        message = format_order_details(order)
        
        # Add payment verification button if pending
        keyboard = []
        if order.status == "pendente" and order.payment_id:
            keyboard.append([
                InlineKeyboardButton("🔍 Verificar Pagamento", callback_data=f"check_payment_{order.id}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("◀️ Voltar aos Pedidos", callback_data="back_to_orders")
        ])
        
        query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        user_id = "Unknown"
        if update.effective_user:
            user_id = update.effective_user.id
            
        log_error(e, f"Error showing order details for user {user_id}")
        
        try:
            update.callback_query.edit_message_text(
                "❌ Ocorreu um erro ao exibir os detalhes do pedido. Por favor, tente novamente."
            )
        except:
            pass

def check_payment_callback(update: Update, context: CallbackContext):
    """Handle check payment callback"""
    query = update.callback_query
    query.answer()
    
    data = query.data
    
    if data == "back_to_orders":
        # Show orders list again
        user_id = query.from_user.id
        
        # Get orders
        orders = db.get_user_orders(user_id)
        
        if not orders:
            query.edit_message_text(
                "📋 *Meus Pedidos*\n\n"
                "Você ainda não fez nenhum pedido.",
                parse_mode="Markdown"
            )
            return
        
        # Sort orders by creation date (newest first)
        orders.sort(key=lambda x: x.created_at, reverse=True)
        
        # Create keyboard with order details buttons
        keyboard = []
        for order in orders:
            status_text = "✅ " if order.status == "pago" else "⏳ " if order.status == "pendente" else "❌ "
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_text}Pedido #{order.id} ({order.created_at[:10]})",
                    callback_data=f"order_details_{order.id}"
                )
            ])
        
        query.edit_message_text(
            "📋 *Seus Pedidos*\n\n"
            "Selecione um pedido para ver detalhes:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith("check_payment_"):
        # Forward to payment check handler
        return check_payment_status(update, context)

# HANDLERS ADMIN

def notify_admin_new_order(context: CallbackContext, order, user):
    """Notify admin about new order"""
    if not ADMIN_ID:
        logger.error("Admin ID not configured, can't send notifications")
        return
    
    total = sum(item.price for item in order.items)
    
    message = (
        f"🔔 *CHEGOU UM NOVO PEDIDO!*\n\n"
        f"🧾 *Pedido #{order.id}*\n"
        f"👤 Cliente: {user.nome}\n"
        f"📱 Telefone: {user.telefone}\n"
        f"💰 Total: R${total:.2f}\n\n"
        f"*Itens:*\n"
    )
    
    for i, item in enumerate(order.items, 1):
        details = ""
        if item.details:
            if 'credits' in item.details:
                details = f" - {item.details['credits']} créditos"
            
            # Add any fields if present
            if 'fields' in item.details and item.details['fields']:
                fields_text = ", ".join(f"{k}: {v}" for k, v in item.details['fields'].items())
                details += f"\n   ↳ {fields_text}"
        
        message += f"{i}. {item.name} - R${item.price:.2f}{details}\n"
    
    # Add buttons for admin actions
    keyboard = [
        [InlineKeyboardButton("✅ Marcar como Entregue", callback_data=f"admin_deliver_{order.id}")],
        [InlineKeyboardButton("❌ Cancelar Pedido", callback_data=f"admin_cancel_{order.id}")]
    ]
    
    try:
        context.bot.send_message(
            chat_id=ADMIN_ID,
            text=message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")

def mark_as_delivered(update: Update, context: CallbackContext):
    """Mark order as delivered (admin only)"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    # Verify admin permissions
    if str(user_id) != ADMIN_ID:
        query.edit_message_text("❌ Você não tem permissão para realizar esta ação.")
        return
    
    data = query.data
    order_id = data.split("_")[2]
    
    # Get order
    order = db.get_order(order_id)
    
    if not order:
        query.edit_message_text("❌ Pedido não encontrado.")
        return
    
    # Update order status
    db.update_order_status(order_id, "entregue")
    
    # Notify admin
    query.edit_message_text(
        f"✅ Pedido #{order_id} marcado como ENTREGUE com sucesso!\n\n"
        f"O cliente foi notificado."
    )
    
    # Notify customer
    try:
        context.bot.send_message(
            chat_id=order.user_id,
            text=(
                f"✅ *Pedido Entregue!*\n\n"
                f"Seu pedido #{order_id} foi marcado como ENTREGUE.\n\n"
                f"Obrigado por comprar conosco!"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error notifying customer about delivery: {e}")

def cancel_order(update: Update, context: CallbackContext):
    """Cancel order (admin only)"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    # Verify admin permissions
    if str(user_id) != ADMIN_ID:
        query.edit_message_text("❌ Você não tem permissão para realizar esta ação.")
        return
    
    data = query.data
    order_id = data.split("_")[2]
    
    # Get order
    order = db.get_order(order_id)
    
    if not order:
        query.edit_message_text("❌ Pedido não encontrado.")
        return
    
    # Update order status
    db.update_order_status(order_id, "cancelado")
    
    # Notify admin
    query.edit_message_text(
        f"❌ Pedido #{order_id} CANCELADO com sucesso!\n\n"
        f"O cliente foi notificado."
    )
    
    # Notify customer
    try:
        context.bot.send_message(
            chat_id=order.user_id,
            text=(
                f"❌ *Pedido Cancelado*\n\n"
                f"Infelizmente seu pedido #{order_id} foi cancelado.\n\n"
                f"Entre em contato conosco para mais informações."
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error notifying customer about cancellation: {e}")

def admin_view_order(update: Update, context: CallbackContext):
    """Admin handler to view and manage a specific order"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    # Verify admin permissions
    if str(user_id) != ADMIN_ID:
        query.edit_message_text("❌ Você não tem permissão para realizar esta ação.")
        return
    
    # Extract order ID from callback data
    order_id = query.data.split("_")[3]
    
    # Get order
    order = db.get_order(order_id)
    if not order:
        query.edit_message_text("❌ Pedido não encontrado.")
        return
    
    # Get user info
    user = db.get_user(order.user_id)
    user_name = user.nome if user else "Cliente desconhecido"
    user_phone = user.telefone if user else "Telefone não disponível"
    
    # Format order details
    order_details = format_order_details(order, include_items=True)
    
    # Format admin message
    admin_message = (
        f"📋 *DETALHES DO PEDIDO #{order_id}*\n\n"
        f"👤 *Cliente:* {user_name}\n"
        f"📱 *Telefone:* {user_phone}\n\n"
        f"{order_details}"
    )
    
    # Create keyboard with admin actions
    keyboard = [
        [InlineKeyboardButton("✅ Marcar como Entregue", callback_data=f"admin_deliver_{order_id}")],
        [InlineKeyboardButton("❌ Cancelar Pedido", callback_data=f"admin_cancel_{order_id}")],
        [InlineKeyboardButton("◀️ Voltar aos Pedidos", callback_data="admin_back_to_pending")]
    ]
    
    # Send message
    query.edit_message_text(
        admin_message,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def list_pending_orders(update: Update, context: CallbackContext):
    """List all pending orders (admin only)"""
    user_id = update.effective_user.id
    
    # Verificar origem da chamada (message ou callback query)
    is_callback = update.callback_query is not None
    
    # Verify admin permissions
    if str(user_id) != ADMIN_ID:
        if is_callback:
            update.callback_query.answer("❌ Você não tem permissão para realizar esta ação.")
            return
        else:
            update.message.reply_text("❌ Você não tem permissão para realizar esta ação.")
            return
    
    # Se for callback, responder imediatamente
    if is_callback:
        update.callback_query.answer()
    
    # Get all orders
    all_orders = db.orders.values()
    pending_orders = [order for order in all_orders if order.status == "pendente" or order.status == "pago"]
    
    # Mensagem para quando não há pedidos pendentes
    if not pending_orders:
        no_orders_text = (
            "📋 *Pedidos Pendentes*\n\n"
            "Não há pedidos pendentes no momento."
        )
        
        if is_callback:
            update.callback_query.edit_message_text(
                no_orders_text,
                parse_mode="Markdown"
            )
        else:
            update.message.reply_text(
                no_orders_text,
                parse_mode="Markdown"
            )
        return
    
    # Sort by date (newest first)
    pending_orders.sort(key=lambda x: x.created_at, reverse=True)
    
    # Create keyboard with order buttons
    keyboard = []
    for order in pending_orders:
        status_emoji = "✅" if order.status == "pago" else "⏳"
        user = db.get_user(order.user_id)
        user_name = user.nome if user else "Cliente desconhecido"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status_emoji} #{order.id} - {user_name}",
                callback_data=f"admin_view_order_{order.id}"
            )
        ])
    
    orders_message = (
        "📋 *Pedidos Pendentes*\n\n"
        "Selecione um pedido para gerenciar:"
    )
    
    # Enviar mensagem de acordo com o tipo de origem
    if is_callback:
        update.callback_query.edit_message_text(
            orders_message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        update.message.reply_text(
            orders_message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# HANDLERS DE ADMIN PRODUTOS

def is_admin(user_id):
    """Check if the user is an admin"""
    return str(user_id) == ADMIN_ID

def admin_area(update: Update, context: CallbackContext):
    """Handler para o botão de área de administrador"""
    user_id = update.message.from_user.id
    
    # Verificar se o usuário já é admin
    if is_admin(user_id):
        # Se já for admin, mostrar menu de administração
        admin_products(update, context)
        return
    
    # Se não for admin, iniciar fluxo de autenticação
    update.message.reply_text(
        "🔐 *Autenticação de Administrador*\n\n"
        "Para acessar a área administrativa, é necessário autenticação.\n"
        "Digite seu ID de administrador para continuar:",
        parse_mode="Markdown"
    )
    
    return ADMIN_AUTH

def admin_auth_handler(update: Update, context: CallbackContext):
    """Processa a tentativa de autenticação como administrador"""
    user_id = update.message.from_user.id
    entered_id = update.message.text.strip()
    
    # Verificar se o ID digitado corresponde ao ADMIN_ID configurado
    if entered_id == ADMIN_ID:
        logger.info(f"Usuário {user_id} autenticado como administrador")
        update.message.reply_text(
            "✅ *Autenticação bem-sucedida!*\n\n"
            "Você foi autenticado como administrador do sistema.\n"
            "Agora você tem acesso às funcionalidades administrativas.",
            parse_mode="Markdown"
        )
        
        # Redirecionar para o menu de administração de produtos
        admin_products(update, context)
        return ConversationHandler.END
    else:
        logger.warning(f"Tentativa de autenticação falha para usuário {user_id}")
        update.message.reply_text(
            "❌ *Autenticação falhou*\n\n"
            "O ID informado não corresponde ao ID de administrador configurado.\n"
            "Acesso negado.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

def admin_products(update: Update, context: CallbackContext):
    """Admin command to manage products"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        if update.callback_query:
            update.callback_query.answer("❌ Você não tem permissão para acessar esta área administrativa.")
            return ConversationHandler.END
        else:
            update.message.reply_text("❌ Você não tem permissão para acessar esta área administrativa.")
            return ConversationHandler.END
    
    # Create keyboard with categories
    keyboard = []
    for category in PRODUCT_CATALOG.keys():
        keyboard.append([InlineKeyboardButton(f"📂 {category}", callback_data=f"admin_cat_{category}")])
    
    # Add button to add new category
    keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
    
    # Mensagem de gerenciamento de produtos
    admin_message = "🛠️ *Gerenciamento de Produtos*\n\n" \
                    "Selecione uma categoria para gerenciar seus produtos:"
    
    # Determinar se é uma mensagem ou um callback
    if update.callback_query:
        update.callback_query.answer()
        update.callback_query.edit_message_text(
            text=admin_message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        update.message.reply_text(
            text=admin_message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return CATEGORY_SELECTION

def admin_select_category(update: Update, context: CallbackContext):
    """Handle admin category selection"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        query.edit_message_text("❌ Você não tem permissão para acessar esta área administrativa.")
        return ConversationHandler.END
    
    data = query.data
    
    # Handle adding new category
    if data == "admin_add_category":
        query.edit_message_text(
            "➕ *Adicionar Nova Categoria*\n\n"
            "Por favor, envie o nome da nova categoria:"
        )
        context.user_data['admin_action'] = 'add_category'
        return ADD_PRODUCT_NAME
    
    # Handle existing category
    category_name = data.split("_")[2]
    context.user_data['admin_category'] = category_name
    
    # Show products in this category
    products = PRODUCT_CATALOG.get(category_name, [])
    
    keyboard = []
    for i, product in enumerate(products):
        keyboard.append([
            InlineKeyboardButton(
                f"{product['name']} - R${product['price']:.2f}", 
                callback_data=f"admin_prod_{i}"
            )
        ])
    
    # Add button to add new product
    keyboard.append([InlineKeyboardButton("➕ Adicionar Produto", callback_data="admin_add_product")])
    # Add button to delete category
    keyboard.append([InlineKeyboardButton("❌ Excluir Categoria", callback_data=f"admin_delete_category_{category_name}")])
    # Add button to go back
    keyboard.append([InlineKeyboardButton("◀️ Voltar", callback_data="admin_back_to_categories")])
    
    query.edit_message_text(
        f"🛠️ *Gerenciamento de Produtos: {category_name}*\n\n"
        f"Selecione um produto para editar ou excluir:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return PRODUCT_ACTION

def admin_select_product(update: Update, context: CallbackContext):
    """Handle admin product selection"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        query.edit_message_text("❌ Você não tem permissão para acessar esta área administrativa.")
        return ConversationHandler.END
    
    data = query.data
    
    # Handle back button
    if data == "admin_back_to_categories":
        # Create keyboard with categories
        keyboard = []
        for category in PRODUCT_CATALOG.keys():
            keyboard.append([InlineKeyboardButton(f"📂 {category}", callback_data=f"admin_cat_{category}")])
        
        # Add button to add new category
        keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
        
        query.edit_message_text(
            "🛠️ *Gerenciamento de Produtos*\n\n"
            "Selecione uma categoria para gerenciar seus produtos:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return CATEGORY_SELECTION
    
    # Handle adding new product
    if data == "admin_add_product":
        category = context.user_data.get('admin_category')
        
        query.edit_message_text(
            f"➕ *Adicionar Novo Produto em {category}*\n\n"
            "Por favor, envie o nome do produto:"
        )
        
        context.user_data['admin_action'] = 'add_product'
        return ADD_PRODUCT_NAME
    
    # Handle existing product
    category = context.user_data.get('admin_category')
    product_index = int(data.split("_")[2])
    
    product = PRODUCT_CATALOG[category][product_index]
    context.user_data['admin_product_index'] = product_index
    
    # Show product details with edit/delete options
    fields_text = ", ".join(product.get('fields', [])) if 'fields' in product else "Nenhum"
    discount_text = "Sim" if product.get('discount', False) else "Não"
    
    product_info = (
        f"🔍 *Detalhes do Produto*\n\n"
        f"📝 Nome: {product['name']}\n"
        f"💰 Preço: R${product['price']:.2f}\n"
    )
    
    if 'fields' in product:
        product_info += f"📋 Campos: {fields_text}\n"
    
    if 'discount' in product:
        product_info += f"🏷️ Desconto: {discount_text}\n"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Editar Nome", callback_data="admin_edit_name")],
        [InlineKeyboardButton("💰 Editar Preço", callback_data="admin_edit_price")]
    ]
    
    if 'fields' in product:
        keyboard.append([InlineKeyboardButton("📋 Editar Campos", callback_data="admin_edit_fields")])
    
    if 'discount' in product:
        keyboard.append([InlineKeyboardButton("🏷️ Alterar Desconto", callback_data="admin_edit_discount")])
    
    keyboard.append([InlineKeyboardButton("❌ Excluir Produto", callback_data="admin_delete_product")])
    keyboard.append([InlineKeyboardButton("◀️ Voltar", callback_data=f"admin_cat_{category}")])
    
    query.edit_message_text(
        product_info,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return EDIT_PRODUCT_FIELD

def admin_edit_product_field(update: Update, context: CallbackContext):
    """Handle product field selection for editing"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        query.edit_message_text("❌ Você não tem permissão para acessar esta área administrativa.")
        return ConversationHandler.END
    
    data = query.data
    category = context.user_data.get('admin_category')
    
    # Handle back to category
    if data.startswith("admin_cat_"):
        return admin_select_category(update, context)
    
    # Handle delete category
    if data.startswith("admin_delete_category_"):
        category_name = data.split("_")[3]
        
        query.edit_message_text(
            f"❓ *Confirmar Exclusão da Categoria*\n\n"
            f"Tem certeza que deseja excluir a categoria:\n"
            f"*{category_name}*?\n\n"
            f"Todos os produtos desta categoria serão removidos.\n"
            f"Esta ação não pode ser desfeita.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Sim, Excluir Categoria", callback_data=f"admin_confirm_delete_category_{category_name}")],
                [InlineKeyboardButton("❌ Não, Cancelar", callback_data=f"admin_cat_{category_name}")]
            ])
        )
        
        return CONFIRM_DELETE
    
    # Handle delete product
    if data == "admin_delete_product":
        product_index = context.user_data.get('admin_product_index')
        product = PRODUCT_CATALOG[category][product_index]
        
        query.edit_message_text(
            f"❓ *Confirmar Exclusão*\n\n"
            f"Tem certeza que deseja excluir o produto:\n"
            f"*{product['name']}*?\n\n"
            f"Esta ação não pode ser desfeita.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Sim, Excluir", callback_data="admin_confirm_delete")],
                [InlineKeyboardButton("❌ Não, Cancelar", callback_data=f"admin_prod_{product_index}")]
            ])
        )
        
        return CONFIRM_DELETE
    
    # Handle various edit options
    if data.startswith("admin_edit_"):
        field = data.split("_")[2]
        product_index = context.user_data.get('admin_product_index')
        product = PRODUCT_CATALOG[category][product_index]
        
        context.user_data['admin_edit_field'] = field
        
        if field == "name":
            query.edit_message_text(
                f"✏️ *Editar Nome do Produto*\n\n"
                f"Nome atual: {product['name']}\n\n"
                f"Por favor, envie o novo nome para este produto:"
            )
            return EDIT_PRODUCT_VALUE
            
        elif field == "price":
            query.edit_message_text(
                f"💰 *Editar Preço do Produto*\n\n"
                f"Preço atual: R${product['price']:.2f}\n\n"
                f"Por favor, envie o novo preço para este produto (apenas números):"
            )
            return EDIT_PRODUCT_VALUE
            
        elif field == "fields":
            fields_text = ", ".join(product.get('fields', []))
            query.edit_message_text(
                f"📋 *Editar Campos do Produto*\n\n"
                f"Campos atuais: {fields_text}\n\n"
                f"Por favor, envie os novos campos separados por vírgula:"
            )
            return EDIT_PRODUCT_VALUE
            
        elif field == "discount":
            current = "ativado" if product.get('discount', False) else "desativado"
            query.edit_message_text(
                f"🏷️ *Alterar Desconto do Produto*\n\n"
                f"Desconto atual: {current}\n\n"
                f"Escolha uma opção:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Ativar Desconto", callback_data="admin_set_discount_true")],
                    [InlineKeyboardButton("❌ Desativar Desconto", callback_data="admin_set_discount_false")],
                    [InlineKeyboardButton("◀️ Voltar", callback_data=f"admin_prod_{product_index}")]
                ])
            )
            return EDIT_PRODUCT_VALUE
    
    return EDIT_PRODUCT_FIELD

def admin_edit_discount(update: Update, context: CallbackContext):
    """Handle discount setting via inline buttons"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        query.edit_message_text("❌ Você não tem permissão para acessar esta área administrativa.")
        return ConversationHandler.END
    
    data = query.data
    category = context.user_data.get('admin_category')
    product_index = context.user_data.get('admin_product_index')
    
    if data.startswith("admin_set_discount_"):
        value = data.split("_")[-1] == "true"
        
        # Update product discount
        PRODUCT_CATALOG[category][product_index]['discount'] = value
        
        product = PRODUCT_CATALOG[category][product_index]
        
        # Indicar que está salvando
        query.edit_message_text(
            f"🔄 Atualizando desconto para *{product['name']}* e salvando alterações...",
            parse_mode="Markdown"
        )
        
        # Salvar o catálogo localmente (removida integração com Git)
        try:
            # Apenas exportamos o catálogo para JSON
            with open('data/catalog.json', 'w', encoding='utf-8') as f:
                json.dump(PRODUCT_CATALOG, f, ensure_ascii=False, indent=4)
            logger.info(f"Catálogo salvo após atualizar desconto do produto '{product['name']}'")
            save_success = True
        except Exception as e:
            logger.error(f"Erro ao salvar catálogo após atualizar desconto: {e}")
            save_success = False
        
        # Mostrar mensagem de confirmação
        query.edit_message_text(
            f"✅ *Desconto Atualizado!*\n\n"
            f"Produto: {product['name']}\n"
            f"Desconto: {'Ativado' if value else 'Desativado'}\n\n"
            f"{'✓ Alterações salvas com sucesso' if save_success else '⚠️ Erro ao salvar alterações'}\n"
            f"Voltando para o menu do produto...",
            parse_mode="Markdown"
        )
        
        # Simulate going back to product view
        context.user_data['admin_action'] = None
        context.user_data['admin_edit_field'] = None
        
        # Wait a moment before returning to product view
        time.sleep(1)
        
        # Now get product details again
        return admin_select_product(update, context)
    
    return EDIT_PRODUCT_FIELD

def admin_handle_edit_value(update: Update, context: CallbackContext):
    """Process the new value for product editing"""
    category = context.user_data.get('admin_category')
    product_index = context.user_data.get('admin_product_index')
    field = context.user_data.get('admin_edit_field')
    
    if not all([category, str(product_index).isdigit(), field]):
        update.message.reply_text("❌ Ocorreu um erro. Por favor, tente novamente.")
        return ConversationHandler.END
    
    product_index = int(product_index)
    new_value = update.message.text.strip()
    product_name = PRODUCT_CATALOG[category][product_index]['name']
    
    # Validate and update accordingly
    try:
        if field == "name":
            if not new_value:
                update.message.reply_text("❌ O nome não pode ficar vazio. Por favor, tente novamente.")
                return EDIT_PRODUCT_VALUE
            
            PRODUCT_CATALOG[category][product_index]['name'] = new_value
            product_name = new_value  # Atualizar nome para mensagem
            
        elif field == "price":
            try:
                price = float(new_value.replace(',', '.'))
                if price <= 0:
                    raise ValueError("Price must be positive")
                
                PRODUCT_CATALOG[category][product_index]['price'] = price
            except:
                update.message.reply_text("❌ Preço inválido. Use apenas números (ex: 10.50). Por favor, tente novamente.")
                return EDIT_PRODUCT_VALUE
                
        elif field == "fields":
            fields = [f.strip() for f in new_value.split(',') if f.strip()]
            if not fields:
                update.message.reply_text("❌ Você deve fornecer pelo menos um campo. Por favor, tente novamente.")
                return EDIT_PRODUCT_VALUE
                
            PRODUCT_CATALOG[category][product_index]['fields'] = fields
        
        # Indicar que está salvando
        update.message.reply_text(
            "🔄 Salvando alterações no catálogo e realizando commit...",
            parse_mode="Markdown"
        )
        
        # Salvar o catálogo localmente
        try:
            save_catalog_to_git()
            logger.info(f"Catálogo salvo após edição do produto '{product_name}', campo '{field}'")
            save_success = True
        except Exception as e:
            logger.error(f"Erro ao salvar catálogo: {e}")
            save_success = False
        
        # Send confirmation and show product menu again
        update.message.reply_text(
            f"✅ *Produto atualizado com sucesso!*\n\n"
            f"Campo: {field}\n"
            f"Novo valor: {new_value}\n\n"
            f"{'✓ Alterações salvas com sucesso' if save_success else '⚠️ Erro ao salvar alterações'}",
            parse_mode="Markdown"
        )
        
        # Show admin menu again
        keyboard = []
        for cat in PRODUCT_CATALOG.keys():
            keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data=f"admin_cat_{cat}")])
        
        keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
        
        update.message.reply_text(
            "🛠️ *Gerenciamento de Produtos*\n\n"
            "Selecione uma categoria para gerenciar seus produtos:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return CATEGORY_SELECTION
        
    except Exception as e:
        logger.error(f"Erro ao editar produto: {e}")
        update.message.reply_text(f"❌ Ocorreu um erro: {str(e)}. Por favor, tente novamente.")
        return EDIT_PRODUCT_VALUE

def admin_confirm_delete_product(update: Update, context: CallbackContext):
    """Confirm and process product/category deletion"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        query.edit_message_text("❌ Você não tem permissão para acessar esta área administrativa.")
        return ConversationHandler.END
    
    data = query.data
    
    # Handle category deletion
    if data.startswith("admin_confirm_delete_category_"):
        category_name = data.split("_")[4]
        
        # Indicar que está salvando as mudanças
        query.edit_message_text(
            f"🔄 Excluindo categoria *{category_name}* e salvando alterações...",
            parse_mode="Markdown"
        )
        
        # Delete the category
        if category_name in PRODUCT_CATALOG:
            del PRODUCT_CATALOG[category_name]
            
            # Salvar o catálogo localmente
            try:
                save_catalog_to_git()
                logger.info(f"Catálogo salvo após exclusão da categoria '{category_name}'")
                save_success = True
            except Exception as e:
                logger.error(f"Erro ao salvar catálogo após exclusão da categoria: {e}")
                save_success = False
            
            # Mostrar mensagem de confirmação
            query.edit_message_text(
                f"✅ *Categoria Excluída!*\n\n"
                f"A categoria *{category_name}* foi excluída com sucesso.\n"
                f"{'✓ Alterações salvas com sucesso' if save_success else '⚠️ Erro ao salvar alterações'}",
                parse_mode="Markdown"
            )
        else:
            query.edit_message_text(
                f"❌ *Erro ao Excluir Categoria*\n\n"
                f"A categoria *{category_name}* não foi encontrada.",
                parse_mode="Markdown"
            )
        
        # Return to categories list after a short delay
        time.sleep(1)
        
        # Show admin menu again with updated categories
        keyboard = []
        for category in PRODUCT_CATALOG.keys():
            keyboard.append([InlineKeyboardButton(f"📂 {category}", callback_data=f"admin_cat_{category}")])
        
        # Add button to add new category
        keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
        
        query.edit_message_text(
            "🛠️ *Gerenciamento de Produtos*\n\n"
            "Selecione uma categoria para gerenciar seus produtos:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return CATEGORY_SELECTION
    
    # Handle product deletion
    elif data == "admin_confirm_delete":
        category = context.user_data.get('admin_category')
        product_index = context.user_data.get('admin_product_index')
        
        # Get product before deletion for confirmation message
        product = PRODUCT_CATALOG[category][product_index]
        product_name = product['name']
        
        # Delete the product
        del PRODUCT_CATALOG[category][product_index]
        
        # Indicar que está salvando as mudanças
        query.edit_message_text(
            f"🔄 Excluindo produto *{product_name}* e salvando alterações...",
            parse_mode="Markdown"
        )
        
        # Salvar o catálogo localmente
        try:
            save_catalog_to_git()
            logger.info(f"Catálogo salvo após exclusão do produto '{product_name}'")
            save_success = True
        except Exception as e:
            logger.error(f"Erro ao salvar catálogo após exclusão: {e}")
            save_success = False
        
        # Mostrar mensagem de confirmação
        query.edit_message_text(
            f"✅ *Produto Excluído!*\n\n"
            f"O produto *{product_name}* foi excluído com sucesso.\n"
            f"{'✓ Alterações salvas com sucesso' if save_success else '⚠️ Erro ao salvar alterações'}",
            parse_mode="Markdown"
        )
        
        # Return to category view after a short delay
        time.sleep(1)
        
        # Show products in this category again
        return admin_select_category(update, context)
    
    # If not confirmed, go back
    if data.startswith("admin_prod_"):
        product_index = context.user_data.get('admin_product_index')
        context.user_data['admin_action'] = None
        return admin_select_product(update, context)
    else:
        # Return to category
        return admin_select_category(update, context)

def admin_add_product_name(update: Update, context: CallbackContext):
    """Handle new product name input"""
    if not update.message:
        # Caso anômalo - não temos uma mensagem para processar
        return ConversationHandler.END
        
    action = context.user_data.get('admin_action')
    
    # Add cancel option with a keyboard
    keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="admin_cancel_add")]]
    
    if action == 'add_category':
        category_name = update.message.text.strip()
        if not category_name:
            update.message.reply_text(
                "❌ O nome da categoria não pode ficar vazio. Tente novamente:", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ADD_PRODUCT_NAME
        
        if category_name in PRODUCT_CATALOG:
            update.message.reply_text(
                "❌ Esta categoria já existe. Escolha outro nome:", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ADD_PRODUCT_NAME
        
        # Add new empty category
        PRODUCT_CATALOG[category_name] = []
        
        # Indicar que está salvando
        update.message.reply_text(
            f"🔄 Adicionando categoria *{category_name}* e salvando alterações...",
            parse_mode="Markdown"
        )
        
        # Salvar o catálogo localmente
        try:
            save_catalog_to_git()
            logger.info(f"Catálogo salvo após adicionar categoria '{category_name}'")
            save_success = True
        except Exception as e:
            logger.error(f"Erro ao salvar catálogo após adicionar categoria: {e}")
            save_success = False
        
        update.message.reply_text(
            f"✅ *Nova Categoria Adicionada!*\n\n"
            f"A categoria *{category_name}* foi criada com sucesso.\n"
            f"{'✓ Alterações salvas com sucesso' if save_success else '⚠️ Erro ao salvar alterações'}",
            parse_mode="Markdown"
        )
        
        # Show admin menu again
        keyboard = []
        for cat in PRODUCT_CATALOG.keys():
            keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data=f"admin_cat_{cat}")])
        
        keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
        
        update.message.reply_text(
            "🛠️ *Gerenciamento de Produtos*\n\n"
            "Selecione uma categoria para gerenciar seus produtos:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return CATEGORY_SELECTION
        
    elif action == 'add_product':
        product_name = update.message.text.strip()
        if not product_name:
            update.message.reply_text(
                "❌ O nome do produto não pode ficar vazio. Tente novamente:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ADD_PRODUCT_NAME
        
        user_id = update.effective_user.id
        # Store in temporary storage
        product_temp_data[user_id] = {'name': product_name}
        
        # Log para debug
        from utils import log_error
        log_error(f"Produto temp iniciado: {product_temp_data[user_id]}", f"Usuário {user_id}")
        
        update.message.reply_text(
            "💰 *Preço do Produto*\n\n"
            "Por favor, informe o preço do produto (apenas números):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ADD_PRODUCT_PRICE
    
    update.message.reply_text(
        "❌ Operação inválida. Use /admin para voltar ao menu administrativo.",
        reply_markup=MAIN_KEYBOARD
    )
    return ConversationHandler.END

def admin_add_product_price(update: Update, context: CallbackContext):
    """Handle new product price input"""
    if not update.message:
        # Caso anômalo - não temos uma mensagem para processar
        return ConversationHandler.END
        
    try:
        price_text = update.message.text.strip().replace(',', '.')
        price = float(price_text)
        
        if price <= 0:
            update.message.reply_text(
                "❌ O preço deve ser maior que zero. Tente novamente:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="admin_cancel_add")]])
            )
            return ADD_PRODUCT_PRICE
        
        # Store price in temp data
        user_id = update.effective_user.id
        if user_id not in product_temp_data:
            # Log para debug
            from utils import log_error
            log_error("Produto temp não encontrado ao tentar adicionar preço", f"Usuário {user_id}")
            product_temp_data[user_id] = {}
        
        product_temp_data[user_id]['price'] = price
        
        # Log para debug
        from utils import log_error
        log_error(f"Preço adicionado ao produto temp: {product_temp_data[user_id]}", f"Usuário {user_id}")
        
        # Ask for product type: app (with fields), credit (with discount), or fixed price (no discount)
        update.message.reply_text(
            "📦 *Tipo de Produto*\n\n"
            "Escolha o tipo do produto:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Aplicativo (Campos)", callback_data="admin_type_app")],
                [InlineKeyboardButton("💰 Créditos (Desconto)", callback_data="admin_type_credit")],
                [InlineKeyboardButton("🏷️ Preço Fixo (Sem Desconto)", callback_data="admin_type_fixed")]
            ])
        )
        
        return ADD_PRODUCT_FIELDS
        
    except ValueError:
        update.message.reply_text(
            "❌ Preço inválido. Use apenas números (ex: 10.50). Tente novamente:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="admin_cancel_add")]])
        )
        return ADD_PRODUCT_PRICE

def admin_add_product_type(update: Update, context: CallbackContext):
    """Handle product type selection"""
    query = update.callback_query
    query.answer()
    
    data = query.data
    user_id = query.from_user.id
    category = context.user_data.get('admin_category')
    
    if user_id not in product_temp_data:
        query.edit_message_text("❌ Erro nos dados do produto. Por favor, comece novamente.")
        return ConversationHandler.END
    
    # Handle app product (needs fields)
    if data == "admin_type_app":
        query.edit_message_text(
            "📋 *Campos do Produto*\n\n"
            "Por favor, informe os campos necessários, separados por vírgula.\n"
            "Exemplo: MAC, Email, Senha"
        )
        product_temp_data[user_id]['type'] = 'app'
        return ADD_PRODUCT_FIELDS
    
    # Handle credit product (has discount option)
    elif data == "admin_type_credit" or data == "admin_type_fixed":
        is_credit = data == "admin_type_credit"
        product_type = "crédito" if is_credit else "preço fixo"
        
        # Finalize product creation
        new_product = {
            'name': product_temp_data[user_id]['name'],
            'price': product_temp_data[user_id]['price'],
            'discount': True if is_credit else False  # Only apply discount for credit products
        }
        
        # Add to catalog
        PRODUCT_CATALOG[category].append(new_product)
        
        # Informar que está salvando as alterações
        query.edit_message_text(
            f"🔄 Adicionando produto *{new_product['name']}* e salvando alterações...",
            parse_mode="Markdown"
        )
        
        # Salvar o catálogo localmente
        try:
            save_catalog_to_git()
            logger.info(f"Catálogo salvo após adicionar produto de {product_type} '{new_product['name']}'")
            save_success = True
        except Exception as e:
            logger.error(f"Erro ao salvar catálogo após adicionar produto: {e}")
            save_success = False
        
        # Clear temp data
        if user_id in product_temp_data:
            del product_temp_data[user_id]
        
        # Mostrar mensagem de confirmação com informação sobre desconto
        discount_info = "com desconto aplicável" if is_credit else "sem desconto aplicável"
        query.edit_message_text(
            f"✅ *Produto Adicionado!*\n\n"
            f"O produto *{new_product['name']}* foi adicionado à categoria *{category}* com sucesso.\n"
            f"Tipo: {product_type} ({discount_info}).\n"
            f"{'✓ Alterações salvas com sucesso' if save_success else '⚠️ Erro ao salvar alterações'}",
            parse_mode="Markdown"
        )
        
        # Return to category view after a short delay
        time.sleep(1)
        
        # Show updated category
        return admin_select_category(update, context)
    
    return ADD_PRODUCT_FIELDS

def admin_add_product_fields(update: Update, context: CallbackContext):
    """Handle product fields input for app products"""
    user_id = update.effective_user.id
    category = context.user_data.get('admin_category')
    
    # Check if this is a callback for cancel
    if update.callback_query:
        query = update.callback_query
        query.answer()
        
        if query.data == "admin_cancel_add":
            # Clear temp data
            if user_id in product_temp_data:
                del product_temp_data[user_id]
                
            query.edit_message_text("❌ Adição de produto cancelada.")
            
            # Show categories after a moment
            time.sleep(1)
            
            # Create keyboard with categories
            keyboard = []
            for cat in PRODUCT_CATALOG.keys():
                keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data=f"admin_cat_{cat}")])
            
            keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
            
            context.bot.send_message(
                chat_id=user_id,
                text="🛠️ *Gerenciamento de Produtos*\n\n"
                    "Selecione uma categoria para gerenciar seus produtos:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return CATEGORY_SELECTION
        return ADD_PRODUCT_FIELDS
    
    # Este é um tratamento para mensagem de texto (não é callback)
    if not update.message:
        # Caso anômalo - nem callback nem mensagem
        return ConversationHandler.END
        
    # Processar mensagem normal
    fields_text = update.message.text.strip()
    fields = [f.strip() for f in fields_text.split(',') if f.strip()]
    
    if user_id not in product_temp_data:
        # Não temos dados temporários - precisamos informar o usuário
        update.message.reply_text(
            "❌ Erro: não encontramos dados do produto em andamento. Por favor, inicie o processo novamente usando o comando de administração.",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END
        
    # Verificar se temos tipo definido (app ou credit)
    if 'type' not in product_temp_data[user_id]:
        product_temp_data[user_id]['type'] = 'app'  # Define padrão como app se não estiver definido
    
    if not fields:
        update.message.reply_text(
            "❌ Você deve fornecer pelo menos um campo. Tente novamente:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="admin_cancel_add")]])
        )
        return ADD_PRODUCT_FIELDS
    
    # Create new app product
    new_product = {
        'name': product_temp_data[user_id]['name'],
        'price': product_temp_data[user_id]['price'],
        'fields': fields
    }
    
    # Add to catalog
    PRODUCT_CATALOG[category].append(new_product)
    
    # Indicar que está salvando o produto
    update.message.reply_text(
        f"🔄 Adicionando produto *{new_product['name']}* e salvando alterações...",
        parse_mode="Markdown"
    )
    
    # Salvar o catálogo localmente
    try:
        save_catalog_to_git()
        logger.info(f"Catálogo salvo após adicionar produto de aplicativo '{new_product['name']}'")
        save_success = True
    except Exception as e:
        logger.error(f"Erro ao salvar catálogo após adicionar produto: {e}")
        save_success = False
    
    # Clear temp data
    if user_id in product_temp_data:
        del product_temp_data[user_id]
    
    update.message.reply_text(
        f"✅ *Produto Adicionado!*\n\n"
        f"O produto *{new_product['name']}* foi adicionado à categoria *{category}* com sucesso.\n"
        f"{'✓ Alterações salvas com sucesso' if save_success else '⚠️ Erro ao salvar alterações'}",
        parse_mode="Markdown"
    )
    
    # Show admin menu again
    keyboard = []
    for cat in PRODUCT_CATALOG.keys():
        keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data=f"admin_cat_{cat}")])
    
    keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
    
    update.message.reply_text(
        "🛠️ *Gerenciamento de Produtos*\n\n"
        "Selecione uma categoria para gerenciar seus produtos:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return CATEGORY_SELECTION

def admin_cancel(update: Update, context: CallbackContext):
    """Cancel admin operations"""
    user_id = update.effective_user.id
    
    # Clear temp data
    if user_id in product_temp_data:
        del product_temp_data[user_id]
    
    context.user_data.pop('admin_category', None)
    context.user_data.pop('admin_product_index', None)
    context.user_data.pop('admin_action', None)
    context.user_data.pop('admin_edit_field', None)
    
    # Handle callback or message
    if update.callback_query:
        query = update.callback_query
        query.answer()
        query.edit_message_text(
            "❌ Operação administrativa cancelada."
        )
        
        # Return to main admin panel after a moment
        time.sleep(1)
        
        # Create keyboard with categories
        keyboard = []
        for cat in PRODUCT_CATALOG.keys():
            keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data=f"admin_cat_{cat}")])
        
        keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
        
        context.bot.send_message(
            chat_id=user_id,
            text="🛠️ *Gerenciamento de Produtos*\n\n"
                "Selecione uma categoria para gerenciar seus produtos:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return CATEGORY_SELECTION
    elif update.message:
        update.message.reply_text(
            "❌ Operação administrativa cancelada.",
            reply_markup=MAIN_KEYBOARD
        )
        
        return ConversationHandler.END
    else:
        # Caso anômalo - nem callback nem mensagem
        return ConversationHandler.END

def admin_cancel_callback(update: Update, context: CallbackContext):
    """Handle cancellation via callback query"""
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    # Clear temp data
    if user_id in product_temp_data:
        del product_temp_data[user_id]
    
    context.user_data.pop('admin_category', None)
    context.user_data.pop('admin_product_index', None)
    context.user_data.pop('admin_action', None)
    context.user_data.pop('admin_edit_field', None)
    
    query.edit_message_text("❌ Operação administrativa cancelada.")
    
    # Return to main admin panel after a moment
    time.sleep(1)
    
    # Create keyboard with categories
    keyboard = []
    for cat in PRODUCT_CATALOG.keys():
        keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data=f"admin_cat_{cat}")])
    
    keyboard.append([InlineKeyboardButton("➕ Adicionar Categoria", callback_data="admin_add_category")])
    
    context.bot.send_message(
        chat_id=user_id,
        text="🛠️ *Gerenciamento de Produtos*\n\n"
            "Selecione uma categoria para gerenciar seus produtos:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return CATEGORY_SELECTION

# OTHER COMMANDS

def github_sync_command(update: Update, context: CallbackContext):
    """Sincroniza o catálogo atual com o repositório GitHub
    
    Este comando está disponível apenas para administradores e 
    envia o catálogo atual para o repositório GitHub configurado.
    """
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        update.message.reply_text(
            "⛔ Você não tem permissão para usar este comando.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    # Verificar se as variáveis de ambiente do GitHub estão configuradas
    if not (GITHUB_TOKEN and GITHUB_REPO_OWNER and GITHUB_REPO_NAME):
        update.message.reply_text(
            "⚠️ Configuração do GitHub incompleta.\n\n"
            "É necessário configurar as seguintes variáveis de ambiente:\n"
            "• GITHUB_TOKEN\n"
            "• GITHUB_REPO_OWNER\n"
            "• GITHUB_REPO_NAME\n\n"
            "Use o comando /github_setup para mais informações.",
            parse_mode="Markdown", 
            reply_markup=ADMIN_KEYBOARD
        )
        return
    
    # Enviar mensagem de processamento
    msg = update.message.reply_text(
        "🔄 Sincronizando catálogo com GitHub...",
        reply_markup=MAIN_KEYBOARD
    )
    
    try:
        # Criar uma cópia do catálogo para exportação
        catalog_copy = {}
        for category, products in PRODUCT_CATALOG.items():
            catalog_copy[category] = []
            for product in products:
                product_copy = product.copy()
                catalog_copy[category].append(product_copy)
        
        # Enviar para o GitHub
        result = github_manager.update_catalog_in_github(
            GITHUB_REPO_OWNER,
            GITHUB_REPO_NAME,
            catalog_copy,
            branch=GITHUB_BRANCH
        )
        
        if result:
            context.bot.edit_message_text(
                chat_id=msg.chat_id,
                message_id=msg.message_id,
                text="✅ Catálogo sincronizado com sucesso no GitHub!\n\n"
                     f"Repositório: {GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}\n"
                     f"Branch: {GITHUB_BRANCH}\n"
                     f"Arquivo: data/catalog.json"
            )
        else:
            context.bot.edit_message_text(
                chat_id=msg.chat_id,
                message_id=msg.message_id,
                text="❌ Erro ao sincronizar catálogo com GitHub.\n\n"
                     "Verifique os logs para mais detalhes."
            )
    except Exception as e:
        logger.error(f"Erro ao sincronizar com GitHub: {e}")
        context.bot.edit_message_text(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            text=f"❌ Erro ao sincronizar catálogo: {str(e)}"
        )

def github_info_command(update: Update, context: CallbackContext):
    """Mostra informações sobre o repositório GitHub conectado
    
    Este comando está disponível apenas para administradores e
    exibe detalhes sobre o repositório GitHub configurado.
    """
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        update.message.reply_text(
            "⛔ Você não tem permissão para usar este comando.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    # Verificar se as variáveis de ambiente do GitHub estão configuradas
    if not (GITHUB_TOKEN and GITHUB_REPO_OWNER and GITHUB_REPO_NAME):
        update.message.reply_text(
            "⚠️ Configuração do GitHub incompleta.\n\n"
            "É necessário configurar as seguintes variáveis de ambiente:\n"
            "• GITHUB_TOKEN\n"
            "• GITHUB_REPO_OWNER\n"
            "• GITHUB_REPO_NAME\n\n"
            "Use o comando /github_setup para mais informações.",
            parse_mode="Markdown", 
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    # Enviar mensagem de processamento
    msg = update.message.reply_text(
        "🔄 Obtendo informações do repositório GitHub...",
        reply_markup=MAIN_KEYBOARD
    )
    
    try:
        # Obter informações do repositório
        repo_info = github_manager.get_repository_info(GITHUB_REPO_OWNER, GITHUB_REPO_NAME)
        
        if repo_info:
            # Formatar informações do repositório
            repo_text = (
                f"📊 *Informações do Repositório GitHub*\n\n"
                f"*Nome:* {repo_info['full_name']}\n"
                f"*Descrição:* {repo_info.get('description', 'Sem descrição')}\n"
                f"*Branch padrão:* {repo_info.get('default_branch', 'main')}\n"
                f"*Branch configurado:* {GITHUB_BRANCH}\n"
                f"*Visibilidade:* {repo_info.get('visibility', 'desconhecida')}\n"
                f"*URL:* {repo_info.get('html_url', '-')}\n\n"
                f"*Estatísticas:*\n"
                f"• Stars: {repo_info.get('stargazers_count', 0)}\n"
                f"• Forks: {repo_info.get('forks_count', 0)}\n"
                f"• Issues abertas: {repo_info.get('open_issues_count', 0)}\n\n"
                f"*Configuração do Bot:*\n"
                f"• Arquivo de catálogo: data/catalog.json\n"
                f"• Último sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Editar mensagem
            context.bot.edit_message_text(
                chat_id=msg.chat_id,
                message_id=msg.message_id,
                text=repo_text,
                parse_mode="Markdown"
            )
        else:
            context.bot.edit_message_text(
                chat_id=msg.chat_id,
                message_id=msg.message_id,
                text="❌ Não foi possível obter informações do repositório.\n\n"
                     "Verifique se o token e o nome do repositório estão corretos."
            )
    except Exception as e:
        logger.error(f"Erro ao obter informações do GitHub: {e}")
        context.bot.edit_message_text(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            text=f"❌ Erro ao acessar repositório: {str(e)}"
        )

def github_setup_command(update: Update, context: CallbackContext):
    """Exibe instruções para configurar o GitHub
    
    Este comando está disponível apenas para administradores e
    fornece orientações sobre como configurar o GitHub.
    """
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        update.message.reply_text(
            "⛔ Você não tem permissão para usar este comando.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    # Preparar mensagem de ajuda para configuração
    setup_text = (
        "🔧 <b>Configuração do GitHub</b>\n\n"
        "Para conectar o bot ao GitHub, configure as seguintes variáveis de ambiente:\n\n"
        "<b>1. GITHUB_TOKEN</b>\n"
        "Token de acesso pessoal do GitHub com permissão para repositórios.\n"
        "Você pode criar um token em GitHub - Settings - Developer Settings - Personal Access Tokens.\n\n"
        "<b>2. GITHUB_REPO_OWNER</b>\n"
        "Nome do usuário ou organização dona do repositório.\n\n"
        "<b>3. GITHUB_REPO_NAME</b>\n"
        "Nome do repositório onde o catálogo será armazenado.\n\n"
        "<b>4. GITHUB_BRANCH</b> (opcional)\n"
        "Branch do repositório. O padrão é 'main' se não for especificado.\n\n"
        "<b>Instruções:</b>\n"
        "• Crie um repositório no GitHub (público ou privado)\n"
        "• Configure as variáveis de ambiente no seu provedor de hospedagem\n"
        "• Reinicie o bot após configurar as variáveis\n"
        "• Use o comando /github_info para verificar a conexão\n"
        "• Use o comando /github_sync para sincronizar o catálogo\n\n"
        "<b>Status atual:</b>\n"
    )
    
    # Verificar status atual das variáveis
    status_github_token = "✅ Configurado" if GITHUB_TOKEN else "❌ Não configurado"
    status_repo_owner = "✅ Configurado" if GITHUB_REPO_OWNER else "❌ Não configurado"
    status_repo_name = "✅ Configurado" if GITHUB_REPO_NAME else "❌ Não configurado"
    status_branch = f"✅ Configurado ({GITHUB_BRANCH})" if GITHUB_BRANCH else "❌ Não configurado"
    
    setup_text += (
        f"• GITHUB_TOKEN: {status_github_token}\n"
        f"• GITHUB_REPO_OWNER: {status_repo_owner}\n"
        f"• GITHUB_REPO_NAME: {status_repo_name}\n"
        f"• GITHUB_BRANCH: {status_branch}\n"
    )
    
    # Enviar mensagem
    update.message.reply_text(
        setup_text,
        parse_mode="HTML",
        reply_markup=ADMIN_KEYBOARD if str(user_id) == ADMIN_ID else MAIN_KEYBOARD
    )

def github_menu_handler(update: Update, context: CallbackContext):
    """Manipulador para o botão GitHub do teclado do administrador
    
    Este handler é acionado quando o administrador clica no botão '🔄 GitHub'
    no teclado personalizado. Exibe um menu com as opções do GitHub.
    """
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        update.message.reply_text(
            "⛔ Você não tem permissão para acessar esta área.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    # Criar teclado inline com opções do GitHub
    keyboard = [
        [InlineKeyboardButton("🔄 Sincronizar catálogo", callback_data="github_sync")],
        [InlineKeyboardButton("ℹ️ Informações do repositório", callback_data="github_info")],
        [InlineKeyboardButton("🔧 Configuração do GitHub", callback_data="github_setup")],
        [InlineKeyboardButton("⚙️ Configurar credenciais", callback_data="github_config_start")]
    ]
    
    # Enviar menu
    update.message.reply_text(
        "🔗 <b>Menu de Integração com GitHub</b>\n\n"
        "Selecione uma das opções abaixo para gerenciar a integração com GitHub:\n\n"
        "• <b>Sincronizar catálogo</b>: Envia o catálogo atual para o GitHub\n"
        "• <b>Informações do repositório</b>: Mostra detalhes sobre o repositório conectado\n"
        "• <b>Configuração do GitHub</b>: Instruções para configurar a integração\n"
        "• <b>Configurar credenciais</b>: Configurar credenciais do GitHub diretamente no bot\n\n"
        "<b>Status:</b> " + ("✅ Conectado" if (GITHUB_TOKEN and GITHUB_REPO_OWNER and GITHUB_REPO_NAME) else "❌ Não configurado"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def github_sync_callback(update: Update, context: CallbackContext):
    """Callback handler para a sincronização com GitHub
    
    Este handler é chamado quando o usuário clica no botão 'Sincronizar catálogo'
    no menu de GitHub.
    """
    query = update.callback_query
    query.answer()  # Responde ao callback para remover o "loading"
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        query.edit_message_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML"
        )
        return
    
    # Verificar se as variáveis de ambiente do GitHub estão configuradas
    if not (GITHUB_TOKEN and GITHUB_REPO_OWNER and GITHUB_REPO_NAME):
        query.edit_message_text(
            "⚠️ Configuração do GitHub incompleta.\n\n"
            "É necessário configurar as seguintes variáveis de ambiente:\n"
            "• GITHUB_TOKEN\n"
            "• GITHUB_REPO_OWNER\n"
            "• GITHUB_REPO_NAME\n\n"
            "Use o comando /github_setup para mais informações.",
            parse_mode="HTML"
        )
        return
    
    # Atualizar a mensagem para indicar que está processando
    query.edit_message_text(
        "🔄 Sincronizando catálogo com GitHub...",
        parse_mode="HTML"
    )
    
    try:
        # Criar uma cópia do catálogo para exportação
        catalog_copy = {}
        for category, products in PRODUCT_CATALOG.items():
            catalog_copy[category] = []
            for product in products:
                product_copy = product.copy()
                catalog_copy[category].append(product_copy)
        
        # Enviar para o GitHub
        result = github_manager.update_catalog_in_github(
            GITHUB_REPO_OWNER,
            GITHUB_REPO_NAME,
            catalog_copy,
            branch=GITHUB_BRANCH
        )
        
        if result:
            query.edit_message_text(
                "✅ Catálogo sincronizado com sucesso no GitHub!\n\n"
                f"Repositório: {GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}\n"
                f"Branch: {GITHUB_BRANCH}\n"
                f"Arquivo: data/catalog.json",
                parse_mode="HTML"
            )
        else:
            query.edit_message_text(
                "❌ Erro ao sincronizar catálogo com GitHub.\n\n"
                "Verifique os logs para mais detalhes.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Erro ao sincronizar com GitHub: {e}")
        query.edit_message_text(
            f"❌ Erro ao sincronizar catálogo: {str(e)}",
            parse_mode="HTML"
        )

def github_info_callback(update: Update, context: CallbackContext):
    """Callback handler para informações do GitHub
    
    Este handler é chamado quando o usuário clica no botão 'Informações do repositório'
    no menu de GitHub.
    """
    query = update.callback_query
    query.answer()  # Responde ao callback para remover o "loading"
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        query.edit_message_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML"
        )
        return
    
    # Verificar se as variáveis de ambiente do GitHub estão configuradas
    if not (GITHUB_TOKEN and GITHUB_REPO_OWNER and GITHUB_REPO_NAME):
        query.edit_message_text(
            "⚠️ Configuração do GitHub incompleta.\n\n"
            "É necessário configurar as seguintes variáveis de ambiente:\n"
            "• GITHUB_TOKEN\n"
            "• GITHUB_REPO_OWNER\n"
            "• GITHUB_REPO_NAME\n\n"
            "Use o comando /github_setup para mais informações.",
            parse_mode="HTML"
        )
        return
    
    # Atualizar a mensagem para indicar que está processando
    query.edit_message_text(
        "🔄 Obtendo informações do repositório GitHub...",
        parse_mode="HTML"
    )
    
    try:
        # Obter informações do repositório
        repo_info = github_manager.get_repository_info(GITHUB_REPO_OWNER, GITHUB_REPO_NAME)
        
        if repo_info:
            # Formatar informações do repositório
            repo_text = (
                f"📊 <b>Informações do Repositório GitHub</b>\n\n"
                f"<b>Nome:</b> {repo_info['full_name']}\n"
                f"<b>Descrição:</b> {repo_info.get('description', 'Sem descrição')}\n"
                f"<b>Branch padrão:</b> {repo_info.get('default_branch', 'main')}\n"
                f"<b>Branch configurado:</b> {GITHUB_BRANCH}\n"
                f"<b>Visibilidade:</b> {repo_info.get('visibility', 'desconhecida')}\n"
                f"<b>URL:</b> {repo_info.get('html_url', '-')}\n\n"
                f"<b>Estatísticas:</b>\n"
                f"• Stars: {repo_info.get('stargazers_count', 0)}\n"
                f"• Forks: {repo_info.get('forks_count', 0)}\n"
                f"• Issues abertas: {repo_info.get('open_issues_count', 0)}\n\n"
                f"<b>Configuração do Bot:</b>\n"
                f"• Arquivo de catálogo: data/catalog.json\n"
                f"• Último sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Editar mensagem
            query.edit_message_text(
                text=repo_text,
                parse_mode="HTML"
            )
        else:
            query.edit_message_text(
                text="❌ Não foi possível obter informações do repositório.\n\n"
                     "Verifique se o token e o nome do repositório estão corretos.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Erro ao obter informações do GitHub: {e}")
        query.edit_message_text(
            text=f"❌ Erro ao acessar repositório: {str(e)}",
            parse_mode="HTML"
        )

def github_setup_callback(update: Update, context: CallbackContext):
    """Callback handler para configuração do GitHub
    
    Este handler é chamado quando o usuário clica no botão 'Configuração do GitHub'
    no menu de GitHub.
    """
    query = update.callback_query
    query.answer()  # Responde ao callback para remover o "loading"
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        query.edit_message_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML"
        )
        return
    
    # Preparar mensagem de ajuda para configuração
    setup_text = (
        "🔧 <b>Configuração do GitHub</b>\n\n"
        "Para conectar o bot ao GitHub, configure as seguintes variáveis de ambiente:\n\n"
        "<b>1. GITHUB_TOKEN</b>\n"
        "Token de acesso pessoal do GitHub com permissão para repositórios.\n"
        "Você pode criar um token em GitHub - Settings - Developer Settings - Personal Access Tokens.\n\n"
        "<b>2. GITHUB_REPO_OWNER</b>\n"
        "Nome do usuário ou organização dona do repositório.\n\n"
        "<b>3. GITHUB_REPO_NAME</b>\n"
        "Nome do repositório onde o catálogo será armazenado.\n\n"
        "<b>4. GITHUB_BRANCH</b> (opcional)\n"
        "Branch do repositório. O padrão é 'main' se não for especificado.\n\n"
        "<b>Instruções:</b>\n"
        "• Crie um repositório no GitHub (público ou privado)\n"
        "• Configure as variáveis de ambiente no seu provedor de hospedagem\n"
        "• Reinicie o bot após configurar as variáveis\n"
        "• Use o comando /github_info para verificar a conexão\n"
        "• Use o comando /github_sync para sincronizar o catálogo\n\n"
        "<b>Status atual:</b>\n"
    )
    
    # Verificar status atual das variáveis
    status_github_token = "✅ Configurado" if GITHUB_TOKEN else "❌ Não configurado"
    status_repo_owner = "✅ Configurado" if GITHUB_REPO_OWNER else "❌ Não configurado"
    status_repo_name = "✅ Configurado" if GITHUB_REPO_NAME else "❌ Não configurado"
    status_branch = f"✅ Configurado ({GITHUB_BRANCH})" if GITHUB_BRANCH else "❌ Não configurado"
    
    setup_text += (
        f"• GITHUB_TOKEN: {status_github_token}\n"
        f"• GITHUB_REPO_OWNER: {status_repo_owner}\n"
        f"• GITHUB_REPO_NAME: {status_repo_name}\n"
        f"• GITHUB_BRANCH: {status_branch}\n"
    )
    
    # Enviar mensagem
    query.edit_message_text(
        setup_text,
        parse_mode="HTML"
    )

def github_config_start_callback(update: Update, context: CallbackContext):
    """Inicia o processo de configuração das credenciais do GitHub diretamente pelo bot.
    
    Este handler é chamado quando o usuário clica no botão 'Configurar credenciais'
    no menu de GitHub.
    """
    query = update.callback_query
    query.answer()  # Responde ao callback para remover o "loading"
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        query.edit_message_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML"
        )
        return
    
    # Iniciar a conversa para configurar as credenciais
    keyboard = [
        [InlineKeyboardButton("🔑 Iniciar configuração", callback_data="github_config_token")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="github_cancel_config")],
        [InlineKeyboardButton("« Voltar", callback_data="github_back_to_menu")]
    ]
    
    query.edit_message_text(
        "⚙️ <b>Configuração de Credenciais do GitHub</b>\n\n"
        "Você está prestes a configurar as credenciais do GitHub diretamente no bot.\n"
        "Este processo é seguro e as credenciais permanecerão apenas na memória do bot.\n\n"
        "<b>Você precisará de:</b>\n"
        "• Um token de acesso pessoal do GitHub\n"
        "• O nome do usuário ou organização dona do repositório\n"
        "• O nome do repositório\n"
        "• Opcionalmente, o branch (padrão: main)\n\n"
        "Clique em 'Iniciar configuração' para começar.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
def github_config_token_callback(update: Update, context: CallbackContext):
    """Solicita o token do GitHub ao usuário."""
    query = update.callback_query
    query.answer()
    user_id = update.effective_user.id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        query.edit_message_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML"
        )
        return ConversationHandler.END
    
    # Limpar dados temporários
    github_temp_data.clear()
    
    keyboard = [
        [InlineKeyboardButton("❌ Cancelar", callback_data="github_cancel_config")]
    ]
    
    query.edit_message_text(
        "🔑 <b>Token do GitHub</b>\n\n"
        "Por favor, envie o token de acesso pessoal do GitHub.\n\n"
        "Você pode criar um token em GitHub - Settings - Developer Settings - Personal Access Tokens.\n"
        "Certifique-se de que o token tenha permissão para acessar repositórios.\n\n"
        "<i>Nota: Por segurança, tentaremos remover sua mensagem contendo o token após o processamento.</i>\n\n"
        "Para cancelar o processo a qualquer momento, clique no botão abaixo ou digite /cancel.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Definir o próximo estado
    return GITHUB_TOKEN_INPUT
    
def github_token_input_handler(update: Update, context: CallbackContext):
    """Processa o token do GitHub enviado pelo usuário."""
    user_id = update.effective_user.id
    token = update.message.text
    message_id = update.message.message_id
    chat_id = update.message.chat_id
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        update.message.reply_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END
    
    # Salvar o token
    github_temp_data['token'] = token
    
    # Criar teclado com botão de cancelamento
    keyboard = ReplyKeyboardMarkup([
        ["❌ Cancelar Configuração"]
    ], one_time_keyboard=True, resize_keyboard=True)
    
    # Solicitar o nome do dono do repositório
    response = update.message.reply_text(
        "👤 <b>Dono do Repositório</b>\n\n"
        "Por favor, envie o nome do usuário ou organização dona do repositório.\n"
        "Este é o primeiro componente da URL do seu repositório: github.com/<b>DONO</b>/nome-do-repo\n\n"
        "<i>A qualquer momento você pode digitar /cancel para cancelar o processo.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    # Apagar a mensagem do usuário para não manter o token visível no chat
    # Agendar a remoção da mensagem para garantir que seja processada
    try:
        context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Mensagem com token removida por segurança")
    except Exception as e:
        logger.error(f"Erro ao deletar mensagem com token: {e}")
        # Tentar substituir a mensagem como alternativa
        try:
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="[Token ocultado por segurança]"
            )
            logger.info("Mensagem com token substituída por segurança")
        except Exception as ex:
            logger.error(f"Também não foi possível editar a mensagem: {ex}")
    
    return GITHUB_OWNER_INPUT
    
def github_owner_input_handler(update: Update, context: CallbackContext):
    """Processa o nome do dono do repositório enviado pelo usuário."""
    user_id = update.effective_user.id
    owner = update.message.text
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        update.message.reply_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END
    
    # Salvar o dono
    github_temp_data['owner'] = owner
    
    # Manter o teclado de cancelamento
    keyboard = ReplyKeyboardMarkup([
        ["❌ Cancelar Configuração"]
    ], one_time_keyboard=True, resize_keyboard=True)
    
    # Solicitar o nome do repositório
    update.message.reply_text(
        "📁 <b>Nome do Repositório</b>\n\n"
        "Por favor, envie o nome do repositório.\n"
        "Este é o segundo componente da URL do seu repositório: github.com/dono/<b>NOME-DO-REPO</b>\n\n"
        "<i>A qualquer momento você pode digitar /cancel para cancelar o processo.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    return GITHUB_REPO_INPUT
    
def github_repo_input_handler(update: Update, context: CallbackContext):
    """Processa o nome do repositório enviado pelo usuário."""
    user_id = update.effective_user.id
    repo = update.message.text
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        update.message.reply_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END
    
    # Salvar o repositório
    github_temp_data['repo'] = repo
    
    # Manter o teclado de cancelamento
    keyboard = ReplyKeyboardMarkup([
        ["❌ Cancelar Configuração"]
    ], one_time_keyboard=True, resize_keyboard=True)
    
    # Solicitar o branch
    update.message.reply_text(
        "🔀 <b>Branch do Repositório</b>\n\n"
        "Por favor, envie o nome do branch (ex: main, master).\n"
        "Se não especificado, será usado o branch 'main'.\n\n"
        "Você pode enviar 'main' ou simplesmente pressionar qualquer tecla para usar o padrão.\n\n"
        "<i>A qualquer momento você pode digitar /cancel para cancelar o processo.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    return GITHUB_BRANCH_INPUT
    
def github_branch_input_handler(update: Update, context: CallbackContext):
    """Processa o branch do repositório enviado pelo usuário e finaliza a configuração."""
    user_id = update.effective_user.id
    branch = update.message.text
    
    # Verificar se é admin
    if str(user_id) != ADMIN_ID:
        update.message.reply_text(
            "⛔ Você não tem permissão para realizar esta ação.",
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END
    
    # Salvar o branch
    github_temp_data['branch'] = branch if branch else 'main'
    
    # Atualizar as credenciais globais
    update_github_credentials(
        token=github_temp_data.get('token'),
        owner=github_temp_data.get('owner'),
        repo=github_temp_data.get('repo'),
        branch=github_temp_data.get('branch')
    )
    
    try:
        # Obter valores seguros para exibição (sem o token)
        safe_owner = github_temp_data.get('owner')
        safe_repo = github_temp_data.get('repo')
        safe_branch = github_temp_data.get('branch', 'main')
        
        logger.info(f"Configuração do GitHub concluída com sucesso para {safe_owner}/{safe_repo}:{safe_branch}")
        
        # Confirmar a configuração com o teclado admin
        update.message.reply_text(
            "✅ <b>Configuração Concluída</b>\n\n"
            "As credenciais do GitHub foram configuradas com sucesso!\n\n"
            f"• <b>Dono:</b> {safe_owner}\n"
            f"• <b>Repositório:</b> {safe_repo}\n"
            f"• <b>Branch:</b> {safe_branch}\n\n"
            "Agora você pode utilizar todas as funcionalidades de integração com GitHub.",
            parse_mode="HTML",
            reply_markup=ADMIN_KEYBOARD
        )
    except Exception as e:
        logger.error(f"Erro ao concluir configuração do GitHub: {e}")
        update.message.reply_text(
            "⚠️ <b>Configuração Concluída com Avisos</b>\n\n"
            "As credenciais foram salvas, mas ocorreu um erro ao exibir os detalhes.\n"
            "Você pode verificar o status usando o comando /github_info",
            parse_mode="HTML",
            reply_markup=ADMIN_KEYBOARD
        )
    
    # Limpar dados temporários
    github_temp_data.clear()
    
    return ConversationHandler.END
    
def github_config_cancel(update: Update, context: CallbackContext):
    """Cancela o processo de configuração do GitHub."""
    user_id = update.effective_user.id
    
    # Limpar dados temporários
    github_temp_data.clear()
    logger.info(f"Configuração do GitHub cancelada pelo usuário {user_id}")
    
    # Verificar se é um objeto Message (comando /cancel ou botão de texto) ou callback_query
    if update.message:
        # Verificar se é o botão de texto "❌ Cancelar Configuração" ou o comando /cancel
        message_text = update.message.text
        if message_text == "❌ Cancelar Configuração":
            update.message.reply_text(
                "❌ <b>Configuração Cancelada</b>\n\n"
                "O processo de configuração do GitHub foi cancelado pelo botão de cancelamento.",
                parse_mode="HTML",
                reply_markup=ADMIN_KEYBOARD
            )
        else:
            update.message.reply_text(
                "❌ <b>Configuração Cancelada</b>\n\n"
                "O processo de configuração do GitHub foi cancelado.",
                parse_mode="HTML",
                reply_markup=ADMIN_KEYBOARD
            )
    elif update.callback_query:
        update.callback_query.answer()
        update.callback_query.edit_message_text(
            "❌ <b>Configuração Cancelada</b>\n\n"
            "O processo de configuração do GitHub foi cancelado.",
            parse_mode="HTML"
        )
        # Enviar uma nova mensagem com o teclado admin para garantir que o usuário tenha acesso a ele
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="<i>Retornando ao menu de administrador.</i>",
            parse_mode="HTML",
            reply_markup=ADMIN_KEYBOARD
        )
    
    return ConversationHandler.END

def github_back_to_menu_callback(update: Update, context: CallbackContext):
    """Retorna ao menu principal do GitHub."""
    query = update.callback_query
    query.answer()
    
    # Chamar o manipulador do menu do GitHub
    github_menu_handler(update, context)

def help_command(update: Update, context: CallbackContext):
    """Send help information"""
    user_id = update.effective_user.id
    
    help_text = (
        "🤖 <b>Comandos Disponíveis</b>\n\n"
        "/start - Iniciar ou reiniciar o bot\n"
        "/help - Mostrar esta ajuda\n\n"
        "Você também pode usar os botões no teclado principal:\n"
        "🛍️ <b>Produtos</b> - Navegar pelo catálogo\n"
        "🛒 <b>Ver Carrinho</b> - Ver itens no seu carrinho\n"
        "📋 <b>Meus Pedidos</b> - Ver histórico de pedidos\n"
        "❓ <b>Ajuda</b> - Obter ajuda e suporte\n\n"
    )
    
    # Add admin commands if user is admin
    if str(user_id) == ADMIN_ID:
        help_text += (
            "👑 <b>Comandos de Administrador</b>\n\n"
            "/admin - Gerenciar produtos e categorias\n"
            "/pending - Ver pedidos pendentes\n"
            "/github_sync - Sincronizar catálogo com GitHub\n"
            "/github_info - Ver informações do repositório\n"
            "/github_setup - Configurar integração com GitHub\n"
        )
    
    update.message.reply_text(
        help_text,
        parse_mode="HTML",
        reply_markup=MAIN_KEYBOARD
    )

def error_handler(update, context):
    """Log errors raised by handlers"""
    try:
        user_id = "Unknown"
        if update and update.effective_user:
            user_id = update.effective_user.id
            
        log_error(context.error, f"User {user_id}")
    except Exception as e:
        logger.error(f"ERROR - Error details: {e}")

# MAIN BOT FUNCTION

def main():
    """Run the bot"""
    try:
        # Verificar e resolver conflitos de instâncias do bot em execução
        # (para evitar o erro "terminated by other getUpdates request")
        try:
            # Verificar processos existentes com o mesmo TOKEN
            import psutil
            current_pid = os.getpid()
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['pid'] == current_pid:
                    continue
                
                cmdline = proc.info.get('cmdline', [])
                if cmdline and len(cmdline) > 1:
                    # Verificar se é uma instância Python executando este script
                    if (('python' in proc.info['name'].lower() or 'python3' in proc.info['name'].lower()) 
                            and any(x.endswith('bot_completo.py') for x in cmdline)):
                        logger.warning(f"Encontrada outra instância do bot (PID: {proc.info['pid']}). Terminando...")
                        try:
                            proc.terminate()
                            proc.wait(timeout=5)
                            logger.info(f"Instância anterior (PID: {proc.info['pid']}) encerrada.")
                        except Exception as e:
                            logger.error(f"Erro ao encerrar instância anterior: {e}")
        except Exception as e:
            logger.warning(f"Não foi possível verificar outras instâncias: {e}")
            
        # Verifica se estamos no Heroku
        is_heroku = bool(os.environ.get('DYNO'))
        
        # Garantir que os diretórios e arquivos de dados existam
        data_dir = "data"
        os.makedirs(data_dir, exist_ok=True)
        
        # Verificar arquivos de persistência
        users_file = os.path.join(data_dir, "users.json")
        orders_file = os.path.join(data_dir, "orders.json")
        carts_file = os.path.join(data_dir, "carts.json")
        
        # Criar arquivos vazios se não existirem
        if not os.path.exists(users_file):
            with open(users_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            logger.info(f"Arquivo {users_file} criado")
                
        if not os.path.exists(orders_file):
            with open(orders_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            logger.info(f"Arquivo {orders_file} criado")
                
        if not os.path.exists(carts_file):
            with open(carts_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            logger.info(f"Arquivo {carts_file} criado")
    except Exception as e:
        logger.error(f"Erro durante a inicialização dos arquivos de dados: {e}")
    
    # Tentativa de usar o sistema de persistência anterior como fallback
    try:
        # Importa e inicializa o módulo de persistência de dados
        from persistent_data import start_backup_service
        
        # Inicia o serviço de backup automático
        data_manager = start_backup_service()
        logger.info("Serviço de persistência de dados legado iniciado como backup")
    except Exception as e:
        logger.info(f"Usando sistema de persistência JSON integrado: {e}")
    
    # Detecção de ambiente: Heroku, Google Cloud ou outro
    is_heroku = 'DYNO' in os.environ
    is_gcp = 'GOOGLE_CLOUD_PROJECT' in os.environ
    
    if is_heroku:
        logger.info("Ambiente Heroku detectado")
        # Configurações específicas para web dynos do Heroku
        # Evitar que o processo seja terminado por inatividade
        keep_alive_url = os.environ.get('HEROKU_URL')
        
        # Se estiver no Heroku, inicia o serviço de keep-alive em thread separada
        if not keep_alive_url:
            logger.warning("HEROKU_URL não definida. Tentando inferir URL.")
            app_name = os.environ.get('HEROKU_APP_NAME')
            if app_name:
                keep_alive_url = f"https://{app_name}.herokuapp.com"
                logger.info(f"URL inferida: {keep_alive_url}")
            else:
                logger.warning("Não foi possível determinar a URL. Keep-alive desativado.")
    elif is_gcp:
        logger.info("Ambiente Google Cloud Platform detectado")
        # Otimizações para Google Cloud
        keep_alive_url = None  # Não é necessário keep-alive no GCP
    else:
        logger.info("Ambiente local ou outro serviço detectado")
        keep_alive_url = None
    
    try:
        # Create the Updater and pass it your bot's token
        updater = Updater(TOKEN, use_context=True)
        
        # Get the dispatcher to register handlers
        dp = updater.dispatcher
        
        # Registration conversation handler
        registration_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                NOME: [MessageHandler(Filters.text & ~Filters.command, handle_name)],
                TELEFONE: [
                    MessageHandler(Filters.contact, handle_phone),
                    MessageHandler(Filters.text & ~Filters.command, handle_phone)
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        dp.add_handler(registration_handler)
        
        # Admin product management conversation handler
        admin_product_conv = ConversationHandler(
            entry_points=[CommandHandler('admin', admin_products)],
            states={
                CATEGORY_SELECTION: [
                    CallbackQueryHandler(admin_select_category, pattern=r'^admin_cat_|^admin_add_category')
                ],
                PRODUCT_ACTION: [
                    CallbackQueryHandler(admin_select_product, pattern=r'^admin_prod_|^admin_add_product|^admin_back_to_')
                ],
                ADD_PRODUCT_NAME: [
                    CallbackQueryHandler(admin_cancel_callback, pattern=r'^admin_cancel_add'),
                    MessageHandler(Filters.text & ~Filters.command, admin_add_product_name)
                ],
                ADD_PRODUCT_PRICE: [
                    CallbackQueryHandler(admin_cancel_callback, pattern=r'^admin_cancel_add'),
                    MessageHandler(Filters.text & ~Filters.command, admin_add_product_price)
                ],
                ADD_PRODUCT_FIELDS: [
                    CallbackQueryHandler(admin_add_product_type, pattern=r'^admin_type_'),
                    CallbackQueryHandler(admin_cancel_callback, pattern=r'^admin_cancel_add'),
                    MessageHandler(Filters.text & ~Filters.command, admin_add_product_fields)
                ],
                CONFIRM_DELETE: [
                    CallbackQueryHandler(admin_confirm_delete_product, pattern=r'^admin_confirm_delete|^admin_confirm_delete_category_|^admin_prod_|^admin_cat_')
                ],
                EDIT_PRODUCT_FIELD: [
                    CallbackQueryHandler(admin_edit_product_field, pattern=r'^admin_edit_|^admin_cat_|^admin_delete_')
                ],
                EDIT_PRODUCT_VALUE: [
                    CallbackQueryHandler(admin_edit_discount, pattern=r'^admin_set_discount_'),
                    MessageHandler(Filters.text & ~Filters.command, admin_handle_edit_value)
                ],
            },
            fallbacks=[CommandHandler('cancel', admin_cancel)]
        )
        dp.add_handler(admin_product_conv)
        
        # Product navigation handlers
        dp.add_handler(MessageHandler(Filters.regex(r'^🛍️ Produtos$'), menu_inicial))
        dp.add_handler(CallbackQueryHandler(show_category, pattern=r'^category_'))
        dp.add_handler(CallbackQueryHandler(select_product, pattern=r'^product_'))
        dp.add_handler(CallbackQueryHandler(handle_quantity, pattern=r'^qty_'))
        dp.add_handler(CallbackQueryHandler(continue_shopping, pattern=r'^back_to_categories|^back_to_products'))
        
        # Field collection for app products
        dp.add_handler(MessageHandler(
            Filters.text & ~Filters.command & ~Filters.regex(r'^🛍️ Produtos$|^🛒 Ver Carrinho$|^📋 Meus Pedidos$|^❓ Ajuda$|^🔐 Área Admin$'),
            collect_product_fields
        ))
        
        # Cart handlers
        dp.add_handler(MessageHandler(Filters.regex(r'^🛒 Ver Carrinho$'), view_cart))
        dp.add_handler(CallbackQueryHandler(view_cart_callback, pattern=r'^view_cart$'))
        dp.add_handler(CallbackQueryHandler(clear_cart, pattern=r'^clear_cart$'))
        dp.add_handler(CallbackQueryHandler(checkout, pattern=r'^checkout$'))
        
        # Handler para adicionar ao carrinho
        def add_cart_handler(update, context):
            # Função interna para adicionar ao carrinho
            try:
                query = update.callback_query
                query.answer()
                user_id = query.from_user.id
                
                # Verificar se o produto está na sessão
                product = context.user_data.get('selected_product')
                if not product:
                    query.edit_message_text(
                        "❌ Erro: Produto não encontrado. Por favor, selecione o produto novamente.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔄 Ver Categorias", callback_data="back_to_categories")
                        ]])
                    )
                    return
                
                # Criar item do carrinho
                item = CartItem(product['name'], product['price'])
                db.add_to_cart(user_id, item)
                
                # Mostrar mensagem de sucesso
                message = f"✅ *{product['name']}* adicionado ao carrinho com sucesso!"
                
                keyboard = [
                    [InlineKeyboardButton("🛒 Ver Carrinho", callback_data="view_cart")],
                    [InlineKeyboardButton("🛍️ Continuar Comprando", callback_data="back_to_categories")]
                ]
                
                query.edit_message_text(
                    message,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Produto '{product['name']}' adicionado ao carrinho do usuário {user_id}")
                
            except Exception as e:
                logger.error(f"Erro ao adicionar ao carrinho: {e}")
                try:
                    update.callback_query.edit_message_text(
                        "❌ Ocorreu um erro ao adicionar o produto ao carrinho. Por favor, tente novamente.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔄 Ver Categorias", callback_data="back_to_categories")
                        ]])
                    )
                except Exception as nested_e:
                    logger.error(f"Erro secundário: {nested_e}")
        
        # Registrar o handler
        dp.add_handler(CallbackQueryHandler(add_cart_handler, pattern=r'^add_to_cart$'))
        
        # Handler para produtos de preço fixo
        def add_to_cart_fixed_handler(update, context):
            try:
                query = update.callback_query
                query.answer()
                user_id = query.from_user.id
                
                # Verificar se o produto está na sessão
                product = context.user_data.get('selected_product')
                if not product:
                    query.edit_message_text(
                        "❌ Erro: Produto não encontrado. Por favor, selecione o produto novamente.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔄 Ver Categorias", callback_data="back_to_categories")
                        ]])
                    )
                    return
                
                # Criar item do carrinho (sem quantidade de créditos)
                item = CartItem(
                    product['name'], 
                    product['price'],
                    {"tipo": "preço fixo", "discount": False}
                )
                db.add_to_cart(user_id, item.to_dict())
                
                # Mostrar mensagem de sucesso
                message = (
                    f"✅ *{product['name']}* adicionado ao carrinho com sucesso!\n\n"
                    f"💰 Preço: R${product['price']:.2f}\n"
                    f"📌 Produto de preço fixo (sem seleção de quantidade)"
                )
                
                keyboard = [
                    [InlineKeyboardButton("🛒 Ver Carrinho", callback_data="view_cart")],
                    [InlineKeyboardButton("🛍️ Continuar Comprando", callback_data="back_to_categories")]
                ]
                
                query.edit_message_text(
                    message,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Produto de preço fixo '{product['name']}' adicionado ao carrinho do usuário {user_id}")
                
            except Exception as e:
                logger.error(f"Erro ao adicionar produto de preço fixo ao carrinho: {e}")
                try:
                    update.callback_query.edit_message_text(
                        "❌ Ocorreu um erro ao adicionar o produto ao carrinho. Por favor, tente novamente.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔄 Ver Categorias", callback_data="back_to_categories")
                        ]])
                    )
                except Exception as nested_e:
                    logger.error(f"Erro secundário: {nested_e}")
                    
        # Registrar o handler para produtos de preço fixo
        dp.add_handler(CallbackQueryHandler(add_to_cart_fixed_handler, pattern=r'^add_to_cart_fixed$'))
        
        # Payment handlers
        dp.add_handler(CallbackQueryHandler(check_payment_status, pattern=r'^check_payment_'))
        
        # Order handlers
        dp.add_handler(MessageHandler(Filters.regex(r'^📋 Meus Pedidos$'), list_orders))
        dp.add_handler(CallbackQueryHandler(order_details, pattern=r'^order_details_'))
        dp.add_handler(CallbackQueryHandler(check_payment_callback, pattern=r'^back_to_orders$'))
        
        # Handler para o botão Admin no teclado de administrador
        dp.add_handler(MessageHandler(Filters.regex(r'^🛠️ Admin$'), admin_products))
        
        # Admin conversation handler para autenticação
        admin_auth_conv = ConversationHandler(
            entry_points=[
                MessageHandler(Filters.regex(r'^🔐 Área Admin$'), admin_area),
                CommandHandler('admin', admin_area)  # Comando /admin também inicia a autenticação
            ],
            states={
                ADMIN_AUTH: [MessageHandler(Filters.text & ~Filters.command, admin_auth_handler)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        dp.add_handler(admin_auth_conv)
        
        # Admin handlers
        dp.add_handler(CommandHandler('pending', list_pending_orders))
        dp.add_handler(CallbackQueryHandler(admin_view_order, pattern=r'^admin_view_order_'))
        dp.add_handler(CallbackQueryHandler(list_pending_orders, pattern=r'^admin_back_to_pending$'))
        dp.add_handler(CallbackQueryHandler(mark_as_delivered, pattern=r'^admin_deliver_'))
        dp.add_handler(CallbackQueryHandler(cancel_order, pattern=r'^admin_cancel_'))
        
        # General commands
        dp.add_handler(CommandHandler('help', help_command))
        dp.add_handler(MessageHandler(Filters.regex(r'^❓ Ajuda$'), help_command))
        
        # GitHub integration removida
        
        # Error handler
        dp.add_error_handler(error_handler)
        
        # Configura um keep-alive para o Heroku
        if keep_alive_url:
            logger.info(f"Configurando keep-alive para Heroku: {keep_alive_url}")
            
            def keep_alive_ping():
                import requests
                try:
                    response = requests.get(keep_alive_url)
                    logger.info(f"Keep-alive ping: {response.status_code}")
                except Exception as e:
                    logger.error(f"Keep-alive error: {e}")
            
            # Adiciona o job à scheduler para rodar a cada 20 minutos (evitar sleep)
            job_queue = updater.job_queue
            job_queue.run_repeating(lambda ctx: keep_alive_ping(), interval=1200)
        
        # Start the Bot - configurar com parâmetros mais seguros para maior estabilidade
        logger.info("Starting bot polling...")
        
        # Limpar mensagens pendentes para evitar conflitos e mensagens antigas
        try:
            # Usar getUpdates com offset -1 e limit 1 para simplesmente descartar atualizações pendentes
            updater.bot.get_updates(offset=-1, limit=1, timeout=1)
            logger.info("Mensagens pendentes descartadas com sucesso")
        except Exception as e:
            logger.warning(f"Erro ao limpar mensagens pendentes: {e}")
        
        # Parâmetros otimizados para Heroku e estabilidade 24/7
        # Configurações compatíveis com python-telegram-bot v13.15
        updater.start_polling(
            timeout=30,  # Este é o único timeout usado na versão 13.15
            drop_pending_updates=True, 
            poll_interval=1.0,
            allowed_updates=['message', 'callback_query', 'chat_member']
        )
        
        # Run the bot until the user presses Ctrl-C or the process receives SIGINT/SIGTERM
        updater.idle(stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT))
        
    except Exception as e:
        logger.error(f"Erro crítico ao iniciar o bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
