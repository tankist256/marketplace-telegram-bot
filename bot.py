import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

logging.basicConfig(level=logging.INFO)

# ---------- CONFIG (or create config.py) ----------
# Create a file named config.py with the following variables:
# BOT_TOKEN = "123456:ABC-DEF..."
# ADMIN_ID = 123456789  # your Telegram user id
# USDT_TRON_ADDRESS = "TD..."  # your USDT (TRC20) receive address
# DB_PATH = "orders.db"

try:
    import config
    BOT_TOKEN = config.BOT_TOKEN
    ADMIN_ID = config.ADMIN_ID
    USDT_TRON_ADDRESS = getattr(config, 'USDT_TRON_ADDRESS', 'SET_YOUR_ADDRESS')
    DB_PATH = getattr(config, 'DB_PATH', 'orders.db')
except Exception as e:
    print("Could not import config.py. Using environment variables or defaults.")
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else None
    USDT_TRON_ADDRESS = os.getenv('USDT_TRON_ADDRESS', 'SET_YOUR_ADDRESS')
    DB_PATH = os.getenv('DB_PATH', 'orders.db')

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN not set. Create config.py or set BOT_TOKEN env var')
if not ADMIN_ID:
    raise RuntimeError('ADMIN_ID not set. Create config.py or set ADMIN_ID env var')

# ---------- DB helpers ----------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            product_type TEXT,
            template_choice TEXT,
            details TEXT,
            files TEXT,
            price REAL,
            payment_method TEXT,
            payment_reference TEXT,
            status TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_order(order: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO orders (user_id, username, product_type, template_choice, details, files, price, payment_method, payment_reference, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        order.get('user_id'),
        order.get('username'),
        order.get('product_type'),
        order.get('template_choice'),
        order.get('details'),
        order.get('files'),
        order.get('price'),
        order.get('payment_method'),
        order.get('payment_reference'),
        order.get('status', 'new'),
        order.get('created_at'),
    ))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id

def list_orders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, user_id, username, product_type, status, created_at FROM orders ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_order(order_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
    row = c.fetchone()
    conn.close()
    return row

def set_order_status(order_id: int, status: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    conn.commit()
    conn.close()

class OrderStates(StatesGroup):
    choosing_product = State()
    choosing_template = State()
    entering_details = State()
    uploading_files = State()
    choosing_payment = State()
    waiting_payment_ref = State()


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


def build_keyboard(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn) for btn in row] for row in rows],
        resize_keyboard=True
    )


main_kb = build_keyboard([
    ['🌐 Buy a Website'],
    ['🤖 Buy a Telegram Bot'],
    ['📦 My Orders'],
    ['💬 Contact Admin'],
])

payment_kb = build_keyboard([
    ['USDT (TRC20) — pay on Tron network'],
    ['Manual payment (bank/card)'],
    ['Cancel'],
])

cancel_kb = build_keyboard([['Cancel']])

# ---------- Handlers ----------
@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Welcome to TANKIST256 marketplace!\nChoose an option:",
        reply_markup=main_kb
    )

@router.message(F.text == '🌐 Buy a Website')
async def buy_website(message: Message, state: FSMContext):
    await state.set_state(OrderStates.choosing_template)
    await message.answer(
        'You chose: Website. Select a template or type "Custom" for a custom website.',
        reply_markup=build_keyboard([
            ['Template A'],
            ['Template B'],
            ['Custom'],
            ['Cancel'],
        ]),
    )
    await state.update_data(product_type='Website')

@router.message(F.text == '🤖 Buy a Telegram Bot')
async def buy_bot(message: Message, state: FSMContext):
    await state.set_state(OrderStates.choosing_template)
    await message.answer(
        'You chose: Telegram Bot. Select a template or type "Custom" for a custom bot.',
        reply_markup=build_keyboard([
            ['Bot Template 1'],
            ['Bot Template 2'],
            ['Custom'],
            ['Cancel'],
        ]),
    )
    await state.update_data(product_type='Telegram Bot')

