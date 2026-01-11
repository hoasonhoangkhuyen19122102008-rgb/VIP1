#!/usr/bin/env python3
"""
Telegram QA Bot - cải tiến: chỉ trả lời khi nhập đúng mã (case-insensitive exact token)

Ví dụ:
- "C5" -> trả lời
- "c5" -> trả lời
- "mã: C5" -> trả lời
- "XC5Y" -> không trả lời (không phải token riêng)
"""
from __future__ import annotations
import os
import re
import json
import logging
from typing import Optional, Dict, Set
from pathlib import Path

# Optional .env support (if python-dotenv is installed)
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # type: ignore

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

if load_dotenv:
    load_dotenv()

# === CONFIG ===
TOKEN = os.environ.get("8595023483:AAErY1Br8KNQEnNb6GWUd4PyAvOfsGd-_tE")
TOKEN_HARDCODED: Optional[str] = "8595023483:AAErY1Br8KNQEnNb6GWUd4PyAvOfsGd-_tE"  # Không khuyến nghị; giữ None
if TOKEN_HARDCODED:
    TOKEN = TOKEN_HARDCODED

if not TOKEN:
    raise SystemExit(
        "Không tìm thấy token. Set environment variable TELEGRAM_TOKEN or set TOKEN_HARDCODED in the script (not recommended)."
    )

# Admins for privileged commands (comma separated user IDs). If empty, reload stays open.
ADMINS: Set[int] = set()
admins_env = os.environ.get("QA_BOT_ADMIN_IDS", "").strip()
if admins_env:
    for part in admins_env.split(","):
        part = part.strip()
        if part:
            try:
                ADMINS.add(int(part))
            except ValueError:
                logging.warning("Invalid admin id in QA_BOT_ADMIN_IDS: %r  Untitled1:58 - Untitled-1v.py:58", part)

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).resolve().parent
QA_FILE = BASE_DIR / "qa.json"

DEFAULT_QA: Dict[str, Dict[str, str]] = {
    "C5": {"answer": "CAU CHI", "image": "https://ibb.co/1fvZtbhC"},
    "T3B4": {"answer": "TONG BI THU", "image": "https://ibb.co/4wDMVwjs"},
    "N6": {"answer": "NANG GIA", "image": "https://ibb.co/1f41V9Bh"},
    "3O3N2": {"answer": "BAO DIEN TU", "image": "https://ibb.co/MkTdg5pB"},
    "4G3": {"answer": "TUONG DAI", "image": "https://ibb.co/2pVdh1C"},
    "H3IT4": {"answer": "HOC LIEN THONG", "image": "https://ibb.co/xKXpvX0v"},
    "3G4": {"answer": "NANG TINH", "image": "https://ibb.co/NGhxNXy"},
    "H1U4": {"answer": "HAU CUNG", "image": "https://ibb.co/n8gSRg6C"},
    "1A3": {"answer": "CAU CU", "image": "https://ibb.co/Ndqdc0MQ"},
    "1U4": {"answer": "QUY CAI", "image": "https://ibb.co/zWDkLv3m"},
}

QA_MAP: Dict[str, Dict[str, str]] = {}


def load_qa_map(force_reload: bool = False) -> None:
    """
    Load mapping from qa.json if exists, else use DEFAULT_QA.
    """
    global QA_MAP
    if not QA_FILE.exists():
        logger.info("qa.json không tồn tại — sẽ dùng mapping mặc định.")
        QA_MAP = {k.upper(): v for k, v in DEFAULT_QA.items()}
        return

    try:
        with QA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        cleaned: Dict[str, Dict[str, str]] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if not isinstance(k, str):
                    logger.warning("Bỏ key không phải chuỗi: %r", k)
                    continue
                if not isinstance(v, dict):
                    logger.warning("Bỏ giá trị không phải dict cho key %s", k)
                    continue
                answer = str(v.get("answer", "")).strip()
                image = str(v.get("image", "")).strip()
                cleaned[k.upper()] = {"answer": answer, "image": image}
        if cleaned:
            QA_MAP = cleaned
            logger.info("Đã load %d mục từ qa.json", len(QA_MAP))
        else:
            logger.warning("qa.json rỗng hoặc không hợp lệ — dùng DEFAULT_QA")
            QA_MAP = {k.upper(): v for k, v in DEFAULT_QA.items()}
    except Exception as e:
        logger.exception("Lỗi khi đọc qa.json: %s. Dùng DEFAULT_QA.", e)
        QA_MAP = {k.upper(): v for k, v in DEFAULT_QA.items()}


