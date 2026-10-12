"""OpenAI SSE function-call deltas with bounded, independently replayable evidence."""
from llm_transport import StreamAccumulator

class ToolAccumulator(StreamAccumulator):
    def __init__(self):super().__init__();self.tools={}
    def add(self,event):
        super().add(event)
        for choice in event['choices']:
            for part in choice['delta'].get('tool_calls',[]):
                index=part.get('index')
                if type(index) is not int or not 0<=index<8:raise ValueError('Invalid streamed tool index')
                target=self.tools.setdefault(index,{'id':'','type':'function','function':{'name':'','arguments':''}})
                if part.get('type','function')!='function':raise ValueError('Unsupported tool call type')
                for field in ('id',):
                    value=part.get(field,'')
                    if not isinstance(value,str):raise ValueError('Malformed tool ID')
                    target[field]+=value
                function=part.get('function',{})
                if not isinstance(function,dict):raise ValueError('Malformed tool function')
                for field in ('name','arguments'):
                    value=function.get(field,'')
                    if not isinstance(value,str):raise ValueError('Malformed tool delta')
                    target['function'][field]+=value
                if len(target['id'])>200 or len(target['function']['name'])>100 or len(target['function']['arguments'])>16000:raise ValueError('Tool call exceeds size limit')
    def summary(self):
        return {**super().summary(),'toolArgumentChars':sum(len(t['function']['arguments']) for t in self.tools.values())}
    def reply(self):
        reply=super().reply()
        if self.tools:reply['choices'][0]['message']['tool_calls']=[self.tools[k] for k in sorted(self.tools)]
        return reply
