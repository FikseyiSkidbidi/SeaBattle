# main.py
import pygame
import sys
import random
import threading
import socket
import pickle
import time
from settings import *
from logic import Board

# --- НАСТРОЙКИ СЕТИ ---
BROADCAST_PORT = 50000  # Порт для поиска серверов
GAME_PORT = 50001       # Порт для самой игры
BUFFER_SIZE = 4096

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Морской Бой - LAN Browser")
font = pygame.font.SysFont("Arial", 20)
big_font = pygame.font.SysFont("Arial", 40)
input_font = pygame.font.SysFont("Consolas", 24)

# --- СЕТЕВАЯ ЧАСТЬ ---
network_events = []
game_conn = None       # TCP соединение для игры
discovery_server = None # UDP слушатель для хоста

class GameServerUDP(threading.Thread):
    """Отвечает на крики 'WHO_IS_HOSTING' в локальной сети"""
    def __init__(self, room_name):
        super().__init__(daemon=True)
        self.room_name = room_name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', BROADCAST_PORT))
        self.running = True

    def run(self):
        print(f"UDP Discovery запущен. Имя комнаты: {self.room_name}")
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                msg = data.decode('utf-8')
                if msg == "BATTLESHIP_DISCOVERY":
                    # Отвечаем: "Я_ТУТ:ИмяКомнаты"
                    response = f"BATTLESHIP_HERE:{self.room_name}"
                    self.sock.sendto(response.encode('utf-8'), addr)
            except Exception as e:
                pass

class GameServerTCP(threading.Thread):
    """Основной игровой сервер (принимает подключения)"""
    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('0.0.0.0', GAME_PORT))
        self.sock.listen(1)
        self.waiting = True

    def run(self):
        global game_conn
        print("TCP Сервер ждет игрока...")
        try:
            conn, addr = self.sock.accept()
            game_conn = ConnectionWrapper(conn)
            # Отправляем сигнал, что игра началась (мы ходим первыми)
            network_events.append({"type": "game_start", "turn": True})
            threading.Thread(target=receive_loop, args=(game_conn,), daemon=True).start()
        except Exception as e:
            print("Ошибка TCP сервера:", e)

class ConnectionWrapper:
    """Обертка для удобной отправки/получения объектов"""
    def __init__(self, sock):
        self.sock = sock
    
    def send(self, data):
        try:
            self.sock.sendall(pickle.dumps(data))
        except:
            pass

    def recv(self):
        try:
            return pickle.loads(self.sock.recv(BUFFER_SIZE))
        except:
            return None

def receive_loop(conn):
    """Слушает сообщения от соперника"""
    while True:
        try:
            data = conn.recv()
            if data:
                network_events.append(data)
            else:
                break
        except:
            break
    network_events.append({"type": "disconnect"})

def scan_lan_servers():
    """Отправляет широковещательный запрос и ждет 1 секунду ответов"""
    found_servers = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(1.0)
    
    try:
        # Кричим в сеть
        sock.sendto(b"BATTLESHIP_DISCOVERY", ('<broadcast>', BROADCAST_PORT))
        
        start_t = time.time()
        while time.time() - start_t < 1.0:
            try:
                data, addr = sock.recvfrom(1024)
                msg = data.decode('utf-8')
                if msg.startswith("BATTLESHIP_HERE:"):
                    name = msg.split(":", 1)[1]
                    # addr[0] - это IP ответившего
                    found_servers.append({'ip': addr[0], 'name': name})
            except socket.timeout:
                break
    except Exception as e:
        print("Ошибка сканирования:", e)
    finally:
        sock.close()
    
    return found_servers

def connect_to_ip(ip):
    global game_conn
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((ip, GAME_PORT))
        sock.settimeout(None)
        
        game_conn = ConnectionWrapper(sock)
        # Если подключились успешно, мы ходим вторыми
        network_events.append({"type": "game_start", "turn": False})
        threading.Thread(target=receive_loop, args=(game_conn,), daemon=True).start()
        return True
    except Exception as e:
        print("Не удалось подключиться:", e)
        return False

# --- ИГРОВЫЕ КЛАССЫ (UI) ---

