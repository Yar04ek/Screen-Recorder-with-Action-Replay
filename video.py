# file: test.py
import tkinter as tk
from tkinter import BOTH, Button, Label, Checkbutton, BooleanVar, Toplevel
import multiprocessing
import pyautogui
import os
import sys

root = None
worker_process = None
worker_queue = None
worker_results = None

timeline_enabled = False
MONITOR_W = 0
MONITOR_H = 0
scale_factor = 1.0

def show_retina_popup():
    """Показываем модальный popup: 'Retina?' [Да/Нет]. Возвращает True/False/None."""
    temp_root = tk.Tk()
    temp_root.withdraw()

    popup = Toplevel(temp_root)
    popup.title("У вас Retina-дисплей?")
    popup.grab_set()

    lbl = Label(popup, text="У вас Retina-дисплей (x2 масштаб)?")
    lbl.pack(padx=10, pady=10)

    answer = {"retina": None}

    def on_yes():
        answer["retina"] = True
        popup.destroy()

    def on_no():
        answer["retina"] = False
        popup.destroy()

    btn_yes = Button(popup, text="Да (Retina)", command=on_yes)
    btn_yes.pack(side="left", padx=10, pady=10)

    btn_no = Button(popup, text="Нет (обычный)", command=on_no)
    btn_no.pack(side="right", padx=10, pady=10)

    popup.wait_window()
    temp_root.destroy()
    return answer["retina"]

def on_timeline_toggle():
    global timeline_enabled
    timeline_enabled = bool(timeline_var.get())
    print("[GUI] timeline_enabled =", timeline_enabled)

def start_worker():
    global worker_process, worker_queue, worker_results
    if worker_process and worker_process.is_alive():
        return

    from worker_main import worker_main
    worker_queue = multiprocessing.Queue()
    worker_results = multiprocessing.Queue()

    worker_process = multiprocessing.Process(
        target=worker_main,
        args=(worker_queue, worker_results),
        daemon=True
    )
    worker_process.start()
    print("[GUI] Воркер-процесс запущен.")

def on_start_stop():
    """Кнопка 'Начать/Остановить запись'."""
    start_worker()
    cmd_data = {
        "MONITOR_W": MONITOR_W,
        "MONITOR_H": MONITOR_H,
        "scale_factor": scale_factor
    }
    worker_queue.put(("toggle_record", cmd_data))
    print("[GUI] отправлена команда toggle_record + monitor_params")

def on_replay_and_compare():
    """Кнопка 'Воспроизвести и сравнить'."""
    start_worker()
    cmd_data = {
        "MONITOR_W": MONITOR_W,
        "MONITOR_H": MONITOR_H,
        "scale_factor": scale_factor,
        "timeline": timeline_enabled
    }
    worker_queue.put(("replay_and_compare", cmd_data))
    print("[GUI] отправлена команда replay_and_compare + monitor_params")

def poll_worker():
    """Читаем сообщения от воркера (log, error, и т.п.)."""
    try:
        while True:
            msg = worker_results.get_nowait()
            ev, data = msg
            if ev == "log":
                print("[WORKER LOG]:", data)
            elif ev == "error":
                print("[WORKER ERROR]:", data)
            else:
                print("[WORKER MSG]:", ev, data)
    except:
        pass
    root.after(300, poll_worker)

def on_close():
    """Закрытие GUI."""
    global worker_process
    if worker_process and worker_process.is_alive():
        worker_queue.put(("shutdown", {}))
        worker_process.join(timeout=1)
        if worker_process.is_alive():
            worker_process.terminate()
    root.destroy()

def build_main_window():
    global root, timeline_var
    root = tk.Tk()
    root.title("GUI + worker + CROSS-PLATFORM ffmpeg + retina popup")
    root.protocol("WM_DELETE_WINDOW", on_close)

    b1 = Button(root, text="Начать/Остановить запись", width=30, height=2, command=on_start_stop)
    b1.pack(fill=BOTH, padx=10, pady=10)

    b2 = Button(root, text="Воспроизвести и сравнить", width=30, height=2, command=on_replay_and_compare)
    b2.pack(fill=BOTH, padx=10, pady=10)

    global timeline_var
    timeline_var = BooleanVar(value=False)
    cb = Checkbutton(root, text="Создавать раскадровку второго видео?",
                     variable=timeline_var, command=on_timeline_toggle)
    cb.pack(fill=BOTH, padx=10, pady=10)

    lbl = Label(root, text=(
        "1) «Начать/Остановить запись»:\n"
        "   - Выбираем область (2 клика)\n"
        "   - При первом клике внутри => ffmpeg capture_1\n"
        "2) «Воспроизвести и сравнить»:\n"
        "   - При первом клике => capture_2 => replay => compare => PDF.\n"
        "Работает на macOS / Windows / Linux (sys.platform)."
    ))
    lbl.pack(fill=BOTH, padx=10, pady=10)

    root.after(300, poll_worker)
    root.mainloop()

def main():
    logic_size = pyautogui.size()
    logic_w, logic_h = logic_size.width, logic_size.height
    print(f"[DEBUG] Логические размеры: {logic_w}x{logic_h}")

    is_retina = show_retina_popup()
    if is_retina is None:
        print("[INFO] Пользователь закрыл popup, завершаем.")
        sys.exit(0)

    global MONITOR_W, MONITOR_H, scale_factor
    if is_retina:
        scale_factor = 2.0
        MONITOR_W = logic_w * 2
        MONITOR_H = logic_h * 2
    else:
        scale_factor = 1.0
        MONITOR_W = logic_w
        MONITOR_H = logic_h

    print(f"[INFO] Итог: scale_factor={scale_factor}, "
          f"MONITOR_W={MONITOR_W}, MONITOR_H={MONITOR_H}")

    build_main_window()

if __name__=="__main__":
    multiprocessing.set_start_method("spawn")
    main()