@router.message(OrderStates.choosing_template)
async def choose_template(message: Message, state: FSMContext):
    if message.text == 'Cancel':
        await state.clear()
        await message.answer('Order cancelled.', reply_markup=main_kb)
        return
    await state.update_data(template_choice=message.text)
    await state.set_state(OrderStates.entering_details)
    await message.answer('Please describe your requirements (features, deadline, domain, hosting, budget).', reply_markup=cancel_kb)

@router.message(OrderStates.entering_details)
async def details_step(message: Message, state: FSMContext):
    if message.text == 'Cancel':
        await state.clear()
        await message.answer('Order cancelled.', reply_markup=main_kb)
        return
    await state.update_data(details=message.text)
    await state.set_state(OrderStates.uploading_files)
    await message.answer('If you have files (designs, logos, docs), please send them now. Send "No files" if none.', reply_markup=cancel_kb)

@router.message(OrderStates.uploading_files)
async def files_step(message: Message, state: FSMContext):
    if message.text == 'Cancel':
        await state.clear()
        await message.answer('Order cancelled.', reply_markup=main_kb)
        return
    files_info = ''
    # Save documents if any
    if message.document:
        saved = await message.document.download(destination_dir='uploads')
        files_info = f'document:{message.document.file_name}'
    elif message.photo:
        # save highest resolution
        photo = message.photo[-1]
        saved = await photo.download(destination_dir='uploads')
        files_info = f'photo'
    elif message.text and message.text.lower() == 'no files':
        files_info = 'no files'
    else:
        # unknown content type - ignore but record
        files_info = 'files:other'

    await state.update_data(files=files_info)
    await state.set_state(OrderStates.choosing_payment)
    await message.answer('Choose a payment method:', reply_markup=payment_kb)

@router.message(OrderStates.choosing_payment)
async def payment_step(message: Message, state: FSMContext):
    if message.text == 'Cancel':
        await state.clear()
        await message.answer('Order cancelled.', reply_markup=main_kb)
        return
    payment_method = message.text
    await state.update_data(payment_method=payment_method)

    data = await state.get_data()

    # Price estimation placeholder: you can extend logic to calculate price
    estimated_price = 100.0 if data.get('product_type') == 'Website' else 80.0

    # Save order to DB
    order = {
        'user_id': message.from_user.id,
        'username': message.from_user.username or message.from_user.full_name,
        'product_type': data.get('product_type'),
        'template_choice': data.get('template_choice'),
        'details': data.get('details'),
        'files': data.get('files'),
        'price': estimated_price,
        'payment_method': payment_method,
        'payment_reference': '',
        'status': 'new',
        'created_at': datetime.utcnow().isoformat()
    }
    order_id = save_order(order)

    # Send instructions depending on payment method
    if 'USDT' in payment_method:
        text = (
            f'Order #{order_id} created.\n'
            f'Amount: {estimated_price} USDT\n'
            f'Pay to TRC20 address: {USDT_TRON_ADDRESS}\n'
            'After payment, send the transaction hash here or press "I paid" so admin can check.'
        )
        keyboard = build_keyboard([['I paid', 'Send TX hash'], ['Cancel']])
        await message.answer(text, reply_markup=keyboard)
        await state.set_state(OrderStates.waiting_payment_ref)
        await state.update_data(order_id=order_id)

    elif 'Manual' in payment_method:
        text = (
            f'Order #{order_id} created.\n'
            f'Estimated price: {estimated_price} (manual payment).\n'
            'Please contact admin for bank/card details or reply here with confirmation.'
        )
        keyboard = build_keyboard([['Contact Admin', 'I paid'], ['Cancel']])
        await message.answer(text, reply_markup=keyboard)
        await state.set_state(OrderStates.waiting_payment_ref)
        await state.update_data(order_id=order_id)

    else:
        # fallback
        await message.answer(f'Order #{order_id} created. We will contact you soon.', reply_markup=main_kb)
        await state.clear()

    # Notify admin
    user = message.from_user
    admin_text = (
        f'New order #{order_id}\n'
        f'From: {user.full_name} (@{user.username}) id:{user.id}\n'
        f'Product: {order["product_type"]}\n'
        f'Template: {order["template_choice"]}\n'
        f'Price: {order["price"]}\n'
        f'Status: new'
    )
    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception as e:
        logging.error('Could not notify admin: %s', e)

