# file: worker_impl.py

import sys
import os
import subprocess
import signal
import shutil
import time
import cv2
import numpy as np

import pyautogui
from pynput import mouse, keyboard

mouse_listener = None
keyboard_listener = None

CURRENT_RECORD_PROC = None
CURRENT_RECORD_PATH = None

# ------------------------------
# СОЗДАНИЕ ПАПКИ
# ------------------------------
def create_session_folder():
    base_dir = "test"
    if not os.path.exists(base_dir):
        os.mkdir(base_dir)
    import datetime
    dt_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(base_dir, f"session_{dt_str}")
    os.mkdir(folder)
    return folder

# ------------------------------
# ВЫБОР ОБЛАСТИ
# ------------------------------
def select_screen_region_logical(result_queue=None):
    coords = []
    def on_click_local(x, y, button, pressed):
        if pressed:
            coords.append((x, y))
            if len(coords)==2:
                listener.stop()

    if result_queue:
        result_queue.put(("log", "[worker_impl] Ожидаем 2 клика: лев.верх и прав.ниж."))

    listener = mouse.Listener(on_click=on_click_local)
    listener.start()
    listener.join()

    if len(coords)<2:
        if result_queue:
            result_queue.put(("log","[worker_impl] Область не выбрана (меньше 2 кликов)"))
        return None
    x1,y1 = coords[0]
    x2,y2 = coords[1]
    left = min(x1,x2)
    top  = min(y1,y2)
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    if w<=0 or h<=0:
        if result_queue:
            result_queue.put(("log","[worker_impl] Некорректная область (w<=0 or h<=0)"))
        return None
    if result_queue:
        result_queue.put(("log", f"[worker_impl] region => left={left}, top={top}, w={w}, h={h}"))
    return (left, top, w, h)

def to_physical_coords(region_log, scale):
    L,T,W,H = region_log
    return (int(L*scale), int(T*scale), int(W*scale), int(H*scale))

