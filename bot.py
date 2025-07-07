
import logging
import requests
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

CLOSE_SUM, CHOOSE_RATE, MANUAL_RATE, DROP_PERCENT, CALL_PEOPLE = range(5)

_cached_usd = None
_cached_date = None


def get_usd_rate():
    global _cached_usd, _cached_date
    today = datetime.now().date()
    if _cached_usd and _cached_date == today:
        return _cached_usd
    try:
        res = requests.get(
            "https://www.cbr-xml-daily.ru/daily_json.js", timeout=5)
        res.raise_for_status()
        data = res.json()
        usd = data["Valute"]["USD"]["Value"]
        _cached_usd = usd
        _cached_date = today
        return usd
    except:
        return 80.0


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Укажите сумму закрыва в рублях:")
    return CLOSE_SUM


async def get_close_sum(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        rub = float(update.message.text.replace(",", "."))
        ctx.user_data["rub"] = rub
    except ValueError:
        await update.message.reply_text("❌ Введите корректную сумму:")
        return CLOSE_SUM

    keyboard = ReplyKeyboardMarkup(
        [["📈 Курс ЦБ", "✏️ Ввести вручную"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text("💱 По какому курсу считать доллар?", reply_markup=keyboard)
    return CHOOSE_RATE


async def use_cbr_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rate = get_usd_rate()
    rub = ctx.user_data["rub"]
    usd = rub / rate
    ctx.user_data.update({"rate": rate, "usd": usd})
    await update.message.reply_text(
        f"📈 Курс ЦБ РФ: 1 $ = {rate:.2f} ₽\n"
        f"💵 Это: {usd:.2f}$\n\n"
        f"Введите процент дропа:"
    )

    return DROP_PERCENT


async def ask_manual_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Введите курс доллара вручную (например: 87.52):")
    return MANUAL_RATE


async def set_manual_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        rate = float(update.message.text.replace(",", "."))
    except:
        await update.message.reply_text("❌ Введите корректный курс:")
        return MANUAL_RATE

    rub = ctx.user_data["rub"]
    usd = rub / rate
    ctx.user_data.update({"rate": rate, "usd": usd})
    await update.message.reply_text(
        f"✅ Курс установлен: 1 $ = {rate:.2f} ₽\nВведите процент дропа:"
    )

    return DROP_PERCENT


async def get_drop_percent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        drop = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Введите корректный процент:")
        return DROP_PERCENT
    usd = ctx.user_data["usd"]
    after_drop = usd * (1 - drop / 100)
    ctx.user_data.update({"drop": drop, "after_drop": after_drop})
    await update.message.reply_text(
        f"📉 После дропа на {drop:.1f}%: {after_drop:.2f}$\n"
        "Сколько человек было в трубке? (целое число)"
    )

    return CALL_PEOPLE


async def get_call_people(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ Введите целое число больше нуля:")
        return CALL_PEOPLE
    ppl = int(text)
    after_drop = ctx.user_data["after_drop"]
    my_share = after_drop * 0.25
    per_person = my_share / ppl
    rate = ctx.user_data["rate"]
    rub_earned = per_person * rate
    result = (
        f"✅ Итоги расчёта:\n"
        f"• После дропа ({ctx.user_data['drop']:.1f}%): {after_drop:.2f}$\n"
        f"• Моя доля (25%): {my_share:.2f}$\n"
        f"• Людей: {ppl}\n"
        f"• Твой заработок: {per_person:.2f}$ (~{rub_earned:.2f}₽)"
    )

    if per_person < 30:
        result += "\n\n🤡 Это всё? Пора в найм!"
    elif per_person > 100:
        result += "\n\n🤑 Ты просто король звонка!"

    keyboard = ReplyKeyboardMarkup(
        [["/start"]],
        resize_keyboard=True
    )
    await update.message.reply_text(result, reply_markup=keyboard)
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Расчёт отменён.")
    return ConversationHandler.END


def main():
    app = Application.builder().token(
        "7552375610:AAENfgPDX6Dvlh6IwXr5R4vBusPWrPfyxh0").build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CLOSE_SUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_close_sum)],
            CHOOSE_RATE: [
                MessageHandler(filters.Regex("^📈 Курс ЦБ$"), use_cbr_rate),
                MessageHandler(filters.Regex(
                    "^✏️ Ввести вручную$"), ask_manual_rate)
            ],
            MANUAL_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_manual_rate)],
            DROP_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_drop_percent)],
            CALL_PEOPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_call_people)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("cancel", cancel))

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
