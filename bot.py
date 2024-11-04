import ccxt
import matplotlib.pyplot as plt
import io
import numpy as np
from telegram import Bot, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext
from datetime import datetime
from telegram.utils.helpers import escape_markdown

TELEGRAM_BOT_TOKEN = "Вставьте ваши данные"
BINANCE_API_KEY = "Вставьте ваши данные"
BINANCE_SECRET_KEY = "Вставьте ваши данные"

bot = Bot(token=TELEGRAM_BOT_TOKEN)
binance = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET_KEY,
})

target_prices = {}


def start(update, context):
    update.message.reply_text(
        "Привет! Я бот для мониторинга цен на криптовалюты. Используй команду /add для добавления целевой цены. Теперь можно загружать монеты списком такого формата:\n"
        "/add BTCUSDT 55000 ETHUSDT 3000 XRPUSDT 1"
    )


def add_target_price(update, context):
    if len(context.args) % 2 != 0:
        update.message.reply_text("Использование: /add <symbol> <target_price> [<symbol> <target_price> ...]")
        return
    
    user_id = update.message.from_user.id
    if user_id not in target_prices:
        target_prices[user_id] = {}
    
    for i in range(0, len(context.args), 2):
        symbol = context.args[i].upper()
        target_price = float(context.args[i + 1])
    
        if symbol not in target_prices[user_id]:
            target_prices[user_id][symbol] = []
    
        target_prices[user_id][symbol].append({
            'target_price': target_price,
            'notified': False,
        })
    
    user_targets = target_prices[user_id]
    formatted_targets = {symbol: [t['target_price'] for t in targets] for symbol, targets in user_targets.items()}
    
    # Проверяем длину сообщения
    formatted_message = f"Установлены целевые цены: {formatted_targets}"
    message_chunks = split_long_message(formatted_message)
    for chunk in message_chunks:
        update.message.reply_text(chunk)



def list_targets(update, context):
    user_id = update.message.from_user.id

    if user_id not in target_prices or not target_prices[user_id]:
        update.message.reply_text("У вас нет установленных целевых цен.")
        return

    message = "Ваши установленные целевые цены:\n"
    for symbol, targets in target_prices[user_id].items():
        for target in targets:
            message += f"{symbol}: {target['target_price']}\n"

    update.message.reply_text(message)


def create_price_chart_info(symbol):
    try:
        ohlcv = binance.fetch_ohlcv(symbol, timeframe='1m', limit=100)
        if not ohlcv or len(ohlcv[0]) < 6:
            print(f"Неверный формат данных для символа {symbol}.")
            return None

        ohlcv = np.array(ohlcv)
        timestamps = [datetime.utcfromtimestamp(ohlcv[i][0] / 1000).strftime('%Y-%m-%d %H:%M:%S') for i in range(len(ohlcv))]

        fig, ax = plt.subplots()
        ax.plot(timestamps, ohlcv[:, 4].astype(float), label='Closing Price')

        ax.set(xlabel='Time', ylabel='Price (USDT)',
               title=f'{symbol} Daily Price Chart')
        ax.legend()
        ax.grid()

        chart_buffer = io.BytesIO()
        plt.savefig(chart_buffer, format='png')
        chart_buffer.seek(0)

        return {
            'buffer': chart_buffer,
            'coin_name': symbol,
            'chart_url': f'https://example.com/{symbol}_chart.png',
        }

    except ccxt.NetworkError as e:
        print(f"Ошибка при получении данных для графика {symbol}: {e}")
        return None


def split_long_message(message, max_length=4096):
    """Split long messages into smaller chunks."""
    return [message[i:i + max_length] for i in range(0, len(message), max_length)]


def send_chart(update, context):
    if not context.args:
        update.message.reply_text("Использование: /chart <symbol>")
        return

    symbol = context.args[0].upper()
    chart_info = create_price_chart_info(symbol)

    if chart_info and chart_info['buffer']:
        try:
            escaped_message = escape_markdown(f"График цены {symbol}:\n{chart_info['chart_url']}")
            message_chunks = split_long_message(escaped_message)

            for chunk in message_chunks:
                bot.send_photo(chat_id=update.message.chat_id, photo=chart_info['buffer'], caption=chunk,
                               parse_mode=ParseMode.MARKDOWN)
        except telegram.error.BadRequest as e:
            if "Message is too long" in str(e):
                update.message.reply_text("График слишком длинный для отправки в чат. Вы можете посмотреть его по ссылке: "
                                          f"{chart_info['chart_url']}")
            else:
                update.message.reply_text(f"Ошибка при отправке графика: {e}")
    else:
        update.message.reply_text(f"Не удалось получить график для {symbol}.")


def monitor_prices(context: CallbackContext):
            for user_id, symbols in list(target_prices.items()):  # Создаем копию словаря для безопасной итерации
                for symbol, target_prices_list in symbols.items():
                    try:
                        ticker = binance.fetch_ticker(symbol)
                        current_price = ticker['last']
                    except ccxt.NetworkError as e:
                        print(f"Ошибка при получении цены {symbol}: {e}")
                        continue
        
                    for target_price_info in target_prices_list:
                        target_price = target_price_info['target_price']
                        delta = 0.5
        
                        target_price_upper = target_price * (1 + delta / 100)
                        target_price_lower = target_price * (1 - delta / 100)
        
                        if current_price <= target_price_upper and current_price >= target_price_lower:
                            if 'notified' not in target_price_info or not target_price_info['notified']:
                                chart_info = create_price_chart_info(symbol)
        
                                if chart_info and chart_info['buffer']:
                                    message = f"Цена {symbol} достигла установленной цели! Текущая цена: {current_price}\n"
                                    message += f"Для просмотра графика используйте команду: /chart {chart_info['coin_name']}"
        
                                    message_chunks = split_long_message(message)
        
                                    for chunk in message_chunks:
                                        bot.send_photo(chat_id=user_id, photo=chart_info['buffer'], caption=chunk,
                                                       parse_mode=ParseMode.MARKDOWN)
                                    target_price_info['notified'] = True
        
                    remove_notified_targets(user_id)
        
        
def remove_notified_targets(user_id):
    if user_id in target_prices:
        for symbol, target_prices_list in target_prices[user_id].items():
            target_prices[user_id][symbol] = [target for target in target_prices_list if not target.get('notified')]



def stop_bot(update, context):
    update.message.reply_text("Бот остановлен.")
    context.bot.stop()
    
def list_targets(update, context):
    user_id = update.message.from_user.id
    
    if user_id not in target_prices or not target_prices[user_id]:
        update.message.reply_text("У вас нет установленных целевых цен.")
        return
    
    message = "Ваши установленные целевые цены:\n"
    for symbol, targets in target_prices[user_id].items():
        for target in targets:
            message += f"{symbol}: {target['target_price']}\n"
    
    message_chunks = split_long_message(message)
    for chunk in message_chunks:
        update.message.reply_text(chunk)



def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add_target_price))
    dp.add_handler(CommandHandler("list", list_targets))
    dp.add_handler(CommandHandler("chart", send_chart))
    dp.add_handler(CommandHandler("stop", stop_bot))

    job_queue = updater.job_queue
    job_queue.run_repeating(monitor_prices, interval=1)

    try:
        updater.start_polling()
        updater.idle()
    except KeyboardInterrupt:
        updater.stop()
        print("Bot stopped.")


if __name__ == "__main__":
    main()
