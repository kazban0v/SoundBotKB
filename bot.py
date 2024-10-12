import telebot
from telebot import types
import yt_dlp
import os
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, APIC, TPE1
from PIL import Image

TOKEN = '7014334157:AAFKrxy9QE97tYXKhV9mY4oZ993g38gAYXA'
bot = telebot.TeleBot(TOKEN)

# Глобальный словарь для хранения информации о файлах, фото и тексте
user_files = {}

def download_and_convert_youtube_video(url):
    ffmpeg_path = 'C:\\ffmpeg\\ffmpeg-7.1-full_build\\bin\\ffmpeg.exe'

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',  # Сохраняем в папку downloads
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': ffmpeg_path
    }
    
    # Создаем папку, если она не существует
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        audio_file = ydl.prepare_filename(info_dict)
        audio_file = os.path.splitext(audio_file)[0] + '.mp3'
    
    return audio_file

def update_mp3(file_path, new_text, new_photo_id, author_text):
    if not os.path.isfile(file_path):
        print(f"Файл {file_path} не найден.")
        return

    try:
        audio = ID3(file_path)
    except ID3NoHeaderError:
        audio = ID3()

    # Обновление текста
    if new_text:
        audio['TIT2'] = TIT2(encoding=3, text=new_text)

    # Обновление автора
    if author_text:
        audio['TPE1'] = TPE1(encoding=3, text=author_text)

    # Обновление обложки
    if new_photo_id:
        # Удалите старую обложку, если она существует
        for tag in list(audio.keys()):
            if tag.startswith('APIC'):
                del audio[tag]

        try:
            # Скачайте и добавьте новую обложку
            file_info = bot.get_file(new_photo_id)
            downloaded_file = bot.download_file(file_info.file_path)

            with open('cover.jpg', 'wb') as new_file:
                new_file.write(downloaded_file)

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
    bot.reply_to(message, "Привет! Скинь мне ссылку на YouTube, и я конвертирую в аудио.")

@bot.message_handler(func=lambda message: "youtube.com" in message.text or "youtu.be" in message.text)
def handle_youtube_link(message):
    url = message.text
    try:
        bot.reply_to(message, "Конвертирую видео в аудио, подожди немного...")

        # Скачиваем и сохраняем MP3 файл
        audio_file = download_and_convert_youtube_video(url)
        
        # Проверяем, что файл был сохранен
        if os.path.isfile(audio_file):
            print(f"Файл успешно сохранен: {audio_file}")
            with open(audio_file, 'rb') as audio:
                msg = bot.send_audio(message.chat.id, audio)
                user_files[message.chat.id] = {'file_id': msg.audio.file_id, 'audio_file': audio_file}
        else:
            bot.send_message(message.chat.id, "Произошла ошибка при сохранении аудио файла.")
        
        # Удаляем временный файл после отправки
        os.remove(audio_file)
    
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {e}")

@bot.message_handler(content_types=['audio'])
def handle_audio(message):
    file_id = message.audio.file_id
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    # Создаем папку, если она не существует
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    file_path = 'downloads/user_audio.mp3'
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)
    
    user_files[message.chat.id] = {'file_path': file_path}
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    item1 = types.InlineKeyboardButton("Изменить обложку альбома", callback_data="edit_photo")
    item2 = types.InlineKeyboardButton("Изменить имя музыки", callback_data="edit_text")
    markup.add(item1, item2)
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["edit_photo", "edit_text"])
def handle_edit_request(call):
    if call.data == "edit_photo":
        bot.send_message(call.message.chat.id, "Отправьте фото, которое вы хотите использовать.")
        bot.register_next_step_handler(call.message, handle_photo)
    elif call.data == "edit_text":
        bot.send_message(call.message.chat.id, "Отправьте текст, который вы хотите добавить.")
        bot.register_next_step_handler(call.message, handle_text)

def handle_photo(message):
    if message.photo:
        user_files[message.chat.id]['photo'] = message.photo[-1].file_id

        # Resize the received photo
        photo_file_id = user_files[message.chat.id]['photo']
        file_info = bot.get_file(photo_file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open('photo.jpg', 'wb') as new_file:
            new_file.write(downloaded_file)

        img = Image.open('photo.jpg')
        resized_img = img.resize((300, 300))  # Уменьшение размера
        resized_img.save('resized_photo.jpg')

        # Обновление обложки аудио
        audio_file = user_files[message.chat.id].get('audio_file')
        if audio_file:
            update_mp3(audio_file, None, 'resized_photo.jpg', None)

        # Удаление временных файлов
        os.remove('photo.jpg')
        os.remove('resized_photo.jpg')

        bot.reply_to(message, "Фото обновлено!")
        send_updated_audio(message.chat.id)
    else:
        bot.reply_to(message, "Пожалуйста, пришлите правильную фотографию.")

def handle_text(message):
    user_files[message.chat.id]['text'] = message.text
    bot.reply_to(message, "Теперь укажите текст автора.")
    bot.register_next_step_handler(message, handle_author_text)

def handle_author_text(message):
    author_text = message.text
    user_files[message.chat.id]['author'] = author_text
    bot.reply_to(message, "Текст и автор обновлены!")
    send_updated_audio(message.chat.id)

def send_updated_audio(chat_id):
    user_info = user_files.get(chat_id)
    if user_info:
        audio_file = user_info.get('file_path')
        new_text = user_info.get('text')
        new_photo_id = user_info.get('photo')
        author_text = user_info.get('author')

        if audio_file:
            update_mp3(audio_file, new_text, new_photo_id, author_text)
            
            # Отправляем обновленное аудио
            with open(audio_file, 'rb') as audio:
                msg = bot.send_audio(chat_id, audio)
                user_files[chat_id]['file_id'] = msg.audio.file_id
            
            os.remove(audio_file)
        else:
            bot.send_message(chat_id, "Нет доступного MP3 файла для обновления.")
    else:
        bot.send_message(chat_id, "Нет данных для обновления.")

# Запуск бота
bot.polling()
