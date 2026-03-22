import argparse
import os
from KKSwx.KKSwx import KKSWx
import asyncio
from KKSqa.KKSqa import QAmanager
from KKSoperator.operator import DifyOperator
import json
import keyboard
import pandas as pd
from tqdm import tqdm


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
        queue = await wx.start(hwnd)
        while True:
            try:
                await self.Interrupt()
                data = await queue.get()
                print("获得一次数据")
                if data:
                    qa.add_conversation(data[0],data[1])
                    if label in data[1] and data[1].replace(label,'').strip() != '':
                        setencetype = await qa.judge_question(data[1].replace(label,''))
                        print(setencetype)
                        if setencetype == '问题':
                            res = operator.query(knowledgeid=difyId['knowledgeid'], query=data[1].replace(label,''))
                            context = ' '.join([item['segment']['content']+ (item['segment']['answer'] if item['segment']['answer'] else '') for item in res['records']])
                            print(context)
                            answer = await qa.rag(data[1],context)
                            if answer['Haveanswer'] and answer['Cananswer']:
                                qa.add_question(data[1].replace(label,''),answer['answer'],'AI')
                            elif not answer['Haveanswer'] and answer['Cananswer']:
                                qa.add_question(data[1].replace(label,''),answer['answer'],'AI')
                                answer['answer'] += ' --由AI生成'
                            elif not answer['Haveanswer'] and not answer['Cananswer']:
                                qa.add_question(data[1].replace(label,''),None,None)
                                answer['answer'] = '我不知道'
                            if wx.version == "4.1.7":
                                wx.send_message_4(hwnd, answer['answer'])
                            else:
                                wx.send_message(hwnd, answer['answer'])
                    print("收到消息:",data[0],data[1])
            except Exception as e:
                if wx.version == "4.1.7":
                    wx.send_message_4(hwnd, "AI正忙请重新提问")
                else:
                    wx.send_message(hwnd, "AI正忙请重新提问")
                
    async def update_qa(self, frequency, qa:QAmanager, operator:DifyOperator, difyId):
        while True:
            self.count_time += 1
            await self.Interrupt()
            await asyncio.sleep(1)
            print(self.count_time)
            if self.count_time == frequency:
                try:
                    if difyId['doc_form'] == 'qa_model':
                        task = asyncio.create_task(qa.update_data(operator, difyId['knowledgeid'], difyId['unconfirmedid'], True))
                    else:
                        task = asyncio.create_task(qa.update_data(operator, difyId['knowledgeid'], difyId['unconfirmedid'], False))
                    await task
                except Exception as e:
                    print("更新数据失败,请检查:", e)
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


    def create_knowledge(self, knowledgeName:str):
        operator = DifyOperator(Authorization=self.config['Dify']['knowledge_Authorization'])
        knowledgeid, doc_form = operator.get_knowledgeid_by_name(knowledgeName)
        if knowledgeid is not None:
            print(f"知识库 {knowledgeName} 已存在，ID为 {knowledgeid}")
            return
        
        if self.config['Dify']['Custom']:
            print("已检测配置，构建QA模式的知识库")
            knowledgeid= operator.create_knowledge(name=knowledgeName)['id']
            operator.Init(knowledgeName=knowledgeName, rule=self.config['Dify']['rule'])
        else:
            print("已检测到配置，构建通用模式的知识库")
        
            knowledgeid = operator.create_knowledge(name=knowledgeName)['id']
            operator.Init(knowledgeName=knowledgeName)
        print(f"已成功建立知识库 {knowledgeName}，ID为 {knowledgeid}")
        

    def Insert_data(self, knowledgeName:str, File:str = "Input.xlsx"):
        operator = DifyOperator(Authorization=self.config['Dify']['knowledge_Authorization'])
        knowledgeid, doc_form = operator.get_knowledgeid_by_name(knowledgeName)
        KnowledgeInfo = operator.Init(knowledgeName=knowledgeName)
        print("开始解析文档")
        data = pd.read_excel(File)
        if knowledgeid is None:
            print(f"知识库 {knowledgeName} 不存在")
            return
        if doc_form == 'qa_model' and self.config['Dify']['Custom']:
            Input = []
            for index in tqdm(range(len(data))):
                Input.append({"question": data.iloc[index]['question'], "answer": data.iloc[index]['answer']})
                if len(Input) == 100:
                    operator.insert_segment(knowledgeid=knowledgeid, documentid=KnowledgeInfo['confirmedid'], contents=Input, QA=True)
                    Input = []
            operator.insert_segment(knowledgeid=knowledgeid, documentid=KnowledgeInfo['confirmedid'], contents=Input, QA=True)
        elif doc_form == 'text_model' and not self.config['Dify']['Custom']:
            Input = []
            for index in tqdm(range(len(data))):
                Input.append("问题："+data.iloc[index]['question']+"\n"+"答案："+data.iloc[index]['answer'])
                if len(Input) == 100:
                    operator.insert_segment(knowledgeid=knowledgeid, documentid=KnowledgeInfo['confirmedid'], contents=Input, QA=False)
                    Input = []
            operator.insert_segment(knowledgeid=knowledgeid, documentid=KnowledgeInfo['confirmedid'], contents=Input, QA=False)
        else:
            print("请检查知识库模式是否与配置一致，如果是QA模式，请检查是否开启了自定义规则，如果是通用模式，请检查是否关闭了自定义规则")


    def get_all_knowledge(self):
        operator = DifyOperator(Authorization=self.config['Dify']['knowledge_Authorization'])
        return operator.get_knowledges()
    
    def delete_knowledge(self, knowledgeName:str):
        operator = DifyOperator(Authorization=self.config['Dify']['knowledge_Authorization'])
        knowledgeid, doc_form = operator.get_knowledgeid_by_name(knowledgeName)
        if knowledgeid is None:
            print(f"知识库 {knowledgeName} 不存在")
            return
        operator.delete_knowledge(knowledgeid)
        print(f"已成功删除知识库 {knowledgeName}，ID为 {knowledgeid}")