def find_code_in_text(text: str) -> Optional[str]:
    """
    Tìm mã (key của QA_MAP) trong text theo nguyên tắc:
    - Tách message thành tokens bởi ký tự không phải chữ/số (regex r'[A-Za-z0-9]+').
    - So sánh token == key (case-insensitive).
    - Trả về key (uppercase) nếu tìm thấy; ngược lại None.

    Ví dụ:
    - "C5" -> match
    - "c5" -> match
    - "mã: c5" -> match (token 'c5')
    - "XC5Y" -> không match (token là 'XC5Y' khác 'C5')
    """
    if not text:
        return None

    # Precompute set of allowed uppercase keys for O(1) lookups
    keys_upper = set(k.upper() for k in QA_MAP.keys())

    # Find tokens: sequences of letters/digits
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    for tok in tokens:
        tok_up = tok.upper()
        if tok_up in keys_upper:
            return tok_up

    return None


# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Chào! Gửi mã câu hỏi chính xác (ví dụ: C5, T3B4, 3O3N2) để mình trả lời.\n"
        "Viết thường hay hoa đều được (ví dụ c5 / C5), nhưng phải là mã riêng (không phải substring).\n"
        "Dùng /list để xem danh sách mã. Admin có thể dùng /reload để nạp lại qa.json."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Hướng dẫn:\n"
        "- Gửi đúng mã (ví dụ C5). Không trả lời nếu mã chỉ là một phần của từ khác.\n"
        "- /list - liệt kê mã -> đáp án\n"
        "- /reload - nạp lại qa.json (chỉ admin nếu cấu hình QA_BOT_ADMIN_IDS)\n"
    )


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    lines = []
    for key in sorted(QA_MAP.keys()):
        ans = QA_MAP[key].get("answer", "")
        lines.append(f"{key} -> {ans}")
    text = "Danh sách mã:\n" + "\n".join(lines) if lines else "Danh sách rỗng."
    await update.message.reply_text(text)


async def reload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    user = update.effective_user
    if ADMINS:
        if not user or user.id not in ADMINS:
            await update.message.reply_text("Bạn không có quyền thực hiện lệnh này.")
            return

    try:
        load_qa_map(force_reload=True)
        await update.message.reply_text("Đã nạp lại qa.json thành công.")
    except Exception as e:
        logger.exception("Lỗi reload: %s", e)
        await update.message.reply_text(f"Lỗi khi nạp lại: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    text = update.message.text or update.message.caption or ""
    chat = update.effective_chat
    user = update.effective_user
    logger.info(
        "Tin nhắn từ chat %s (%s): %s",
        chat.id if chat else "?",
        user and (user.username or str(user.id)),
        text,
    )

    code = find_code_in_text(text)
    if not code:
        await update.message.reply_text(
            "Mình không tìm thấy mã hợp lệ (phải là mã riêng, ví dụ C5). Gửi mã chính xác hoặc dùng /list."
        )
        return

    entry = QA_MAP.get(code)
    if not entry:
        await update.message.reply_text(f"Đã tìm thấy mã {code} nhưng không có dữ liệu tương ứng.")
        return

    answer = entry.get("answer", "").strip()
    image_url = entry.get("image", "").strip()

    try:
        if answer:
            await update.message.reply_text(f"Đáp án cho {code}: {answer}")
        else:
            await update.message.reply_text(f"Đáp án cho {code}: (không có nội dung)")

        if image_url:
            try:
                await update.message.reply_photo(photo=image_url, caption=f"Hình: {code}")
            except Exception as e:
                logger.warning("Không thể gửi ảnh bằng URL trực tiếp: %s", e)
                await update.message.reply_text(f"Hình: {image_url}")
    except Exception as e:
        logger.exception("Lỗi khi trả lời: %s", e)
        await update.message.reply_text(f"Đã có lỗi khi trả lời: {e}")


def main() -> None:
    load_qa_map()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("reload", reload_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot khởi động - bắt đầu polling...")
    app.run_polling()


if __name__ == "__main__":
    main()