# ------------------------------
# СТАРТ/СТОП FFMPEG (МУЛЬТИПЛАТФОРМЕННО)
# ------------------------------
def start_ffmpeg_crop(out_path, left_px, top_px, w_px, h_px, fps, MONITOR_W, MONITOR_H):
    """
    Запускает ffmpeg для записи экрана на разных платформах (macOS, Windows, Linux).
    - macOS => -f avfoundation, устройство "Capture screen 0"
    - Windows => -f gdigrab, устройство "desktop"
    - Linux => -f x11grab, устройство ":0.0"
    Далее crop=... через filter_v.
    """
    import sys
    platform = sys.platform
    if platform.startswith("darwin"):
        # macOS => avfoundation
        input_device = "Capture screen 0"
        cmd = [
            "ffmpeg","-y",
            "-f","avfoundation",
            "-video_size", f"{MONITOR_W}x{MONITOR_H}",
            "-framerate", str(fps),
            "-i", input_device,
            "-filter:v", f"crop={w_px}:{h_px}:{left_px}:{top_px}",
            "-vcodec","libx264",
            "-pix_fmt","yuv420p",
            "-preset","veryfast",
            out_path
        ]
    elif platform.startswith("win"):
        # Windows => gdigrab
        # можно прописать -offset_x, -offset_y, и т.п. но тут для простоты:
        input_device = "desktop"
        cmd = [
            "ffmpeg","-y",
            "-f","gdigrab",
            "-framerate", str(fps),
            "-i", input_device,
            # crop=...
            "-filter:v", f"crop={w_px}:{h_px}:{left_px}:{top_px}",
            "-vcodec","libx264",
            "-pix_fmt","yuv420p",
            "-preset","veryfast",
            out_path
        ]
    else:
        # Полагаем, что Linux => x11grab
        display = ":0.0"
        cmd = [
            "ffmpeg","-y",
            "-f","x11grab",
            "-video_size", f"{MONITOR_W}x{MONITOR_H}",
            "-framerate", str(fps),
            "-i", display,
            "-filter:v", f"crop={w_px}:{h_px}:{left_px}:{top_px}",
            "-vcodec","libx264",
            "-pix_fmt","yuv420p",
            "-preset","veryfast",
            out_path
        ]

    print("[worker_impl] Запуск ffmpeg:", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc

def stop_ffmpeg(proc):
    """Останавливает ffmpeg (SIGINT), печатает stdout/stderr, проверяет готовый файл."""
    global CURRENT_RECORD_PATH
    if not proc:
        return

    retc = proc.poll()
    print(f"[worker_impl] stop_ffmpeg: poll()={retc}")

    try:
        if retc is None:
            print("[worker_impl] ffmpeg still running => send SIGINT")
            proc.send_signal(signal.SIGINT)

            out, err = proc.communicate(timeout=5)
            print("[FFMPEG] STDOUT:", out.decode("utf-8", errors="ignore"))
            print("[FFMPEG] STDERR:", err.decode("utf-8", errors="ignore"))
        else:
            out, err = proc.communicate()
            print("[FFMPEG - already ended] STDOUT:", out.decode("utf-8", errors="ignore"))
            print("[FFMPEG - already ended] STDERR:", err.decode("utf-8", errors="ignore"))

    except subprocess.TimeoutExpired:
        print("[worker_impl] ffmpeg did not stop => kill()")
        proc.kill()
        out, err = proc.communicate()
        print("[FFMPEG-timeout] STDOUT:", out.decode("utf-8", errors="ignore"))
        print("[FFMPEG-timeout] STDERR:", err.decode("utf-8", errors="ignore"))

    # Проверяем результат
    if CURRENT_RECORD_PATH:
        if not os.path.isfile(CURRENT_RECORD_PATH):
            print(f"[worker_impl] Ошибка: файл {CURRENT_RECORD_PATH} не создан!")
        else:
            sizeb = os.path.getsize(CURRENT_RECORD_PATH)
            if sizeb <= 0:
                print(f"[worker_impl] Ошибка: файл {CURRENT_RECORD_PATH} пуст (size=0).")
            else:
                print(f"[worker_impl] OK: файл {CURRENT_RECORD_PATH} size={sizeb} байт.")
    CURRENT_RECORD_PATH = None


# ------------------------------
# ЧАСТЬ: РАСКАДРОВКА (TIMELINE)
# ------------------------------
def generate_timeline_pdf_for_video(vpath, pdf_path, fps=10.0):
    """
    Создаёт PDF, где каждый кадр video's — отдельная страница.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    cap = cv2.VideoCapture(vpath)
    if not cap.isOpened():
        print(f"[worker_impl] Не удалось открыть {vpath}")
        return
    temp_dir = os.path.join(os.path.dirname(pdf_path),"temp_timeline")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.mkdir(temp_dir)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    frame_idx = 0
    x_img,y_img=20,300
    w_img,h_img=180*mm,100*mm

    while True:
        ret,frame = cap.read()
        if not ret:
            break
        img_path = os.path.join(temp_dir,f"frame_{frame_idx}.png")
        cv2.imwrite(img_path, frame)
        c.setFont("Helvetica",12)
        c.drawString(50,800,f"Frame {frame_idx}, time={frame_idx/fps:.2f}s")
        try:
            c.drawImage(img_path, x_img, y_img, width=w_img, height=h_img)
        except:
            pass
        c.showPage()
        frame_idx+=1
    cap.release()
    c.save()
    print(f"[worker_impl] timeline => {pdf_path}")


# ------------------------------
# ПЕРВАЯ ЗАПИСЬ
# ------------------------------
def start_listeners(actions, region_logical, region_physical, session_folder,
                    MONITOR_W, MONITOR_H,
                    result_queue=None):
    global mouse_listener, keyboard_listener
    global CURRENT_RECORD_PROC, CURRENT_RECORD_PATH

    def log(msg):
        if result_queue:
            result_queue.put(("log", msg))
        else:
            print(msg)

    state = {
        "first_click_done": False,
        "start_time": time.time()
    }

    def in_region(x,y):
        L,T,W,H = region_logical
        return (x>=L) and (x<L+W) and (y>=T) and (y<T+H)

    def on_click(x, y, button, pressed):
        nonlocal actions
        global CURRENT_RECORD_PROC, CURRENT_RECORD_PATH

        if pressed and (not state["first_click_done"]) and in_region(x,y):
            state["first_click_done"] = True
            state["start_time"] = time.time()
            log("=== Первый клик (первая запись) => ffmpeg capture_1 start ===")

            cap1_path = os.path.join(session_folder, "capture_1.mp4")
            CURRENT_RECORD_PATH = cap1_path
            CURRENT_RECORD_PROC = start_ffmpeg_crop(
                out_path = cap1_path,
                left_px = region_physical[0],
                top_px  = region_physical[1],
                w_px    = region_physical[2],
                h_px    = region_physical[3],
                fps=10,
                MONITOR_W=MONITOR_W,
                MONITOR_H=MONITOR_H
            )

            actions.append((time.time()-state["start_time"], "mouse", ("click", x,y,str(button), pressed)))
        elif state["first_click_done"] and in_region(x,y):
            actions.append((time.time()-state["start_time"], "mouse", ("click", x,y,str(button), pressed)))

    def on_move(x,y):
        if state["first_click_done"]:
            actions.append((time.time()-state["start_time"], "mouse", ("move",x,y)))

    def on_scroll(x,y,dx,dy):
        if state["first_click_done"] and in_region(x,y):
            actions.append((time.time()-state["start_time"], "mouse", ("scroll",x,y,dx,dy)))

    def on_press(key):
        if state["first_click_done"]:
            actions.append((time.time()-state["start_time"], "keyboard",("press", str(key))))

    def on_release(key):
        if state["first_click_done"]:
            actions.append((time.time()-state["start_time"], "keyboard",("release",str(key))))

    mouse_listener = mouse.Listener(on_click=on_click, on_move=on_move, on_scroll=on_scroll)
    keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    mouse_listener.start()
    keyboard_listener.start()
    log("[worker_impl] start_listeners (первая запись) запущены.")

def stop_listeners():
    global mouse_listener, keyboard_listener
    global CURRENT_RECORD_PROC
    if mouse_listener:
        mouse_listener.stop()
        mouse_listener = None
    if keyboard_listener:
        keyboard_listener.stop()
        keyboard_listener = None

    if CURRENT_RECORD_PROC:
        stop_ffmpeg(CURRENT_RECORD_PROC)
        CURRENT_RECORD_PROC = None

    print("[worker_impl] stop_listeners: первая запись остановлена.")


# ------------------------------
# ВОСПРОИЗВЕДЕНИЕ
# ------------------------------
def replay_actions(actions, region_logical, result_queue=None):
    def log(msg):
        if result_queue:
            result_queue.put(("log", msg))
        else:
            print(msg)

    log("[worker_impl] Начинаем replay_actions")

    from pynput.mouse import Controller as Mctl
    import pyautogui

    if not actions:
        log("Нет действий!")
        return

    base_time = actions[0][0]
    start_rep = time.time()
    mouse_ctl = Mctl()

    def in_region(x,y):
        L,T,W,H = region_logical
        return (x>=L) and (x<(L+W)) and (y>=T) and (y<(T+H))

    for (t_off,kind,data) in actions:
        # Ждем, пока не наступит "время" действия
        while (time.time()-start_rep) < (t_off - base_time):
            time.sleep(0.001)

        if kind == "mouse":
            etype = data[0]
            if etype == "move":
                _, x,y = data
                if in_region(x,y):
                    mouse_ctl.position = (x,y)
            elif etype == "click":
                _, x,y, btn_str, pressed = data
                if in_region(x,y):
                    mouse_ctl.position = (x,y)
                    b = btn_str.replace("Button.","")
                    if pressed:
                        pyautogui.mouseDown(x=x, y=y, button=b)
                    else:
                        pyautogui.mouseUp(x=x, y=y, button=b)
            elif etype == "scroll":
                _, x,y,dx,dy = data
                if in_region(x,y):
                    mouse_ctl.position = (x,y)
                    pyautogui.scroll(dy)

        elif kind == "keyboard":
            etype, key_str = data
            mx, my = mouse_ctl.position
            if in_region(mx,my):
                if etype == "press":
                    if key_str.startswith("Key."):
                        k = key_str.replace("Key.","")
                        if k=="enter":
                            pyautogui.press("enter")
                        elif k=="space":
                            pyautogui.press("space")
                        elif k=="tab":
                            pyautogui.press("tab")
                    else:
                        char = key_str.strip("'")
                        pyautogui.write(char)
                # release можно пропустить
    log("[worker_impl] replay_actions завершён.")


# ------------------------------
# ВТОРАЯ ЗАПИСЬ + PDF-ОТЧЁТ
# ------------------------------
def start_second_click_listener(actions,
                                region_logical, region_physical, session_folder,
                                MONITOR_W, MONITOR_H,
                                timeline_enabled,
                                result_queue):
    from pynput import mouse

    def log(msg):
        result_queue.put(("log", msg))

    global CURRENT_RECORD_PROC, CURRENT_RECORD_PATH
    second_listener = None
    second_first_done = {"val":False}

    def in_region(x,y):
        L,T,W,H = region_logical
        return (x>=L) and (x<(L+W)) and (y>=T) and (y<(T+H))

    def on_click_second(x, y, btn, pressed):
        global CURRENT_RECORD_PROC, CURRENT_RECORD_PATH
        if pressed and (not second_first_done["val"]) and in_region(x,y):
            second_first_done["val"] = True
            cap2_path = os.path.join(session_folder,"capture_2.mp4")
            CURRENT_RECORD_PATH = cap2_path
            CURRENT_RECORD_PROC = start_ffmpeg_crop(
                cap2_path,
                region_physical[0],
                region_physical[1],
                region_physical[2],
                region_physical[3],
                fps=10,
                MONITOR_W=MONITOR_W,
                MONITOR_H=MONITOR_H
            )
            log("=== Первый клик (вторая запись) => ffmpeg capture_2 => replay => compare => PDF ===")

            # 1) replay
            replay_actions(actions, region_logical, result_queue)

            # 2) stop ffmpeg
            if CURRENT_RECORD_PROC:
                stop_ffmpeg(CURRENT_RECORD_PROC)
                CURRENT_RECORD_PROC = None

            # 3) timeline (опционально)
            if timeline_enabled:
                pdf_tl = os.path.join(session_folder,"timeline_2nd_video.pdf")
                generate_timeline_pdf_for_video(cap2_path, pdf_tl, fps=10.0)
                log(f"Раскадровка второго видео => {pdf_tl}")

            # 4) Формируем подробный PDF-отчёт с отличиями
            cap1_path = os.path.join(session_folder, "capture_1.mp4")
            pdf_diff = os.path.join(session_folder, "differences_detailed.pdf")
            generate_detailed_diff_report(
                cap1_path, cap2_path,
                pdf_diff,
                fps=10.0,
                diff_threshold=1000
            )
            log(f"Подробный отчёт (PDF) => {pdf_diff}")

            if second_listener:
                second_listener.stop()
                log("Слушатель 2й записи остановлен.")

    second_listener = mouse.Listener(on_click=on_click_second)
    second_listener.start()

# ------------------------------
# ПОДРОБНЫЙ PDF-ОТЧЁТ (ПО КАДРАМ)
# ------------------------------
def generate_detailed_diff_report(v1, v2, pdf_out, fps=10.0, diff_threshold=1000):
    """
    Покадровое сравнение (v1, v2). На каждый кадр => страница PDF.
    Если diff_px>=threshold => надпись (Frame i, time=..., diff_px=...) красным.
    Склеиваем (f1, f2 c контурами) => PNG => вставляем в PDF.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import black, red

    if not os.path.exists(os.path.dirname(pdf_out)):
        os.makedirs(os.path.dirname(pdf_out), exist_ok=True)

    cap1 = cv2.VideoCapture(v1)
    cap2 = cv2.VideoCapture(v2)
    if not cap1.isOpened() or not cap2.isOpened():
        print("[worker_impl] Не удалось открыть одно из видео!")
        return

    temp_dir = os.path.join(os.path.dirname(pdf_out), "temp_detailed")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.mkdir(temp_dir)

    c = canvas.Canvas(pdf_out, pagesize=A4)
    w_img, h_img = 180*mm, 100*mm
    x_img, y_img = 20, 300

    frame_idx = 0
    while True:
        r1,f1 = cap1.read()
        r2,f2 = cap2.read()
        if not (r1 and r2):
            break  # конец хотя бы одного из видео

        frame_time = frame_idx / fps
        diff = cv2.absdiff(f1, f2)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        thr = cv2.threshold(gray,30,255,cv2.THRESH_BINARY)[1]
        nz = cv2.countNonZero(thr)

        vis2 = f2.copy()
        if nz >= diff_threshold:
            cont,_ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c0 in cont:
                xx,yy,ww,hh = cv2.boundingRect(c0)
                cv2.rectangle(vis2,(xx,yy),(xx+ww,yy+hh),(0,0,255),2)

        side = np.concatenate((f1, vis2), axis=1)
        img_path = os.path.join(temp_dir, f"frame_{frame_idx}.png")
        cv2.imwrite(img_path, side)

        # Рисуем PDF-страницу
        if nz >= diff_threshold:
            c.setFillColor(red)
        else:
            c.setFillColor(black)

        text_line = f"Frame {frame_idx}, time={frame_time:.2f}s, diff_px={nz}"
        c.setFont("Helvetica",12)
        c.drawString(50,820, text_line)
        try:
            c.drawImage(img_path, x_img, y_img, width=w_img, height=h_img)
        except:
            pass

        c.showPage()
        frame_idx += 1

    cap1.release()
    cap2.release()
    c.save()
    print(f"[worker_impl] generate_detailed_diff_report => {pdf_out}")
