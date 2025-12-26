# 모든 모델이 상속받을 공통 베이스
from typing import Any
from sqlalchemy.ext.declarative import as_declarative, declared_attr

@as_declarative()
class Base:
    id: Any
    __name__: str
    
    # 테이블 이름을 클래스 이름의 소문자로 자동 생성 (예: TrainingJob -> trainingjob)
    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()