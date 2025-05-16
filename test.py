import chardet

def detect_encoding(file_path):
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Читаем первые 10кб для определения кодировки
        result = chardet.detect(raw_data)
        return result['encoding']

encoding = detect_encoding('линк.txt')

with open('линк.txt', 'r', encoding=encoding) as file:
    unique_words = set()
    for line in file:
        word = line.strip()
        if word:
            unique_words.add(word)
print(len(unique_words))