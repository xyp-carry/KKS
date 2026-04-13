import requests
import json
import time
import pandas as pd
from KKSRAG.KKSContentDB import KKSContentDB
from KKSRAG.KKStool import KKSTokenizer, KKSEmbedding
import os


class Operator:
    def Insert(self):
        pass

    def Update(self):
        pass

    def Delete(self):
        pass

    def Query(self):
        pass


class DifyOperator(Operator):
    def __init__(self, Authorization: str, rule: dict ={}):
        self.Authorization = Authorization
        self.header = {
                    "Authorization": f"Bearer {self.Authorization}",
                    "Content-Type": "application/json",
                }
        if len(rule) == 0:
            self.rule = {
                "indexing_technique": "high_quality",
                "doc_form": "text_model",
                "embedding_model": "embedding-3",
                "embedding_model_provider": "langgenius/zhipuai/zhipuai",
                "embedding_available": True
        }

    def Operate(self):
        pass
    
    def get_knowledges(self):
        url = "http://127.0.0.1/v1/datasets"
        data = {
                    "page": 1,
                    "limit": 50,
                }
        data = requests.get(url, headers=self.header,data=json.dumps(data))
        output = {}
        for item in data.json()['data']:
            output[item['name']] = {"id":item['id'],"doc_form":item['doc_form']}
        if data.json()['total'] > 50:
            for page in range(2, data.json()['total'] // 50 + 2):
                data = {
                    "page": page,
                    "limit": 50,
                }
                data = requests.get(url, headers=self.header,data=json.dumps(data))
                for item in data.json()['data']:
                    output[item['name']] = {"id":item['id'],"doc_form":item['doc_form']}
        return output



    def get_knowledgeid_by_name(self, name: str):
        url = "http://127.0.0.1/v1/datasets"
        data = {
                    "page": 1,
                    "limit": 50,
                }
        data = requests.get(url, headers=self.header,data=json.dumps(data))
        for item in data.json()['data']:
            if item['name'] == name:
                return item['id'], item['doc_form']
        # 如果没有获取到id，且总数大于50，说明可能在其他页面
        if data.json()['total'] > 50:
            for page in range(2, data.json()['total'] // 50 + 2):
                data = {
                    "page": page,
                    "limit": 50,
                }
                data = requests.get(url, headers=self.header,data=json.dumps(data))
                for item in data.json()['data']:
                    if item['name'] == name:
                        return item['id'], item['doc_form']
        return None, None
    
    def get_documents(self, knowledgeid: str, rule: dict = None):
        url = f"http://127.0.0.1/v1/datasets/{knowledgeid}/documents"
        data = requests.get(url, headers=self.header)
        output = {}
        for item in data.json()['data']:
            if item['name'] == "已确认":
                output['已确认'] = item['id']
            if item['name'] == "未确认":
                output['未确认'] = item['id']
        if '已确认' not in output:
            id = self.create_document(knowledgeid, "已确认", rule)
            output['已确认'] = id
        if '未确认' not in output:
            id = self.create_document(knowledgeid, "未确认", rule)
            # self.disable_documents(knowledgeid, id)
            output['未确认'] = id
        return output
    
    def disable_documents(self, knowledgeid: str, documentid: str):
        url = f"https://api.dify.ai/v1/datasets/{knowledgeid}/documents/status/disable"
        payload = { "document_ids": [documentid] }
        res = requests.patch(url, headers=self.header,json=payload)
        print(res.json())
    
    def enable_documents(self, knowledgeid: str, documentid: str):
        url = f"https://api.dify.ai/v1/datasets/{knowledgeid}/documents/status/enable"
        payload = { "document_ids": [documentid] }
        res = requests.patch(url, headers=self.header,json=json.dumps(payload))
        print(res.json())
    
    def create_document(self, knowledgeid: str, name: str, rule: dict = None):
        url = f"http://127.0.0.1/v1/datasets/{knowledgeid}/document/create-by-text"
        if rule is None:
            data = self.rule.copy()
            ifcreate = True
        else:
            data = rule.copy()
            ifcreate = False
        data['name'] = name
        data['text'] = ""

        data = requests.post(url, headers=self.header,data=json.dumps(data))
        print(data.json())
        # segments = self.get_segments(knowledgeid, data.json()['document']['id'], ifcreate)
        # self.delete_segment(knowledgeid, data.json()['document']['id'], segments)
        return data.json()['document']['id']

    def get_segments(self, knowledgeid: str, documentid: str, ifcreate: bool = False):
        params = {
                "page": 1,
                "limit": 100,
        }
        output = []
        while True:
            url = f"http://127.0.0.1/v1/datasets/{knowledgeid}/documents/{documentid}/segments?page={params['page']}&limit={params['limit']}"
            data = requests.get(url, headers=self.header)
            for item in data.json()['data']:
                output.append(item['id'])
            if data.json()['total'] >= params['page'] * params['limit']:
                params['page'] += 1
                continue
            if not ifcreate or len(output) > 0:
                break
            
        return output
    
    def delete_segment(self, knowledgeid: str, documentid: str, segmentids: list[str]):
        for segmentid in segmentids:
            url = f"http://127.0.0.1/v1/datasets/{knowledgeid}/documents/{documentid}/segments/{segmentid}"
            print(url)
            res = requests.delete(url, headers=self.header)
            print(res)

    def insert_segment(self, knowledgeid: str, documentid: str, contents: str, QA: bool = False):
        url = f"http://127.0.0.1/v1/datasets/{knowledgeid}/documents/{documentid}/segments"
        if QA:
            data = {"segments": [{"content": content['question'], "answer": content['answer']} for content in contents]}
        else:
            data = {"segments": [{"content": content} for content in contents]}
        
        data = requests.post(url, headers=self.header,data=json.dumps(data))
        print(data.json())
        return data.json()
    
    def create_knowledge(self, **kwargs):
        url = "http://127.0.0.1/v1/datasets"
        if 'name' not in kwargs:
            raise ValueError("name is required")
        preload = {}
        for key, value in kwargs.items():
            preload[key] = value
        data = requests.post(url, headers=self.header,data=json.dumps(preload))
        return data.json()
        
    
    def delete_knowledge(self, knowledgeid: str):
        url = f"http://127.0.0.1/v1/datasets/{knowledgeid}"
        requests.delete(url, headers=self.header)
    
    def get_segment_detail(self, knowledgeid: str, documentid: str, segmentid: str):
        url = f"http://127.0.0.1/v1/datasets/{knowledgeid}/documents/{documentid}/segments/{segmentid}"
        data = requests.get(url, headers=self.header)
        return data.json()

    def transfer_segment(self, knowledgeid: str, transferor: str, transferee: str, segmentids: list[str], QA: bool = False):
        contents = []
        for segmentid in segmentids:
            item = self.get_segment_detail(knowledgeid, transferor, segmentid)
            if 'data' not in item:
                continue
            if QA:
                content = {"question":item['data']['content'], "answer":item['data']['answer']}
            else:
                content = item['data']['content']
            contents.append(content)

        self.insert_segment(knowledgeid, transferee, contents, QA)
        self.delete_segment(knowledgeid, transferor, segmentids)


    def Output_unconfirmed(self,name,dir:str = "output.xlsx"):
        knowledgeid, doc_form = self.get_knowledgeid_by_name(name)
        documentid = self.get_documents(knowledgeid)['未确认']
        segmentids = self.get_segments(knowledgeid, documentid)
        output = []
        for segmentid in segmentids:
            if doc_form == 'qa_model':
                data = self.get_segment_detail(knowledgeid, documentid, segmentid)
                output.append({"segmentid":segmentid, "question":data['data']['content'], "answer":data['data']['answer']})
            else:
                data = self.get_segment_detail(knowledgeid, documentid, segmentid)
                output.append({"segmentid":segmentid, "content":data['data']['content']})
        df = pd.DataFrame(output)
        df.to_excel(dir, index=False)


    def confirm_by_file(self, name, data:pd.DataFrame):
        knowledgeid, doc_form = self.get_knowledgeid_by_name(name)
        transferorid, transfereeid = self.get_documents(knowledgeid)['未确认'], self.get_documents(knowledgeid)['已确认']
        segmentids = data['segmentid'].tolist()
        if doc_form == 'qa_model':
            self.transfer_segment(knowledgeid, transferorid, transfereeid, segmentids, QA=True)
        else:
            self.transfer_segment(knowledgeid, transferorid, transfereeid, segmentids)    

    def query(self, knowledgeid: str, query: str, retrieval_model:dict= None):
        print("开始请求")
        if retrieval_model is None:
            retrieval_model = {
                "search_method":"hybrid_search",
                "weights":{"vector_weight":0.6,"keyword_weight":0.4},
                "top_k":5,
                "score_threshold_enabled":False,
                "reranking_enable":False,
            }
        data = {"query": query, "retrieval_model": retrieval_model}
        url = f"http://127.0.0.1/v1/datasets/{knowledgeid}/retrieve"
        
        res = requests.post(url, headers=self.header,data=json.dumps(data))
        
        return res.json()
    
    def Init(self, knowledgeName: str, rule: dict = None):
        knowledgeid, doc_form = self.get_knowledgeid_by_name(name=knowledgeName)
        if knowledgeid is None:
            raise ValueError(f"Knowledge {knowledgeName} not found")
            knowledgeid = self.create_knowledge(name=knowledgeName)['id']
        documents = self.get_documents(knowledgeid=knowledgeid, rule=rule)
        unconfirmedid = documents['未确认']
        confirmedid = documents['已确认']
        return {"unconfirmedid":unconfirmedid, "confirmedid":confirmedid, "knowledgeid":knowledgeid, "doc_form":doc_form}



class KKSOperator(Operator):
    def __init__(self):
        pass

    def get_knowledges(self):
        knowledgelist = []
        dirpath = "db"
        filenames = os.listdir(os.getcwd() + "\\KKSRAG\\" + dirpath)
        for filename in filenames:
            if filename.endswith(".db"):
                knowledgelist.append((filename.split(".")[0], os.path.join(dirpath, filename)))
        return {"tables": knowledgelist}

    def create_knowledge(self, name: str, EmbeddingSetting: dict = {}):
        pass