class GameMode:
    MENU = 0
    VS_AI = 1
    HOTSEAT = 2
    # Онлайн режимы
    ONLINE_HUB = 3         # Выбор: Создать / Найти / Прямой IP
    CREATE_ROOM = 4        # Ввод имени комнаты
    SERVER_BROWSER = 5     # Список комнат в локалке
    DIRECT_CONNECT = 6     # Ввод IP (Hamachi)
    
    PLACEMENT_P1 = 10
    PLACEMENT_P2 = 11
    PLACEMENT_TRANSITION = 12
    RULES = 13
    ONLINE_WAITING = 14    # Хост ждет подключения
    ONLINE_PLAY = 15       # Сама игра

class Button:
    def __init__(self, x, y, w, h, text, color=GRAY, text_color=BLACK):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.text_color = text_color

    def draw(self, surf):
        pygame.draw.rect(surf, self.color, self.rect, border_radius=5)
        pygame.draw.rect(surf, BLACK, self.rect, 2, border_radius=5)
        draw_text(self.text, font, self.text_color, self.rect.centerx, self.rect.centery, center=True)

    def is_clicked(self, pos):
        return self.rect.collidepoint(pos)

# --- ГЛОБАЛЬНЫЕ UI ЭЛЕМЕНТЫ ---
# Кнопка "В меню"
menu_btn = Button(10, 10, 100, 30, "В меню")

# Поля ввода
input_room_name = "Моя игра"
input_ip_text = ""
servers_list = [] # Список найденных серверов [{'ip':..., 'name':...}]
scan_thread = None
is_scanning = False

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def draw_text(text, font_obj, color, x, y, center=False):
    img = font_obj.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    screen.blit(img, rect)

# Копируем классы анимации и кораблей из прошлого кода для экономии места
# (Они идентичны, но нужны для работы)
class Animation:
    def __init__(self, x, y, color):
        self.x, self.y, self.color = x, y, color
        self.radius, self.max_radius, self.alpha, self.done = 0, CELL_SIZE, 255, False
    def update(self):
        if self.radius < self.max_radius: self.radius += 2
        else:
            self.alpha -= 15
            if self.alpha <= 0: self.done = True
    def draw(self, surface):
        if not self.done:
            s = pygame.Surface((CELL_SIZE*2, CELL_SIZE*2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, max(0, self.alpha)), (CELL_SIZE, CELL_SIZE), int(self.radius))
            surface.blit(s, (self.x-CELL_SIZE, self.y-CELL_SIZE))

