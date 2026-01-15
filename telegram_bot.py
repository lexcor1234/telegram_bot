import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp
import asyncio

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Token del bot (desde variable de entorno)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN no está configurado. Crea un archivo .env con tu token.")

# Carpeta de descargas
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Almacenamiento temporal de URLs por usuario
user_urls = {}


def format_seconds(seconds):
    """Formatea segundos a HH:MM:SS o MM:SS"""
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    welcome_message = (
        "🎬 *Descargador Universal Bot*\n\n"
        "Envíame un enlace de YouTube, TikTok, Instagram, etc. y te ayudaré a descargarlo.\n\n"
        "*Comandos:*\n"
        "/start - Mostrar este mensaje\n"
        "/help - Ayuda\n\n"
        "Simplemente pega un enlace para comenzar!"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    help_text = (
        "📖 *Cómo usar el bot:*\n\n"
        "1. Envía un enlace de video (YouTube, TikTok, Instagram, etc.)\n"
        "2. El bot analizará el enlace y mostrará la información\n"
        "3. Selecciona el formato (Video o Audio MP3)\n"
        "4. Selecciona la calidad deseada\n"
        "5. Espera a que se descargue y recibe el archivo!\n\n"
        "*Plataformas soportadas:*\n"
        "YouTube, TikTok, Instagram, Twitter/X, Facebook, y más..."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def get_video_info(url: str) -> dict:
    """Obtiene información del video"""
    ydl_opts = {'quiet': True, 'skip_download': True}
    try:
        loop = asyncio.get_event_loop()
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        return await loop.run_in_executor(None, extract)
    except Exception as e:
        logger.error(f"Error obteniendo info: {e}")
        return None


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja URLs enviadas por el usuario"""
    url = update.message.text.strip()
    user_id = update.effective_user.id

    status_msg = await update.message.reply_text("🔍 Analizando enlace...")

    # Obtener información del video
    info = await get_video_info(url)

    if not info:
        await status_msg.edit_text("❌ No pude obtener información del video. Verifica el enlace.")
        return

    # Guardar URL para el usuario
    user_urls[user_id] = {'url': url, 'info': info}

    # Preparar mensaje con información
    title = info.get('title', 'Sin título')[:100]
    duration = format_seconds(info.get('duration'))
    uploader = info.get('uploader', 'Desconocido')

    info_text = (
        f"📹 *{title}*\n\n"
        f"👤 Canal: {uploader}\n"
        f"⏱ Duración: {duration}\n\n"
        "Selecciona el formato de descarga:"
    )

    # Botones de selección de formato
    keyboard = [
        [
            InlineKeyboardButton("🎬 Video", callback_data="format_video"),
            InlineKeyboardButton("🎵 Audio MP3", callback_data="format_audio")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Enviar thumbnail si está disponible
    thumbnail = info.get('thumbnail')
    if thumbnail:
        try:
            await status_msg.delete()
            await update.message.reply_photo(
                photo=thumbnail,
                caption=info_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except:
            await status_msg.edit_text(info_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await status_msg.edit_text(info_text, reply_markup=reply_markup, parse_mode='Markdown')


async def format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de formato"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    format_type = query.data.replace("format_", "")

    if user_id not in user_urls:
        await query.edit_message_text("❌ Sesión expirada. Envía el enlace nuevamente.")
        return

    user_urls[user_id]['format'] = format_type

    if format_type == "video":
        # Mostrar opciones de calidad para video
        keyboard = [
            [InlineKeyboardButton("🏆 Mejor calidad", callback_data="quality_best")],
            [InlineKeyboardButton("📺 1080p Full HD", callback_data="quality_1080")],
            [InlineKeyboardButton("📺 720p HD", callback_data="quality_720")],
            [InlineKeyboardButton("📺 480p SD", callback_data="quality_480")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_caption(
                caption="🎬 *Video seleccionado*\n\nElige la calidad:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except:
            await query.edit_message_text(
                text="🎬 *Video seleccionado*\n\nElige la calidad:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    else:
        # Para audio, iniciar descarga directamente
        user_urls[user_id]['quality'] = 'audio'
        await start_download(update, context)


async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de calidad"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    quality = query.data.replace("quality_", "")

    if user_id not in user_urls:
        await query.edit_message_text("❌ Sesión expirada. Envía el enlace nuevamente.")
        return

    user_urls[user_id]['quality'] = quality
    await start_download(update, context)


async def start_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia la descarga del video/audio"""
    query = update.callback_query
    user_id = update.effective_user.id

    if user_id not in user_urls:
        return

    user_data = user_urls[user_id]
    url = user_data['url']
    format_type = user_data['format']
    quality = user_data['quality']
    title = user_data['info'].get('title', 'video')[:50]

    # Actualizar mensaje
    try:
        await query.edit_message_caption(caption="⏳ Descargando... Por favor espera.")
    except:
        await query.edit_message_text("⏳ Descargando... Por favor espera.")

    # Configurar yt-dlp
    output_template = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')

    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }

    if format_type == "audio":
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'
            }]
        })
    else:
        # Formatos flexibles con fallback
        if quality == "best":
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        else:
            ydl_opts['format'] = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'
        # Merge a mp4 si es necesario
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        # Descargar
        loop = asyncio.get_event_loop()

        def do_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if format_type == "audio":
                    filename = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'
                else:
                    filename = ydl.prepare_filename(info)
                return filename, info

        filename, info = await loop.run_in_executor(None, do_download)

        # Verificar que el archivo existe
        if not os.path.exists(filename):
            # Buscar archivo con nombre similar
            base_name = os.path.splitext(os.path.basename(filename))[0]
            for f in os.listdir(DOWNLOAD_DIR):
                if base_name in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break

        if os.path.exists(filename):
            file_size = os.path.getsize(filename)

            # Telegram tiene límite de 50MB para bots
            if file_size > 50 * 1024 * 1024:
                try:
                    await query.edit_message_caption(
                        caption=f"⚠️ El archivo es muy grande ({file_size // (1024*1024)}MB).\n"
                                "Telegram solo permite archivos hasta 50MB.\n"
                                "Intenta con una calidad menor."
                    )
                except:
                    await query.edit_message_text(
                        f"⚠️ El archivo es muy grande ({file_size // (1024*1024)}MB).\n"
                        "Telegram solo permite archivos hasta 50MB."
                    )
            else:
                # Enviar archivo
                try:
                    await query.edit_message_caption(caption="📤 Enviando archivo...")
                except:
                    await query.edit_message_text("📤 Enviando archivo...")

                with open(filename, 'rb') as f:
                    if format_type == "audio":
                        await context.bot.send_audio(
                            chat_id=update.effective_chat.id,
                            audio=f,
                            title=title,
                            caption=f"🎵 {title}"
                        )
                    else:
                        await context.bot.send_video(
                            chat_id=update.effective_chat.id,
                            video=f,
                            caption=f"🎬 {title}",
                            supports_streaming=True
                        )

                try:
                    await query.delete_message()
                except:
                    pass

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="✅ ¡Descarga completada! Envía otro enlace para continuar."
                )

            # Limpiar archivo después de enviar
            try:
                os.remove(filename)
            except:
                pass
        else:
            raise Exception("Archivo no encontrado después de la descarga")

    except Exception as e:
        logger.error(f"Error en descarga: {e}")
        try:
            await query.edit_message_caption(caption=f"❌ Error al descargar: {str(e)[:100]}")
        except:
            await query.edit_message_text(f"❌ Error al descargar: {str(e)[:100]}")

    # Limpiar datos del usuario
    if user_id in user_urls:
        del user_urls[user_id]


def main():
    """Función principal"""
    # Crear aplicación
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Handler para URLs (mensajes de texto que contengan http)
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'https?://'), handle_url))

    # Handlers para callbacks de botones
    application.add_handler(CallbackQueryHandler(format_callback, pattern=r'^format_'))
    application.add_handler(CallbackQueryHandler(quality_callback, pattern=r'^quality_'))

    # Iniciar bot
    print("Bot iniciado! Presiona Ctrl+C para detener.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
