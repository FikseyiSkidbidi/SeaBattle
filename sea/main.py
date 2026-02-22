# main.py
import pygame
import sys
import random
import threading
from multiprocessing.connection import Listener, Client
from settings import *
from logic import Board

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Морской Бой - LAN/VPN")
font = pygame.font.SysFont("Arial", 24)
big_font = pygame.font.SysFont("Arial", 48)

# --- СЕТЕВАЯ ЧАСТЬ (P2P / LAN) ---
network_events = []
game_client = None
game_server = None

class GameServer(threading.Thread):
    def __init__(self, port=25565):
        super().__init__(daemon=True)
        self.port = port
        self.listener = None
        self.clients = {} 
        self.waiting = None

    def run(self):
        self.listener = Listener(('0.0.0.0', self.port), authkey=b'battleship')
        print(f"Локальный сервер запущен на порту {self.port}...")
        while True:
            try:
                conn = self.listener.accept()
                threading.Thread(target=self.handle_client, args=(conn,), daemon=True).start()
            except Exception as e:
                print("Сервер остановлен:", e)
                break

    def handle_client(self, conn):
        # Логика комнат: связываем игроков парами
        if self.waiting is None:
            self.waiting = conn
            try:
                conn.send({"type": "waiting"})
            except:
                self.waiting = None
                return
        else:
            pair = self.waiting
            self.waiting = None
            self.clients[conn] = pair
            self.clients[pair] = conn
            try:
                pair.send({"type": "game_start", "turn": True})
                conn.send({"type": "game_start", "turn": False})
            except:
                pass

        # Пересылка сообщений между напарниками
        while True:
            try:
                msg = conn.recv()
                pair = self.clients.get(conn)
                if pair:
                    pair.send(msg)
            except EOFError:
                pair = self.clients.get(conn)
                if pair:
                    try:
                        pair.send({"type": "opponent_disconnected"})
                    except:
                        pass
                break

class GameClient(threading.Thread):
    def __init__(self, ip, port=25565):
        super().__init__(daemon=True)
        self.ip = ip
        self.port = port
        self.conn = None
        self.error = False

    def run(self):
        try:
            self.conn = Client((self.ip, self.port), authkey=b'battleship')
            while True:
                msg = self.conn.recv()
                network_events.append(msg)
        except Exception as e:
            print("Ошибка клиента:", e)
            self.error = True
            network_events.append({"type": "connection_error"})

    def send(self, msg):
        if self.conn:
            try:
                self.conn.send(msg)
            except Exception as e:
                print("Ошибка отправки:", e)

# --- ИГРОВЫЕ КЛАССЫ ---

class GameMode:
    MENU = 0
    VS_AI = 1
    HOTSEAT = 2
    ONLINE_MENU = 3
    ONLINE_INPUT_IP = 4
    PLACEMENT_P1 = 5
    PLACEMENT_P2 = 6
    PLACEMENT_TRANSITION = 7
    RULES = 8
    ONLINE_MATCHMAKING = 9
    ONLINE_PLAY = 10

class HotseatState:
    P1_TURN = 0
    TRANSITION_TO_P2 = 1
    P2_TURN = 2
    TRANSITION_TO_P1 = 3
    GAME_OVER = 4

class Animation:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.radius = 0
        self.max_radius = CELL_SIZE
        self.color = color
        self.alpha = 255
        self.done = False

    def update(self):
        if self.radius < self.max_radius:
            self.radius += 2
        else:
            self.alpha -= 15
            if self.alpha <= 0:
                self.done = True

    def draw(self, surface):
        if not self.done:
            s = pygame.Surface((CELL_SIZE * 2, CELL_SIZE * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, max(0, self.alpha)), (CELL_SIZE, CELL_SIZE), int(self.radius))
            surface.blit(s, (self.x - CELL_SIZE, self.y - CELL_SIZE))

