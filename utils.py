from datetime import datetime

def format_date():
    return datetime.now().strftime("%d.%m.%y")

def parse_date(date_str):
    return datetime.strptime(date_str, "%d.%m.%y").strftime("%y-%m")

def format_time():
    return datetime.now().strftime("%H:%M")