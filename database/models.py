"""데이터베이스 계층에서 사용하는 공통 도메인 모델.

Product의 실제 정의는 ``app.models``에 하나만 유지한다.
기존 import 경로(``from database.models import Product``)는
호환성을 위해 그대로 지원한다.
"""

from app.models import Product

__all__ = ["Product"]
