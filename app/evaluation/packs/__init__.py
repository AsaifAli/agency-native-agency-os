from .base import EvalPack
from .rag import PACK as RAG_PACK
from .agent_workflow import PACK as AGENT_WORKFLOW_PACK

PACKS = {pack.name: pack for pack in (RAG_PACK, AGENT_WORKFLOW_PACK)}
