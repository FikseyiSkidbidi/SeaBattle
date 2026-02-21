import socketio
from aiohttp import web
import os

sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

# Хранилище игрока, который ждет пару
waiting_player = None

@sio.event
async def connect(sid, environ):
    print(f"Подключился: {sid}")

@sio.event
async def find_game(sid):
    global waiting_player
    if waiting_player is None:
        waiting_player = sid
        await sio.emit('waiting', {'message': 'Поиск соперника...'}, to=sid)
    else:
        room = f"room_{waiting_player}"
        sio.enter_room(waiting_player, room)
        sio.enter_room(sid, room)
        
        # Рассылаем роли: один ходит первым, другой вторым
        await sio.emit('game_start', {'turn': True, 'enemy': sid}, to=waiting_player)
        await sio.emit('game_start', {'turn': False, 'enemy': waiting_player}, to=sid)
        waiting_player = None

@sio.event
async def shoot(sid, data):
    # Пересылаем данные о выстреле второму игроку в комнате
    rooms = sio.rooms(sid)
    for room in rooms:
        if room.startswith("room_"):
            await sio.emit('receive_shot', data, room=room, skip_sid=sid)

@sio.event
async def shot_result(sid, data):
    # Пересылаем результат выстрела обратно тому, кто стрелял
    rooms = sio.rooms(sid)
    for room in rooms:
        if room.startswith("room_"):
            await sio.emit('receive_shot_result', data, room=room, skip_sid=sid)

@sio.event
async def disconnect(sid):
    global waiting_player
    if waiting_player == sid:
        waiting_player = None
    print(f"Отключился: {sid}")

if __name__ == '__main__':
    # Render передает PORT через переменную окружения
    port = int(os.environ.get('PORT', 10000))
    web.run_app(app, port=port)