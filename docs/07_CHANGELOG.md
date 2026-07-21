# HYB Opportunity AI
## CHANGELOG

Version: 1.0

---

# 목적

모든 변경 사항은 이 문서에 기록한다.

기록하지 않은 변경은
존재하지 않는 변경으로 간주한다.

---

# 기록 규칙

모든 변경은 아래 형식을 따른다.

날짜

버전

변경 종류

변경 내용

영향 범위

작성자

---

# Change Types

ADD

새 기능

UPDATE

기능 개선

FIX

버그 수정

REFACTOR

구조 개선

REMOVE

삭제

DOCS

문서 변경

TEST

테스트 추가

---

# 예시

## 2026-07-21

Version

0.3.0

Type

REFACTOR

내용

AI Engine 구조 분리

영향

engine/

작성자

Yubin

---

## 2026-07-22

Version

0.3.1

Type

ADD

내용

Temu Marketplace 추가

영향

marketplaces/

---

# 버전 정책

MAJOR

호환성 깨짐

예

1.x → 2.x

MINOR

새 기능

예

1.2 → 1.3

PATCH

버그 수정

예

1.2.3 → 1.2.4

---

# 변경 원칙

모든 기능은

Git Commit

↓

Test

↓

Changelog

↓

Push

순으로 관리한다.

---

# Release Checklist

□ 테스트 통과

□ CHANGELOG 작성

□ Git Commit

□ Git Push

□ Release Tag 생성

---

# 목표

몇 달 후에도

언제

무엇을

왜

변경했는지

100% 추적 가능해야 한다.