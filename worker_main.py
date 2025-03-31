# file: worker_main.py
import worker_impl

def worker_main(cmd_queue, result_queue):
    def log(msg):
        result_queue.put(("log", msg))

    region_logical = None
    region_physical = None
    session_folder = None
    actions = []

    recording = False
    first_record_done = False

    log("[worker_main] старт.")

    while True:
        cmd = cmd_queue.get()
        if not cmd:
            continue
        name, params = cmd

        if name == "shutdown":
            log("[worker_main] получен shutdown => выходим")
            break

        elif name == "toggle_record":
            # берём нужные параметры
            MONITOR_W = params.get("MONITOR_W", 1470)
            MONITOR_H = params.get("MONITOR_H", 956)
            scale_factor = params.get("scale_factor", 1.0)

            if not recording:
                # НАЧАТЬ
                sel = worker_impl.select_screen_region_logical(result_queue)
                if not sel:
                    log("[worker_main] Область не выбрана => отмена")
                    continue
                region_logical = sel
                region_physical = worker_impl.to_physical_coords(region_logical, scale_factor)
                session_folder = worker_impl.create_session_folder()
                actions.clear()

                worker_impl.start_listeners(
                    actions,
                    region_logical,
                    region_physical,
                    session_folder,
                    MONITOR_W,
                    MONITOR_H,
                    result_queue
                )
                log("Ожидание первого клика => capture_1.mp4")
                recording = True
            else:
                # ОСТАНОВИТЬ
                worker_impl.stop_listeners()
                first_record_done = True
                recording = False
                log("Первая запись завершена.")

        elif name == "replay_and_compare":
            MONITOR_W = params.get("MONITOR_W", 1470)
            MONITOR_H = params.get("MONITOR_H", 956)
            scale_factor = params.get("scale_factor", 1.0)
            timeline_enabled = params.get("timeline", False)

            if not first_record_done:
                log("Сначала завершите первую запись!")
                continue

            if not region_logical or not region_physical or not session_folder:
                log("[worker_main] Ошибка: нет сохранённых region_..., значит не было первой записи?")
                continue

            log("[worker_main] Запускаем второй слушатель => capture_2 => replay => compare => PDF")
            worker_impl.start_second_click_listener(
                actions,
                region_logical,
                region_physical,
                session_folder,
                MONITOR_W,
                MONITOR_H,
                timeline_enabled,
                result_queue
            )

        else:
            log(f"[worker_main] неизвестная команда: {name}")
