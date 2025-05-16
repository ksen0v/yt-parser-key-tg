import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import requests
import os
import time
import random
import re
import threading
import chardet

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Telegram Parser by Ksenov")
        self.root.geometry('720x500')

        self.lock = threading.Lock()
        self.all_channel_ids = set()
        self.all_tg_links = set()
        self.active_threads = 0
        self.processing = False
        self.amount_threads = 1

        self.create_widgets()

    def create_widgets(self):
        style = ttk.Style()
        style.configure("TLabel", padding=5, font=('Arial', 10))
        style.configure("TButton", font=('Arial', 10))
        style.configure("TEntry", padding=5)

        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Файл с API ключами
        ttk.Label(main_frame, text="Файл с API ключами:").grid(row=0, column=0, sticky=tk.W)
        self.api_key_entry = ttk.Entry(main_frame, width=50)
        self.api_key_entry.grid(row=0, column=1, pady=5, sticky=tk.EW)
        ttk.Button(main_frame, text="Обзор", command=lambda: self.select_file(self.api_key_entry))\
            .grid(row=0, column=2, padx=5)

        # Файл с прокси
        ttk.Label(main_frame, text="Файл с прокси:").grid(row=1, column=0, sticky=tk.W)
        self.proxy_entry = ttk.Entry(main_frame, width=50)
        self.proxy_entry.grid(row=1, column=1, pady=5, sticky=tk.EW)
        ttk.Button(main_frame, text="Обзор", command=lambda: self.select_file(self.proxy_entry))\
            .grid(row=1, column=2, padx=5)

        # Файл с ключевыми словами
        ttk.Label(main_frame, text="Файл с ключевыми словами:").grid(row=2, column=0, sticky=tk.W)
        self.keywords_entry = ttk.Entry(main_frame, width=50)
        self.keywords_entry.grid(row=2, column=1, pady=5, sticky=tk.EW)
        ttk.Button(main_frame, text="Обзор", command=lambda: self.select_file(self.keywords_entry))\
            .grid(row=2, column=2, padx=5)

        # Количество видео
        ttk.Label(main_frame, text="Видео на запрос:").grid(row=3, column=0, sticky=tk.W)
        self.videos_count = ttk.Entry(main_frame, width=50)
        self.videos_count.grid(row=3, column=1, pady=5, sticky=tk.EW)

        # Кнопка запуска
        self.search_btn = ttk.Button(main_frame, text="Начать парсинг", command=self.start_parsing)
        self.search_btn.grid(row=4, column=1, pady=10, sticky=tk.EW)

        # Лог
        self.result_area = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=15)
        self.result_area.grid(row=5, column=0, columnspan=3, sticky=tk.NSEW)

        # Прогресс бар
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=6, column=0, columnspan=3, sticky=tk.EW, pady=5)

        # Настройка сетки
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(5, weight=1)

    def select_file(self, entry_widget):
        filename = filedialog.askopenfilename()
        if filename:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)

    def start_parsing(self):
        if self.processing:
            return

        self.processing = True
        self.result_area.delete(1.0, tk.END)
        self.all_channel_ids = set()
        self.all_tg_links = set()
        self.amount_threads = 1

        # Получаем пути к файлам
        api_file = self.api_key_entry.get()
        proxy_file = self.proxy_entry.get()
        keywords_file = self.keywords_entry.get()
        videos_count = self.videos_count.get()

        # Валидация параметров
        if not all([api_file, keywords_file, videos_count]) or not videos_count.isdigit():
            self.log("Ошибка: Проверьте введенные параметры!")
            self.processing = False
            return

        try:
            # Загрузка данных
            with open(api_file) as f:
                api_keys = [line.strip() for line in f if line.strip()]
            
            proxies = []
            if proxy_file and os.path.exists(proxy_file):
                with open(proxy_file) as f:
                    proxies = [line.strip() for line in f if line.strip()]
            
            encoding = self.detect_encoding(keywords_file)
            with open(keywords_file, encoding=encoding) as f:
                all_keywords = [line.strip().replace(' ', '+') for line in f if line.strip()]
            
            videos_count = int(videos_count)
            
        except Exception as e:
            self.log(f"Ошибка загрузки файлов: {str(e)}")
            self.processing = False
            return

        # Выравниваем количество прокси
        proxies = proxies if proxies else [None]*len(api_keys)
        if len(api_keys) != len(proxies):
            self.log("Предупреждение: Количество API ключей и прокси не совпадает!")
            proxies = [None]*len(api_keys)

        # Распределяем ключевые слова между потоками
        chunks = self.split_list(all_keywords, len(api_keys))
        self.log(f"Распределение ключевых слов: {[len(c) for c in chunks]} слов на поток")

        self.search_btn['state'] = tk.DISABLED
        self.progress.start()
        self.active_threads = len(api_keys)

        # Запуск потоков
        for i, (api_key, proxy) in enumerate(zip(api_keys, proxies)):
            thread_keywords = chunks[i] if i < len(chunks) else []
            if not thread_keywords:
                continue

            thread = threading.Thread(
                target=self.worker,
                args=(self.amount_threads, api_key, proxy, thread_keywords, videos_count),
                daemon=True
            )
            thread.start()
            self.amount_threads += 1

    def split_list(self, lst, n):
        """Разделить список на n примерно равных частей"""
        k, m = divmod(len(lst), n)
        return [lst[i*k+min(i, m):(i+1)*k+min(i+1, m)] for i in range(n)]

    def worker(self, thread_id, api_key, proxy, keywords, videos_count):
        try:
            self.log(f"[Поток {thread_id}] Старт потока с {len(keywords)} ключевыми словами")
            
            # Парсим каналы для выделенных ключевых слов
            channels = self.get_youtube_channels(thread_id, api_key, keywords, videos_count, proxy)
            
            # Парсим Telegram ссылки
            tg_links = self.get_channels_tg_urls(thread_id, channels, proxy)
            
            with self.lock:
                self.log(f"[Поток {thread_id}] Завершен поток: {len(channels)} каналов, {tg_links} ссылок")
                
        except Exception as e:
            self.log(f"[Поток {thread_id}] Ошибка в потоке: {str(e)}")
        finally:
            with self.lock:
                self.active_threads -= 1
                if self.active_threads == 0:
                    self.finish_processing()

    def finish_processing(self):       
        self.progress.stop()
        self.search_btn['state'] = tk.NORMAL
        self.processing = False
        self.log("\nИтоговые результаты:\n"
                f"Всего каналов: {len(self.all_channel_ids)}\n"
                f"Телеграм ссылок: {len(self.all_tg_links)}\n"
                "Данные сохранены в файлы: channel_ids.txt и tg_links.txt")

    def get_youtube_channels(self, thread_id, api_key, keywords, max_videos, proxy):
        proxies = {'http': f'socks5://{proxy}', 'https': f'socks5://{proxy}'} if proxy else None
        channel_ids = set()
        total_keywords = len(keywords)

        for idx, keyword in enumerate(keywords, 1):
            self.log(f"[Поток {thread_id}] Получение видео по ворду ({idx}/{total_keywords}): {keyword.replace('+', ' ')}")
            
            next_page_token = None
            remaining = max_videos
            
            while remaining > 0:
                max_results = min(remaining, 50)
                url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={keyword}&key={api_key}&type=video&maxResults={max_results}"
                
                if next_page_token:
                    url += f"&pageToken={next_page_token}"
                
                try:
                    response = requests.get(url, proxies=proxies, timeout=15)
                    response.raise_for_status()
                    data = response.json()

                    # Проверка на превышение квоты
                    if 'error' in data and data['error']['code'] == 403:
                        self.log("[Поток {thread_id}] Ошибка: Превышена квота API YouTube. Перехожу к поиску ссылок в найденных каналах.")
                        return channel_ids  # Завершаем поток, возвращая текущие каналы
                
                except Exception as e:
                    self.log(f"[Поток {thread_id}] Ошибка запроса: {str(e)}")
                    break
                
                for video in data.get("items", []):
                    if channel_id := video["snippet"].get("channelId"):
                        with self.lock:
                            if channel_id not in self.all_channel_ids:
                                self.all_channel_ids.add(channel_id)
                                self.write_channel_to_file(channel_id)
                        channel_ids.add(channel_id)
                
                next_page_token = data.get("nextPageToken")
                remaining -= len(data.get("items", []))
                if not next_page_token:
                    break
        
        return channel_ids

    def get_channels_tg_urls(self, thread_id, channel_ids, proxy):
        proxies = {'http': f'socks5://{proxy}', 'https': f'socks5://{proxy}'} if proxy else None
        tg_urls = 0
        pattern = re.compile(r'\b(?:https?://)?(?:www\.)?(?:t|telegram)\.me/(\w+)\b')
        total_channels = len(channel_ids)

        for idx, channel_id in enumerate(channel_ids, 1):
            try:
                self.log(f'[Поток {thread_id}] Поиск ссылки на Telegram канал ({idx}/{total_channels}): {channel_id}')

                self.human_delay(0.7, 2)
                response = requests.get(
                    f'https://www.youtube.com/channel/{channel_id}/about',
                    proxies=proxies,
                    timeout=15
                )
                matches = pattern.findall(response.text)

                for match in set(matches):
                    link = f't.me/{match}'
                    if 'bot' not in link.lower():
                        with self.lock:
                            if link not in self.all_tg_links:
                                self.all_tg_links.add(link)
                                self.write_link_to_file(link)
                                tg_urls += 1
                        self.log(f'[Поток {thread_id}] На канале {channel_id} найдена ссылка {link}')
            except Exception as e:
                self.log(f"[Поток {thread_id}] Ошибка парсинга канала {channel_id}: {str(e)}")
        
        return tg_urls

    def log(self, message):
        self.root.after(0, self.result_area.insert, tk.END, message + "\n")

    def write_channel_to_file(self, channel_id):
        """Атомарная запись канала в файл"""
        with open('channel_ids.txt', 'a', encoding='utf-8') as f:
            f.write(f"{channel_id}\n")

    def write_link_to_file(self, link):
        """Атомарная запись ссылки в файл"""
        with open('tg_links.txt', 'a', encoding='utf-8') as f:
            f.write(f"{link}\n")

    def human_delay(self, min_sec=0.5, max_sec=1.2):
        time.sleep(random.uniform(min_sec, max_sec))

    def detect_encoding(self, file_path):
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Читаем первые 10кб для определения кодировки
        result = chardet.detect(raw_data)
        return result['encoding']

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()