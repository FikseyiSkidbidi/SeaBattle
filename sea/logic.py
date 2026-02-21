# logic.py
import random
from settings import GRID_SIZE, SHIP_SIZES

class Board:
    def __init__(self, random_placement=True):
        # 0 - пусто, 1 - корабль, 2 - промах, 3 - попадание, 4 - убит
        self.grid = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.ships = [] # Храним координаты кораблей
        self.ships_alive = len(SHIP_SIZES)
        
        # Если включена случайная расстановка (для ИИ), расставляем сразу
        if random_placement:
            self.place_ships_randomly()

    def place_ships_randomly(self):
        for size in SHIP_SIZES:
            placed = False
            while not placed:
                x = random.randint(0, GRID_SIZE - 1)
                y = random.randint(0, GRID_SIZE - 1)
                horizontal = random.choice([True, False])
                if self.add_ship(x, y, size, horizontal):
                    placed = True

    def add_ship(self, x, y, size, horizontal):
        if not self.can_place_ship(x, y, size, horizontal):
            return False
            
        ship_coords = []
        for i in range(size):
            nx, ny = (x + i, y) if horizontal else (x, y + i)
            self.grid[ny][nx] = 1
            ship_coords.append((nx, ny))
        self.ships.append(ship_coords)
        return True

    def can_place_ship(self, x, y, size, horizontal):
        if horizontal and x + size > GRID_SIZE: return False
        if not horizontal and y + size > GRID_SIZE: return False

        for i in range(size):
            nx, ny = (x + i, y) if horizontal else (x, y + i)
            # Проверка соседних клеток (чтобы корабли не касались)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    check_x, check_y = nx + dx, ny + dy
                    if 0 <= check_x < GRID_SIZE and 0 <= check_y < GRID_SIZE:
                        if self.grid[check_y][check_x] == 1:
                            return False
        return True

    def shoot(self, x, y):
        if self.grid[y][x] in [2, 3, 4]: 
            return False # Уже стреляли сюда
            
        if self.grid[y][x] == 1:
            self.grid[y][x] = 3 # Попадание
            self.check_destroyed(x, y)
            return True # Попал (можно ходить еще раз)
        elif self.grid[y][x] == 0:
            self.grid[y][x] = 2 # Промах
            return False # Промах (ход переходит)

    def check_destroyed(self, x, y):
        for ship in self.ships:
            if (x, y) in ship:
                if all(self.grid[sy][sx] == 3 for sx, sy in ship):
                    # Корабль убит
                    for sx, sy in ship:
                        self.grid[sy][sx] = 4
                    self.ships_alive -= 1
                break

    def is_game_over(self):
        return self.ships_alive == 0