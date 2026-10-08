from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import requests
import json
import os
import time

app = Flask(__name__)

GROUP_ID = 45622
API_URL = f"https://ruz.spbstu.ru/api/v1/ruz/scheduler/{GROUP_ID}"
SCHEDULE_FILE = "schedule.json"
LAST_UPDATE_FILE = "last_update.txt"

def get_day_name_ru(offset_days=0):
    target_date = datetime.now() + timedelta(days=offset_days)
    days_ru = {
        0: "понедельник", 1: "вторник", 2: "среду",
        3: "четверг", 4: "пятницу", 5: "субботу", 6: "воскресенье"
    }
    return days_ru[target_date.weekday()]

def fetch_and_cache_schedule():
    """Пытается скачать расписание с API СПбПУ. Если не выходит, использует сохраненное."""
    should_update = True
    if os.path.exists(LAST_UPDATE_FILE):
        with open(LAST_UPDATE_FILE, 'r') as f:
            last_update = float(f.read().strip())
        # Обновляем не чаще чем раз в 6 часов, чтобы не нагружать сервер вуза
        if time.time() - last_update < 21600:
            should_update = False

    if should_update:
        try:
            response = requests.get(API_URL, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Сохраняем свежие данные в файл
                with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                with open(LAST_UPDATE_FILE, 'w') as f:
                    f.write(str(time.time()))
                print("✅ Расписание успешно обновлено с API СПбПУ!")
                return data
        except Exception as e:
            print(f"⚠️ Не удалось получить данные с API (возможно, ограничение хостинга): {e}")

    # Если обновление не нужно или не удалось, читаем локальный файл (наш надежный fallback)
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    return None

def format_lessons(data, offset_days=0):
    if not data:
        return "Извините, не удалось загрузить расписание. Попробуйте позже."
    
    # Проверяем, что это новый формат от API
    if "days" in data:
        target_date = (datetime.now() + timedelta(days=offset_days)).strftime("%Y-%m-%d")
        day_data = next((d for d in data["days"] if d["date"] == target_date), None)
        
        if not day_data or not day_data.get("lessons"):
            week_type = "нечётная" if data["week"].get("is_odd") else "чётная"
            day_name = get_day_name_ru(offset_days)
            return f"На {day_name} ({week_type} неделя) у вас нет пар. Можно отдыхать! 🎉"
        
        week_type = "нечётная" if data["week"].get("is_odd") else "чётная"
        day_name = get_day_name_ru(offset_days)
        lessons = day_data["lessons"]
        
        result = f"На {day_name} ({week_type} неделя) у вас {len(lessons)} пар:\n\n"
        
        for i, lesson in enumerate(lessons, 1):
            time_range = f"{lesson.get('time_start', '?')} – {lesson.get('time_end', '?')}"
            subject = lesson.get('subject', 'Предмет не указан')
            lesson_type = lesson.get('typeObj', {}).get('name', '')
            
            # Красивое название типа занятия
            type_str = ""
            if "Лекции" in lesson_type: type_str = " (Лекция)"
            elif "Лабораторные" in lesson_type: type_str = " (Лабораторная)"
            elif "Практика" in lesson_type: type_str = " (Практика)"
            
            # Корпус и аудитория
            room_str = "Аудитория не указана"
            if lesson.get("auditories"):
                aud = lesson["auditories"][0]
                room_name = aud.get("name", "")
                building_name = aud.get("building", {}).get("name", "")
                if room_name and building_name:
                    room_str = f"{building_name}, ауд. {room_name}"
                elif room_name:
                    room_str = f"ауд. {room_name}"
            
            # Преподаватель
            teacher_str = ""
            if lesson.get("teachers") and lesson["teachers"][0]:
                teacher_str = f"\n   👨‍🏫 {lesson['teachers'][0].get('full_name', '')}"
            
            result += f"{i}. ⏰ {time_range} — **{subject}**{type_str}\n"
            result += f"   📍 {room_str}{teacher_str}\n\n"
            
        return result
    else:
        return "Расписание в старом формате. Навык скоро обновит его автоматически."

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    command = data.get('request', {}).get('command', '').lower().strip()
    
    # Определяем, какой день спрашивают
    offset = 1 if "завтра" in command else 2 if "послезавтра" in command else 0
    
    # Пытаемся обновить расписание (сделает это тихо и только раз в 6 часов)
    schedule_data = fetch_and_cache_schedule()
    
    text = format_lessons(schedule_data, offset)
    
    return jsonify({
        "response": {
            "text": text,
            "tts": text.replace("\n", " ").replace("*", ""), # Убираем звездки для голосового синтеза
            "end_session": True
        },
        "version": "1.0"
    })

@app.route('/health', methods=['GET'])
def health():
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
