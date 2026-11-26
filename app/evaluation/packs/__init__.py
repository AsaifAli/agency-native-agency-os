from .base import EvalPack
from .rag import PACK as RAG_PACK
from .agent_workflow import PACK as AGENT_WORKFLOW_PACK
from .safety_security import PACK as SAFETY_SECURITY_PACK

PACKS = {pack.name: pack for pack in (RAG_PACK, AGENT_WORKFLOW_PACK, SAFETY_SECURITY_PACK)}
