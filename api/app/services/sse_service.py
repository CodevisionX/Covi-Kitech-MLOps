import asyncio
from datetime import datetime
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SSEService:
    def __init__(self):
        # 연결된 모든 클라이언트(큐)를 관리하는 리스트
        self.connections: List[asyncio.Queue] = []
    
    async def connect(self):
        """
        클라이언트가 SSE 엔드포인트에 접속하면 호출됨.
        새로운 큐를 생성하여 구독자 리스트에 추가.
        """
        queue = asyncio.Queue()
        self.connections.append(queue)
        logger.info(f"SSE Client Connected. Total clients: {len(self.connections)}")
        try:
            while True:
                message = await queue.get()
                yield message
        except asyncio.CancelledError:
            if queue in self.connections:
                self.connections.remove(queue)
                logger.info(f"SSE Client Disconnected. Remaining: {len(self.connections)}")
    
    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """
        모든 클라이언트에게 이벤트 전송
        예: await sse_manager.broadcast("이벤트 이름", {"job_id": 1, "status": "RUNNING"})
        """
        payload = {
            **data, 
            "timestamp": datetime.now().isoformat()
        }

        message = f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
        
        for queue in self.connections:
            queue.put_nowait(message)

sse_manager = SSEService()