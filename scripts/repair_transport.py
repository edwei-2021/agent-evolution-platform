"""OpenAI SSE function-call deltas with bounded, independently replayable evidence."""
from llm_transport import StreamAccumulator


def response_metadata(reply):
    """Bounded body-free fields, including rejected but received completions."""
    choices=reply.get('choices') if isinstance(reply,dict) else None
    choice=choices[0] if isinstance(choices,list) and choices and isinstance(choices[0],dict) else {}
    message=choice.get('message')
    if not isinstance(message,dict):message={}
    tools=message.get('tool_calls',[])
    reason=choice.get('finish_reason')
    names=[]
    if isinstance(tools,list):
        for tool in tools[:8]:
            fn=tool.get('function') if isinstance(tool,dict) else None
            name=fn.get('name') if isinstance(fn,dict) else None
            names.append(name if name in ('read_solution','write_solution','run_tests') else 'other')
    usage=reply.get('usage') if isinstance(reply,dict) else None
    tokens=usage.get('completion_tokens') if isinstance(usage,dict) else None
    return {'hasResponse':bool(choice),'finishReason':reason if reason in ('stop','length','tool_calls','content_filter','cancel',None) else 'other',
            'requestedTools':names,'toolCallCount':len(tools) if isinstance(tools,list) else None,
            'hasContent':isinstance(message.get('content'),str) and bool(message['content'].strip()),
            'completionCount':tokens if type(tokens) is int and 0<=tokens<=1000000 else None}


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
