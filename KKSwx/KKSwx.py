from pywinauto import Desktop
from KKSwx.KKShandler.processhandler.phandler import phandler
import pywinauto
from KKSqueue.KKSqueue import QueueManager
import threading
import keyboard
import time
import asyncio
from ultralytics import YOLO
from PIL import Image, ImageEnhance
from rapidocr import RapidOCR
import numpy as np
import os
import random


class KKSWx():
    def __init__(self):
        self.phandler = phandler()
        self.manager = QueueManager()
        self.lastqueue:list = [] # 用于判断是否有新的消息
        self.history:list[tuple[str,str]] = [] # 用于存储消息历史记录
        self.stop_event = None
        self.version = None
        self.model_avatar = None
        self.first = True

    async def start(self,hwnd:int):
        # 创建任务队列
        queue = await self.manager.create_queue(f"task_queue_{hwnd}")
        app = Desktop(backend="uia").window(handle=hwnd)
        ui = self.get_UI_childern(app)
        if ui:
            print("启动UI模式")
            self.version = self.judge_version(app)
            monitor_task = asyncio.create_task(
                self.monitor_UI(hwnd, queue),
                name=f"UI-Monitor-{hwnd}" # 给任务起个名字方便调试
            )
        else:
            print("启动OCR模式")
            monitor_task = asyncio.create_task(
                self.monitor_OCR(hwnd,queue),
                name=f"OCR-Monitor-{hwnd}" # 给任务起个名字方便调试
            )
        
        # quit_hotkey = "ctrl+alt+q"
        # self.stop_event = threading.Event()
        # keyboard.add_hotkey(quit_hotkey, self.cleanup,args=[queue])
        # asyncio.create_task(self.cleanup(queue))
        
        return queue

    # 查找所有包含指定关键词的窗口，为检测提供句柄
    def find_all_windows_by_keyword(self, keyword:str):
        return self.phandler.find_all_windows_by_keyword(keyword)

    def get_UI_childern(self, app):
        for child in app.children():
            if child.element_info.control_type == "List" and child.element_info.name == '消息':
                return child
            a = self.get_UI_childern(child)
            if a:
                return a
            
    
    def judge_message(self, message):
        childs = message.children()[0].children()
        for child in childs:
            if child.element_info.control_type == "Button":
                return message.element_info.name, child.element_info.name
        return None,None 
    
    
    def judge_message4(self, message):
        if len(message.element_info.automation_id) > 0:
            return message.element_info.name,'None'
        return None, None

    def judge_version(self, app):
        messages = self.get_UI_childern(app)
        if len(messages.element_info.automation_id) > 0:
            return "4.1.7"
        else:
            return "3.9"
            
    async def monitor_UI(self,hwnd:int, queue:QueueManager):
        # while not self.stop_event.is_set():
        while True:
            sentences = []
            app = Desktop(backend="uia").window(handle=hwnd)
            messages = self.get_UI_childern(app)
            for message in messages.children():
                if self.version == "4.1.7":
                    m, username = self.judge_message4(message)
                else:
                    m, username = self.judge_message(message)
                if m and username:
                    sentences.append((username,m))
            if self.version == "4.1.7":
                await self.detectnew_by_UI_4(sentences, queue)
            else:
                await self.detectnew_by_UI_4(sentences, queue)
            await asyncio.sleep(5)

    async def monitor_OCR(self,hwnd:int,queue:QueueManager):
        
        self.loadmodel()
        
        GPU = True
        while True:
            try:
                self.phandler.set_window_activte(hwnd)
                if GPU:
                    screenshot = self.phandler.capture_win_alt(hwnd = hwnd)
                else:
                    screenshot = self.phandler.capture_window(hwnd)
                results = self.identify(self.model_avatar, screenshot)
                if len(results) == 0:
                    GPU = not GPU
                    continue
                answer_list = []
                text_area = []
                ban_area = []
                for i,box in enumerate(results[0].boxes):
                    if box.cls == 0:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        text_area.append((x1, y1, x2, y2))
                    elif box.cls == 4:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        ban_area.append((x1, y1, x2, y2))
                    elif box.cls == 3:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        Input = (x1, y1, x2, y2)

                input_area = []
                for text in text_area:
                    is_input = []
                    for ban in ban_area:                    
                        if ban[0] > text[0] and ban[1] > text[1] and ban[2] < text[2] and ban[3] < text[3]:
                            is_input.append(ban)
                    input_area.append((text,is_input))
                
                input_area.sort(key=lambda x: x[0][1])

                for text,is_input in input_area:
                    x1, y1, x2, y2 = text
                    if is_input:
                        area = 0
                        minx = 10000
                        miny = 10000
                        maxx = 0
                        maxy = 0
                        for ban in is_input:
                            area += abs(ban[2] - ban[0]) * abs(ban[3] - ban[1])
                            minx = min(minx, ban[0])
                            miny = min(miny, ban[1])
                            maxx = max(maxx, ban[2])
                            maxy = max(maxy, ban[3])
                        if abs(x2 - x1) * abs(y2 - y1) * 0.8 <= area:
                            continue
                        if abs(minx - x1) < abs(x2 -maxx):
                            self.phandler.send_click_pywin32(hwnd, (maxx + x2) // 2, (maxy + y2) // 2)
                        else:
                            print("点击左侧")
                            self.phandler.send_click_pywin32(hwnd, (minx + x1) // 2, (miny + y1) // 2)
                        await asyncio.sleep(0.1)
                    else:
                        self.phandler.send_click_pywin32(hwnd, (x1 + x2) // 2, (y1 + y2) // 2)
                        await asyncio.sleep(0.1)
                    self.phandler.select_all()
                    await asyncio.sleep(0.1)
                    self.phandler.copy()
                    await asyncio.sleep(0.1)
                    self.phandler.send_click_pywin32(hwnd, x2+20, (y1 + y2) // 2)
                    await asyncio.sleep(0.1)
                    
                    answer_list.append(self.phandler.get_clipboard_text())

                if len(results[0].boxes) == 0:
                    print('box not found')
                    screenshot.save('screa.png')
                    self.phandler.trigger_paint(hwnd)


                # text_area.sort(key=lambda x: x[0])
                # print(text_area)

                
                Chatlist = [x for x in answer_list]
                Usernames = ['None' for x in answer_list]

                await self.detectnew_by_OCR(Chatlist, Usernames, queue)
                await asyncio.sleep(5)
            except Exception as e:
                print(e)
                continue

    def identify(self, model, img):
        '''
        0 = 'I'
        1 = 'Search'
        2 = 'partner'
        3 = 'avatar'
        4 = 'text'
        5 = 'mytext'
        6 = 'myavatar'
        7 = 'nomytext'
        8 = 'notext'
        9 = 'Input'
        10 = 'history'
        11 = 'url'
        '''
        model_results = model.predict(img, save=True, verbose=False)
        return model_results


    def loadmodel(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_avatar =  YOLO(os.path.join(base_dir,r"KKShandler\handlermodel\best.pt"))
        # self.model_avatar =  YOLO(os.path.join(base_dir,r"best.pt"))
        # return RapidOCR(config_path=os.path.join(base_dir,r"config.yaml"))

    def cleanup(self):
        self.stop_event.set()
        print("执行优雅退出流程...")
        return 
    
    async def detectnew_by_UI(self, setences, queue:QueueManager):
        new_setences = []
        if self.first == True:
            self.first = False
            self.lastqueue = setences
            return
        if len(self.lastqueue) == 0:
            new_setences.extend(setences)
        elif len(setences) > len(self.lastqueue):
            new_setences.extend(setences[len(self.lastqueue):])
        elif len(setences) == len(self.lastqueue):
            return 
        
        for sentence in new_setences:
            await queue.put(sentence)
            await asyncio.sleep(0.1)
        self.lastqueue = setences

    async def detectnew_by_UI_4(self, setences, queue:QueueManager):
        def find_indices(target, newlist):
            indices = [i for i, x in enumerate(newlist) if x == target]
            indices = sorted(indices, reverse=True)
            return indices
        new_setences = []
        if self.first == True:
            self.first = False
            self.lastqueue = setences
            return
        if len(self.lastqueue) == 0:
            new_setences.extend(setences)
                
        else:
            indices = find_indices(self.lastqueue[-1], setences)
            if len(indices) == 0:
                new_setences.extend(setences)
            elif self.lastqueue == setences:
                return
            else:
                for index in indices:
                    newlabel = 1
                    for n in range(index, 0, -1):
                        if setences[n] != self.lastqueue[-1-index+n]:
                            newlabel = 0
                            break
                    if newlabel == 1:
                        new_setences.extend(setences[index+1:])
                        break
        
        for sentence in new_setences:
            await queue.put(sentence)
            await asyncio.sleep(0.1)
        self.lastqueue = setences

    async def detectnew_by_OCR(self, setences, Usernames, queue:QueueManager):
        def find_indices(target, newlist):
            indices = [i for i, x in enumerate(newlist) if x == target]
            indices = sorted(indices, reverse=True)
            return indices
        
        new_setences = []
        new_Usernames = []
        if len(self.lastqueue) == 0:
            new_setences.extend(setences)
            new_Usernames.extend(Usernames)
        else:
            indices = find_indices(self.lastqueue[-1], setences)
            if len(indices) == 0:
                new_setences.extend(setences)
                new_Usernames.extend(Usernames)
            else:
                for index in indices:
                    newlabel = 1
                    for n in range(index, -1, -1):
                        if setences[n] != self.lastqueue[-1-index+n]:
                            newlabel = 0
                            break
                    if newlabel == 1:
                        new_setences.extend(setences[index+1:])
                        new_Usernames.extend(Usernames[index+1:])
                        break
        for num in range(len(new_setences)):
            await queue.put((new_Usernames[num],new_setences[num]))
            await asyncio.sleep(0.1)
        self.lastqueue = setences
    # 适合4.1版本的微信
    
    def send_message_4(self, hwnd:int, message:str):
        self.phandler.set_window_show(hwnd)
        for char in message:
            self.phandler.send_char_pywin32(hwnd, char)
        self.phandler.send_enter_pywin32(hwnd)
        self.phandler.set_window_pos(hwnd, 0, 0, 0, 0)

    
    def send_message(self, hwnd:int, message:str):
        app = Desktop(backend="uia").window(handle=hwnd)
        app.set_focus()
        time.sleep(1)
        for char in message:
            self.phandler.send_char_pywin32(hwnd, char)
        self.phandler.send_enter_pywin32(hwnd)
        self.phandler.set_window_pos(hwnd, 0, 0, 0, 0)
            