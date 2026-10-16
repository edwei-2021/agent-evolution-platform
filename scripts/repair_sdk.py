"""Pinned nanobot SDK integration with caller-owned tools and a no-retry provider."""
from step_trace import traced
import asyncio
import importlib.metadata
import json
from nanobot import Nanobot
from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest, GenerationSettings, LLMUsage
from nanobot.session.manager import SessionManager
from repair_fixture import PROMPT, TOOLS
from repair_engine import RepairRunner, progress
from repair_runtime import SDK_VERSION
from skill_engine import write

class BoundedLoop(AgentLoop):
    def _register_default_tools(self,**kwargs):
        # This version-pinned seam prevents built-in shell/network/spawn tools
        # from ever entering the grant set. Contract tested against real 0.3.5.
        if sorted(self.tools.tool_names)!=sorted(TOOLS):raise ValueError('Invalid bounded SDK tool registry')

class BoundedTool(Tool):
    def __init__(self,runner,name):self.runner=runner;self._name=name
    @property
    def name(self):return self._name
    @property
    def description(self):return {'read_solution':'Read only solution.py.','write_solution':'Replace only solution.py with a bounded clamp function.','run_tests':'Run fixed visible tests; hidden tests are inaccessible.'}[self.name]
    @property
    def parameters(self):
        properties={}
        if self.name in ('read_solution','write_solution'):properties['path']={'type':'string','description':'Use exactly solution.py'}
        if self.name=='write_solution':properties['source']={'type':'string','maxLength':8000,'description':'Complete Python source preserving clamp(value, lower, upper)'}
        return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    async def execute(self,**kwargs):
        try:return await asyncio.to_thread(self.runner.tool,self.name,kwargs)
        except (ValueError,SyntaxError,RuntimeError) as exc:return self.error(str(exc))

class BoundedProvider(LLMProvider):
    def __init__(self,runner):
        super().__init__(api_base=runner.config['provider']['endpoint']+'/v1',provider_name='ollama-bounded')
        self.runner=runner;self.generation=GenerationSettings(temperature=0,max_tokens=runner.config['provider']['config']['maxTokens'])
    def get_default_model(self):return self.runner.config['provider']['config']['model']
    async def chat(self,messages,tools=None,**kwargs):
        reply=await asyncio.to_thread(self.runner.call,messages,tools)
        choice=reply['choices'][0];message=choice['message'];calls=[]
        for c in message.get('tool_calls',[]):calls.append(ToolCallRequest(c['id'],c['function']['name'],json.loads(c['function']['arguments'])))
        raw=reply.get('usage');usage=None
        if isinstance(raw,dict) and type(raw.get('prompt_tokens')) is int and type(raw.get('completion_tokens')) is int:
            input_count,output_count=raw['prompt_tokens'],raw['completion_tokens'];total=max(input_count+output_count,raw.get('total_tokens',0))
            usage=LLMUsage(input_count,output_count,total,reported_tokens=total,request_count=1)
        return LLMResponse(content=message.get('content') or None,tool_calls=calls,finish_reason=choice.get('finish_reason','stop'),usage=usage)
    async def chat_stream_with_retry(self,messages,tools=None,**kwargs):
        # Native transport streams to polling evidence. Do not inherit SDK's
        # transient/persistent provider retry loops or idle-timeout fallback.
        return await self.chat(messages,tools)
    async def chat_with_retry(self,messages,tools=None,**kwargs):return await self.chat(messages,tools)

@traced('nanobot','sdk.turn')
async def run_sdk(directory,config,runner=None):
    version=importlib.metadata.version('nanobot-ai')
    if version!=SDK_VERSION:raise RuntimeError('Unsupported nanobot SDK version: '+version)
    runner=runner or RepairRunner(directory,config);registry=ToolRegistry()
    for name in TOOLS:registry.register(BoundedTool(runner,name))
    loop=BoundedLoop(bus=MessageBus(),provider=BoundedProvider(runner),workspace=runner.workspace,
        model=config['provider']['config']['model'],max_iterations=config['callBudget'],context_window_tokens=32768,
        max_tool_result_chars=16000,restrict_to_workspace=True,tool_registry=registry,
        session_manager=SessionManager(runner.workspace,sessions_root=directory/'sdk-sessions'),
        idle_compact_check_interval_seconds=0)
    async with Nanobot(loop) as bot:
        result=await bot.run(config['skill']['body']+'\n\n'+config.get('fixture',{}).get('prompt',PROMPT),session_key='repair:'+directory.name,ephemeral=True)
    report={'sdkVersion':version,'stopReason':result.stop_reason,'error':result.error,'content':result.content,
        'toolsUsed':result.tools_used,'usage':result.usage.to_dict() if result.usage is not None else None,'messages':result.messages,'sessionKey':'repair:'+directory.name,
        'grantedTools':list(TOOLS)}
    write(directory/'repair-sdk-result.json',report)
    runner.logs.append('nanobot','INFO' if result.stop_reason=='completed' and not result.error else 'ERROR',
        'SDK turn result',config.get('correlationRunId',directory.name),
        {'stopReason':result.stop_reason,'calls':len(runner.calls),'toolCalls':len(runner.tools),
         'finalSummary':bool(runner.calls and runner.calls[-1].get('finalSummary'))})
    if result.error or result.stop_reason!='completed':raise RuntimeError(result.error or 'SDK stopped: '+str(result.stop_reason))
    candidate=runner.path('solution.py').read_bytes().decode('utf-8');(directory/'repair-candidate.py').write_text(candidate)
    progress(directory,sdkStopReason=result.stop_reason,candidateFrozen=True)