@router.message(OrderStates.waiting_payment_ref)
async def waiting_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('order_id')
    if message.text == 'Cancel':
        await state.clear()
        await message.answer('Order cancelled. You can start again from main menu.', reply_markup=main_kb)
        return

    if message.text in ['I paid', 'Contact Admin']:
        await message.answer('Please send payment reference (TX hash or payment screenshot) or contact admin.', reply_markup=cancel_kb)
        return

    # assume user sent tx hash or text reference
    payment_reference = message.text
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE orders SET payment_reference = ?, status = ? WHERE id = ?', (payment_reference, 'pending_confirm', order_id))
    conn.commit()
    conn.close()

    await message.answer(f'Thanks — payment reference saved for order #{order_id}. Admin will confirm.', reply_markup=main_kb)
    await bot.send_message(ADMIN_ID, f'Payment reference for order #{order_id}: {payment_reference} (from user {message.from_user.id})')
    await state.clear()

# ---------- Simple user commands ----------
@router.message(F.text == '📦 My Orders')
async def my_orders(message: Message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, product_type, status, created_at FROM orders WHERE user_id = ? ORDER BY id DESC', (message.from_user.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await message.answer('You have no orders yet.', reply_markup=main_kb)
        return
    text = 'Your orders:\n' + '\n'.join([f'#{r[0]} — {r[1]} — {r[2]} — {r[3]}' for r in rows])
    await message.answer(text, reply_markup=main_kb)

@router.message(F.text == '💬 Contact Admin')
async def contact_admin(message: Message):
    await message.answer('Admin will be notified. You can also contact directly: @YourAdminUsername', reply_markup=main_kb)
    await bot.send_message(ADMIN_ID, f'User {message.from_user.full_name} (@{message.from_user.username}) wants to contact admin.')

# ---------- Admin commands (minimal) ----------
@router.message(Command('orders'))
async def admin_list_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    rows = list_orders()
    if not rows:
        await message.answer('No orders yet.')
        return
    text = '\n'.join([f'#{r[0]} | user:{r[1]} | {r[2]} | {r[3]} | {r[4]}' for r in rows])
    await message.answer(text)

@router.message(F.text.startswith('/order_'))
async def admin_view_order(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        oid = int(message.text.split('_', 1)[1])
    except:
        await message.answer('Invalid command. Use /order_<id>')
        return
    row = get_order(oid)
    if not row:
        await message.answer('Order not found')
        return
    # row columns: id, user_id, username, product_type, template_choice, details, files, price, payment_method, payment_reference, status, created_at
    text = (f'Order #{row[0]}\nUser: {row[2]} (id:{row[1]})\nProduct: {row[3]}\nTemplate: {row[4]}\nDetails: {row[5]}\nFiles: {row[6]}\nPrice: {row[7]}\nPayment: {row[8]}\nPayment ref: {row[9]}\nStatus: {row[10]}\nCreated: {row[11]}')
    await message.answer(text)

@router.message(F.text.startswith('/setstatus'))
async def admin_set_status(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer('Usage: /setstatus <order_id> <status>')
        return
    try:
        oid = int(parts[1])
    except:
        await message.answer('Invalid order id')
        return
    status = parts[2]
    set_order_status(oid, status)
    await message.answer(f'Order #{oid} status set to {status}')
    # notify user
    row = get_order(oid)
    if row:
        user_id = row[1]
        try:
            await bot.send_message(user_id, f'Your order #{oid} status changed to: {status}')
        except Exception as e:
            logging.error('Could not notify user: %s', e)

async def main():
    os.makedirs('uploads', exist_ok=True)
    init_db()
    print('Starting bot...')
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