class ShipSprite:
    def __init__(self, size, x, y):
        self.size, self.x, self.y = size, x, y
        self.start_x, self.start_y = x, y
        self.horizontal, self.dragging, self.placed = True, False, False
        self.grid_x, self.grid_y = -1, -1
    def draw(self, surface):
        w = self.size * CELL_SIZE if self.horizontal else CELL_SIZE
        h = CELL_SIZE if self.horizontal else self.size * CELL_SIZE
        s_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(s_surf, GRAY, (0,0,w,h))
        pygame.draw.rect(s_surf, BLACK, (0,0,w,h), 2)
        if self.dragging:
            s_surf = pygame.transform.rotozoom(s_surf, 5, 1.1)
            rect = s_surf.get_rect(center=(self.x+w//2, self.y+h//2))
        else:
            rect = s_surf.get_rect(topleft=(self.x, self.y))
        surface.blit(s_surf, rect.topleft)

def init_ships():
    ships = []
    coords = [(450, 150), (450, 200), (570, 200), (450, 250), (540, 250), (630, 250), (450, 300), (510, 300), (570, 300), (630, 300)]
    for i, size in enumerate(SHIP_SIZES): ships.append(ShipSprite(size, *coords[i]))
    return ships

def draw_grid_simple(surface, board, ox, oy, hide=True):
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            r = pygame.Rect(ox + x*CELL_SIZE, oy + y*CELL_SIZE, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(surface, BLUE, r, 1)
            c = board.grid[y][x]
            if c==1 and not hide: pygame.draw.rect(surface, GRAY, r)
            elif c==2: pygame.draw.circle(surface, BLACK, r.center, 5)
            elif c==3: 
                pygame.draw.line(surface, RED, r.topleft, r.bottomright, 3)
                pygame.draw.line(surface, RED, r.bottomleft, r.topright, 3)
            elif c==4: pygame.draw.rect(surface, RED, r)

# --- MAIN ---

def main():
    global input_room_name, input_ip_text, is_scanning, servers_list, game_conn, discovery_server
    
    clock = pygame.time.Clock()
    mode = GameMode.MENU
    
    p1_board, p2_board = None, None
    turn, winner = 1, None
    animations, placement_ships = [], []
    dragging_ship = None
    next_mode_post_place = None
    online_my_turn = False
    online_waiting_shot = False

    # Кнопки для разных меню
    btn_create_ui = Button(WIDTH//2 - 100, 350, 200, 50, "Создать игру", GREEN)
    btn_refresh = Button(50, 500, 150, 40, "Обновить")
    btn_direct = Button(600, 500, 150, 40, "По IP (Hamachi)")
    btn_connect_direct = Button(WIDTH//2 - 100, 400, 200, 50, "Подключиться", GREEN)

    def reset_game_state():
        nonlocal p1_board, p2_board, winner, animations, online_my_turn, online_waiting_shot
        p1_board = None
        p2_board = None
        winner = None
        animations.clear()
        online_my_turn = False
        online_waiting_shot = False

    def full_reset():
        nonlocal mode
        global game_conn, discovery_server
        reset_game_state()
        if game_conn: 
            try: game_conn.sock.close() 
            except: pass
            game_conn = None
        if discovery_server:
            discovery_server.running = False
            discovery_server = None
        mode = GameMode.MENU

    def run_scan():
        global is_scanning, servers_list
        is_scanning = True
        servers_list = scan_lan_servers()
        is_scanning = False

    while True:
        # ОБРАБОТКА СЕТЕВЫХ СОБЫТИЙ
        while network_events:
            ev = network_events.pop(0)
            if ev['type'] == 'game_start':
                online_my_turn = ev['turn']
                p2_board = Board(random_placement=False) # Пустая доска врага
                mode = GameMode.ONLINE_PLAY
            elif ev['type'] == 'shoot':
                # Враг выстрелил
                hit = p1_board.shoot(ev['x'], ev['y'])
                animations.append(Animation(50 + ev['x']*CELL_SIZE + 15, 150 + ev['y']*CELL_SIZE + 15, RED if hit else BLUE))
                game_over = p1_board.is_game_over()
                game_conn.send({'type': 'result', 'x': ev['x'], 'y': ev['y'], 'hit': hit, 'go': game_over})
                if game_over: winner = "Противник"
                if not hit: online_my_turn = True
            elif ev['type'] == 'result':
                # Пришел результат нашего выстрела
                online_waiting_shot = False
                hit = ev['hit']
                p2_board.grid[ev['y']][ev['x']] = 3 if hit else 2
                animations.append(Animation(450 + ev['x']*CELL_SIZE + 15, 150 + ev['y']*CELL_SIZE + 15, RED if hit else BLUE))
                if ev['go']: winner = "Ты"
                if not hit: online_my_turn = False
            elif ev['type'] == 'disconnect':
                winner = "Враг вышел"

        # ОТРИСОВКА И ЛОГИКА
        screen.fill(WHITE)
        mouse_pos = pygame.mouse.get_pos()
        events = pygame.event.get()

        # Кнопка "В меню" всегда доступна, кроме активной игры (чтобы случайно не выйти)
        if mode != GameMode.MENU:
            menu_btn.draw(screen)

        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                if mode != GameMode.MENU and menu_btn.is_clicked(event.pos):
                    full_reset()
                    continue

        # --- МЕНЮ ---
        if mode == GameMode.MENU:
            draw_text("МОРСКОЙ БОЙ", big_font, DARK_BLUE, WIDTH//2, 100, center=True)
            
            # Кнопки меню
            btns = [
                ("Одиночная игра", 200, GameMode.PLACEMENT_P1, GameMode.VS_AI),
                ("Хот-сит (2 игрока)", 270, GameMode.PLACEMENT_P1, GameMode.HOTSEAT),
                ("Играть онлайн", 340, GameMode.ONLINE_HUB, None),
                ("Правила", 410, GameMode.RULES, None)
            ]
            
            for txt, y, m_next, m_sub in btns:
                rect = pygame.Rect(WIDTH//2 - 100, y, 200, 50)
                col = (220,220,220) if rect.collidepoint(mouse_pos) else GRAY
                pygame.draw.rect(screen, col, rect, border_radius=5)
                draw_text(txt, font, BLACK, rect.centerx, rect.centery, center=True)
                
                for e in events:
                    if e.type == pygame.MOUSEBUTTONDOWN and rect.collidepoint(e.pos):
                        mode = m_next
                        if m_next == GameMode.PLACEMENT_P1:
                            next_mode_post_place = m_sub
                            placement_ships = init_ships()
                            reset_game_state()

        # --- ОНЛАЙН ХАБ ---
        elif mode == GameMode.ONLINE_HUB:
            draw_text("СЕТЕВАЯ ИГРА", big_font, DARK_BLUE, WIDTH//2, 100, center=True)
            
            # 1. Создать комнату
            btn_create = Button(WIDTH//2 - 100, 200, 200, 50, "Создать комнату")
            btn_create.draw(screen)
            
            # 2. Найти сервера (LAN)
            btn_find = Button(WIDTH//2 - 100, 270, 200, 50, "Список серверов")
            btn_find.draw(screen)
            
            # 3. Подключиться по IP
            btn_ip = Button(WIDTH//2 - 100, 340, 200, 50, "Прямой IP (Hamachi)")
            btn_ip.draw(screen)

            for e in events:
                if e.type == pygame.MOUSEBUTTONDOWN:
                    if btn_create.is_clicked(e.pos):
                        mode = GameMode.CREATE_ROOM
                    elif btn_find.is_clicked(e.pos):
                        mode = GameMode.SERVER_BROWSER
                        threading.Thread(target=run_scan, daemon=True).start()
                    elif btn_ip.is_clicked(e.pos):
                        mode = GameMode.DIRECT_CONNECT

        # --- СОЗДАНИЕ КОМНАТЫ ---
        elif mode == GameMode.CREATE_ROOM:
            draw_text("СОЗДАНИЕ КОМНАТЫ", big_font, DARK_BLUE, WIDTH//2, 100, center=True)
            draw_text("Название комнаты:", font, BLACK, WIDTH//2, 200, center=True)
            
            # Поле ввода
            pygame.draw.rect(screen, BLACK, (WIDTH//2 - 150, 240, 300, 40), 2)
            draw_text(input_room_name + "|", input_font, BLACK, WIDTH//2 - 140, 250)
            
            btn_create_ui.draw(screen)
            
            for e in events:
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_BACKSPACE: input_room_name = input_room_name[:-1]
                    elif len(input_room_name) < 15: input_room_name += e.unicode
                if e.type == pygame.MOUSEBUTTONDOWN and btn_create_ui.is_clicked(e.pos) and len(input_room_name) > 0:
                    # Запускаем создание
                    mode = GameMode.PLACEMENT_P1
                    next_mode_post_place = GameMode.ONLINE_WAITING
                    placement_ships = init_ships()
                    
        # --- СПИСОК СЕРВЕРОВ (LAN) ---
        elif mode == GameMode.SERVER_BROWSER:
            draw_text("ПОИСК ИГР (LAN)", big_font, DARK_BLUE, WIDTH//2, 60, center=True)
            
            # Список кнопок-серверов
            start_y = 120
            if is_scanning:
                draw_text("Сканирование...", font, RED, WIDTH//2, 200, center=True)
            elif not servers_list:
                draw_text("Комнаты не найдены", font, GRAY, WIDTH//2, 200, center=True)
            else:
                for i, srv in enumerate(servers_list):
                    rect = pygame.Rect(100, start_y + i*60, 600, 50)
                    col = (200, 255, 200) if rect.collidepoint(mouse_pos) else WHITE
                    pygame.draw.rect(screen, col, rect, border_radius=5)
                    pygame.draw.rect(screen, BLACK, rect, 2, border_radius=5)
                    
                    name_txt = f"{srv['name']}"
                    ip_txt = f"IP: {srv['ip']}"
                    draw_text(name_txt, font, BLACK, 120, rect.y + 15)
                    draw_text(ip_txt, font, GRAY, 500, rect.y + 15)
                    
                    for e in events:
                        if e.type == pygame.MOUSEBUTTONDOWN and rect.collidepoint(e.pos):
                            # Подключение!
                            mode = GameMode.PLACEMENT_P1
                            next_mode_post_place = GameMode.ONLINE_PLAY
                            placement_ships = init_ships()
                            # Сохраняем IP куда коннектиться
                            input_ip_text = srv['ip'] 

            btn_refresh.draw(screen)
            btn_direct.draw(screen) # Переход к ручному вводу отсюда тоже удобен

            for e in events:
                if e.type == pygame.MOUSEBUTTONDOWN:
                    if btn_refresh.is_clicked(e.pos) and not is_scanning:
                        threading.Thread(target=run_scan, daemon=True).start()
                    elif btn_direct.is_clicked(e.pos):
                        mode = GameMode.DIRECT_CONNECT

        # --- ПРЯМОЕ ПОДКЛЮЧЕНИЕ (HAMACHI) ---
        elif mode == GameMode.DIRECT_CONNECT:
            draw_text("ПРЯМОЕ ПОДКЛЮЧЕНИЕ", big_font, DARK_BLUE, WIDTH//2, 80, center=True)
            
            # Инструкция
            info = [
                "Используйте это для игры через VPN (Radmin/Hamachi).",
                "1. Хост создает комнату как обычно.",
                "2. Хост копирует свой IP в программе VPN.",
                "3. Вы вставляете этот IP ниже."
            ]
            for i, line in enumerate(info):
                draw_text(line, font, GRAY, WIDTH//2, 140 + i*25, center=True)
                
            draw_text("IP Адрес хоста:", font, BLACK, WIDTH//2, 260, center=True)
            pygame.draw.rect(screen, BLACK, (WIDTH//2 - 150, 300, 300, 40), 2)
            draw_text(input_ip_text + "_", input_font, BLACK, WIDTH//2 - 140, 310)
            
            btn_connect_direct.draw(screen)
            
            for e in events:
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_BACKSPACE: input_ip_text = input_ip_text[:-1]
                    else: input_ip_text += e.unicode
                if e.type == pygame.MOUSEBUTTONDOWN and btn_connect_direct.is_clicked(e.pos):
                    if len(input_ip_text) > 5:
                        mode = GameMode.PLACEMENT_P1
                        next_mode_post_place = GameMode.ONLINE_PLAY
                        placement_ships = init_ships()

        # --- РАССТАНОВКА КОРАБЛЕЙ (Код почти без изменений) ---
        elif mode == GameMode.PLACEMENT_P1:
            draw_text("Расстановка флота", big_font, DARK_BLUE, WIDTH//2, 50, center=True)
            draw_text("ЛКМ - тащить, ПКМ - крутить", font, GRAY, WIDTH//2, 90, center=True)
            draw_grid_simple(screen, Board(False), 50, 150, False)
            
            ready_rect = pygame.Rect(450, 400, 200, 50)
            col = GREEN if all(s.placed for s in placement_ships) else GRAY
            pygame.draw.rect(screen, col, ready_rect, border_radius=5)
            draw_text("В БОЙ!", font, WHITE, ready_rect.centerx, ready_rect.centery, center=True)
            
            for s in placement_ships: s.draw(screen)
            
            for e in events:
                if e.type == pygame.MOUSEBUTTONDOWN:
                    if e.button == 1:
                        if ready_rect.collidepoint(e.pos) and all(s.placed for s in placement_ships):
                            p1_board = Board(False)
                            for s in placement_ships: p1_board.add_ship(s.grid_x, s.grid_y, s.size, s.horizontal)
                            
                            # ЛОГИКА ПЕРЕХОДА ПОСЛЕ РАССТАНОВКИ
                            if next_mode_post_place == GameMode.VS_AI:
                                p2_board = Board(True)
                                mode = GameMode.VS_AI
                            elif next_mode_post_place == GameMode.HOTSEAT:
                                p2_board = Board(False); mode = GameMode.PLACEMENT_TRANSITION
                            elif next_mode_post_place == GameMode.ONLINE_WAITING:
                                # Мы ХОСТ. Запускаем сервер.
                                discovery_server = GameServerUDP(input_room_name)
                                discovery_server.start()
                                tcp_srv = GameServerTCP()
                                tcp_srv.start()
                                mode = GameMode.ONLINE_WAITING
                            elif next_mode_post_place == GameMode.ONLINE_PLAY:
                                # Мы КЛИЕНТ. Пытаемся подключиться к input_ip_text
                                if connect_to_ip(input_ip_text):
                                    mode = GameMode.ONLINE_PLAY
                                else:
                                    print("Ошибка подключения")
                                    mode = GameMode.ONLINE_HUB
                            continue
                        
                        # Dragging logic
                        for s in reversed(placement_ships):
                            r = pygame.Rect(s.x, s.y, s.size*CELL_SIZE if s.horizontal else CELL_SIZE, CELL_SIZE if s.horizontal else s.size*CELL_SIZE)
                            if r.collidepoint(e.pos):
                                s.dragging = True; dragging_ship = s; s.placed = False
                                placement_ships.remove(s); placement_ships.append(s)
                                break
                    elif e.button == 3 and dragging_ship: dragging_ship.horizontal = not dragging_ship.horizontal

                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and dragging_ship:
                    dragging_ship.dragging = False
                    gx, gy = round((e.pos[0]-dragging_ship.size*15-50)/30), round((e.pos[1]-15-150)/30) # Приблизительно
                    # Более точный расчет координат сброса
                    w = dragging_ship.size * CELL_SIZE if dragging_ship.horizontal else CELL_SIZE
                    h = CELL_SIZE if dragging_ship.horizontal else dragging_ship.size * CELL_SIZE
                    gx = round((e.pos[0] - w//2 - 50) / CELL_SIZE)
                    gy = round((e.pos[1] - h//2 - 150) / CELL_SIZE)

                    temp_b = Board(False)
                    for s in placement_ships: 
                        if s.placed and s!=dragging_ship: temp_b.add_ship(s.grid_x, s.grid_y, s.size, s.horizontal)
                    
                    if temp_b.can_place_ship(gx, gy, dragging_ship.size, dragging_ship.horizontal):
                        dragging_ship.placed = True; dragging_ship.grid_x = gx; dragging_ship.grid_y = gy
                        dragging_ship.x = 50 + gx*CELL_SIZE; dragging_ship.y = 150 + gy*CELL_SIZE
                    else:
                        dragging_ship.x, dragging_ship.y, dragging_ship.horizontal = dragging_ship.start_x, dragging_ship.start_y, True
                    dragging_ship = None
                
                elif e.type == pygame.MOUSEMOTION and dragging_ship:
                    dragging_ship.x = e.pos[0] - (dragging_ship.size*CELL_SIZE if dragging_ship.horizontal else CELL_SIZE)//2
                    dragging_ship.y = e.pos[1] - (CELL_SIZE if dragging_ship.horizontal else dragging_ship.size*CELL_SIZE)//2

        # --- ОЖИДАНИЕ ИГРОКА (ХОСТ) ---
        elif mode == GameMode.ONLINE_WAITING:
            draw_text("ОЖИДАНИЕ СОПЕРНИКА...", big_font, DARK_BLUE, WIDTH//2, 200, center=True)
            draw_text(f"Комната: {input_room_name}", font, BLACK, WIDTH//2, 250, center=True)
            
            # Анимация точек
            dots = "." * ((pygame.time.get_ticks() // 500) % 4)
            draw_text(dots, big_font, BLACK, WIDTH//2, 300, center=True)
            
            # Проверка, подключился ли кто-то (через events от TCP потока)
            # Переход произойдет автоматически в блоке обработки network_events

        # --- ОНЛАЙН ИГРА ---
        elif mode == GameMode.ONLINE_PLAY:
            draw_text("Твой флот", font, BLACK, 50, 100)
            draw_text("Враг", font, BLACK, 450, 100)
            draw_grid_simple(screen, p1_board, 50, 150, False)
            draw_grid_simple(screen, p2_board, 450, 150, True) # Скрываем корабли врага

            # Статус
            if winner:
                col = GREEN if winner == "Ты" else RED
                draw_text(f"ПОБЕДА: {winner}!", big_font, col, WIDTH//2, 50, center=True)
            else:
                if online_my_turn:
                    draw_text("ТВОЙ ХОД", big_font, GREEN, WIDTH//2, 50, center=True)
                else:
                    draw_text("ХОД ВРАГА", big_font, RED, WIDTH//2, 50, center=True)

            # Стрельба
            for e in events:
                if e.type == pygame.MOUSEBUTTONDOWN and online_my_turn and not winner and not online_waiting_shot:
                    mx, my = e.pos
                    if 450 <= mx < 750 and 150 <= my < 450:
                        gx, gy = (mx - 450)//CELL_SIZE, (my - 150)//CELL_SIZE
                        if p2_board.grid[gy][gx] == 0: # Если еще не стреляли
                            online_waiting_shot = True
                            game_conn.send({'type': 'shoot', 'x': gx, 'y': gy})

        # --- ОТРИСОВКА АНИМАЦИЙ ---
        for a in animations[:]:
            a.update()
            a.draw(screen)
            if a.done: animations.remove(a)

        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    main()