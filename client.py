import argparse
import os
from KKSwx.KKSwx import KKSWx
import asyncio
from KKSqa.KKSqa import QAmanager
from KKSoperator.operator import DifyOperator
import json
import keyboard
import pandas as pd

class WX_moniter():
    def __init__(self):
        self.update_label = True
        self.interruptlabel = False
        self.count_time = 0
        with open('config.json', 'r', encoding='utf-8') as file:
            self.config = json.load(file)

    async def Interrupt(self):
        while True:
            if self.interruptlabel != True:
                break

    async def moniter(self, hwnd, wx:KKSWx, qa:QAmanager, operator:DifyOperator, difyId, label:str = '@robot'):
        print("开始运行1")
        queue = await wx.start(hwnd)
        while True:
            await self.Interrupt()
            data = await queue.get()
            print("获得一次数据")
            if data:
                qa.add_conversation(data[0],data[1])
                if label in data[1]:
                    setencetype = await qa.judge_question(data[1].replace(label,''))
                    if setencetype == '问题':
                        res = operator.query(knowledgeid=difyId['knowledgeid'], query=data[1].replace(label,''))
                        context = ' '.join([item['segment']['content']+ (item['segment']['answer'] if item['segment']['answer'] else '') for item in res['records']])
                        print(context)
                        answer = await qa.rag(data[1],context)
                        print(answer)
                        if wx.version == "4.1.7":
                            wx.send_message_4(hwnd, answer['answer'])
                        else:
                            wx.send_message(hwnd, answer['answer'])
                        if answer['Cananswer']:
                            qa.add_question(data[1].replace(label,''),answer['answer'],'AI')
                        else:
                            qa.add_question(data[1].replace(label,''),None,None)
                print("收到消息:",data[0],data[1])

                
    async def update_qa(self, frequency, qa:QAmanager, operator:DifyOperator, difyId):
        while True:
            self.count_time += 1
            await self.Interrupt()
            await asyncio.sleep(1)
            if self.count_time == frequency:
                if difyId['doc_form'] == 'qa_model':
                    task = asyncio.create_task(qa.update_data(operator, difyId['knowledgeid'], difyId['unconfirmedid'], True))
                else:
                    task = asyncio.create_task(qa.update_data(operator, difyId['knowledgeid'], difyId['unconfirmedid'], False))
                await task
                self.count_time = 0

    def updateqa(self, settime):
        self.count_time = settime


    def set_key(self):
        keyboard.add_hotkey('ctrl+alt+h', self.change)
        keyboard.add_hotkey('ctrl+alt+u', self.updateqa, args=(590,))
        keyboard.wait('ctrl+alt+p')


    async def main(self, moniterName, knowledgeName:str, label:str = '@robot'):
        wx = KKSWx()
        windows = wx.find_all_windows_by_keyword(moniterName)
        if len(windows) == 0:
            print("未找到窗口")
            return
        hwnd = windows[0]['hwnd']
        qa = QAmanager(
        base_url=self.config['QAmanager']['base_url'],
        model=self.config['QAmanager']['chatmodel'],
        api_key=self.config['QAmanager']['api_key']
    )
        try:
            if self.config['Dify']['Custom']:
                operator = DifyOperator(Authorization=self.config['Dify']['knowledge_Authorization'], rule=self.config['Dify']['rule'])
            else:
                operator = DifyOperator(Authorization=self.config['Dify']['knowledge_Authorization'])
        except Exception as e:
            raise("Dify初始化失败", e)
        difyId = operator.Init(knowledgeName=knowledgeName)
        task1 =asyncio.create_task(self.moniter(hwnd, wx, qa, operator, difyId, label=label))
        asyncio.create_task(self.update_qa(600, qa, operator, difyId))
        await asyncio.to_thread(self.set_key)


    def start(self, moniterName, knowledgeName:str, label:str = '@robot'):
        print("加载")
        asyncio.run(self.main(moniterName, knowledgeName, label))



    def change(self):
        self.interruptlabel = not self.interruptlabel


    def get_unconfirm(self,knowledgeName:str, dir:str = None):
        if dir is None:
            dir = os.path.join(os.path.dirname(__file__), "KKS_unconfirm_segment.xlsx")
        operator = DifyOperator(Authorization=self.config['Dify']['knowledge_Authorization'])
        operator.Output_unconfirmed(name = knowledgeName,dir=dir)

    def confirm_by_file(self,knowledgeName:str, dir:str = None):
        if dir is None:
            dir = os.path.join(os.path.dirname(__file__), "Input.xlsx")
        data = pd.read_excel(dir)
        operator = DifyOperator(Authorization=self.config['Dify']['knowledge_Authorization'])
        operator.confirm_by_file(name = knowledgeName, data=data)


parser = argparse.ArgumentParser(description='KKS')

parser.add_argument('-a', '--age', type=int, default=20, help='你的年龄')
parser.add_argument('-n', '--name', type=str, default='robot_test', help='窗口名称')
parser.add_argument('-s', '--start', action='store_true', help='启动KKS')
parser.add_argument('-l', '--label', type=str, default='@robot', help='KKS标签')
parser.add_argument('-k', '--knowledgeName', type=str, default='os', help='知识库名称')
parser.add_argument('-d', '--dir', type=str, default=None, help='输出文件目录')
parser.add_argument('-g', '--get', action='store_true', help='获取未确认数据')
parser.add_argument('-c', '--confirm', action='store_true', help='确认数据')

args = parser.parse_args()
if args.start:
    cilent = WX_moniter()
    cilent.start(args.name, args.knowledgeName, args.label)

if args.get:
    cilent = WX_moniter()
    cilent.get_unconfirm(args.knowledgeName, args.dir)

if args.confirm:
    cilent = WX_moniter()
    cilent.confirm_by_file(args.knowledgeName, args.dir)


