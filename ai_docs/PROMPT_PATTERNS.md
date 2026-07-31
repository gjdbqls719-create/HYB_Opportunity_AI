# PROMPT PATTERNS

Version 1.0

---

# 목적

자주 사용하는 작업을

일관된 방식으로 수행하기 위한

표준 프롬프트 모음이다.

---

# 구현 시작

프로젝트 구조를 먼저 분석하라.

관련 문서를 읽고

관련 코드를 읽고

관련 테스트를 읽은 후

구현 계획을 제시하라.

추측 구현은 하지 않는다.

---

# 버그 수정

버그를 수정하기 전에

재현 가능한 원인을 분석하라.

영향 범위를 설명하라.

최소 수정 원칙으로 해결하라.

관련 테스트를 추가하거나 수정하라.

---

# 신규 기능

Architecture를 변경하지 않는다.

기존 패턴을 재사용한다.

필요한 경우에만

새 클래스를 추가한다.

---

# 테스트

기존 테스트를 먼저 읽는다.

새 테스트를 작성한다.

Regression까지 확인한다.

---

# 문서 수정

코드 변경과 함께

관련 문서를 반드시 수정한다.

README 영향도 검토한다.

---

# PR 생성

변경 사항을 요약한다.

테스트 결과를 포함한다.

변경 파일을 나열한다.

Architecture 영향 여부를 설명한다.

---

# 구현 프롬프트

당신은 HYB Opportunity AI 프로젝트의 구현 AI이다.

반드시 다음 순서를 따른다.

1.
관련 문서를 읽는다.

2.
관련 코드를 읽는다.

3.
관련 테스트를 읽는다.

4.
구현 계획을 작성한다.

5.
기존 패턴을 재사용한다.

6.
구현한다.

7.
테스트한다.

8.
문서를 수정한다.

9.
리뷰 가능한 상태로 마무리한다.

추측 구현은 절대로 하지 않는다.

---

# Architecture 검토 프롬프트

현재 구현이

기존 Architecture와 충돌하는지 검토하라.

아래 항목을 확인하라.

- Layer

- Dependency

- Domain

- Port

- Adapter

- UseCase

Architecture 변경이 필요하면

직접 수정하지 말고

변경 이유만 제안하라.

---

# 코드 리뷰 프롬프트

아래 항목을 기준으로 리뷰하라.

Correctness

Stability

Maintainability

Consistency

Readability

Performance

Architecture

테스트

문서

리뷰 결과는

Critical

Major

Minor

Suggestion

으로 구분한다.

---

# 테스트 생성 프롬프트

관련 테스트를 먼저 읽는다.

기존 테스트 스타일을 유지한다.

다음을 포함한다.

Normal Case

Boundary Case

Edge Case

Failure Case

Regression Case

---

# 버그 수정 프롬프트

버그를 바로 수정하지 않는다.

먼저

재현

↓

원인 분석

↓

영향 범위

↓

최소 수정

↓

테스트

↓

문서

순서로 진행한다.

---

# 리팩토링 프롬프트

동작은 절대 변경하지 않는다.

중복 제거

가독성 향상

책임 분리

만 수행한다.

Architecture는 변경하지 않는다.

---

# 문서 업데이트 프롬프트

코드 변경 사항을 기반으로

관련 문서를 모두 수정하라.

다음을 확인한다.

README

Architecture

Development

API

Testing

Release Note

AI Docs

---

# PR 생성 프롬프트

다음을 포함한다.

Summary

Motivation

Changed Files

Architecture Impact

Domain Impact

Tests

Documentation

Risks

Rollback

Reviewer Guide

Checklist

---

# Sprint 시작 프롬프트

현재 Sprint 목표를 이해한다.

관련 ADR를 읽는다.

관련 Architecture를 읽는다.

관련 Domain을 읽는다.

현재 진행 상황을 요약한다.

구현 계획을 제안한다.

---

# Sprint 종료 프롬프트

다음을 확인한다.

모든 기능 완료

모든 테스트 통과

문서 최신화

Release Note 작성

Architecture 반영

AI 문서 반영

다음 Sprint 제안

---

# Context Pack 생성 프롬프트

현재 프로젝트를 이어받을 수 있도록

Quick Context를 생성한다.

다음을 포함한다.

현재 Sprint

현재 Branch

Architecture

진행 상황

남은 작업

최근 변경

주의사항

---

Full Context 생성 시

Quick Context 내용과 함께

Architecture

Domain

Application

Infrastructure

Database

Tests

Documents

ADR

Development History

를 모두 포함한다.

---

# ChatGPT 리뷰 프롬프트

구현 결과를

제품 관점

Architecture 관점

Business 관점

Maintenance 관점

Testing 관점

에서 검토하라.

구현을 다시 하지 말고

리뷰만 수행한다.

---

# Codex 구현 프롬프트

구현만 수행한다.

Architecture를 변경하지 않는다.

문서를 무시하지 않는다.

테스트를 생략하지 않는다.

추측 구현하지 않는다.

기존 패턴을 따른다.

---

# HYB 표준 작업 프롬프트

항상 아래 순서를 따른다.

이해

↓

분석

↓

계획

↓

구현

↓

테스트

↓

문서

↓

리뷰

↓

PR

↓

Commit Ready

---

# 금지 프롬프트

다음 행동은 하지 않는다.

Architecture 재설계

추측 구현

테스트 생략

문서 생략

대규모 리팩토링

TODO만 남기기

Debug 코드 커밋

기존 패턴 무시

---

# AI 행동 선언

나는

빠른 구현보다

정확한 구현을 선택한다.

새로운 구조보다

검증된 구조를 선택한다.

많은 코드보다

이해하기 쉬운 코드를 선택한다.

작동하는 코드보다

유지보수 가능한 코드를 만든다.

---

END