class ShipSprite:
    def __init__(self, size, x, y):
        self.size = size
        self.start_x = x
        self.start_y = y
        self.x = x
        self.y = y
        self.horizontal = True
        self.dragging = False
        self.placed = False
        self.grid_x = -1
        self.grid_y = -1

    def draw(self, surface):
        w = self.size * CELL_SIZE if self.horizontal else CELL_SIZE
        h = CELL_SIZE if self.horizontal else self.size * CELL_SIZE
        
        ship_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(ship_surf, GRAY, (0, 0, w, h))
        pygame.draw.rect(ship_surf, BLACK, (0, 0, w, h), 2)

        if self.dragging:
            ship_surf = pygame.transform.rotozoom(ship_surf, 5, 1.1)
            rect = ship_surf.get_rect(center=(self.x + w//2, self.y + h//2))
        else:
            rect = ship_surf.get_rect(topleft=(self.x, self.y))
            
        surface.blit(ship_surf, rect.topleft)

def init_placement_ships():
    ships = []
    coords = [
        (450, 150), 
        (450, 200), (570, 200), 
        (450, 250), (540, 250), (630, 250), 
        (450, 300), (510, 300), (570, 300), (630, 300)
    ]
    for i, size in enumerate(SHIP_SIZES):
        ships.append(ShipSprite(size, coords[i][0], coords[i][1]))
    return ships

def build_board_from_sprites(sprites):
    board = Board(random_placement=False)
    for s in sprites:
        board.add_ship(s.grid_x, s.grid_y, s.size, s.horizontal)
    return board

def draw_grid(surface, board, offset_x, offset_y, hide_ships=True):
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            rect = pygame.Rect(offset_x + x * CELL_SIZE, offset_y + y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(surface, BLUE, rect, 1)
            
            cell = board.grid[y][x]
            if cell == 1 and not hide_ships:
                pygame.draw.rect(surface, GRAY, rect)
            elif cell == 2:
                pygame.draw.circle(surface, BLACK, rect.center, 5)
            elif cell == 3:
                pygame.draw.line(surface, RED, rect.topleft, rect.bottomright, 3)
                pygame.draw.line(surface, RED, rect.bottomleft, rect.topright, 3)
            elif cell == 4:
                pygame.draw.rect(surface, RED, rect)

def draw_text(text, font, color, x, y, center=False):
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    screen.blit(img, rect)

def main():
    global game_client, game_server, network_events
    
    clock = pygame.time.Clock()
    mode = GameMode.MENU
    
    p1_board = None
    p2_board = None
    
    turn = 1
    hs_state = HotseatState.P1_TURN
    winner = None

    animations = []
    wait_until = 0
    next_action = None
    
    # UI элементы
    menu_btn_rect = pygame.Rect(10, 10, 120, 40)
    ready_btn_rect = pygame.Rect(450, 400, 200, 50)
    
    placement_ships = []
    dragging_ship = None
    next_mode_after_placement = None
    
    # Онлайн переменные
    input_ip_text = ""
    online_role = None # 'host' или 'client'
    target_ip = ""
    online_state = {
        "status": "disconnected", 
        "my_turn": False, 
        "waiting_for_server": False
    }

    def reset_online():
        nonlocal online_state, input_ip_text, online_role
        global game_client, network_events
        network_events.clear()
        if game_client:
            game_client.conn = None # Отключаем старый клиент
            game_client = None
        online_state = {"status": "disconnected", "my_turn": False, "waiting_for_server": False}
        input_ip_text = ""
        online_role = None

    def add_anim(gx, gy, offset_x, offset_y, is_hit):
        px = offset_x + gx * CELL_SIZE + CELL_SIZE // 2
        py = offset_y + gy * CELL_SIZE + CELL_SIZE // 2
        color = RED if is_hit else (0, 150, 255)
        animations.append(Animation(px, py, color))

    running = True
    while running:
        current_time = pygame.time.get_ticks()
        input_blocked = (current_time < wait_until) or (next_action is not None)
        mouse_pos = pygame.mouse.get_pos()
        
        screen.fill(WHITE)
        
        for anim in animations[:]:
            anim.update()
            if anim.done:
                animations.remove(anim)

        # Обработка сетевых событий
        while network_events:
            event = network_events.pop(0)
            msg_type = event.get("type")

            if mode == GameMode.ONLINE_MATCHMAKING:
                if msg_type == "waiting":
                    online_state["status"] = "waiting"
                elif msg_type == "game_start":
                    online_state["status"] = "playing"
                    online_state["my_turn"] = event['turn']
                    mode = GameMode.ONLINE_PLAY
                elif msg_type == "connection_error":
                    mode = GameMode.ONLINE_MENU
                    reset_online()

            elif mode == GameMode.ONLINE_PLAY:
                if msg_type == "shoot":
                    ex, ey = event['x'], event['y']
                    hit = p1_board.shoot(ex, ey)
                    add_anim(ex, ey, 50, 150, hit)
                    is_over = p1_board.is_game_over()
                    if is_over:
                        winner = "Противник"
                    game_client.send({'type': 'shot_result', 'x': ex, 'y': ey, 'hit': hit, 'game_over': is_over})
                    if not hit:
                        online_state["my_turn"] = True

                elif msg_type == "shot_result":
                    online_state["waiting_for_server"] = False
                    rx, ry = event['x'], event['y']
                    hit = event['hit']
                    add_anim(rx, ry, 450, 150, hit)
                    
                    if hit:
                        p2_board.grid[ry][rx] = 3
                    else:
                        p2_board.grid[ry][rx] = 2
                        online_state["my_turn"] = False
                        
                    if event.get('game_over'):
                        winner = "Ты"
                        
                elif msg_type == "opponent_disconnected":
                    winner = "Противник сдался (отключился)"

        # Отложенные действия для ИИ
        if current_time >= wait_until and next_action:
            action = next_action
            next_action = None 
            
            if action == "to_p2":
                hs_state = HotseatState.TRANSITION_TO_P2
            elif action == "to_p1":
                hs_state = HotseatState.TRANSITION_TO_P1
            elif action == "ai_turn_start":
                turn = 2
                wait_until = current_time + 600 
                next_action = "ai_shoot"
            elif action == "ai_shoot":
                valid_shot = False
                while not valid_shot:
                    x, y = random.randint(0, 9), random.randint(0, 9)
                    hit = p1_board.shoot(x, y)
                    if hit is not None:
                        valid_shot = True
                        add_anim(x, y, 50, 150, hit) 
                        if p1_board.is_game_over():
                            winner = "ИИ"
                        elif hit:
                            wait_until = current_time + 1000
                            next_action = "ai_shoot" 
                        else:
                            wait_until = current_time + 1000
                            next_action = "player_turn" 
            elif action == "player_turn":
                turn = 1

        # Обработка ввода
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            # Глобальная кнопка "В меню"
            if mode != GameMode.MENU:
                is_transition = (mode == GameMode.HOTSEAT and hs_state in [HotseatState.TRANSITION_TO_P1, HotseatState.TRANSITION_TO_P2]) or (mode == GameMode.PLACEMENT_TRANSITION)
                if not is_transition and event.type == pygame.MOUSEBUTTONDOWN and not input_blocked:
                    if menu_btn_rect.collidepoint(event.pos):
                        reset_online()
                        mode = GameMode.MENU
                        next_action = None 
                        dragging_ship = None
                        continue 

            if mode == GameMode.MENU:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    x, y = event.pos
                    if 300 < x < 500:
                        if 200 < y < 250:
                            mode = GameMode.PLACEMENT_P1
                            next_mode_after_placement = GameMode.VS_AI
                            placement_ships = init_placement_ships()
                            winner, turn, next_action = None, 1, None
                            animations.clear()
                        elif 300 < y < 350:
                            mode = GameMode.PLACEMENT_P1
                            next_mode_after_placement = GameMode.HOTSEAT
                            placement_ships = init_placement_ships()
                            hs_state, winner, next_action = HotseatState.P1_TURN, None, None
                            animations.clear()
                        elif 400 < y < 450:
                            mode = GameMode.ONLINE_MENU
                            reset_online()
                        elif 500 < y < 550:
                            mode = GameMode.RULES

            elif mode == GameMode.ONLINE_MENU:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    x, y = event.pos
                    if 300 < x < 500:
                        if 250 < y < 300: # Хост
                            online_role = 'host'
                            target_ip = '127.0.0.1'
                            mode = GameMode.PLACEMENT_P1
                            next_mode_after_placement = GameMode.ONLINE_MATCHMAKING
                            placement_ships = init_placement_ships()
                            winner, animations.clear()
                        elif 350 < y < 400: # Подключиться
                            mode = GameMode.ONLINE_INPUT_IP

            elif mode == GameMode.ONLINE_INPUT_IP:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN and len(input_ip_text) > 0:
                        online_role = 'client'
                        target_ip = input_ip_text
                        mode = GameMode.PLACEMENT_P1
                        next_mode_after_placement = GameMode.ONLINE_MATCHMAKING
                        placement_ships = init_placement_ships()
                        winner, animations.clear()
                    elif event.key == pygame.K_BACKSPACE:
                        input_ip_text = input_ip_text[:-1]
                    else:
                        if len(input_ip_text) < 15 and event.unicode in "0123456789.":
                            input_ip_text += event.unicode

            elif mode == GameMode.ONLINE_PLAY:
                if event.type == pygame.MOUSEBUTTONDOWN and winner is None:
                    if online_state["my_turn"] and not online_state["waiting_for_server"]:
                        x, y = event.pos
                        if 450 <= x < 450 + GRID_SIZE * CELL_SIZE and 150 <= y < 150 + GRID_SIZE * CELL_SIZE:
                            gx, gy = (x - 450) // CELL_SIZE, (y - 150) // CELL_SIZE
                            if p2_board.grid[gy][gx] == 0:
                                online_state["waiting_for_server"] = True
                                game_client.send({'type': 'shoot', 'x': gx, 'y': gy})

            elif mode in [GameMode.PLACEMENT_P1, GameMode.PLACEMENT_P2]:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if ready_btn_rect.collidepoint(event.pos) and all(s.placed for s in placement_ships):
                            if mode == GameMode.PLACEMENT_P1:
                                p1_board = build_board_from_sprites(placement_ships)
                                if next_mode_after_placement == GameMode.VS_AI:
                                    p2_board = Board(random_placement=True)
                                    mode = GameMode.VS_AI
                                elif next_mode_after_placement == GameMode.ONLINE_MATCHMAKING:
                                    p2_board = Board(random_placement=False)
                                    mode = GameMode.ONLINE_MATCHMAKING
                                    
                                    # Запуск сети после расстановки кораблей
                                    if online_role == 'host':
                                        if game_server is None or not game_server.is_alive():
                                            game_server = GameServer()
                                            game_server.start()
                                    
                                    game_client = GameClient(target_ip)
                                    game_client.start()
                                else:
                                    mode = GameMode.PLACEMENT_TRANSITION
                            elif mode == GameMode.PLACEMENT_P2:
                                p2_board = build_board_from_sprites(placement_ships)
                                mode = GameMode.HOTSEAT
                                hs_state = HotseatState.TRANSITION_TO_P1
                            continue

                        # Захват корабля
                        for ship in reversed(placement_ships):
                            w = ship.size * CELL_SIZE if ship.horizontal else CELL_SIZE
                            h = CELL_SIZE if ship.horizontal else ship.size * CELL_SIZE
                            rect = pygame.Rect(ship.x, ship.y, w, h)
                            if rect.collidepoint(event.pos):
                                ship.dragging = True
                                dragging_ship = ship
                                ship.placed = False
                                placement_ships.remove(ship)
                                placement_ships.append(ship)
                                break
                                
                    elif event.button == 3: # ПКМ - Поворот
                        if dragging_ship:
                            dragging_ship.horizontal = not dragging_ship.horizontal

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1 and dragging_ship:
                        dragging_ship.dragging = False
                        w = dragging_ship.size * CELL_SIZE if dragging_ship.horizontal else CELL_SIZE
                        h = CELL_SIZE if dragging_ship.horizontal else dragging_ship.size * CELL_SIZE
                        
                        center_x, center_y = event.pos
                        drop_x = center_x - w//2
                        drop_y = center_y - h//2
                        
                        gx = round((drop_x - 50) / CELL_SIZE)
                        gy = round((drop_y - 150) / CELL_SIZE)
                        
                        if 0 <= gx <= GRID_SIZE - (dragging_ship.size if dragging_ship.horizontal else 1) and \
                           0 <= gy <= GRID_SIZE - (1 if dragging_ship.horizontal else dragging_ship.size):
                            
                            temp_board = Board(random_placement=False)
                            for s in placement_ships:
                                if s.placed and s != dragging_ship:
                                    temp_board.add_ship(s.grid_x, s.grid_y, s.size, s.horizontal)
                                    
                            if temp_board.can_place_ship(gx, gy, dragging_ship.size, dragging_ship.horizontal):
                                dragging_ship.placed = True
                                dragging_ship.grid_x = gx
                                dragging_ship.grid_y = gy
                                dragging_ship.x = 50 + gx * CELL_SIZE
                                dragging_ship.y = 150 + gy * CELL_SIZE
                            else:
                                dragging_ship.x, dragging_ship.y = dragging_ship.start_x, dragging_ship.start_y
                                dragging_ship.horizontal = True
                        else:
                            dragging_ship.x, dragging_ship.y = dragging_ship.start_x, dragging_ship.start_y
                            dragging_ship.horizontal = True
                        
                        dragging_ship = None
                        
                elif event.type == pygame.MOUSEMOTION:
                    if dragging_ship:
                        w = dragging_ship.size * CELL_SIZE if dragging_ship.horizontal else CELL_SIZE
                        h = CELL_SIZE if dragging_ship.horizontal else dragging_ship.size * CELL_SIZE
                        dragging_ship.x = event.pos[0] - w//2
                        dragging_ship.y = event.pos[1] - h//2

            elif mode == GameMode.VS_AI:
                if event.type == pygame.MOUSEBUTTONDOWN and turn == 1 and winner is None and not input_blocked:
                    x, y = event.pos
                    if 450 <= x < 450 + GRID_SIZE * CELL_SIZE and 150 <= y < 150 + GRID_SIZE * CELL_SIZE:
                        grid_x, grid_y = (x - 450) // CELL_SIZE, (y - 150) // CELL_SIZE
                        hit = p2_board.shoot(grid_x, grid_y)
                        if hit is not None:
                            add_anim(grid_x, grid_y, 450, 150, hit)
                            if p2_board.is_game_over(): 
                                winner = "Игрок 1"
                            elif not hit: 
                                wait_until = current_time + 800
                                next_action = "ai_turn_start" 
                            else:
                                wait_until = current_time + 400

            elif mode == GameMode.HOTSEAT:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    if hs_state == HotseatState.TRANSITION_TO_P2:
                        hs_state, turn = HotseatState.P2_TURN, 2
                    elif hs_state == HotseatState.TRANSITION_TO_P1:
                        hs_state, turn = HotseatState.P1_TURN, 1

                if event.type == pygame.MOUSEBUTTONDOWN and winner is None and not input_blocked:
                    x, y = event.pos
                    if hs_state == HotseatState.P1_TURN:
                        if 450 <= x < 450 + GRID_SIZE * CELL_SIZE and 150 <= y < 150 + GRID_SIZE * CELL_SIZE:
                            gx, gy = (x - 450) // CELL_SIZE, (y - 150) // CELL_SIZE
                            hit = p2_board.shoot(gx, gy)
                            if hit is not None:
                                add_anim(gx, gy, 450, 150, hit)
                                if p2_board.is_game_over(): 
                                    winner, hs_state = "Игрок 1", HotseatState.GAME_OVER
                                elif not hit: 
                                    wait_until, next_action = current_time + 1000, "to_p2"
                                else:
                                    wait_until = current_time + 400

                    elif hs_state == HotseatState.P2_TURN:
                        if 50 <= x < 50 + GRID_SIZE * CELL_SIZE and 150 <= y < 150 + GRID_SIZE * CELL_SIZE:
                            gx, gy = (x - 50) // CELL_SIZE, (y - 150) // CELL_SIZE
                            hit = p1_board.shoot(gx, gy)
                            if hit is not None:
                                add_anim(gx, gy, 50, 150, hit) 
                                if p1_board.is_game_over(): 
                                    winner, hs_state = "Игрок 2", HotseatState.GAME_OVER
                                elif not hit: 
                                    wait_until, next_action = current_time + 1000, "to_p1"
                                else:
                                    wait_until = current_time + 400

        # --- Отрисовка ---
        if mode == GameMode.MENU:
            draw_text("МОРСКОЙ БОЙ", big_font, DARK_BLUE, WIDTH//2, 100, center=True)
            
            c1 = (200, 200, 200) if 300 < mouse_pos[0] < 500 and 200 < mouse_pos[1] < 250 else GRAY
            pygame.draw.rect(screen, c1, (300, 200, 200, 50), border_radius=5)
            draw_text("Против ИИ", font, BLACK, 400, 225, center=True)
            
            c2 = (200, 200, 200) if 300 < mouse_pos[0] < 500 and 300 < mouse_pos[1] < 350 else GRAY
            pygame.draw.rect(screen, c2, (300, 300, 200, 50), border_radius=5)
            draw_text("2 Игрока (Один ПК)", font, BLACK, 400, 325, center=True)
            
            c3 = (200, 200, 200) if 300 < mouse_pos[0] < 500 and 400 < mouse_pos[1] < 450 else GRAY
            pygame.draw.rect(screen, c3, (300, 400, 200, 50), border_radius=5)
            draw_text("Онлайн (LAN/VPN)", font, BLACK, 400, 425, center=True)

            c4 = (200, 200, 200) if 300 < mouse_pos[0] < 500 and 500 < mouse_pos[1] < 550 else GRAY
            pygame.draw.rect(screen, c4, (300, 500, 200, 50), border_radius=5)
            draw_text("Правила", font, BLACK, 400, 525, center=True)

        elif mode == GameMode.ONLINE_MENU:
            draw_text("МУЛЬТИПЛЕЕР", big_font, DARK_BLUE, WIDTH//2, 100, center=True)
            
            c_host = (200, 200, 200) if 300 < mouse_pos[0] < 500 and 250 < mouse_pos[1] < 300 else GRAY
            pygame.draw.rect(screen, c_host, (300, 250, 200, 50), border_radius=5)
            draw_text("Создать комнату", font, BLACK, 400, 275, center=True)
            
            c_join = (200, 200, 200) if 300 < mouse_pos[0] < 500 and 350 < mouse_pos[1] < 400 else GRAY
            pygame.draw.rect(screen, c_join, (300, 350, 200, 50), border_radius=5)
            draw_text("Подключиться", font, BLACK, 400, 375, center=True)

        elif mode == GameMode.ONLINE_INPUT_IP:
            draw_text("ПОДКЛЮЧЕНИЕ", big_font, DARK_BLUE, WIDTH//2, 150, center=True)
            draw_text("Введите IP-адрес хоста:", font, BLACK, WIDTH//2, 230, center=True)
            
            pygame.draw.rect(screen, GRAY, (250, 280, 300, 40), 2)
            draw_text(input_ip_text + "_", font, BLACK, 260, 285)
            
            draw_text("Нажмите ENTER для продолжения", font, GRAY, WIDTH//2, 350, center=True)

        elif mode == GameMode.RULES:
            draw_text("ПРАВИЛА ИГРЫ", big_font, DARK_BLUE, WIDTH//2, 80, center=True)
            rules_text = [
                "1. У каждого игрока флот из 10 кораблей.",
                "2. Корабли нельзя ставить вплотную.",
                "3. Игроки стреляют по очереди вслепую.",
                "4. Если вы ранили корабль, ваш ход продолжается!",
                "5. Если вы промахнулись, ход переходит врагу."
            ]
            for i, line in enumerate(rules_text):
                draw_text(line, font, BLACK, 50, 180 + i * 45)

        elif mode in [GameMode.PLACEMENT_P1, GameMode.PLACEMENT_P2]:
            player_text = "Игрок 1" if mode == GameMode.PLACEMENT_P1 else "Игрок 2"
            draw_text(f"Расстановка", big_font, DARK_BLUE, WIDTH//2, 50, center=True)
            
            draw_grid(screen, Board(random_placement=False), 50, 150, hide_ships=False)
            draw_text("Корабли:", font, BLACK, 450, 115)
            
            ready_color = GREEN if all(s.placed for s in placement_ships) else GRAY
            pygame.draw.rect(screen, ready_color, ready_btn_rect, border_radius=5)
            draw_text("ГОТОВО", font, WHITE, ready_btn_rect.centerx, ready_btn_rect.centery, center=True)
            
            for ship in placement_ships:
                ship.draw(screen)

        elif mode == GameMode.VS_AI:
            draw_text("Твое поле", font, BLACK, 50, 100)
            draw_text("Поле противника (ИИ)", font, BLACK, 450, 100)
            draw_grid(screen, p1_board, 50, 150, hide_ships=False)
            draw_grid(screen, p2_board, 450, 150, hide_ships=True)

            if winner:
                draw_text(f"Победитель: {winner}!", big_font, RED, WIDTH//2, 50, center=True)
            elif turn == 2:
                draw_text("ИИ думает...", font, RED, WIDTH//2, 50, center=True)
                
        elif mode == GameMode.ONLINE_MATCHMAKING:
            draw_text("ОНЛАЙН", big_font, DARK_BLUE, WIDTH//2, HEIGHT//2 - 30, center=True)
            if online_state["status"] == "waiting":
                draw_text("Ожидание подключения соперника...", font, GRAY, WIDTH//2, HEIGHT//2 + 30, center=True)
            else:
                draw_text("Подключение к хосту...", font, GRAY, WIDTH//2, HEIGHT//2 + 30, center=True)

        elif mode == GameMode.ONLINE_PLAY:
            draw_text("Твой флот", font, BLACK, 50, 100)
            draw_text("Флот врага", font, BLACK, 450, 100)
            
            draw_grid(screen, p1_board, 50, 150, hide_ships=False)
            draw_grid(screen, p2_board, 450, 150, hide_ships=True)

            if winner:
                win_color = GREEN if winner == "Ты" else RED
                draw_text(winner, big_font, win_color, WIDTH//2, 50, center=True)
            else:
                if online_state.get("waiting_for_server"):
                    status_text = "ОЖИДАНИЕ..."
                    status_color = (255, 165, 0)
                else:
                    status_text = "ТВОЙ ХОД" if online_state["my_turn"] else "ХОД ПРОТИВНИКА"
                    status_color = GREEN if online_state["my_turn"] else RED
                draw_text(status_text, big_font, status_color, WIDTH//2, 45, center=True)

        elif mode == GameMode.HOTSEAT:
            if hs_state in [HotseatState.TRANSITION_TO_P2, HotseatState.TRANSITION_TO_P1]:
                screen.fill(BLACK)
                player_next = "Игрока 2" if hs_state == HotseatState.TRANSITION_TO_P2 else "Игрока 1"
                draw_text(f"Ход {player_next}.", big_font, WHITE, WIDTH//2, HEIGHT//2 - 50, center=True)
                draw_text("Нажмите ПРОБЕЛ, когда будете готовы.", font, GRAY, WIDTH//2, HEIGHT//2 + 20, center=True)
            else:
                active_p = "Игрок 1" if hs_state == HotseatState.P1_TURN else "Игрок 2"
                draw_text(f"Ходит: {active_p}", font, RED, WIDTH//2, 50, center=True)
                
                if hs_state == HotseatState.P1_TURN:
                    draw_text("Твое поле (Игрок 1)", font, BLACK, 50, 100)
                    draw_text("Поле Игрока 2", font, BLACK, 450, 100)
                    draw_grid(screen, p1_board, 50, 150, hide_ships=False)
                    draw_grid(screen, p2_board, 450, 150, hide_ships=True)
                elif hs_state == HotseatState.P2_TURN:
                    draw_text("Поле Игрока 1", font, BLACK, 50, 100)
                    draw_text("Твое поле (Игрок 2)", font, BLACK, 450, 100)
                    draw_grid(screen, p1_board, 50, 150, hide_ships=True)
                    draw_grid(screen, p2_board, 450, 150, hide_ships=False)

                if winner:
                    draw_text(f"Победитель: {winner}!", big_font, GREEN, WIDTH//2, 80, center=True)

        if mode != GameMode.MENU:
            is_transition = (mode == GameMode.HOTSEAT and hs_state in [HotseatState.TRANSITION_TO_P1, HotseatState.TRANSITION_TO_P2]) or (mode == GameMode.PLACEMENT_TRANSITION)
            if not is_transition:
                btn_color = (200, 200, 200) if menu_btn_rect.collidepoint(mouse_pos) else GRAY
                pygame.draw.rect(screen, btn_color, menu_btn_rect, border_radius=5)
                draw_text("В меню", font, BLACK, menu_btn_rect.centerx, menu_btn_rect.centery, center=True)

                for anim in animations:
                    anim.draw(screen)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()