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
        if app:
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
        
        ocr = self.loadmodel()
        GPU = True
        while True:
            if GPU:
                screenshot = self.phandler.capture_win_alt(hwnd = hwnd)
            else:
                screenshot = self.phandler.capture_window(hwnd)
            results = self.identify(self.model_avatar, screenshot)
            if len(results) == 0:
                GPU = not GPU
                continue
            answer_list = []
            for i,box in enumerate(results[0].boxes):
                if box.cls == 5:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                elif box.cls == 4:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    Bubble_name = np.array(screenshot)[y1-25:y1,x1:x2]
                    try:
                        enhancer = ImageEnhance.Contrast(Image.fromarray(Bubble_name))
                    except:
                        Image.fromarray(Bubble_name).save('test.png')
                    enhanced_img = enhancer.enhance(2.0)
                    names = ocr(enhanced_img).txts
                    if names is None:
                        continue
                    Username = ' '.join(names) if isinstance(names, tuple) else ''
                    crop_img = np.array(screenshot)[y1:y2,x1:x2]
                    texts = ocr(crop_img).txts
                    result = ''.join(texts) if isinstance(texts, tuple) else ''
                    answer_list.append((y1, result, Username))

            if len(results[0].boxes) == 0:
                print('box not found')
                screenshot.save('screa.png')
                self.phandler.trigger_paint(hwnd)

            answer_list.sort(key=lambda x: x[0])
            Chatlist = [x[1] for x in answer_list]
            Usernames = [x[2] for x in answer_list]

            await self.detectnew_by_OCR(Chatlist, Usernames, queue)
            await asyncio.sleep(5)

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
        model_results = model.predict(img, save=False, verbose=False)
        return model_results


    def loadmodel(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # self.model_avatar =  YOLO(os.path.join(base_dir,r"KKShandler\handlermodel\best.pt"))
        self.model_avatar =  YOLO(os.path.join(base_dir,r"best.pt"))
        return RapidOCR(config_path=os.path.join(base_dir,r"config.yaml"))

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
            