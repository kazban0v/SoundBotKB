import telebot
from telebot import types
import yt_dlp
import os
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, APIC, TPE1
from PIL import Image

TOKEN = '7014334157:AAFKrxy9QE97tYXKhV9mY4oZ993g38gAYXA'
bot = telebot.TeleBot(TOKEN)

user_files = {}

def download_and_convert_youtube_video(url):
    ffmpeg_path = 'C:\\ffmpeg\\ffmpeg-7.1-full_build\\bin\\ffmpeg.exe'
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': ffmpeg_path
    }

    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        audio_file = ydl.prepare_filename(info_dict)
        audio_file = os.path.splitext(audio_file)[0] + '.mp3'
    return audio_file

def update_mp3(file_path, new_text=None, photo_id=None, author_text=None, cover_path=None):
    if not os.path.isfile(file_path):
        print(f"Файл {file_path} не найден.")
        return

    try:
        audio = ID3(file_path)
    except ID3NoHeaderError:
        audio = ID3()

    # Обновление тегов
    if new_text:
        audio['TIT2'] = TIT2(encoding=3, text=new_text)
    if author_text:
        audio['TPE1'] = TPE1(encoding=3, text=author_text)

    # Удаляем старую обложку
    for tag in list(audio.keys()):
        if tag.startswith('APIC'):
            del audio[tag]

    # Обновляем обложку
    if cover_path and os.path.isfile(cover_path):
        with open(cover_path, 'rb') as cover_file:
            audio['APIC'] = APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=cover_file.read()
            )
    elif photo_id:
        try:
            file_info = bot.get_file(photo_id)
            downloaded_file = bot.download_file(file_info.file_path)
            with open('cover.jpg', 'wb') as f:
                f.write(downloaded_file)
            with open('cover.jpg', 'rb') as cover_file:
                audio['APIC'] = APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc='Cover',
                    data=cover_file.read()
                )
            os.remove('cover.jpg')
        except Exception as e:
            print(f"Ошибка при обновлении обложки: {e}")

    audio.save()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Отправь мне ссылку на YouTube, я конвертирую её в аудио, или пришли свой MP3-файл.")

@bot.message_handler(func=lambda message: "youtube.com" in message.text or "youtu.be" in message.text)
def handle_youtube_link(message):
    url = message.text
    try:
        bot.reply_to(message, "Конвертирую видео в аудио, подожди немного...")
        audio_file = download_and_convert_youtube_video(url)

        if os.path.isfile(audio_file):
            # Отправляем и сохраняем под 'audio_file'
            with open(audio_file, 'rb') as audio:
                msg = bot.send_audio(message.chat.id, audio)
                user_files[message.chat.id] = {
                    'file_id': msg.audio.file_id,
                    'audio_file': audio_file
                }
        else:
            bot.send_message(message.chat.id, "Произошла ошибка при сохранении аудио файла.")

        # Не удаляем файл сразу, чтобы была возможность изменить обложку/теги позже.

    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {e}")

@bot.message_handler(content_types=['audio'])
def handle_audio(message):
    file_id = message.audio.file_id
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    audio_file = 'downloads/user_audio.mp3'
    with open(audio_file, 'wb') as new_file:
        new_file.write(downloaded_file)

    user_files[message.chat.id] = {'audio_file': audio_file}

    markup = types.InlineKeyboardMarkup(row_width=2)
    item1 = types.InlineKeyboardButton("Изменить обложку альбома", callback_data="edit_photo")
    item2 = types.InlineKeyboardButton("Изменить имя музыки", callback_data="edit_text")
    markup.add(item1, item2)
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["edit_photo", "edit_text", "finalize", "change_tags"])
def handle_edit_request(call):
    if call.data == "edit_photo":
        bot.send_message(call.message.chat.id, "Отправьте фото для обложки.")
        bot.register_next_step_handler(call.message, handle_photo)
    elif call.data == "edit_text":
        bot.send_message(call.message.chat.id, "Отправьте название трека.")
        bot.register_next_step_handler(call.message, handle_text)
    elif call.data == "change_tags":
        # Пользователь после смены обложки хочет изменить название и автора
        bot.send_message(call.message.chat.id, "Отправьте название трека.")
        bot.register_next_step_handler(call.message, handle_text)
    elif call.data == "finalize":
        # Пользователь сразу хочет получить результат
        send_updated_audio(call.message.chat.id)

def handle_photo(message):
    chat_id = message.chat.id
    if message.photo:
        user_files[chat_id]['photo'] = message.photo[-1].file_id

        photo_file_id = user_files[chat_id]['photo']
        file_info = bot.get_file(photo_file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open('photo.jpg', 'wb') as new_file:
            new_file.write(downloaded_file)

        # Принудительно в JPEG и размер 300x300
        img = Image.open('photo.jpg').convert('RGB')
        img = img.resize((300, 300))
        img.save('resized_photo.jpg', format='JPEG')

        audio_file = user_files[chat_id].get('audio_file')

        if audio_file:
            update_mp3(audio_file, cover_path='resized_photo.jpg')

        os.remove('photo.jpg')
        os.remove('resized_photo.jpg')

        # Предлагаем изменить теги или завершить
        markup = types.InlineKeyboardMarkup(row_width=2)
        item_yes = types.InlineKeyboardButton("Изменить название и автора", callback_data="change_tags")
        item_no = types.InlineKeyboardButton("Готово", callback_data="finalize")
        markup.add(item_yes, item_no)

        bot.reply_to(message, "Обложка обновлена! Если хотите, можете изменить название и автора или сразу получить результат.", reply_markup=markup)
    else:
        bot.reply_to(message, "Отправьте правильную фотографию.")

def handle_text(message):
    chat_id = message.chat.id
    user_files[chat_id]['text'] = message.text
    bot.reply_to(message, "Теперь укажите имя автора.")
    bot.register_next_step_handler(message, handle_author_text)

def handle_author_text(message):
    chat_id = message.chat.id
    user_files[chat_id]['author'] = message.text
    bot.reply_to(message, "Название и автор обновлены!")
    send_updated_audio(chat_id)

def send_updated_audio(chat_id):
    user_info = user_files.get(chat_id)
    if not user_info:
        bot.send_message(chat_id, "Нет данных для обновления.")
        return

    audio_file = user_info.get('audio_file')
    if not audio_file or not os.path.isfile(audio_file):
        bot.send_message(chat_id, "Аудио-файл не найден для обновления.")
        return

    new_text = user_info.get('text')
    author_text = user_info.get('author')

    # Обновляем MP3 с учётом новых тегов (обложка уже была обновлена ранее)
    update_mp3(audio_file, new_text=new_text, author_text=author_text)

    with open(audio_file, 'rb') as audio:
        msg = bot.send_audio(
            chat_id,
            audio,
            caption="Обновлённый файл с обложкой!",
            title=new_text if new_text else "No Title",
            performer=author_text if author_text else "No Author"
        )
        user_files[chat_id]['file_id'] = msg.audio.file_id

    # Удаляем файл, так как все изменения внесены и файл отправлен
    os.remove(audio_file)
    # Очищаем данные о пользователе
    del user_files[chat_id]

bot.polling()
