# 각 요청마다 DB 세션을 생성하고 작업이 끝나면 닫아주는 로직을 공통화
from typing import Generator
from app.db.session import SessionLocal

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db # API 핸들러에서 사용될 세션 주입
    finally:
        db.close() # 요청이 완료되면 자동으로 세션 종료