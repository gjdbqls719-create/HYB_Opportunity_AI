# COMMON COMMANDS

Version 1.0

---

# Windows

가상환경

python -m venv .venv

---

활성화

.venv\Scripts\activate

---

패키지 설치

pip install -r requirements.txt

---

전체 테스트

pytest

---

특정 테스트

pytest tests/

---

Verbose

pytest -v

---

실패 즉시 종료

pytest -x

---

Coverage

pytest --cov

---

Lint

ruff check .

---

Format

ruff format .

---

Git

상태

git status

---

추가

git add .

---

Commit

git commit -m "message"

---

Push

git push

---

Branch

git branch

---

Log

git log --oneline

---

Tree

tree

---

프로젝트 구조

tree app /f

tree tests /f

---

문서 검색

rg "keyword"

---

파일 검색

rg --files

---

END