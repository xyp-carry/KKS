import time 
import json
import os
import uuid
import httpx
import asyncio
import re

class QAmanager:
    def __init__(self, 
                 base_url:str, 
                 model:str, 
                 api_key:str) -> None:
        """
        question.format:
        question:str = 'Q: {question}\n A: {answer} source: {source}'
        """
        self.questions = []
        self.conversation_history = []
        self.base_url = base_url
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        self.params = {
            "model": self.model,
            "temperature": 0,
            "stream": False,
        }

    def add_question(self, question:str, answer:str=None, source:str=None):
        self.questions.append({'id':len(self.questions)+1,'question':question,'answer':answer,'source':source})
    
    async def add_answer_by_ai(self):
        PROMPT = """
        # Role
        你是一位严谨、负责的助教，擅长从上下文中提取信息并整理问答对。

        # Task
        请阅读下方提供的【对话信息】和【问题集】。你需要根据对话信息，尝试为问题集中的每一个问题补充答案。

        # Rules (必须严格遵守)
        1. **答案来源**：答案必须完全来源于【对话信息】。严禁使用外部知识或进行主观推断，可能会存在多条语句都涉及，需要对答案进行整理总结，如果答案是来自用户的验证，则将source设为用户。
        2. **逻辑一致性**：必须完全尊重对话中的逻辑和事实，不可断章取义。
        3. **无法回答的处理**：如果【对话信息】中没有提及该问题的答案，或者信息不足以推导出答案，请将该问题的答案设为 `None`（或者字符串 "None"），**绝对不要编造答案**。
        4. **输出格式**：请直接输出 JSON 格式数据，不要包含任何解释性文字。
        5. **问题集**：一些问题过于口语话，需要对问题进行优化，使其更具体更清晰,尽量加上一些限定词比如2026年，上半学期之类的限制词,且你可以根据一些常识来给问题追加限定词,比如如果问题是关于2026年1月的，你可以追加限定词2025年下半学期，如果是2026年5月份，则是2026年上半学期等。       

        # Output Format
        请直接返回一个单行或格式化的 JSON 对象字符串，不要添加任何其他解释性文字或 Markdown 符号。
        id要与问题集中的id一致
        请按照以下 JSON 格式输出：[{{"id":1,"question":"问题1","answer":"答案1","source":"用户"}}, {{"id":2,"question":"问题2","answer":None,"source":None}},{{"id":3,"question":"问题3","answer":"答案","source":"用户"}} ...]
        """

        Input_PROMPT = """
        ## 【时间】
        {time}

        ## 【对话信息】
        {conversation_history}

        ## 【问题集】
        {question_list}
        """
        question_list = [question for question in self.questions if question['answer'] is None]

        prompt = Input_PROMPT.format(conversation_history=self.conversation_history, question_list=question_list, time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
        response = await self.llm(prompt,system_prompt=PROMPT,thinking=True)
        
        content_str = self.textformat(response['content'])
        add_res = eval(content_str)

        for question in add_res:
            self.questions[question['id'] - 1]['question'] = question['question']
            self.questions[question['id'] - 1]['answer'] = question['answer']
            self.questions[question['id'] - 1]['source'] = question['source']

    async def judge_question(self, text:str):
        PROMPT = """
            根据文本意思判断这句话是一个问题还是一个评价还是问候语还是其他语义。返回类型为['问题','评价','问候语','其他']中的一个,有且仅有一个.
            比如文本为 你好 ，则返回 问候语
            比如文本为 本次考试的时间 ，则返回 问题
            比如文本为 这个回答还不错 ，则返回 评价
            比如文本为 我今天买了3斤苹果 ，则返回 其他
            ## output

            请直接返回一个单行或格式化的 JSON 对象字符串，不要添加任何其他解释性文字或 Markdown 符号。{{"type":"问题/评价/问候语/其他"}}
        """
        Input_PROMPT = """
            ## 【文本】
            {text}
        """
        prompt = Input_PROMPT.format(text=text)
        response = await self.llm(prompt,system_prompt=PROMPT)
        content_str = self.textformat(response['content'])
        return eval(content_str)['type']

    async def judge_answer(self):
        PROMPT = """
            # Role
            你是一位专业的“AI问答质量评估专家”。你的任务是分析用户与AI之间的对话记录，判断AI的最终回复是否有效地解决了用户的问题或需求。
            
            # Evaluation Criteria (评价标准)
            请根据以下标准进行综合判断：

            1. **问题理解**：
            - AI是否准确理解了用户的真实意图？
            - 对于模糊的问题，AI是否进行了有效的引导或澄清？

            2. **解决方案的有效性**：
            - **知识类问题**：AI提供的信息是否准确、全面？
            - **操作类问题**：AI是否提供了清晰、可执行的步骤？
            - **闲聊/情感类**：AI的回复是否符合语境，是否提供了情绪价值？

            3. **用户反馈信号**：
            - **解决信号**：用户表示感谢（“谢谢”、“解决了”）、表示赞同、停止追问、或开启了新话题。
            - **未解决信号**：用户重复提问、表示不满（“不对”、“没用”）、指出AI的错误、或因问题未解决而感到困惑继续追问。

            4. **安全性与合规性**：
            - 如果AI拒绝了回答（如涉及敏感话题），需判断拒绝是否合理。合理的拒绝视为“已处理”。

        请直接返回一个单行或格式化的 JSON 对象字符串，不要添加任何其他解释性文字或 Markdown 符号。其中的id要与问题id一致。返回格式:[{{"id":1,"question":"问题1","answer":"答案1","judge":"有用"}},{{"id":3, "question":"问题2","answer":"答案2","judge":"无用"}}....]

        
        """
        qa = []
        for question in self.questions:
            if question['answer'] is not None and question['source'] == 'AI':
                qa.append({"id":question['id'],"question":question['question'],"answer":question['answer']})
        Input_PROMPT = """
            历史消息格式:[((用户),用户输入,时间),((AI),AI回复,时间)....]
            历史消息为:
            {conversation_history}
            以下是要评价的问答:
            {QA}"""
        prompt = Input_PROMPT.format(QA=qa,conversation_history=self.conversation_history)
        response = await self.llm(prompt,system_prompt=PROMPT,thinking=True)
        
        content_str = self.textformat(response['content'])
        judge_res = eval(content_str)
        for judge in judge_res:
            if judge['judge'] == '无用':
                self.questions[judge['id'] - 1] = {"id":judge['id'],"question":judge['question'],"answer":None,"source":None}

    async def CombineAnswer(self):
        PROMPT = """
                # Role
                你是一位资深的对话数据分析师和知识库架构师。你的核心任务是清洗用户对话数据，识别用户真实意图，将散乱、重复的用户提问整合为标准化的知识库条目。

                # Task & Input Data Format (输入格式)
                我将提供一组用户在对话中得到的N条问答对，问答对格式为[{{"question":"问题1","answer":"答案1","source":"用户"}}...]。请你根据这些数据，输出整合后的标准知识库格式。

                # Constraints & Rules (整合规则)
                1. **意图聚合**：分析所有提问，将指向同一个解决方案或同一类信息的问题归为同一个意图簇。
                2. **标准问题提取**：从每个意图簇中，提炼出一个最清晰、最标准、覆盖面最广的提问作为“标准主问题”。不要使用口语化表达，要使用书面语。
                3. **变体保留**：保留有价值的用户原话作为“扩展问法”。这些原话代表了用户的真实口语习惯，有助于语义匹配。
                - *过滤规则*：剔除完全无意义的乱码、单纯的问候语（如“你好”）、或逻辑不通的语句。
                4. **数量统计**：统计该意图簇下的原始问题总数，以此判断该问题的热度（高频/低频）。
                5. **来源记录**：记录每个问题的来源（用户/AI），如果合并多个问答对时发现不止一个来源，那么只有AI的来源定义为AI，如果有用户的来源定义为用户。

                # Output Data Format (输出格式)
                请直接返回一个单行或格式化的 JSON 对象字符串，不要添加任何其他解释性文字或 Markdown 符号。
            请务必严格按照以下 JSON 格式输出，不要包含其他多余文字：
                [{{"question":"问题1","answer":"答案1","source":"用户 or AI"}}...]
            """
        Input_PROMPT = """
        以下为问答对内容:{questions}
        """
        question_list = [question for question in self.questions if question['answer'] is not None]
        prompt = Input_PROMPT.format(questions=question_list)
        response = await self.llm(prompt,system_prompt=PROMPT,thinking=True)
        content_str = self.textformat(response['content'])
        return eval(content_str)

    def textformat(self, text:str):
        content_str = text.decode('utf-8') if isinstance(text, bytes) else text
        if "```json" in content_str:
            content_str = content_str.replace("```json","")
            content_str = content_str.replace("```","")

        content_str = content_str.replace('，', ',').replace('：', ':').replace('（', '(').replace('）', ')').replace('true', 'True').replace('false', 'False').replace('null', 'None')
        return content_str

    def add_conversation(self, role:str, content:str):
        self.conversation_history.append((role, content, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())))

    def get_conversation(self):
        return self.conversation_history


    async def rag(self, query:str, context:str, cite:bool=False):
        
        if not cite:
            GENERATE_PROMPT = """
                ### 角色设定
                你是一个严谨的专家级助手。请以专家一样的语气回答问题，避免使用“根据上下文”、“根据提供的文档”等引用措辞。我会给你一些知识块和聊天记录，你需要根据这些信息回答问题，并在找不出答案时尝试利用自己训练的数据进行回答。

                ### 任务规则
                1. **依据内容**：利用检索到的上下文信息和给出的聊天内容回答问题，若有答案将Haveanswer设置为True，若无答案将Haveanswer设置为False，无答案时需要尝试以自己训练的数据进行回答,如果可以回答则Cananswer设置为True,如果不能回答则Cananswer设置为False。
                2. **诚实原则**：不要编造，严格按照第一条规则进行回答。
                3. **回答要求**：请严格控制回答长度，不超过三句话，保持简洁，同时以json形式输出。
                4. **聊天记录优先**：如果历史记录中包含相关问题的回答，优先使用历史记录的回答。
                5. **代词消解**：如果问题中包含代词（如“它”、“这个”等），请根据上下文进行消解，避免使用代词，尤其是本次本期这种时间代词请严格按照当前时间判断，如果上下文中的时间不正确则可以给出总结让他人进行参考。
                6. 每个引用文档中的来源信息都不要被提炼到answer中。

                ### 输出格式
                请直接返回一个单行或格式化的 JSON 对象字符串。
                请务必严格按照以下 JSON 格式输出，不要包含其他多余文字, 不要出现markdown形式，只要可以被python识别的json字符串：
                {{
                    "answer": "这里填写你的回答",
                    "Haveanswer": True/False,
                    "Cananswer": True/False
                }}
                
                            """
        else:
            GENERATE_PROMPT = """
                ### 角色设定
                你是一个严谨的专家级助手。请以专家一样的语气回答问题，避免使用“根据上下文”、“根据提供的文档”等引用措辞。我会给你一些知识块和聊天记录，你需要根据这些信息回答问题，并在找不出答案时尝试利用自己训练的数据进行回答。

                ### 任务规则
                1. **依据内容**：利用检索到的上下文信息和给出的聊天内容回答问题，若有答案将Haveanswer设置为True，若无答案将Haveanswer设置为False，无答案时需要尝试以自己训练的数据进行回答,如果可以回答则Cananswer设置为True,如果不能回答则Cananswer设置为False。
                2. **诚实原则**：不要编造，严格按照第一条规则进行回答。
                3. **回答要求**：请严格控制回答长度，不超过三句话，保持简洁，同时以json形式输出。
                4. **聊天记录优先**：如果历史记录中包含相关问题的回答，优先使用历史记录的回答。
                5. **代词消解**：如果问题中包含代词（如“它”、“这个”等），请根据上下文进行消解，避免使用代词，尤其是本次本期这种时间代词请严格按照当前时间判断，如果上下文中的时间不正确则可以给出总结让他人进行参考。
                6. **引用来源**：如果答案来自于上下文，请在回答中引用上下文的来源，上下文的来源为文档最后的网页链接，以“（来源：链接）”的格式表示，这样的链接也可能不存在(不存在链接但回答有依据该文档则返回一个空字符串"")，最后的输出以list形式返回，若没有引用则为空list。
                7. 每个引用文档中的来源信息绝对不可以出现在answer中，只能在cite字段中出现。

                ### 输出格式
                请直接返回一个单行或格式化的 JSON 对象字符串。
                请务必严格按照以下 JSON 格式输出，不要包含其他多余文字, 不要出现markdown形式，只要可以被python识别的json字符串：
                {{
                    "answer": "这里填写你的回答",
                    "Haveanswer": True/False,
                    "Cananswer": True/False,
                    "cite": [引用来源1,引用来源2,...]
                }}
                
            """

        Input_PROMPT = """
        ### 输入信息
        - 当前时间：{time}
        - 群聊历史记录：{history}
        - 用户问题：{question}
        - 检索到的上下文：{context}
        """
        currenttime = time.strftime("%Y-%m-%d-%H%M%S", time.localtime())
        prompt = Input_PROMPT.format(question=query, context=context, history=self.conversation_history, time=currenttime)
        response = await self.llm(prompt,system_prompt=GENERATE_PROMPT,thinking=False)
        record = {
            "time":currenttime,
            "question":query,
            "context":context,
            "history":self.conversation_history,
            "response":response,
            "systemPrompt":GENERATE_PROMPT,
            "Prompt":prompt,
            "type":"rag"
        }
        # QAdata_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),"QAdata")
        # if not os.path.exists(QAdata_dir):
        #     os.makedirs(QAdata_dir)
        # QAdata_file = os.path.join(QAdata_dir, str(uuid.uuid4())+f"{str(currenttime)}.json")
        # with open(QAdata_file, 'a', encoding='utf-8') as f:
        #     f.write(json.dumps(record, ensure_ascii=False) + '\n')
        print(response['content'])
        content_str = self.textformat(response['content'])
        
        res = eval(content_str)

        #去掉answer中的来源信息
        pattern = r'\(来源:.*?\)'
        res['answer'] = re.sub(pattern, '', res['answer'])
        return res

    def answer_without_context(self,query:str):
        GENERATE_PROMPT = """
        # Role
        你是一个严谨的专家级助手。你的任务是根据提供的【对话上下文】，并利用你自身的专业知识回答问题。

        # Execution Steps
        1. **意图理解**：首先阅读【对话上下文】，分析用户问题中的代词（如“它”、“他”、“这个”等）具体指代的是什么对象。如果无法从上下文中推断出指代对象，请直接回答“我无法回答：问题表述不清晰”。
        2. **知识调用**：确定指代对象后，忽略上下文中的碎片信息，仅利用你内部预训练的专业知识库对问题进行详细解答。
        3. **风控检查**：
        - 如果你对该专业知识有确切把握，请详细作答。
        - 如果你对该知识点不确定或超出你的知识范围，请直接回答“我无法回答”。
        - 严禁根据上下文进行猜测或编造事实。

        # Constraints
        - 必须结合上下文来理解问题，但**不要**直接复制上下文中的只言片语作为答案（除非那是标准定义）。
        - 回答必须专业、准确、结构清晰。
        - 如果用户问题在消解代词后依然逻辑不通，请指出问题所在。

        # Output
        请直接返回一个单行或格式化的 JSON 对象字符串，不要添加任何其他解释性文字或 Markdown 符号。
            请务必严格按照以下 JSON 格式输出，不要包含其他多余文字：
            {{
                "answer": "这里填写你的回答",
                "Cananswer": True/False
            }}
            (注：如果能回答问题,Cananswer 为 True,否则为 False)
        """
        Input_PROMPT = """
        # Input Data
        - 【对话上下文】：{history} 
        - 【用户问题】：{query}
        - 【当前时间】：{time}
        """
        currenttime = time.strftime("%Y-%m-%d-%H%M%S", time.localtime())
        prompt = Input_PROMPT.format(query=query, history=self.conversation_history, time=currenttime)
        response = self.llm(prompt,system_prompt=GENERATE_PROMPT,thinking=True)
        record = {
            "time":currenttime,
            "question":query,
            "history":self.conversation_history,
            "response":response.to_json(),
            "Prompt":prompt,
            "type":"without_rag"
        }
        QAdata_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),"QAdata")
        if not os.path.exists(QAdata_dir):
            os.makedirs(QAdata_dir)
        QAdata_file = os.path.join(QAdata_dir, str(uuid.uuid4())+f"{str(currenttime)}.json")
        with open(QAdata_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        content_str = self.textformat(response['content'])
        return eval(content_str)

    async def llm(self,prompt:str,system_prompt:str = None,thinking:bool=False):
        params = self.params.copy()
        
        params["messages"] = [{"role": "system", "content": system_prompt}] if system_prompt else []
        params["messages"].append({"role": "user", "content": prompt})

        if not thinking:
            params["thinking"] = {"type": "disabled"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=120.0)) as client:
            response = await client.post(url=self.base_url, headers=self.headers, data=json.dumps(params))
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]
        else:
            return {"error": response.status_code, "message": response.text}


    async def update_data(self, operator, knowledgeid, documentid, QA:bool=False):
        print(self.questions,self.conversation_history)
        print("判断结果优劣")
        task1 = asyncio.create_task(self.judge_answer())
        print(self.questions,self.conversation_history)
        await task1
        print("AI自己总结")
        task2 = asyncio.create_task(self.add_answer_by_ai())
        print(self.questions,self.conversation_history)
        await task2
        print("合并结果")
        qa_list = await self.CombineAnswer()
        print(qa_list)
        InsertList = []
        for qa in qa_list:
             if qa['source'] != 'AI':
                if QA:
                    InsertList.append({"question":qa['question'],"answer":qa['answer']})
                else:
                    InsertList.append(f"问题:{qa['question']}\n答案:{qa['answer']}")

        operator.insert_segment(knowledgeid, documentid, InsertList, QA)
        
        
        # qa_list = await self.CombineAnswer()
        # self.conversation_history = []
        # self.questions = []
        # return qa_list

