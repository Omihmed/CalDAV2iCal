from flask import Flask, render_template, request, redirect, url_for, send_file
import caldav
import os
from datetime import datetime, timedelta
from threading import Thread
import time
import logging
from icalendar import Calendar, Event
from dateutil.tz import tzlocal

app = Flask(__name__)

# Загрузка конфигурации
if os.path.exists('config.py'):
    app.config.from_pyfile('config.py')

# Логирование
logging.basicConfig(filename='sync.log', level=logging.INFO)

# Глобальные переменные
servers = []
log_entries = []

def parse_event(event_data):
    try:
        event = Calendar.from_ical(event_data)
        for component in event.walk():
            if component.name == "VEVENT":
                return component.to_ical()
        return None
    except Exception as e:
        log_entries.append(f"[{datetime.now()}] Error parsing event: {e}")
        return None

def sync_calendar(server):
    try:
        client = caldav.DAVClient(url=server['CALDAV_URL'], username=server['USERNAME'], password=server['PASSWORD'])
        principal = client.principal()
        
        # Получение конкретного календаря по URL
        calendar_url = 'https://calendar.mail.ru'
        calendar = client.calendar(url=calendar_url)
        
        if not calendar:
            raise Exception("Calendar not found")
        
        log_entries.append(f"[{datetime.now()}] Found calendar: {calendar.url}")
        
        # Создание нового календаря для записи событий
        combined_calendar = Calendar()
        combined_calendar.add('prodid', '-//My calendar product//mxm.dk//')
        combined_calendar.add('version', '2.0')
        
        current_date = datetime.now(tzlocal())
        
        # Поиск событий за текущий день и далее
        events = calendar.date_search(
            start=current_date,
            end=current_date + timedelta(days=365),
            expand=True
        )
        
        if not events:
            log_entries.append(f"[{datetime.now()}] No events found in calendar: {calendar.url}")
        else:
            for event in events:
                parsed_event = parse_event(event.data)
                if parsed_event:
                    # Парсим событие и проверяем его дату начала
                    event_component = Calendar.from_ical(parsed_event)
                    for component in event_component.walk():
                        if component.name == "VEVENT":
                            event_start = component.get('DTSTART').dt
                            if isinstance(event_start, datetime) and event_start >= current_date:
                                combined_calendar.add_component(component)
                                log_entries.append(f"[{datetime.now()}] Added event to combined calendar from: {calendar.url}")
                    
        # Сохранение комбинированного календаря в файл *.ics
        filename = 'calendar.ics'
        with open(filename, 'wb') as f:
            f.write(combined_calendar.to_ical())
            log_entries.append(f"[{datetime.now()}] Combined calendar written to file: {filename}")
                    
        server['status'] = 'OK'
        log_entries.append(f"[{datetime.now()}] Sync successful for {server['CALDAV_URL']}")
    except Exception as e:
        server['status'] = 'ERROR'
        log_entries.append(f"[{datetime.now()}] Sync failed for {server['CALDAV_URL']}: {str(e)}")
        log_entries.append(f"[{datetime.now()}] Debug info: {e}")

@app.route('/')
def index():
    return render_template('index.html', servers=servers, log_entries=log_entries[-20:])

@app.route('/settings/<int:index>', methods=['GET', 'POST'])
def settings(index):
    if request.method == 'POST':
        servers[index]['CALDAV_URL'] = request.form['CALDAV_URL']
        servers[index]['USERNAME'] = request.form['USERNAME']
        servers[index]['PASSWORD'] = request.form['PASSWORD']
        servers[index]['CHECK_INTERVAL'] = int(request.form['CHECK_INTERVAL'])
        return redirect(url_for('index'))
    
    return render_template('settings.html', server=servers[index])

@app.route('/syncnow/<int:index>')
def sync_now(index):
    Thread(target=sync_calendar, args=(servers[index],)).start()
    return redirect(url_for('index'))

@app.route('/download/calendar.ics')
def download_calendar():
    filename = 'calendar.ics'
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)
    else:
        return "File not found", 404

def periodic_sync():
    while True:
        for i, server in enumerate(servers):
            if (datetime.now() - server.get('last_sync', datetime.min)).total_seconds() >= server['CHECK_INTERVAL'] * 60:
                Thread(target=sync_calendar, args=(servers[i],)).start()
                server['last_sync'] = datetime.now()
        time.sleep(60)

if __name__ == '__main__':
    # Пример сервера для тестирования
    servers.append({
        'CALDAV_URL': 'https://calendar.mail.ru/',
        'USERNAME': 'USERNAME',
        'PASSWORD': 'PASSWORD',
        'CHECK_INTERVAL': 20,
        'last_sync': datetime.min,
        'status': 'UNKNOWN'
    })
    
    Thread(target=periodic_sync).start()
    app.run(host='0.0.0.0', port=9090)