parser = argparse.ArgumentParser(description='KKS')

parser.add_argument('-n', '--name', type=str, default='robot_test', help='窗口名称')
parser.add_argument('-s', '--start', action='store_true', help='启动KKS')
parser.add_argument('-l', '--label', type=str, default='@robot', help='KKS标签')
parser.add_argument('-k', '--knowledgeName', type=str, help='知识库名称')
parser.add_argument('-d', '--dir', type=str, default=None, help='输出文件目录')
parser.add_argument('-g', '--get', action='store_true', help='获取未确认数据')
parser.add_argument('-c', '--confirm', action='store_true', help='确认数据')
parser.add_argument('--createknowledge', action='store_true', help='创建知识库')
parser.add_argument('-i', '--Insert_data', action='store_true', help='插入数据')
parser.add_argument('-f', '--File', type=str, default="Input.xlsx", help='输入文件')
parser.add_argument('-a', '--get_all_knowledge', action='store_true', help='获取所有知识库')
parser.add_argument('-rm','--remove_knowledge', action='store_true', help='删除知识库')



args = parser.parse_args()
if args.start:
    cilent = WX_moniter()
    if args.knowledgeName is None:
        parser.error("创建知识库时必须指定知识库名称，使用 -k 或 --knowledgeName 参数")
    cilent.start(args.name, args.knowledgeName, args.label)

if args.get:
    cilent = WX_moniter()
    if args.knowledgeName is None:
        parser.error("获取未确认数据时必须指定知识库名称，使用 -k 或 --knowledgeName 参数")
    cilent.get_unconfirm(args.knowledgeName, args.dir)

if args.confirm:
    cilent = WX_moniter()
    if args.knowledgeName is None:
        parser.error("确认数据时必须指定知识库名称，使用 -k 或 --knowledgeName 参数")
    cilent.confirm_by_file(args.knowledgeName, args.dir)

if args.createknowledge:
    cilent = WX_moniter()
    if args.knowledgeName is None:
        parser.error("创建知识库时必须指定知识库名称，使用 -k 或 --knowledgeName 参数")
    cilent.create_knowledge(args.knowledgeName)

if args.Insert_data:
    cilent = WX_moniter()
    if args.knowledgeName is None:
        parser.error("插入数据时必须指定知识库名称，使用 -k 或 --knowledgeName 参数")
    cilent.Insert_data(args.knowledgeName, args.File)

if args.get_all_knowledge:
    cilent = WX_moniter()
    data = cilent.get_all_knowledge().items()
    print("知识库名称 知识库ID 知识库模式")
    for item in data:
        print(item[0], item[1]['id'], "问答模式" if item[1]['doc_form']=='qa_model' else '通用模式')

if args.remove_knowledge:
    cilent = WX_moniter()
    if args.knowledgeName is None:
        parser.error("删除知识库时必须指定知识库名称，使用 -k 或 --knowledgeName 参数")
    cilent.delete_knowledge(args.knowledgeName)